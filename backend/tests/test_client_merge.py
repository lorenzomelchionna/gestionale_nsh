"""Unione di due schede che sono la stessa persona.

Il rischio di questa funzionalità non è che non funzioni: è che funzioni a
metà. Sei tabelle puntano a `clients.id` e si comportano in tre modi diversi,
e due possono far sparire dei dati se le si tocca nell'ordine sbagliato —
`waitlist_entries` è in `CASCADE`, quindi sparirebbe con la scheda, e
`appointments` è in `RESTRICT`, quindi la blocca. Metà dei test qui contano
righe prima e dopo per questo motivo.

L'altra metà riguarda ciò che l'operazione **non** deve fare, ed è la parte
che conta di più: non si annulla. Una fusione sbagliata consegna a una persona
lo storico di un'altra, e non c'è un pulsante per tornare indietro.
"""
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.chat import Conversation
from app.models.client import Client, ClientAccount
from app.models.communication import Communication, CommunicationType
from app.models.payment import Payment, PaymentMethod
from app.models.waitlist import WaitlistEntry
from app.services import client_merge
from tests.conftest import auth

pytestmark = pytest.mark.asyncio

DOMANI = datetime.now(timezone.utc) + timedelta(days=3)


@pytest_asyncio.fixture
async def scheda_salone(db) -> Client:
    """Quella compilata a mano in salone: completa, con lo storico."""
    c = Client(
        first_name="Giulia", last_name="Bianchi",
        phone="+393331112223", email="Giulia.Bianchi@example.com",
        birth_date=date(1990, 4, 12),
        notes="Allergica all'ammoniaca.",
    )
    db.add(c)
    await db.commit()
    return c


@pytest_asyncio.fixture
async def scheda_online(db) -> Client:
    """Quella nata dalla registrazione: stessa persona, indirizzo scritto in
    minuscolo, quindi `_adopt_salon_record` non l'ha collegata."""
    c = Client(
        first_name="Giulia", last_name="Bianchi",
        phone=None, email="giulia.bianchi@example.com",
        birth_date=None, notes=None,
    )
    db.add(c)
    await db.commit()
    return c


async def _appuntamento(db, cliente, collaborator, quando=DOMANI) -> Appointment:
    a = Appointment(
        client_id=cliente.id, collaborator_id=collaborator.id,
        start_time=quando, end_time=quando + timedelta(hours=1),
        status=AppointmentStatus.confirmed,
    )
    db.add(a)
    await db.commit()
    return a


class TestCosaSiSposta:
    async def test_gli_appuntamenti_passano_alla_scheda_che_resta(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        await _appuntamento(db, scheda_online, collaborator)
        await _appuntamento(db, scheda_online, collaborator, DOMANI + timedelta(days=1))

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()

        rimasti = (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda_online.id)
        )).scalars().all()
        spostati = (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda_salone.id)
        )).scalars().all()
        assert rimasti == []
        assert len(spostati) == 2

    async def test_la_lista_d_attesa_non_sparisce(
        self, db, scheda_salone, scheda_online, service, collaborator
    ):
        """`waitlist_entries` è l'unica in `CASCADE`: se la scheda sparisse
        prima che le sue righe siano state spostate, sparirebbero con lei
        senza che nessuno se ne accorga. Per questo viene spostata per prima."""
        db.add(WaitlistEntry(
            client_id=scheda_online.id, service_id=service.id,
            collaborator_id=collaborator.id,
            preferred_date=date.today() + timedelta(days=7),
        ))
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()

        voci = (await db.execute(select(WaitlistEntry))).scalars().all()
        assert len(voci) == 1, "la voce in lista d'attesa è sparita nella fusione"
        assert voci[0].client_id == scheda_salone.id

    async def test_gli_incassi_non_restano_orfani(
        self, db, scheda_salone, scheda_online
    ):
        """`payments.client_id` è `SET NULL`: senza spostarlo, l'incasso
        resterebbe in cassa senza sapere di chi era."""
        db.add(Payment(
            client_id=scheda_online.id, amount=35, method=PaymentMethod.cash,
        ))
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()

        incassi = (await db.execute(select(Payment))).scalars().all()
        assert [p.client_id for p in incassi] == [scheda_salone.id]

    async def test_la_chat_whatsapp_segue_la_persona(
        self, db, scheda_salone, scheda_online
    ):
        db.add(Conversation(phone="+393331112223", client_id=scheda_online.id))
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()

        conv = (await db.execute(select(Conversation))).scalar_one()
        assert conv.client_id == scheda_salone.id

    async def test_lo_storico_invii_segue(self, db, scheda_salone, scheda_online):
        db.add(Communication(
            client_id=scheda_online.id, type=CommunicationType.email,
            subject="Promemoria", content="...",
        ))
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()

        c = (await db.execute(select(Communication))).scalar_one()
        assert c.client_id == scheda_salone.id


class TestCosaSiUnisce:
    async def test_i_buchi_si_riempiono_ma_i_valori_non_si_sovrascrivono(
        self, db, scheda_salone, scheda_online
    ):
        """La scheda del salone ha telefono e data di nascita, quella online
        no. Al contrario, l'email della destinazione non deve essere
        sostituita da quella dell'origine: chi resta, resta com'è."""
        scheda_salone.phone = None
        scheda_online.phone = "+393339998887"
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_salone)

        assert scheda_salone.phone == "+393339998887", "il buco non è stato riempito"
        assert scheda_salone.email == "Giulia.Bianchi@example.com", (
            "l'email della scheda che resta è stata sovrascritta"
        )

    async def test_le_note_si_sommano_invece_di_scegliere(
        self, db, scheda_salone, scheda_online
    ):
        """Sono testo libero scritto dal salone — allergie, preferenze — e
        scartarne metà vuol dire perdere sapere che non sta scritto altrove."""
        scheda_online.notes = "Preferisce il pomeriggio."
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_salone)

        assert "Allergica all'ammoniaca." in scheda_salone.notes
        assert "Preferisce il pomeriggio." in scheda_salone.notes

    async def test_una_nota_identica_non_viene_duplicata(
        self, db, scheda_salone, scheda_online
    ):
        scheda_online.notes = "Allergica all'ammoniaca."
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_salone)

        assert scheda_salone.notes.count("Allergica all'ammoniaca.") == 1

    async def test_l_account_del_portale_passa_alla_scheda_che_resta(
        self, db, scheda_salone, scheda_online
    ):
        """È il punto della funzionalità: la cliente si è registrata online,
        ha ottenuto una scheda nuova, e il salone la ricollega alla sua."""
        account = ClientAccount(
            email="giulia.bianchi@example.com",
            password_hash="x", is_active=True, email_verified=True,
        )
        db.add(account)
        await db.flush()
        scheda_online.account_id = account.id
        await db.commit()

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_salone)
        await db.refresh(scheda_online)

        assert scheda_salone.account_id == account.id
        assert scheda_online.account_id is None


class TestCosaNonDeveSuccedere:
    async def test_due_account_del_portale_bloccano_la_fusione(
        self, db, scheda_salone, scheda_online
    ):
        """Due account vuol dire due persone che entrano con due password.
        Unirle ne chiuderebbe fuori una dai propri appuntamenti senza dirglielo,
        e non è una cosa che un endpoint può decidere: prima va stabilito quale
        account resta, e quello è un discorso con la cliente."""
        for scheda, indirizzo in ((scheda_salone, "a@x.it"), (scheda_online, "b@x.it")):
            acc = ClientAccount(
                email=indirizzo, password_hash="x", is_active=True, email_verified=True,
            )
            db.add(acc)
            await db.flush()
            scheda.account_id = acc.id
        await db.commit()

        with pytest.raises(client_merge.MergeRefused, match="account"):
            await client_merge.esegui(db, scheda_salone.id, scheda_online.id)

    async def test_non_si_unisce_una_scheda_con_se_stessa(self, db, scheda_salone):
        with pytest.raises(client_merge.MergeRefused):
            await client_merge.esegui(db, scheda_salone.id, scheda_salone.id)

    async def test_una_scheda_inesistente_e_un_errore_non_un_silenzio(
        self, db, scheda_salone
    ):
        with pytest.raises(client_merge.MergeRefused):
            await client_merge.esegui(db, scheda_salone.id, 999999)

    async def test_la_scheda_di_partenza_non_viene_cancellata(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        """Disattivata, non cancellata — come fa già `DELETE
        /api/admin/clients`. La riga resta a dire che quella persona era stata
        registrata due volte, e la nota dice dove è finita: senza, fra un anno
        una scheda vuota e inattiva non si distingue da un errore."""
        await _appuntamento(db, scheda_online, collaborator)

        await client_merge.esegui(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_online)

        assert scheda_online.is_active is False
        assert f"#{scheda_salone.id}" in scheda_online.notes

    async def test_niente_si_sposta_se_la_fusione_viene_rifiutata(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        """Il controllo sui due account scatta **prima** di spostare le righe.
        Se scattasse dopo, un rifiuto lascerebbe gli appuntamenti già spostati
        e le due schede peggio di prima."""
        await _appuntamento(db, scheda_online, collaborator)
        for scheda, indirizzo in ((scheda_salone, "c@x.it"), (scheda_online, "d@x.it")):
            acc = ClientAccount(
                email=indirizzo, password_hash="x", is_active=True, email_verified=True,
            )
            db.add(acc)
            await db.flush()
            scheda.account_id = acc.id
        await db.commit()

        with pytest.raises(client_merge.MergeRefused):
            await client_merge.esegui(db, scheda_salone.id, scheda_online.id)

        ancora_li = (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda_online.id)
        )).scalars().all()
        assert len(ancora_li) == 1, "gli appuntamenti si sono mossi nonostante il rifiuto"


class TestAnteprima:
    async def test_dice_quante_righe_si_muoverebbero(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        await _appuntamento(db, scheda_online, collaborator)
        db.add(Payment(client_id=scheda_online.id, amount=20, method=PaymentMethod.cash))
        await db.commit()

        a = await client_merge.prepara(db, scheda_salone.id, scheda_online.id)

        assert a.conteggi["appointments"] == 1
        assert a.conteggi["payments"] == 1
        assert a.righe_totali == 2

    async def test_non_cambia_niente(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        """È il senso stesso di un'anteprima, e vale la pena fissarlo: se
        toccasse qualcosa, guardare cosa succederebbe sarebbe già farlo."""
        await _appuntamento(db, scheda_online, collaborator)

        await client_merge.prepara(db, scheda_salone.id, scheda_online.id)
        await db.commit()
        await db.refresh(scheda_online)
        await db.refresh(scheda_salone)

        assert scheda_online.is_active is True
        assert (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda_online.id)
        )).scalars().all(), "l'anteprima ha spostato gli appuntamenti"

    async def test_annuncia_i_campi_che_riempirebbe(
        self, db, scheda_salone, scheda_online
    ):
        scheda_salone.phone = None
        scheda_online.phone = "+393339998887"
        scheda_online.notes = "Preferisce il pomeriggio."
        await db.commit()

        a = await client_merge.prepara(db, scheda_salone.id, scheda_online.id)

        assert "phone" in a.campi_riempiti
        assert a.note_unite is True

    async def test_anteprima_ed_esecuzione_dicono_la_stessa_cosa(
        self, db, scheda_salone, scheda_online, collaborator
    ):
        """La regressione che questo file esiste per impedire: due copie delle
        stesse regole che divergono, e l'anteprima mostra una cosa mentre la
        fusione ne fa un'altra — su un'operazione che non si annulla."""
        await _appuntamento(db, scheda_online, collaborator)
        scheda_salone.phone = None
        scheda_online.phone = "+393339998887"
        scheda_online.notes = "Preferisce il pomeriggio."
        await db.commit()

        prima = await client_merge.prepara(db, scheda_salone.id, scheda_online.id)
        dopo = await client_merge.esegui(db, scheda_salone.id, scheda_online.id)

        assert prima.conteggi == dopo.conteggi
        assert prima.campi_riempiti == dopo.campi_riempiti
        assert prima.note_unite == dopo.note_unite
        assert prima.account_spostato == dopo.account_spostato


class TestDallApi:
    async def test_un_admin_puo_unire(
        self, client, db, admin_tokens, scheda_salone, scheda_online, collaborator
    ):
        await _appuntamento(db, scheda_online, collaborator)

        resp = await client.post(
            f"/api/admin/clients/{scheda_salone.id}/merge",
            headers=auth(admin_tokens),
            json={"source_id": scheda_online.id},
        )

        assert resp.status_code == 200, resp.text
        corpo = resp.json()
        assert corpo["moved"]["appointments"] == 1
        assert corpo["total_rows"] == 1
        assert corpo["target"]["id"] == scheda_salone.id

    async def test_l_anteprima_e_leggibile_prima_di_confermare(
        self, client, db, admin_tokens, scheda_salone, scheda_online, collaborator
    ):
        await _appuntamento(db, scheda_online, collaborator)

        resp = await client.get(
            f"/api/admin/clients/{scheda_salone.id}/merge-preview",
            params={"source_id": scheda_online.id},
            headers=auth(admin_tokens),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["moved"]["appointments"] == 1
        # e non ha fatto niente
        assert (await db.execute(
            select(Appointment).where(Appointment.client_id == scheda_online.id)
        )).scalars().all()

    async def test_un_collaboratore_non_puo(
        self, client, collab_tokens, scheda_salone, scheda_online
    ):
        resp = await client.post(
            f"/api/admin/clients/{scheda_salone.id}/merge",
            headers=auth(collab_tokens),
            json={"source_id": scheda_online.id},
        )
        assert resp.status_code == 403

    async def test_un_cliente_del_portale_non_puo(
        self, client, client_tokens, scheda_salone, scheda_online
    ):
        resp = await client.post(
            f"/api/admin/clients/{scheda_salone.id}/merge",
            headers=auth(client_tokens),
            json={"source_id": scheda_online.id},
        )
        assert resp.status_code in (401, 403)

    async def test_una_richiesta_impossibile_risponde_400_non_500(
        self, client, admin_tokens, scheda_salone
    ):
        resp = await client.post(
            f"/api/admin/clients/{scheda_salone.id}/merge",
            headers=auth(admin_tokens),
            json={"source_id": scheda_salone.id},
        )
        assert resp.status_code == 400
        assert "stessa" in resp.json()["detail"].lower()
