"""
Più fasce di lavoro nello stesso giorno.

Erano gli ultimi due `scalar_one_or_none()` della famiglia già chiusa sulle
assenze il 2026-08-04. Nessuna delle due tabelle ha un vincolo di unicità e
`POST /api/admin/extra-days` non controlla niente, quindi due righe sulla
stessa data si creano con due click — e da quel momento il calcolo della
disponibilità **sollevava** per quel collaboratore in quel giorno, invece di
rispondere. L'agenda smetteva di funzionare per un doppio click.

Ma più righe non sono un errore da tollerare: sono il turno spezzato, che in
un salone è la norma. Quindi non si scarta la seconda e non si fondono in
una sola — si tengono come fasce separate.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.collaborator import CollaboratorSchedule
from app.models.extra_day import CollaboratorExtraDay
from app.services.availability import get_available_slots

pytestmark = pytest.mark.asyncio

# Lontano abbastanza da non finire sotto il minimo di preavviso, e mai di
# domenica: il fixture `collaborator` lavora lun–sab, quindi su una domenica
# `get_available_slots` restituisce giustamente `[]` e i test di
# `TestQuelloCheNonCambia` fallirebbero senza che ci sia niente di rotto.
#
# Trovato dal vivo: scritto come `date.today() + timedelta(days=10)` il file
# passava, finché la data non è cambiata e il decimo giorno è caduto di
# domenica. Un test che fallisce un giorno su sette è peggio di uno che
# fallisce sempre — si presenta come un guasto misterioso proprio mentre si
# sta guardando dell'altro.
#
# Stesso rimedio già usato in `test_partial_absences.py`.
def _giorno_lavorativo(base: date) -> date:
    while base.weekday() == 6:
        base += timedelta(days=1)
    return base


GIORNO = _giorno_lavorativo(date.today() + timedelta(days=10))


def _orari(slot):
    return [s.strftime("%H:%M") for s in slot]


async def _pulisci_orari(db, collaborator):
    """Toglie l'orario ordinario, così restano solo le fasce del test."""
    from sqlalchemy import delete

    await db.execute(
        delete(CollaboratorSchedule).where(
            CollaboratorSchedule.collaborator_id == collaborator.id
        )
    )
    await db.commit()


class TestOrarioSpezzato:
    async def test_due_fasce_nello_stesso_giorno_non_sollevano(
        self, db, booking_config, collaborator
    ):
        """Il bug: due righe per lo stesso giorno e il calcolo esplodeva."""
        await _pulisci_orari(db, collaborator)
        for inizio, fine in ((time(9, 0), time(13, 0)), (time(15, 0), time(19, 0))):
            db.add(CollaboratorSchedule(
                collaborator_id=collaborator.id,
                day_of_week=GIORNO.weekday(),
                start_time=inizio, end_time=fine, is_working=True,
            ))
        await db.commit()

        slot = await get_available_slots(db, collaborator.id, GIORNO, 1)
        assert slot, "con due fasce valide qualche slot deve uscire"

    async def test_la_pausa_pranzo_resta_chiusa(
        self, db, booking_config, collaborator
    ):
        """Il motivo per cui le fasce non si fondono: unire 09–13 e 15–19 in
        09–19 aprirebbe due ore in cui in salone non c'è nessuno."""
        await _pulisci_orari(db, collaborator)
        for inizio, fine in ((time(9, 0), time(13, 0)), (time(15, 0), time(19, 0))):
            db.add(CollaboratorSchedule(
                collaborator_id=collaborator.id,
                day_of_week=GIORNO.weekday(),
                start_time=inizio, end_time=fine, is_working=True,
            ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 1))
        assert "12:30" in orari
        assert "15:00" in orari
        for chiuso in ("13:00", "13:30", "14:00", "14:30"):
            assert chiuso not in orari, f"{chiuso} è pausa, non deve essere prenotabile"

    async def test_un_appuntamento_non_scavalca_la_pausa(
        self, db, booking_config, collaborator
    ):
        """Un colore da due ore non può cominciare alle 12 e finire dopo
        pranzo: deve stare dentro una fascia, non a cavallo di due."""
        await _pulisci_orari(db, collaborator)
        for inizio, fine in ((time(9, 0), time(13, 0)), (time(15, 0), time(19, 0))):
            db.add(CollaboratorSchedule(
                collaborator_id=collaborator.id,
                day_of_week=GIORNO.weekday(),
                start_time=inizio, end_time=fine, is_working=True,
            ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 4))
        assert "12:00" not in orari
        assert "11:00" in orari  # 11:00–13:00 ci sta tutto nella mattina
        assert "15:00" in orari


class TestGiorniStraordinari:
    async def test_due_giorni_extra_sulla_stessa_data_non_sollevano(
        self, db, booking_config, collaborator
    ):
        """Il caso che si crea con due click, perché l'endpoint non controlla."""
        for inizio, fine in ((time(10, 0), time(12, 0)), (time(16, 0), time(18, 0))):
            db.add(CollaboratorExtraDay(
                collaborator_id=collaborator.id, date=GIORNO,
                start_time=inizio, end_time=fine,
            ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 1))
        assert "10:00" in orari
        assert "16:00" in orari
        assert "13:00" not in orari

    async def test_il_giorno_extra_vince_sull_orario_ordinario(
        self, db, booking_config, collaborator
    ):
        """Comportamento di sempre, da non perdere per strada: se c'è una
        giornata straordinaria, è quella a valere."""
        db.add(CollaboratorExtraDay(
            collaborator_id=collaborator.id, date=GIORNO,
            start_time=time(20, 0), end_time=time(22, 0),
        ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 1))
        assert orari and all(o >= "20:00" for o in orari)
        assert "09:00" not in orari

    async def test_due_righe_identiche_non_sdoppiano_gli_orari(
        self, db, booking_config, collaborator
    ):
        """Il duplicato vero e proprio: due righe uguali. Senza deduplica lo
        stesso orario comparirebbe due volte nell'elenco."""
        for _ in range(2):
            db.add(CollaboratorExtraDay(
                collaborator_id=collaborator.id, date=GIORNO,
                start_time=time(10, 0), end_time=time(12, 0),
            ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 1))
        assert len(orari) == len(set(orari))


class TestQuelloCheNonCambia:
    async def test_una_fascia_sola_si_comporta_come_prima(
        self, db, booking_config, collaborator
    ):
        """Il caso normale, che è anche quello di tutti i collaboratori veri."""
        orari = _orari(await get_available_slots(db, collaborator.id, GIORNO, 1))
        assert "09:00" in orari
        assert "18:30" in orari
        assert "19:00" not in orari  # l'ultimo slot deve finire entro le 19

    async def test_senza_orario_il_giorno_resta_chiuso(
        self, db, booking_config, collaborator
    ):
        await _pulisci_orari(db, collaborator)
        assert await get_available_slots(db, collaborator.id, GIORNO, 1) == []

    async def test_una_riga_senza_orari_non_apre_il_giorno(
        self, db, booking_config, collaborator
    ):
        """`is_working=True` con gli orari vuoti non è una fascia: prima
        veniva scartata dal controllo, e deve continuare a esserlo."""
        await _pulisci_orari(db, collaborator)
        db.add(CollaboratorSchedule(
            collaborator_id=collaborator.id, day_of_week=GIORNO.weekday(),
            start_time=None, end_time=None, is_working=True,
        ))
        await db.commit()

        assert await get_available_slots(db, collaborator.id, GIORNO, 1) == []
