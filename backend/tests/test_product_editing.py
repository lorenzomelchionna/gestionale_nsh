"""
Modifica di un prodotto già a magazzino.

Richiesta di Flavia (2026-08-04): descrizione e fornitore. Il campo
`description` esisteva già nel modello ma nessun form ci scriveva dentro,
quindi restava sempre vuoto; `supplier` non esisteva proprio.

Ma il punto vero era un altro: fino a ora un prodotto, una volta creato, non
si poteva più toccare — `PUT /products/{id}` esisteva nel backend e non lo
chiamava nessuno. Chi sbagliava a scrivere un prezzo lo teneva sbagliato.

Quello che questi test tengono fermo non è tanto che la modifica funzioni,
quanto **cosa la modifica non deve poter fare**: due campi che sembrano
scrivibili e non lo sono, ognuno per un motivo suo.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.product import Product, ProductImage
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def product(db) -> Product:
    p = Product(
        name="Shampoo idratante",
        description="Per capelli secchi",
        purchase_price=4.5,
        sale_price=12.0,
        category="Capelli",
        quantity=10,
        min_quantity=3,
    )
    db.add(p)
    await db.commit()
    return p


class TestFornitoreEDescrizione:
    async def test_si_creano_insieme_al_prodotto(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/products",
            headers=auth(admin_tokens),
            json={
                "name": "Maschera",
                "description": "Posa 10 minuti",
                "supplier": "Fornitore Bellezza",
                "purchase_price": 6.0,
                "sale_price": 18.0,
                "category": "Trattamenti",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["description"] == "Posa 10 minuti"
        assert body["supplier"] == "Fornitore Bellezza"

    async def test_si_aggiungono_a_un_prodotto_che_esiste_gia(
        self, client, db, admin_tokens, product
    ):
        """Il caso concreto: 13 prodotti sono già a magazzino senza fornitore."""
        resp = await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"supplier": "L'Oréal", "description": "Per capelli molto secchi"},
        )
        assert resp.status_code == 200, resp.text

        await db.refresh(product)
        assert product.supplier == "L'Oréal"
        assert product.description == "Per capelli molto secchi"

    async def test_i_campi_non_inviati_restano_come_stavano(
        self, client, db, admin_tokens, product
    ):
        """`exclude_unset`: un form che manda solo il fornitore non azzera il resto."""
        await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"supplier": "Wella"},
        )
        await db.refresh(product)
        assert product.name == "Shampoo idratante"
        assert product.description == "Per capelli secchi"
        assert float(product.sale_price) == 12.0

    async def test_si_possono_svuotare(self, client, db, admin_tokens, product):
        """`null` esplicito su un campo che ammette NULL vuol dire cancellalo."""
        resp = await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"description": None, "supplier": None},
        )
        assert resp.status_code == 200, resp.text
        await db.refresh(product)
        assert product.description is None
        assert product.supplier is None


class TestCosaLaModificaNonPuoToccare:
    """Due campi che il PUT rifiuta di scrivere, e non è una svista."""

    async def test_la_giacenza_non_si_scrive_a_mano(
        self, client, db, admin_tokens, product
    ):
        """Ogni pezzo che entra o esce lascia una riga in `product_movements`.

        Se il PUT scrivesse `quantity` si potrebbero far sparire dieci pezzi
        senza che niente dica dove sono finiti — e il magazzino smetterebbe di
        essere un registro. La strada resta carico/scarico.
        """
        resp = await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"name": "Shampoo idratante", "quantity": 999},
        )
        assert resp.status_code == 200, resp.text

        await db.refresh(product)
        assert product.quantity == 10

    async def test_la_foto_non_si_reindirizza(
        self, client, db, admin_tokens, product
    ):
        """`photo_url` è il permalink del token dell'immagine, non un campo.

        Se fosse scrivibile da qui, la foto di un prodotto potrebbe puntare a
        un host qualsiasi — o rompersi scrivendoci dentro un valore a caso.
        Ha i suoi endpoint, che rigenerano il token.
        """
        product.image = ProductImage(
            token="token-di-prova", content_type="image/png", data=b"x", byte_size=1
        )
        product.photo_url = "/api/public/product-images/token-di-prova"
        await db.commit()

        await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"photo_url": "https://esterno.example/tracker.png"},
        )

        await db.refresh(product)
        assert product.photo_url == "/api/public/product-images/token-di-prova"


class TestValoriRifiutati:
    async def test_un_campo_obbligatorio_a_null_da_422_non_500(
        self, client, admin_tokens, product
    ):
        """Senza il controllo nello schema il `None` arriverebbe fino alla
        colonna NOT NULL, e il database risponderebbe con un errore che non
        dice quale campo è sbagliato."""
        resp = await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(admin_tokens),
            json={"name": None},
        )
        assert resp.status_code == 422, resp.text

    async def test_un_prodotto_che_non_esiste_da_404(self, client, admin_tokens):
        resp = await client.put(
            "/api/admin/products/999999",
            headers=auth(admin_tokens),
            json={"supplier": "Nessuno"},
        )
        assert resp.status_code == 404


class TestPermessi:
    async def test_il_collaboratore_non_modifica_i_prodotti(
        self, client, db, collab_tokens, product
    ):
        resp = await client.put(
            f"/api/admin/products/{product.id}",
            headers=auth(collab_tokens),
            json={"sale_price": 1.0},
        )
        assert resp.status_code == 403

        await db.refresh(product)
        assert float(product.sale_price) == 12.0
