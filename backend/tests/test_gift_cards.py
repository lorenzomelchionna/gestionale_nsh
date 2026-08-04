"""
Buoni regalo.

Richiesta di Flavia (2026-08-04), l'ultima della sua lista e la più grossa:
si compra al banco, il codice arriva via email **a chi lo riceve**, si spende
in salone anche un po' per volta.

Quasi tutto quello che è fissato qui riguarda il fatto che una gift card è
denaro di qualcun altro: non si spende due volte, non si spende più di quanto
vale, non si spende scaduta o stornata, e quello che entra in cassa ci entra
una volta sola.
"""
import asyncio
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models.gift_card import GiftCard, GiftCardRedemption, GiftCardStatus, generate_code
from app.models.payment import Payment, PaymentType
from tests.conftest import auth

pytestmark = pytest.mark.asyncio


def _vendita(**kwargs) -> dict:
    corpo = {
        "amount": 50.0,
        "recipient_name": "Giulia Bianchi",
        "recipient_email": "giulia@example.it",
        "purchaser_name": "Marco Rossi",
        "payment_method": "contanti",
    }
    corpo.update(kwargs)
    return corpo


@pytest_asyncio.fixture
async def buono(client, admin_tokens) -> dict:
    resp = await client.post(
        "/api/admin/gift-cards", headers=auth(admin_tokens), json=_vendita()
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestIlCodice:
    async def test_non_contiene_caratteri_che_si_confondono(self):
        """Viene ricopiato a mano da un'email e dettato al telefono: `0`/`O` e
        `1`/`I`/`L` sono la ragione per cui un buono valido verrebbe rifiutato."""
        for _ in range(200):
            assert not set(generate_code()) & set("01OIL")

    async def test_due_codici_di_fila_non_coincidono(self):
        assert len({generate_code() for _ in range(500)}) == 500


class TestVendita:
    async def test_crea_il_buono_col_credito_pieno(self, buono):
        assert buono["initial_amount"] == 50.0
        assert buono["balance"] == 50.0
        assert buono["status"] == "attiva"
        assert buono["code"].startswith("NSH-")

    async def test_scade_a_un_anno(self, buono):
        assert buono["expires_at"] == (date.today() + timedelta(days=365)).isoformat()

    async def test_incassa_in_cassa_alla_vendita(self, db, buono):
        """I soldi entrano oggi, perché oggi sono davvero nel cassetto."""
        pagamento = (await db.execute(
            select(Payment).where(Payment.id == buono["payment_id"])
        )).scalar_one()
        assert float(pagamento.amount) == 50.0
        assert pagamento.type == PaymentType.gift_card

    async def test_il_pagamento_ha_un_tipo_suo(self, db, buono):
        """Non `servizio`: dieci buoni venduti non devono sembrare un mese di
        lavoro record."""
        pagamento = (await db.execute(
            select(Payment).where(Payment.id == buono["payment_id"])
        )).scalar_one()
        assert pagamento.type is PaymentType.gift_card
        assert pagamento.type is not PaymentType.service

    async def test_importi_fuori_scala_rifiutati(self, client, admin_tokens):
        for importo in (0, -10, 4.99, 5000):
            resp = await client.post(
                "/api/admin/gift-cards", headers=auth(admin_tokens),
                json=_vendita(amount=importo),
            )
            assert resp.status_code == 422, f"accettato {importo}"

    async def test_email_destinatario_obbligatoria_e_valida(self, client, admin_tokens):
        """È il senso della cosa: senza indirizzo il buono esisterebbe solo qui."""
        senza = _vendita()
        del senza["recipient_email"]
        assert (await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens), json=senza
        )).status_code == 422

        assert (await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            json=_vendita(recipient_email="non-una-email"),
        )).status_code == 422

    async def test_acquirente_inesistente_rifiutato(self, client, admin_tokens):
        resp = await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            json=_vendita(purchaser_client_id=999999),
        )
        assert resp.status_code == 400


class TestRiscatto:
    async def test_parziale_lascia_il_resto(self, client, admin_tokens, buono):
        """50€ su un servizio da 30 ne lasciano 20."""
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 30.0},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["balance"] == 20.0
        assert resp.json()["status"] == "attiva"

    async def test_a_credito_finito_diventa_esaurita(self, client, admin_tokens, buono):
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 50.0},
        )
        resp = await client.get(
            f"/api/admin/gift-cards/by-code/{buono['code']}", headers=auth(admin_tokens)
        )
        assert resp.json()["balance"] == 0.0
        assert resp.json()["status"] == "esaurita"

    async def test_non_si_spende_piu_di_quanto_vale(self, client, db, admin_tokens, buono):
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 80.0},
        )
        assert resp.status_code == 400
        assert "credito residuo" in resp.json()["detail"]

        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        assert float(card.balance) == 50.0

    async def test_ogni_prelievo_lascia_una_riga(self, client, db, admin_tokens, buono):
        """Il saldo dice quanto resta; il registro dice dov'è finito il resto."""
        for importo in (10.0, 15.0):
            await client.post(
                f"/api/admin/gift-cards/{buono['id']}/redeem",
                headers=auth(admin_tokens), json={"amount": importo},
            )
        righe = (await db.execute(
            select(GiftCardRedemption).where(
                GiftCardRedemption.gift_card_id == buono["id"]
            ).order_by(GiftCardRedemption.id)
        )).scalars().all()
        assert [float(r.amount) for r in righe] == [10.0, 15.0]

    async def test_saldo_e_registro_non_divergono(self, client, db, admin_tokens, buono):
        """Il saldo è ridondante per costruzione: questo test è il motivo per
        cui la ridondanza è accettabile."""
        for importo in (5.0, 12.5, 7.25):
            await client.post(
                f"/api/admin/gift-cards/{buono['id']}/redeem",
                headers=auth(admin_tokens), json={"amount": importo},
            )
        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        speso = (await db.execute(
            select(func.coalesce(func.sum(GiftCardRedemption.amount), 0)).where(
                GiftCardRedemption.gift_card_id == buono["id"]
            )
        )).scalar_one()
        assert float(card.initial_amount) - float(speso) == float(card.balance)

    async def test_il_riscatto_non_incassa_di_nuovo(self, client, db, admin_tokens, buono):
        """Il rischio vero della scelta «incasso alla vendita»: se anche il
        riscatto creasse un pagamento, gli stessi 50€ risulterebbero 100."""
        prima = (await db.execute(select(func.count()).select_from(Payment))).scalar_one()
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 30.0},
        )
        dopo = (await db.execute(select(func.count()).select_from(Payment))).scalar_one()
        assert dopo == prima

        totale = (await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
        )).scalar_one()
        assert float(totale) == 50.0


class TestQuandoNonSiPuoSpendere:
    async def test_scaduta(self, client, db, admin_tokens, buono):
        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        card.expires_at = date.today() - timedelta(days=1)
        await db.commit()

        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 10.0},
        )
        assert resp.status_code == 400
        assert "scaduto" in resp.json()["detail"]

    async def test_annullata(self, client, admin_tokens, buono):
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": "Rimborsato in contanti"},
        )
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 10.0},
        )
        assert resp.status_code == 400
        assert "annullato" in resp.json()["detail"]

    async def test_lo_storno_non_cancella_quello_gia_speso(
        self, client, admin_tokens, buono
    ):
        """Serve a rispondere a «quanto gli dobbiamo?» il giorno del rimborso."""
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 20.0},
        )
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/cancel",
            headers=auth(admin_tokens), json={"reason": "Cliente insoddisfatta"},
        )
        corpo = resp.json()
        assert corpo["status"] == "annullata"
        assert corpo["balance"] == 30.0
        assert len(corpo["redemptions"]) == 1

    async def test_annullare_due_volte_non_si_puo(self, client, admin_tokens, buono):
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/cancel",
            headers=auth(admin_tokens), json={},
        )
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/cancel",
            headers=auth(admin_tokens), json={},
        )
        assert resp.status_code == 400

    async def test_esaurita_vince_su_scaduta(self, client, db, admin_tokens, buono):
        """A saldo zero e data passata sono vere entrambe, ma «esaurita»
        racconta cosa è successo davvero."""
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 50.0},
        )
        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        card.expires_at = date.today() - timedelta(days=1)
        await db.commit()
        assert card.compute_status() == GiftCardStatus.exhausted


class TestRicercaPerCodice:
    async def test_trova_il_buono(self, client, admin_tokens, buono):
        resp = await client.get(
            f"/api/admin/gift-cards/by-code/{buono['code']}", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == buono["id"]

    async def test_perdona_minuscole_spazi_e_trattini(self, client, admin_tokens, buono):
        """Il codice viene letto da un'email o dettato al telefono: rifiutarlo
        per un trattino vuol dire dare della bugiarda a chi ce l'ha in mano."""
        sporco = buono["code"].lower().replace("-", " ")
        resp = await client.get(
            f"/api/admin/gift-cards/by-code/{sporco}", headers=auth(admin_tokens)
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == buono["id"]

    async def test_codice_inventato_da_404(self, client, admin_tokens):
        resp = await client.get(
            "/api/admin/gift-cards/by-code/NSH-XXXX-YYYY-ZZZZ", headers=auth(admin_tokens)
        )
        assert resp.status_code == 404


class TestEmailAlDestinatario:
    async def test_parte_verso_chi_riceve_non_chi_paga(
        self, client, db, admin_tokens, monkeypatch
    ):
        """La parte che Flavia ha sottolineato."""
        from app.tasks import reminders

        inviate = []

        async def finta(card):
            inviate.append((card.recipient_email, card.code, float(card.initial_amount)))

        monkeypatch.setattr("app.utils.email.send_gift_card_email", finta)

        resp = await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            json=_vendita(recipient_email="destinataria@example.it"),
        )
        card_id = resp.json()["id"]
        await reminders._async_send_gift_card(card_id)

        assert len(inviate) == 1
        assert inviate[0][0] == "destinataria@example.it"
        assert inviate[0][2] == 50.0

    async def test_segna_l_invio_solo_se_riuscito(
        self, client, db, admin_tokens, buono, monkeypatch
    ):
        """Se l'email non parte, la scheda deve continuare a dirlo."""
        from app.tasks import reminders

        async def esplode(card):
            raise RuntimeError("SMTP giù")

        monkeypatch.setattr("app.utils.email.send_gift_card_email", esplode)

        with pytest.raises(RuntimeError):
            await reminders._async_send_gift_card(buono["id"])

        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        await db.refresh(card)
        assert card.email_sent_at is None

    async def test_il_rinvio_corregge_l_indirizzo(self, client, db, admin_tokens, buono):
        """Un'email sbagliata dettata al banco è la norma: rimandarla allo
        stesso indirizzo non risolverebbe niente."""
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/resend-email",
            headers=auth(admin_tokens),
            json={"recipient_email": "giusta@example.it"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["recipient_email"] == "giusta@example.it"

    async def test_non_si_rimanda_un_buono_annullato(self, client, admin_tokens, buono):
        await client.post(
            f"/api/admin/gift-cards/{buono['id']}/cancel",
            headers=auth(admin_tokens), json={},
        )
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/resend-email",
            headers=auth(admin_tokens), json={},
        )
        assert resp.status_code == 400


class TestElenco:
    async def test_filtra_per_stato(self, client, admin_tokens, buono):
        altra = await client.post(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            json=_vendita(amount=20.0, recipient_email="altra@example.it"),
        )
        await client.post(
            f"/api/admin/gift-cards/{altra.json()['id']}/cancel",
            headers=auth(admin_tokens), json={},
        )

        attive = await client.get(
            "/api/admin/gift-cards", headers=auth(admin_tokens), params={"status": "attiva"}
        )
        assert attive.json()["total"] == 1
        assert attive.json()["items"][0]["id"] == buono["id"]

    async def test_cerca_per_destinatario(self, client, admin_tokens, buono):
        resp = await client.get(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            params={"search": "Giulia"},
        )
        assert resp.json()["total"] == 1

    async def test_il_totale_segue_il_filtro(self, client, admin_tokens, buono):
        """Contato sulla lista non filtrata direbbe che ci sono altre pagine,
        e la seconda sarebbe vuota."""
        resp = await client.get(
            "/api/admin/gift-cards", headers=auth(admin_tokens),
            params={"search": "nessuno-con-questo-nome"},
        )
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []


class TestPermessi:
    async def test_il_collaboratore_non_vende_buoni(self, client, collab_tokens):
        resp = await client.post(
            "/api/admin/gift-cards", headers=auth(collab_tokens), json=_vendita()
        )
        assert resp.status_code == 403

    async def test_il_collaboratore_non_riscatta(self, client, collab_tokens, buono):
        resp = await client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(collab_tokens), json={"amount": 10.0},
        )
        assert resp.status_code == 403

    async def test_la_cliente_non_vede_i_buoni(self, client, client_tokens):
        resp = await client.get("/api/admin/gift-cards", headers=auth(client_tokens))
        assert resp.status_code in (401, 403)


class TestDueCasseInsieme:
    """Il punto in cui due persone possono toccare la stessa riga, e la riga
    è denaro."""

    async def test_due_riscatti_simultanei_non_sfondano_il_credito(
        self, client, db, admin_tokens, buono
    ):
        """Due postazioni riscattano 40€ da un buono da 50 nello stesso istante.

        Senza il `FOR UPDATE` leggono entrambe «saldo 50», trovano entrambe
        40 ≤ 50 e scalano entrambe: il buono ne pagherebbe 80. Con il lock la
        seconda aspetta, rilegge 10 e viene rifiutata.
        """
        chiamata = lambda: client.post(
            f"/api/admin/gift-cards/{buono['id']}/redeem",
            headers=auth(admin_tokens), json={"amount": 40.0},
        )
        prima, seconda = await asyncio.gather(chiamata(), chiamata())

        esiti = sorted([prima.status_code, seconda.status_code])
        assert esiti == [200, 400], f"esiti {esiti}"

        card = (await db.execute(
            select(GiftCard).where(GiftCard.id == buono["id"])
        )).scalar_one()
        await db.refresh(card)
        assert float(card.balance) == 10.0

        righe = (await db.execute(
            select(func.count()).select_from(GiftCardRedemption).where(
                GiftCardRedemption.gift_card_id == buono["id"]
            )
        )).scalar_one()
        assert righe == 1, "un solo prelievo doveva andare a buon fine"
