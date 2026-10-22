"""Le schede delle registrazioni mai finite non sono clienti.

Segnalazione di Flavia del 2026-10-22: «alcune clienti escono due volte»
quando sceglie la cliente di un appuntamento nuovo. `register` crea subito la
scheda dell'account e la unisce a quella del salone solo quando il numero è
dimostrato col codice WhatsApp: chi si registra e si ferma prima lascia una
seconda scheda col suo nome, attiva. Dal 15 al 22/10, 7 account nuovi e 5
telefoni verificati.

`scheda_in_uso()` le tiene fuori da tutto quello che tratta le schede come
clienti: l'elenco del gestionale (che è anche la scelta della cliente), i
messaggi, la chat, gli auguri, la prenotazione senza account. Qui la prova
per ciascuno, e che una registrazione completata resti visibile.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.client import Client, ClientAccount
from tests.conftest import auth, giorno_lavorativo

pytestmark = pytest.mark.asyncio

NUMERO = "+393401234567"


@pytest_asyncio.fixture
async def del_salone(db) -> Client:
    """La scheda vera, creata dal salone."""
    c = Client(first_name="Maria", last_name="Rossi", phone=NUMERO,
               birth_date=date.today().replace(year=1990))
    db.add(c)
    await db.commit()
    return c


async def _registrazione(db, email="maria@nsh-test.it", email_ok=False, tel_ok=False) -> Client:
    account = ClientAccount(email=email, password_hash="x", email_verified=email_ok,
                            phone_verified=tel_ok, is_active=True)
    db.add(account)
    await db.flush()
    c = Client(first_name="Maria", last_name="Rossi", phone=NUMERO, email=email,
               birth_date=date.today().replace(year=1990), account_id=account.id)
    db.add(c)
    await db.commit()
    return c


@pytest_asyncio.fixture
async def a_meta(db) -> Client:
    """Si è registrata, non ha mai inserito il codice WhatsApp."""
    return await _registrazione(db, email_ok=True, tel_ok=False)


class TestLaSceltaDellaCliente:
    async def test_una_volta_sola(self, client, admin_tokens, del_salone, a_meta):
        """Il caso di Flavia."""
        r = await client.get("/api/admin/clients", headers=auth(admin_tokens), params={"page_size": 500})
        assert r.status_code == 200, r.text
        ids = [c["id"] for c in r.json()["items"]]
        assert ids == [del_salone.id]

    async def test_nemmeno_cercandola(self, client, admin_tokens, del_salone, a_meta):
        r = await client.get("/api/admin/clients", headers=auth(admin_tokens), params={"search": "Rossi"})
        assert [c["id"] for c in r.json()["items"]] == [del_salone.id]

    @pytest.mark.parametrize("email_ok,tel_ok", [(False, False), (True, False), (False, True)])
    async def test_ogni_registrazione_incompleta(self, client, db, admin_tokens, del_salone, email_ok, tel_ok):
        """Servono entrambe le verifiche, come per il login."""
        await _registrazione(db, email="altra@nsh-test.it", email_ok=email_ok, tel_ok=tel_ok)
        r = await client.get("/api/admin/clients", headers=auth(admin_tokens))
        assert r.json()["total"] == 1

    async def test_registrazione_completa_si_vede(self, client, db, admin_tokens):
        """Con un nome diverso da quello del salone non si unisce da sola: è
        una cliente vera e deve comparire."""
        completa = await _registrazione(db, email_ok=True, tel_ok=True)
        r = await client.get("/api/admin/clients", headers=auth(admin_tokens))
        assert [c["id"] for c in r.json()["items"]] == [completa.id]

    async def test_la_scheda_resta_raggiungibile_per_id(self, client, admin_tokens, a_meta):
        """Nascosta dagli elenchi, non cancellata: se serve la si apre."""
        r = await client.get(f"/api/admin/clients/{a_meta.id}", headers=auth(admin_tokens))
        assert r.status_code == 200


class TestGliAltriPosti:
    async def test_messaggi(self, db, del_salone, a_meta):
        from app.api.admin.messaging import MessageFilter, _resolve_recipients
        destinatari = await _resolve_recipients(db, MessageFilter(type="all"))
        assert [c.id for c in destinatari] == [del_salone.id]

    async def test_chat_trova_la_cliente(self, db, del_salone, a_meta):
        """Con due schede sullo stesso numero non ne trovava nessuna."""
        from app.services.chat import find_client_by_phone
        trovata = await find_client_by_phone(db, NUMERO)
        assert trovata is not None and trovata.id == del_salone.id

    async def test_auguri_una_volta_sola(self, db, engine, session_factory, monkeypatch, del_salone, a_meta):
        import app.database as database
        import app.utils.notifications as notifications
        from app.tasks.reminders import _async_send_birthday_greetings

        spenta = Client(first_name="Vecchia", last_name="Scheda", phone="+393409999999",
                        birth_date=date.today().replace(year=1985), is_active=False)
        db.add(spenta)
        await db.commit()

        class _Motore:
            async def dispose(self):
                pass

        monkeypatch.setattr(database, "create_task_session_factory", lambda: (_Motore(), session_factory))
        festeggiate = []

        async def finta(db_, c):
            festeggiate.append(c.id)
        monkeypatch.setattr(notifications, "notify_birthday", finta)

        await _async_send_birthday_greetings()
        assert festeggiate == [del_salone.id]

    async def test_prenotazione_senza_account(self, db, del_salone, a_meta):
        """Avendo un account, la scheda a metà vinceva sulle altre: la
        prenotazione finiva su una scheda che il gestionale non mostra."""
        from app.api.public.guest import _scheda_per
        from app.schemas.guest import GuestIdentity
        scelta = await _scheda_per(db, GuestIdentity(first_name="Maria", last_name="Rossi", phone=NUMERO))
        assert scelta.id == del_salone.id
