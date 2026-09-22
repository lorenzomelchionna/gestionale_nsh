"""
Il promemoria che risultava «inviato» senza esserlo — due modi diversi.

1. `notify_appointment_reminder` intercetta l'errore di ogni canale (email,
   WhatsApp) e non lo rilancia: è la scelta giusta, un canale rotto non deve
   far fallire l'altro. Ma il chiamante non aveva modo di sapere se *almeno
   uno* fosse arrivato, quindi segnava `reminder_sent = True` comunque —
   anche quando entrambi i canali fallivano. Da quel momento l'appuntamento
   non rientra più nella finestra che il task periodico interroga
   (`reminder_sent == False`): il tentativo è perso per sempre, con solo una
   riga di log a saperlo.

   La funzione ora ritorna se il promemoria è «gestito»: consegnato su
   almeno un canale, o senza canali da tentare. Ritorna `False` solo quando
   un canale è stato tentato ed è fallito — il segnale a non spuntare il
   flag, perché al giro dopo vale la pena riprovare.

2. Spostare un appuntamento dall'agenda non faceva ripartire il promemoria:
   `update_appointment` applica ogni campo del payload con `setattr`, ma
   `reminder_sent` non veniva mai riportato a `False` quando cambiava
   `start_time`. Un promemoria già mandato per il vecchio orario restava
   segnato «inviato» anche per il nuovo, che quindi non ne riceveva uno.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.appointment import Appointment, AppointmentStatus
from app.models.client import Client

pytestmark = pytest.mark.asyncio


class TestNotifyAppointmentReminderRitornaSeConsegnato:
    async def test_ritorna_false_se_entrambi_i_canali_falliscono(
        self, db, client_account, collaborator, monkeypatch
    ):
        from app.utils import notifications as notif

        async def rotto_email(*a, **kw):
            raise RuntimeError("email giù")

        async def rotto_whatsapp(*a, **kw):
            raise RuntimeError("whatsapp giù")

        monkeypatch.setattr(notif.email_util, "send_appointment_reminder", rotto_email)
        monkeypatch.setattr(notif.wa_util, "send_reminder_message", rotto_whatsapp)
        monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: True)

        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()
        cliente.phone = "+393331112222"
        await db.commit()

        quando = datetime.now(timezone.utc) + timedelta(hours=25)
        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=quando,
            end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=False,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        gestito = await notif.notify_appointment_reminder(db, appt)
        assert gestito is False, (
            "con entrambi i canali rotti non c'è stata consegna: il chiamante "
            "deve saperlo per non segnare il promemoria come inviato"
        )

    async def test_ritorna_true_se_almeno_un_canale_consegna(
        self, db, client_account, collaborator, monkeypatch
    ):
        from app.utils import notifications as notif

        async def ok_email(*a, **kw):
            return None

        async def rotto_whatsapp(*a, **kw):
            raise RuntimeError("whatsapp giù")

        monkeypatch.setattr(notif.email_util, "send_appointment_reminder", ok_email)
        monkeypatch.setattr(notif.wa_util, "send_reminder_message", rotto_whatsapp)
        monkeypatch.setattr(notif, "_wa_enabled", lambda cfg: True)

        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()
        cliente.phone = "+393331112222"
        await db.commit()

        quando = datetime.now(timezone.utc) + timedelta(hours=25)
        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=quando,
            end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=False,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        gestito = await notif.notify_appointment_reminder(db, appt)
        assert gestito is True, (
            "l'email è arrivata anche se WhatsApp è fallito: va considerato consegnato"
        )

    async def test_ritorna_true_senza_nessun_canale_disponibile(
        self, db, collaborator, monkeypatch
    ):
        """Un cliente senza email né telefono non ha nessun canale da
        tentare: non va segnato come fallito, altrimenti il task lo
        ritenterebbe ogni 15 minuti per sempre senza che possa mai riuscire."""
        from app.utils import notifications as notif
        from app.models.client import Client as ClientModel

        senza_contatti = ClientModel(first_name="Senza", last_name="Contatti", phone=None, email=None)
        db.add(senza_contatti)
        await db.commit()
        await db.refresh(senza_contatti)

        quando = datetime.now(timezone.utc) + timedelta(hours=25)
        appt = Appointment(
            client_id=senza_contatti.id,
            collaborator_id=collaborator.id,
            start_time=quando,
            end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=False,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)
        appt.client = senza_contatti

        gestito = await notif.notify_appointment_reminder(db, appt)
        assert gestito is True


class TestSpostareAppuntamentoRiattivaIlPromemoria:
    async def test_reminder_sent_torna_false_quando_cambia_lo_start_time(
        self, client, db, admin_tokens, client_account, collaborator, service
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        vecchio_inizio = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=vecchio_inizio,
            end_time=vecchio_inizio + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=True,  # il promemoria per il vecchio orario è già partito
            whatsapp_reminder_sent=True,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        nuovo_inizio = vecchio_inizio + timedelta(days=3)
        resp = await client.put(
            f"/api/admin/appointments/{appt.id}",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            json={
                "start_time": nuovo_inizio.isoformat(),
                "end_time": (nuovo_inizio + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == 200

        await db.refresh(appt)
        assert appt.start_time == nuovo_inizio
        assert appt.reminder_sent is False, (
            "spostare l'orario deve far ripartire il promemoria per il nuovo orario"
        )
        assert appt.whatsapp_reminder_sent is False

    async def test_reminder_sent_resta_vero_se_non_cambia_l_orario(
        self, client, db, admin_tokens, client_account, collaborator, service
    ):
        """Il controllo è specifico allo spostamento: una modifica che non
        tocca `start_time` (per esempio le note) non deve azzerare un
        promemoria già mandato, o ne partirebbe uno di troppo."""
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        inizio = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=inizio,
            end_time=inizio + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=True,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        resp = await client.put(
            f"/api/admin/appointments/{appt.id}",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            json={"notes": "cliente ha chiesto di anticipare la prossima volta"},
        )
        assert resp.status_code == 200

        await db.refresh(appt)
        assert appt.reminder_sent is True

    async def test_reminder_sent_resta_vero_se_il_nuovo_start_time_e_uguale(
        self, client, db, admin_tokens, client_account, collaborator, service
    ):
        """Anche mandando esplicitamente lo stesso `start_time` non deve
        azzerarsi: non è cambiato niente da avvisare di nuovo."""
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        inizio = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=2)
        appt = Appointment(
            client_id=cliente.id,
            collaborator_id=collaborator.id,
            start_time=inizio,
            end_time=inizio + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
            reminder_sent=True,
        )
        db.add(appt)
        await db.commit()
        await db.refresh(appt)

        resp = await client.put(
            f"/api/admin/appointments/{appt.id}",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
            json={"start_time": inizio.isoformat(), "end_time": (inizio + timedelta(hours=1)).isoformat()},
        )
        assert resp.status_code == 200

        await db.refresh(appt)
        assert appt.reminder_sent is True
