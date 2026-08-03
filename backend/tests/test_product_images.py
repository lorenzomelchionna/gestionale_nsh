"""
Photos for products, including products that already exist.

The upload endpoint is the one place in the app where a file crosses the
boundary, so most of what is pinned here is about refusing things: the declared
content type is a claim, the extension is a claim, and the only fact is what
the decoder can make of the bytes.

The read endpoint is unauthenticated because an `<img>` tag cannot send an
Authorization header. That makes the token the whole access control, so its
properties — unguessable, non-sequential, re-minted on replace — are pinned
here too rather than left as an implementation detail.
"""
import io

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import select

from app.models.product import Product, ProductImage
from app.services.images import MAX_EDGE, MAX_UPLOAD_BYTES
from tests.conftest import auth


def png_bytes(size=(120, 90), mode="RGB", color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(size=(120, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 90, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def upload(data: bytes, filename="foto.png", content_type="image/png") -> dict:
    return {"file": (filename, data, content_type)}


@pytest_asyncio.fixture
async def product(db) -> Product:
    """A product created before images existed — the case the request is about."""
    p = Product(
        name="Shampoo idratante",
        purchase_price=4.5,
        sale_price=12.0,
        category="Capelli",
        quantity=10,
    )
    db.add(p)
    await db.commit()
    return p


class TestAttachingAPhoto:
    async def test_an_existing_product_can_be_given_one(
        self, client, db, admin_tokens, product
    ):
        assert product.photo_url is None

        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["photo_url"].startswith("/api/public/product-images/")
        assert body["name"] == "Shampoo idratante", "il resto del prodotto è stato toccato"

    async def test_the_url_it_returns_actually_serves_the_image(
        self, client, admin_tokens, product
    ):
        put = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )
        url = put.json()["photo_url"]

        got = await client.get(url)
        assert got.status_code == 200, got.text
        assert got.headers["content-type"] == "image/jpeg"
        # It is a real decodable image, not an error page with a 200 on it.
        assert Image.open(io.BytesIO(got.content)).format == "JPEG"

    async def test_the_listing_carries_the_url(self, client, admin_tokens, product):
        await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )
        resp = await client.get("/api/admin/products", headers=auth(admin_tokens))
        assert resp.status_code == 200
        row = next(p for p in resp.json()["items"] if p["id"] == product.id)
        assert row["photo_url"]

    async def test_replacing_it_invalidates_the_old_url(
        self, client, admin_tokens, product
    ):
        """Otherwise a browser keeps showing the previous picture — which is why
        the served bytes may carry a year-long cache lifetime."""
        first = (await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes(color=(255, 0, 0))),
        )).json()["photo_url"]

        second = (await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(jpeg_bytes()),
        )).json()["photo_url"]

        assert first != second
        assert (await client.get(first)).status_code == 404
        assert (await client.get(second)).status_code == 200

    async def test_replacing_it_does_not_pile_up_rows(
        self, client, db, admin_tokens, product
    ):
        for _ in range(3):
            await client.put(
                f"/api/admin/products/{product.id}/image",
                headers=auth(admin_tokens),
                files=upload(png_bytes()),
            )
        rows = (await db.execute(
            select(ProductImage).where(ProductImage.product_id == product.id)
        )).scalars().all()
        assert len(rows) == 1

    async def test_the_product_does_not_jump_around_the_list(
        self, client, db, admin_tokens
    ):
        """An update rewrites the row at the end of the table, so an unordered
        listing moved the product to the bottom the moment it got a photo."""
        for name in ("Zolfo", "Argan", "Miele"):
            db.add(Product(
                name=name, purchase_price=1, sale_price=2, category="Test", quantity=1,
            ))
        await db.commit()

        before = [p["name"] for p in
                  (await client.get("/api/admin/products", headers=auth(admin_tokens))).json()["items"]]

        argan = next(p for p in (await db.execute(select(Product))).scalars() if p.name == "Argan")
        await client.put(
            f"/api/admin/products/{argan.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )

        after = [p["name"] for p in
                 (await client.get("/api/admin/products", headers=auth(admin_tokens))).json()["items"]]
        assert after == before

    async def test_an_unknown_product_is_404(self, client, admin_tokens):
        resp = await client.put(
            "/api/admin/products/999999/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )
        assert resp.status_code == 404


class TestRemovingAPhoto:
    async def test_it_clears_the_url_and_the_bytes(
        self, client, db, admin_tokens, product
    ):
        url = (await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )).json()["photo_url"]

        resp = await client.delete(
            f"/api/admin/products/{product.id}/image", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["photo_url"] is None
        assert (await client.get(url)).status_code == 404

        rows = (await db.execute(select(ProductImage))).scalars().all()
        assert rows == [], "i byte sono rimasti nel database"

    async def test_removing_a_photo_that_is_not_there_is_fine(
        self, client, admin_tokens, product
    ):
        """Clicking twice should not produce an error the second time."""
        resp = await client.delete(
            f"/api/admin/products/{product.id}/image", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200
        assert resp.json()["photo_url"] is None


class TestWhatIsRefused:
    async def test_a_file_that_is_not_an_image(self, client, admin_tokens, product):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(b"#!/bin/sh\nrm -rf /\n", "foto.png", "image/png"),
        )
        assert resp.status_code == 400
        assert "immagine" in resp.json()["detail"].lower()

    async def test_a_lying_content_type_does_not_help(
        self, client, admin_tokens, product
    ):
        """The header is the caller's claim; only the decoder gets a vote."""
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "x.png", "image/png"),
        )
        assert resp.status_code == 400

    async def test_an_oversized_upload(self, client, admin_tokens, product):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(b"\x89PNG\r\n\x1a\n" + b"\0" * (MAX_UPLOAD_BYTES + 1)),
        )
        assert resp.status_code == 400
        assert "grande" in resp.json()["detail"]

    async def test_an_empty_file(self, client, admin_tokens, product):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(b""),
        )
        assert resp.status_code == 400


class TestWhatGetsStored:
    async def test_a_huge_photo_is_scaled_down(self, client, db, admin_tokens, product):
        """A phone shot is several thousand pixels wide and megabytes heavy;
        nobody views a shampoo bottle at that size."""
        big = png_bytes(size=(3000, 2000))
        await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(big),
        )
        row = (await db.execute(select(ProductImage))).scalar_one()
        stored = Image.open(io.BytesIO(row.data))
        assert max(stored.size) <= MAX_EDGE
        assert stored.size[0] / stored.size[1] == pytest.approx(3000 / 2000, rel=0.02)
        assert row.byte_size == len(row.data)

    async def test_it_is_re_encoded_rather_than_kept_as_uploaded(
        self, client, db, admin_tokens, product
    ):
        """What is stored has to be a file this app produced. Re-encoding is
        also what drops the EXIF block, which on a phone photo carries the GPS
        coordinates of wherever it was taken."""
        original = png_bytes()
        await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(original),
        )
        row = (await db.execute(select(ProductImage))).scalar_one()
        assert row.data != original
        assert row.content_type == "image/jpeg"
        assert Image.open(io.BytesIO(row.data)).format == "JPEG"

    async def test_transparency_lands_on_white_not_black(
        self, client, db, admin_tokens, product
    ):
        transparent = io.BytesIO()
        Image.new("RGBA", (60, 60), (0, 0, 0, 0)).save(transparent, format="PNG")
        await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(transparent.getvalue()),
        )
        row = (await db.execute(select(ProductImage))).scalar_one()
        assert Image.open(io.BytesIO(row.data)).convert("RGB").getpixel((30, 30)) == (255, 255, 255)


class TestTheTokenIsTheAccessControl:
    async def test_an_unknown_token_is_404(self, client):
        assert (await client.get("/api/public/product-images/qualunque")).status_code == 404

    async def test_tokens_are_not_sequential(self, client, db, admin_tokens):
        """The endpoint is public, so a guessable id would publish the whole
        catalogue to anyone who counts upwards."""
        tokens = []
        for n in range(3):
            p = Product(
                name=f"Prodotto {n}", purchase_price=1, sale_price=2,
                category="Test", quantity=1,
            )
            db.add(p)
            await db.commit()
            resp = await client.put(
                f"/api/admin/products/{p.id}/image",
                headers=auth(admin_tokens),
                files=upload(png_bytes()),
            )
            tokens.append(resp.json()["photo_url"].rsplit("/", 1)[-1])

        assert len(set(tokens)) == 3
        assert all(len(t) >= 32 for t in tokens), "token troppo corto per non essere indovinato"
        assert not any(str(i) == t for i, t in enumerate(tokens))

    async def test_the_bytes_are_cacheable_because_the_url_is_unique(
        self, client, admin_tokens, product
    ):
        url = (await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )).json()["photo_url"]
        resp = await client.get(url)
        assert "immutable" in resp.headers.get("cache-control", "")


class TestWhoMayDoIt:
    async def test_a_collaborator_cannot_upload(
        self, client, collab_tokens, product
    ):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(collab_tokens),
            files=upload(png_bytes()),
        )
        assert resp.status_code == 403

    async def test_a_collaborator_cannot_delete(
        self, client, collab_tokens, product
    ):
        resp = await client.delete(
            f"/api/admin/products/{product.id}/image", headers=auth(collab_tokens)
        )
        assert resp.status_code == 403

    async def test_a_client_account_cannot_upload(
        self, client, client_tokens, product
    ):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(client_tokens),
            files=upload(png_bytes()),
        )
        assert resp.status_code in (401, 403)

    async def test_signed_out_cannot_upload(self, client, product):
        resp = await client.put(
            f"/api/admin/products/{product.id}/image", files=upload(png_bytes())
        )
        assert resp.status_code in (401, 403)


class TestDeletingTheProduct:
    async def test_the_photo_goes_with_it(self, client, db, admin_tokens, product):
        """A row of orphaned bytes is invisible and never shrinks."""
        await client.put(
            f"/api/admin/products/{product.id}/image",
            headers=auth(admin_tokens),
            files=upload(png_bytes()),
        )
        p = (await db.execute(select(Product).where(Product.id == product.id))).scalar_one()
        await db.delete(p)
        await db.commit()

        assert (await db.execute(select(ProductImage))).scalars().all() == []
