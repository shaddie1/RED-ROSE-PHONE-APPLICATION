"""Business logic for order creation and pricing."""
import random
import string
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import Order, ServiceType
from app.schemas.schemas import OrderCreate


# ── Pricing table (KES) ──────────────────────────────────────────────────────
PRICING: dict[ServiceType, dict[str, float]] = {
    ServiceType.laundry: {
        "small": 400,
        "medium": 800,
        "large": 1200,
        "extra_large": 1600,
    },
    ServiceType.carpet: {
        "small": 800,
        "medium": 1500,
        "large": 2500,
        "extra_large": 3500,
    },
    ServiceType.sofa: {
        "small": 1200,    # 1-seater
        "medium": 2000,   # 2-seater
        "large": 2800,    # 3-seater
        "extra_large": 4000,  # L-shape / sectional
    },
    ServiceType.curtains: {
        "small": 300,
        "medium": 600,
        "large": 900,
        "extra_large": 1200,
    },
}


def calculate_amount(service: ServiceType, size: str, quantity: int) -> float:
    """Return total price based on service, size, and quantity."""
    size_key = size.lower().replace(" ", "_")
    base = PRICING.get(service, {}).get(size_key, 800)
    return base * quantity


def generate_order_ref() -> str:
    """Generate a unique reference like RRL-2405-7X3K."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    month = datetime.utcnow().strftime("%m%y")
    return f"RRL-{month}-{suffix}"


async def create_order(db: AsyncSession, payload: OrderCreate) -> Order:
    amount = calculate_amount(payload.service_type, payload.size, payload.quantity)
    ref = generate_order_ref()

    order = Order(
        ref=ref,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_address=payload.customer_address,
        service_type=payload.service_type,
        quantity=payload.quantity,
        size=payload.size,
        notes=payload.notes,
        amount=amount,
        pickup_date=payload.pickup_date,
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)
    return order


async def get_order_by_id(db: AsyncSession, order_id) -> Order | None:
    result = await db.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one_or_none()


async def get_order_by_ref(db: AsyncSession, ref: str) -> Order | None:
    result = await db.execute(select(Order).where(Order.ref == ref))
    return result.scalar_one_or_none()
