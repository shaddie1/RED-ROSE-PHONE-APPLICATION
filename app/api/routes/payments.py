"""
Payment Routes
==============
POST /payments/stk-push          → Trigger STK Push to customer
POST /payments/mpesa/callback    → Safaricom posts payment result here
GET  /payments/{payment_id}      → Get payment status (frontend polling)
GET  /payments/stk/query/{checkout_request_id} → Manual status query
"""
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.database import get_db
from app.models.models import Payment, PaymentStatus, Order, OrderStatus
from app.schemas.schemas import (
    STKPushRequest,
    STKPushResponse,
    PaymentOut,
    MpesaCallbackPayload,
)
from app.services.mpesa import mpesa_service, MpesaError
from app.services.order_service import get_order_by_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["Payments"])


# ─────────────────────────────────────────────────────────────────────────────
# 1. INITIATE STK PUSH
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/stk-push",
    response_model=STKPushResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send M-Pesa STK Push prompt to customer's phone",
)
async def initiate_stk_push(
    body: STKPushRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1. Load order
    order = await get_order_by_id(db, body.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status not in (OrderStatus.pending, OrderStatus.confirmed):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pay for order in status '{order.status.value}'",
        )

    # 2. Send STK Push via Daraja
    try:
        daraja_resp = await mpesa_service.stk_push(
            phone_number=body.phone_number,
            amount=int(order.amount),
            order_ref=order.ref,
            description="Red Rose Laundry",
        )
    except MpesaError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # 3. Persist payment record
    payment = Payment(
        order_id=order.id,
        phone_number=body.phone_number,
        amount=order.amount,
        merchant_request_id=daraja_resp["MerchantRequestID"],
        checkout_request_id=daraja_resp["CheckoutRequestID"],
        status=PaymentStatus.stk_sent,
    )
    db.add(payment)

    # 4. Update order status
    order.status = OrderStatus.confirmed
    await db.flush()
    await db.refresh(payment)

    return STKPushResponse(
        payment_id=payment.id,
        merchant_request_id=payment.merchant_request_id,
        checkout_request_id=payment.checkout_request_id,
        response_description=daraja_resp["ResponseDescription"],
        customer_message=daraja_resp["CustomerMessage"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. M-PESA CALLBACK  (Safaricom POSTs here after customer acts on prompt)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/mpesa/callback",
    status_code=status.HTTP_200_OK,
    summary="Daraja callback — receives payment confirmation from Safaricom",
    include_in_schema=False,   # Hide from public docs
)
async def mpesa_callback(
    payload: MpesaCallbackPayload,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Safaricom calls this URL once the customer completes or cancels the prompt.

    ResultCode meanings:
      0     → Success (paid)
      1032  → Request cancelled by user
      1037  → Timeout (user didn't respond)
      Other → Error
    """
    cb = payload.Body.stkCallback
    checkout_id = cb.CheckoutRequestID
    result_code = cb.ResultCode
    result_desc = cb.ResultDesc

    logger.info(
        "M-Pesa callback received | checkout_id=%s | result_code=%s | desc=%s",
        checkout_id, result_code, result_desc,
    )

    # Find the matching payment record
    result = await db.execute(
        select(Payment).where(Payment.checkout_request_id == checkout_id)
    )
    payment = result.scalar_one_or_none()

    if not payment:
        logger.warning("Callback for unknown checkout_id=%s", checkout_id)
        # Always return 200 to Safaricom — never let them retry indefinitely
        return {"ResultCode": 0, "ResultDesc": "Accepted"}

    payment.result_code = result_code
    payment.result_desc = result_desc
    payment.updated_at = datetime.utcnow()

    if result_code == 0:
        # ── Payment successful ──────────────────────────────
        payment.status = PaymentStatus.paid

        # Extract M-Pesa receipt from metadata
        if cb.CallbackMetadata:
            for item in cb.CallbackMetadata.Item:
                if item.Name == "MpesaReceiptNumber":
                    payment.mpesa_receipt_number = str(item.Value)

        # Mark order as confirmed/paid
        await db.execute(
            update(Order)
            .where(Order.id == payment.order_id)
            .values(status=OrderStatus.confirmed, updated_at=datetime.utcnow())
        )
        logger.info(
            "Payment CONFIRMED | receipt=%s | order_id=%s",
            payment.mpesa_receipt_number, payment.order_id,
        )

        # Trigger downstream tasks (SMS, push notification) in background
        background_tasks.add_task(
            send_confirmation_sms, payment.phone_number, payment.mpesa_receipt_number
        )

    else:
        # ── Payment failed / cancelled ──────────────────────
        payment.status = PaymentStatus.failed
        logger.warning(
            "Payment FAILED | checkout_id=%s | code=%s | desc=%s",
            checkout_id, result_code, result_desc,
        )

    await db.flush()

    # Safaricom requires this exact response body
    return {"ResultCode": 0, "ResultDesc": "Accepted"}


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET PAYMENT STATUS  (frontend polls this)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{payment_id}",
    response_model=PaymentOut,
    summary="Get payment status by payment ID",
)
async def get_payment(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payment


# ─────────────────────────────────────────────────────────────────────────────
# 4. MANUAL STATUS QUERY  (fallback if callback is delayed)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stk/query/{checkout_request_id}",
    summary="Manually query STK Push status from Daraja",
)
async def query_stk(
    checkout_request_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Call Daraja directly to check if a pending STK Push was paid.
    Use this if the callback hasn't arrived within 30–60 seconds.
    """
    try:
        daraja_result = await mpesa_service.query_stk_status(checkout_request_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Daraja query failed: {exc}")

    result_code = int(daraja_result.get("ResultCode", -1))

    # Sync our DB if Daraja says it's done
    if result_code == 0:
        await db.execute(
            update(Payment)
            .where(Payment.checkout_request_id == checkout_request_id)
            .values(
                status=PaymentStatus.paid,
                result_code=result_code,
                result_desc=daraja_result.get("ResultDesc"),
                updated_at=datetime.utcnow(),
            )
        )

    return {
        "checkout_request_id": checkout_request_id,
        "result_code": result_code,
        "result_desc": daraja_result.get("ResultDesc"),
        "status": "paid" if result_code == 0 else "pending",
    }


# ─────────────────────────────────────────────────────────────────────────────
# BACKGROUND TASK — SMS confirmation (stub — wire in Africa's Talking / Twilio)
# ─────────────────────────────────────────────────────────────────────────────

async def send_confirmation_sms(phone: str, receipt: str):
    """
    Stub: Send SMS to customer after successful payment.
    Replace with Africa's Talking or Twilio SDK call.
    """
    logger.info(
        "[SMS stub] Sending confirmation to %s | M-Pesa receipt: %s", phone, receipt
    )
    # Example with Africa's Talking:
    # import africastalking
    # africastalking.initialize(username, api_key)
    # sms = africastalking.SMS
    # await asyncio.to_thread(sms.send,
    #     f"Red Rose Laundry: Payment of KES {amount} received. "
    #     f"M-Pesa receipt {receipt}. We will pick up your items shortly!",
    #     [f"+{phone}"]
    # )
