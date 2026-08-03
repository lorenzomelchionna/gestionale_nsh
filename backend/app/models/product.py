import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Enum, DateTime, Integer, LargeBinary, Numeric, Text, ForeignKey,
    func, Boolean,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class MovementType(str, enum.Enum):
    load = "carico"
    unload = "scarico"
    sale = "vendita"


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    purchase_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    sale_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_quantity: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    movements: Mapped[List["ProductMovement"]] = relationship(
        "ProductMovement", back_populates="product"
    )
    # Never eager-loaded: see ProductImage for why the bytes stay out of the way.
    image: Mapped[Optional["ProductImage"]] = relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan",
        uselist=False,
    )


class ProductImage(Base):
    """The photo of a product, deliberately not a column on `products`.

    Two decisions are baked in here, and both are about how the image gets
    read rather than how it gets stored.

    It lives in its own table because a blob on the product row would be
    dragged into every inventory listing — the magazzino page fetches twenty
    products at a time and wants none of the bytes.

    The URL carries `token` and not `product_id` because an `<img>` tag cannot
    send an Authorization header, so whatever serves the file has to be
    reachable without one. A public endpoint keyed by a sequential id would let
    anyone walk the whole catalogue; an unguessable token gives the browser
    something it can fetch on its own without publishing what the salon stocks.
    Replacing the photo mints a new token, which doubles as cache busting.
    """

    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship("Product", back_populates="image")


class ProductMovement(Base):
    __tablename__ = "product_movements"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped["Product"] = relationship("Product", back_populates="movements")
