"""
Gli orari offerti dal portale sono quelli in cui il salone è davvero aperto.

Il difetto chiuso qui: `availability.py` costruiva gli slot con
`combine(data, ora, tzinfo=utc)`, cioè prendeva un'ora di orologio — che è
quello che c'è negli orari di lavoro, colonne `Time` senza fuso — e la
etichettava UTC. Il browser la rendeva poi nel fuso di Roma, spostandola avanti
di due ore d'estate e una d'inverno.

Il risultato, con un salone aperto 09:00–19:00 d'estate:
  - le clienti vedevano i bottoni dalle 11:00 alle 20:00;
  - si poteva prenotare alle 20:00, a serranda abbassata;
  - le 09:00–10:30 non comparivano mai;
  - un permesso 14:00–16:00 restava prenotabile.

Il difetto **non si vedeva confrontando appuntamenti fra loro**: quelli
entravano nella griglia con la stessa ora UTC, quindi si bloccavano a vicenda
correttamente. Si vedeva solo confrontando con gli orari di lavoro. È il motivo
per cui questi test guardano il confine, non la collisione.

`TestNonSiCorreggeAMeta` è la guardia contro la correzione parziale: sistemare
solo la riga degli slot, lasciando gli appuntamenti a entrare in griglia con
l'ora UTC, aprirebbe **doppie prenotazioni**.
"""
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.models.appointment import Appointment, AppointmentStatus
from app.models.collaborator import CollaboratorSchedule
from app.services.availability import get_available_slots
from app.utils.tempo import SALONE, istante, ora_salone

pytestmark = pytest.mark.asyncio

def _prossimo_giorno_con_scarto(ore: int) -> date:
    """La prima data futura in cui Roma è a `ore` da UTC.

    Calcolata e non fissata: una data scritta a mano finisce nel passato, e da
    quel momento `get_available_slots` restituisce `[]` per via del preavviso
    minimo — il test fallirebbe per un motivo che non c'entra niente con quello
    che sta verificando. È lo stesso inciampo già annotato in
    `test_turni_spezzati.py`.
    """
    giorno = date.today() + timedelta(days=3)
    for _ in range(400):
        if istante(giorno, time(12, 0)).astimezone(SALONE).utcoffset() == timedelta(hours=ore):
            return giorno
        giorno += timedelta(days=1)
    raise AssertionError(f"nessun giorno con scarto {ore}h nel prossimo anno")


# Lo scarto non è una costante: una correzione a scarto fisso passerebbe
# sull'ora legale e cadrebbe su quella solare.
ESTATE = _prossimo_giorno_con_scarto(2)
INVERNO = _prossimo_giorno_con_scarto(1)


async def _solo_orario(db, collaborator, giorno: date, inizio: time, fine: time):
    """Riscrive l'orario del collaboratore per quel giorno della settimana."""
    await db.execute(
        delete(CollaboratorSchedule).where(
            CollaboratorSchedule.collaborator_id == collaborator.id
        )
    )
    db.add(CollaboratorSchedule(
        collaborator_id=collaborator.id,
        day_of_week=giorno.weekday(),
        start_time=inizio, end_time=fine, is_working=True,
    ))
    await db.commit()


def _orari(slot):
    return [ora_salone(s).strftime("%H:%M") for s in slot]


class TestGliOrariOffertiSonoQuelliDiApertura:
    @pytest.mark.parametrize("giorno", [ESTATE, INVERNO])
    async def test_il_primo_slot_e_l_ora_di_apertura(
        self, db, booking_config, collaborator, giorno
    ):
        await _solo_orario(db, collaborator, giorno, time(9, 0), time(19, 0))
        orari = _orari(await get_available_slots(db, collaborator.id, giorno, 1))
        assert orari[0] == "09:00", "il salone apre alle 9, il primo bottone deve dire 9"

    @pytest.mark.parametrize("giorno", [ESTATE, INVERNO])
    async def test_non_si_prenota_dopo_la_chiusura(
        self, db, booking_config, collaborator, giorno
    ):
        """Il caso più grave del difetto: la cliente prenotava a salone chiuso
        e si presentava davanti alla serranda abbassata."""
        await _solo_orario(db, collaborator, giorno, time(9, 0), time(19, 0))
        orari = _orari(await get_available_slots(db, collaborator.id, giorno, 1))
        assert orari[-1] == "18:30", "l'ultimo slot da mezz'ora finisce alle 19"
        assert not [o for o in orari if o >= "19:00"]

    async def test_lo_slot_delle_nove_e_davvero_le_sette_utc_d_estate(
        self, db, booking_config, collaborator
    ):
        """Il valore che finisce a database è un istante, non un'ora di
        orologio travestita."""
        await _solo_orario(db, collaborator, ESTATE, time(9, 0), time(19, 0))
        primo = (await get_available_slots(db, collaborator.id, ESTATE, 1))[0]
        assert primo == datetime.combine(ESTATE, time(7, 0), tzinfo=timezone.utc)

    async def test_d_inverno_lo_stesso_slot_e_le_otto_utc(
        self, db, booking_config, collaborator
    ):
        await _solo_orario(db, collaborator, INVERNO, time(9, 0), time(19, 0))
        primo = (await get_available_slots(db, collaborator.id, INVERNO, 1))[0]
        assert primo == datetime.combine(INVERNO, time(8, 0), tzinfo=timezone.utc)


class TestNonSiCorreggeAMeta:
    """La trappola della correzione parziale.

    Sistemare la costruzione degli slot senza sistemare il modo in cui gli
    appuntamenti entrano nella griglia dei minuti li farebbe cadere su due
    scale diverse: l'appuntamento occuperebbe un minuto che nessuno slot
    guarda, e lo slot resterebbe libero. Due clienti sulla stessa poltrona.
    """

    @pytest.mark.parametrize("giorno", [ESTATE, INVERNO])
    async def test_un_appuntamento_toglie_il_suo_slot(
        self, db, booking_config, collaborator, other_client, giorno
    ):
        await _solo_orario(db, collaborator, giorno, time(9, 0), time(19, 0))
        quando = istante(giorno, time(11, 0))
        db.add(Appointment(
            client_id=other_client.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(hours=1),
            status=AppointmentStatus.confirmed,
        ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, giorno, 1))
        assert "11:00" not in orari, "lo slot occupato non può restare prenotabile"
        assert "11:30" not in orari, "l'appuntamento dura un'ora"
        assert "12:00" in orari, "e non un minuto di più"

    async def test_un_appuntamento_di_prima_mattina_occupa_il_suo_slot(
        self, db, booking_config, collaborator, other_client
    ):
        """Il caso che i confini di giornata in UTC perdevano: d'estate le
        09:00 del salone sono le 07:00 UTC, ma la finestra della query partiva
        dalla mezzanotte UTC, quindi il giorno era quello giusto per caso.
        Con l'apertura alle 01:00 non lo sarebbe più."""
        await _solo_orario(db, collaborator, ESTATE, time(9, 0), time(19, 0))
        quando = istante(ESTATE, time(9, 0))
        db.add(Appointment(
            client_id=other_client.id, collaborator_id=collaborator.id,
            start_time=quando, end_time=quando + timedelta(minutes=30),
            status=AppointmentStatus.confirmed,
        ))
        await db.commit()

        orari = _orari(await get_available_slots(db, collaborator.id, ESTATE, 1))
        assert "09:00" not in orari
        assert "09:30" in orari
