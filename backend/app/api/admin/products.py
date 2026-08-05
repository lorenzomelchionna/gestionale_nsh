import secrets
from typing import Annotated
from fastapi import APIRouter, Depends, File, HTTPException, status, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.product import Product, ProductImage, ProductMovement
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut, ProductMovementCreate, ProductMovementOut
from app.schemas.common import PaginatedResponse
from app.dependencies import get_current_user, require_admin
from app.services.images import MAX_UPLOAD_BYTES, ImageRejected, process_upload

router = APIRouter(prefix="/products", tags=["Products"])

# Where the browser will come looking for the bytes. Relative, so it works
# behind the Vite proxy in development and on the deployed host without a
# second base-URL setting to keep in sync.
IMAGE_URL_PREFIX = "/api/public/product-images"


async def _read_capped(file: UploadFile) -> bytes:
    """Read the upload, refusing it as soon as it goes over the limit.

    Reading first and checking the length after would mean an oversized upload
    is fully in memory before anyone objects to it.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            mb = MAX_UPLOAD_BYTES // (1024 * 1024)
            raise ImageRejected(f"Immagine troppo grande: il limite è {mb} MB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("", response_model=PaginatedResponse[ProductOut])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    low_stock: bool = Query(False),
    active_only: bool = Query(True),
):
    """Il magazzino. Di default solo quello che si vende ancora.

    `active_only=false` mostra anche gli archiviati, ed è quello che rende
    l'archiviazione una scelta reversibile: prima il filtro non esisteva —
    la query fissava `is_active == True` — quindi togliere un prodotto dal
    catalogo avrebbe voluto dire non poterlo più vedere né recuperare da
    nessuna schermata.
    """
    q = select(Product)
    if active_only:
        q = q.where(Product.is_active == True)
    if low_stock:
        q = q.where(Product.quantity <= Product.min_quantity)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    # Ordered explicitly: without it Postgres is free to return rows in whatever
    # order it finds them, and an update rewrites the row at the end of the
    # table — so editing a product made it jump to the bottom of the magazzino.
    # Rare enough to go unnoticed while only prices were edited; adding photos
    # made it happen every time. Ordering also makes pagination stable, since
    # `offset` over an unordered set can repeat or skip rows between pages.
    result = await db.execute(
        q.order_by(Product.name).offset((page - 1) * page_size).limit(page_size)
    )
    return PaginatedResponse(
        items=[ProductOut.model_validate(p) for p in result.scalars().all()],
        total=total, page=page, page_size=page_size, pages=-(-total // page_size),
    )


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
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
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    await db.flush()
    return ProductOut.model_validate(product)


@router.put("/{product_id}/image", response_model=ProductOut)
async def set_product_image(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
    file: Annotated[UploadFile, File()],
):
    """Attach or replace the photo of a product.

    A replace mints a new token, so the old URL stops resolving and no browser
    keeps showing the previous picture — which is why the served bytes can
    carry a long cache lifetime.
    """
    result = await db.execute(
        select(Product).options(selectinload(Product.image)).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    try:
        raw = await _read_capped(file)
        data, content_type = process_upload(raw)
    except ImageRejected as e:
        raise HTTPException(status_code=400, detail=str(e))

    token = secrets.token_urlsafe(32)
    if product.image is None:
        product.image = ProductImage(
            token=token, content_type=content_type, data=data, byte_size=len(data)
        )
    else:
        product.image.token = token
        product.image.content_type = content_type
        product.image.data = data
        product.image.byte_size = len(data)

    product.photo_url = f"{IMAGE_URL_PREFIX}/{token}"
    await db.flush()
    return ProductOut.model_validate(product)


@router.delete("/{product_id}/image", response_model=ProductOut)
async def delete_product_image(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
):
    result = await db.execute(
        select(Product).options(selectinload(Product.image)).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    # Idempotent: a product with no photo is already in the requested state, and
    # a 404 here would only make the button fail for someone who clicked twice.
    if product.image is not None:
        product.image = None
    product.photo_url = None
    await db.flush()
    return ProductOut.model_validate(product)


@router.post("/movements", response_model=ProductMovementOut, status_code=status.HTTP_201_CREATED)
async def add_movement(
    payload: ProductMovementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_admin)],
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
