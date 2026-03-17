from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.product import Product, ProductMovement
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut, ProductMovementCreate, ProductMovementOut
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=PaginatedResponse[ProductOut])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    low_stock: bool = Query(False),
):
    q = select(Product).where(Product.is_active == True)
    if low_stock:
        q = q.where(Product.quantity <= Product.min_quantity)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    result = await db.execute(q.offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(
        items=[ProductOut.model_validate(p) for p in result.scalars().all()],
        total=total, page=page, page_size=page_size, pages=-(-total // page_size),
    )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    product = Product(**payload.model_dump())
    db.add(product)
    await db.flush()
    await db.refresh(product)
    return ProductOut.model_validate(product)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return ProductOut.model_validate(product)


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    return ProductOut.model_validate(product)


@router.post("/movements", response_model=ProductMovementOut, status_code=status.HTTP_201_CREATED)
async def add_movement(
    payload: ProductMovementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    result = await db.execute(select(Product).where(Product.id == payload.product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    movement = ProductMovement(**payload.model_dump())
    db.add(movement)

    # Update stock
    from app.models.product import MovementType
    if payload.type == MovementType.load:
        product.quantity += payload.quantity
    else:
        if product.quantity < payload.quantity:
            raise HTTPException(status_code=400, detail="Quantità insufficiente")
        product.quantity -= payload.quantity

    await db.flush()
    await db.refresh(movement)
    return ProductMovementOut.model_validate(movement)
