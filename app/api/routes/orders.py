from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.db.database import get_db
from app.models.models import Order
from app.schemas.schemas import OrderCreate, OrderOut
from app.services.order_service import create_order, get_order_by_id, get_order_by_ref

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post(
    "/",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new service order",
)
async def create_new_order(
    body: OrderCreate,
    db: AsyncSession = Depends(get_db),
):
    order = await create_order(db, body)
    return order


@router.get(
    "/{order_id}",
    response_model=OrderOut,
    summary="Get order by ID",
)
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    order = await get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get(
    "/ref/{ref}",
    response_model=OrderOut,
    summary="Get order by reference number (e.g. RRL-0526-AB3K)",
)
async def get_order_by_reference(ref: str, db: AsyncSession = Depends(get_db)):
    order = await get_order_by_ref(db, ref.upper())
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get(
    "/customer/{phone}",
    response_model=list[OrderOut],
    summary="List all orders for a customer by phone number",
)
async def list_customer_orders(phone: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Order)
        .where(Order.customer_phone.contains(phone[-9:]))
        .order_by(Order.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()
