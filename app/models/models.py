import uuid
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.db.database import Base


class ServiceType(str, enum.Enum):
    laundry = "laundry"
    carpet = "carpet"
    sofa = "sofa"
    curtains = "curtains"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    picked_up = "picked_up"
    cleaning = "cleaning"
    out_for_delivery = "out_for_delivery"
    delivered = "delivered"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    stk_sent = "stk_sent"
    paid = "paid"
    failed = "failed"
    cancelled = "cancelled"
    refunded = "refunded"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    customer_phone: Mapped[str] = mapped_column(String(20))
    customer_address: Mapped[str] = mapped_column(String(255))

    service_type: Mapped[ServiceType] = mapped_column(SAEnum(ServiceType))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    size: Mapped[str] = mapped_column(String(20), default="medium")
    notes: Mapped[str] = mapped_column(String(500), default="")
    amount: Mapped[float] = mapped_column(Float)

    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus), default=OrderStatus.pending
    )
    pickup_date: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="order", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False
    )

    # M-Pesa fields
    phone_number: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Float)

    # STK Push tracking
    merchant_request_id: Mapped[str] = mapped_column(String(100), nullable=True)
    checkout_request_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    mpesa_receipt_number: Mapped[str] = mapped_column(String(30), nullable=True)

    status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus), default=PaymentStatus.pending
    )
    result_code: Mapped[int] = mapped_column(Integer, nullable=True)
    result_desc: Mapped[str] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    order: Mapped["Order"] = relationship("Order", back_populates="payments")
