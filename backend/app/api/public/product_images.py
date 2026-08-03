"""Serves product photos to the browser.

Unauthenticated on purpose, and the reason is narrow: an `<img>` tag cannot
attach an Authorization header, so the only alternative would be fetching every
thumbnail through JavaScript and handing it to the DOM as a blob — more code,
no browser caching, and the same bytes reaching the same screen.

What replaces the header is the token in the path: 32 random bytes, minted per
image and re-minted on replace. It is not guessable and it is not sequential,
so this endpoint cannot be walked to enumerate what the salon stocks. Knowing a
token means someone was already shown the picture.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.product import ProductImage

router = APIRouter(prefix="/product-images", tags=["Product images"])


@router.get("/{token}")
async def get_product_image(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(ProductImage).where(ProductImage.token == token))
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="Immagine non trovata")

    return Response(
        content=image.data,
        media_type=image.content_type,
        headers={
            # Safe to cache hard: the URL contains the token, and replacing the
            # photo mints a new one, so this exact URL can only ever mean these
            # exact bytes.
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
