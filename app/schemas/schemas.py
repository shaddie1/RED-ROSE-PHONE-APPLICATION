from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import uuid
import re

from app.models.models import ServiceType, OrderStatus, PaymentStatus


# ── Order Schemas ─────────────────────────────────────────────────────────────

class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    customer_address: str
    service_type: ServiceType
    quantity: int = 1
    size: str = "medium"
    notes: str = ""
    pickup_date: datetime

    @field_validator("customer_phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) < 9:
            raise ValueError("Phone number must have at least 9 digits")
        return digits


class OrderOut(BaseModel):
    id: uuid.UUID
    ref: str
    customer_name: str
    customer_phone: str
    customer_address: str
    service_type: ServiceType
    quantity: int
    size: str
    notes: str
    amount: float
    status: OrderStatus
    pickup_date: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Payment Schemas ───────────────────────────────────────────────────────────

class STKPushRequest(BaseModel):
    """Body sent by the frontend to trigger STK Push."""
    order_id: uuid.UUID
    phone_number: str    # e.g. "0712345678" or "254712345678" or "712345678"

    @field_validator("phone_number")
    @classmethod
    def normalise_phone(cls, v: str) -> str:
        """
        Always return in 254XXXXXXXXX format.
        Accepts: 07XXXXXXXX | 7XXXXXXXX | 2547XXXXXXXX | +2547XXXXXXXX
        """
        digits = re.sub(r"\D", "", v)
        if digits.startswith("254"):
            normalised = digits
        elif digits.startswith("0"):
            normalised = "254" + digits[1:]
        elif len(digits) == 9:
            normalised = "254" + digits
        else:
            raise ValueError(
                "Invalid phone number. Use format 07XXXXXXXX or 254XXXXXXXXX"
            )
        if len(normalised) != 12:
            raise ValueError("Phone number must be 12 digits in 254XXXXXXXXX format")
        return normalised


class STKPushResponse(BaseModel):
    payment_id: uuid.UUID
    merchant_request_id: str
    checkout_request_id: str
    response_description: str
    customer_message: str


class PaymentOut(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    phone_number: str
    amount: float
    status: PaymentStatus
    mpesa_receipt_number: Optional[str]
    result_desc: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── M-Pesa Callback Schemas ───────────────────────────────────────────────────

class STKCallbackMetadataItem(BaseModel):
    Name: str
    Value: Optional[str | int | float] = None


class STKCallbackMetadata(BaseModel):
    Item: list[STKCallbackMetadataItem]


class STKCallback(BaseModel):
    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    CallbackMetadata: Optional[STKCallbackMetadata] = None


class STKCallbackBody(BaseModel):
    stkCallback: STKCallback


class MpesaCallbackPayload(BaseModel):
    Body: STKCallbackBody
