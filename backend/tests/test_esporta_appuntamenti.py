"""
Gli appuntamenti in Excel (`GET /api/admin/appointments/export`).

Nato dal 2026-11-27: senza internet in salone il gestionale era vuoto. Il
file serve a lavorare la giornata senza il gestionale, quindi deve dire
chi arriva, quando, con chi, a far cosa, e come richiamarla — con l'ora del
salone, non quella UTC del server.
"""
from datetime import date, datetime, time, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

from app.models.appointment import (
    Appointment, AppointmentOrigin, AppointmentService, AppointmentStatus,
)
from app.models.client import Client
from tests.conftest import auth

ROMA = ZoneInfo("Europe/Rome")
GIORNO = date.today() + timedelta(days=3)
URL = "/api/admin/appointments/export"


async def _appuntamento(db, cliente, collaborator, service, ora, stato=AppointmentStatus.confirmed,
                        giorno=GIORNO, note=None):
    inizio = datetime.combine(giorno, time(ora, 0), tzinfo=ROMA)
    a = Appointment(
        client_id=cliente.id, collaborator_id=collaborator.id,
        start_time=inizio, end_time=inizio + timedelta(minutes=45),
        status=stato, origin=AppointmentOrigin.salon, notes=note,
    )
    db.add(a)
    await db.flush()
    db.add(AppointmentService(appointment_id=a.id, service_id=service.id,
                              price_snapshot=float(service.price)))
    await db.commit()
    return a


async def _cliente(db, nome="Anna", telefono="+393331112223"):
    c = Client(first_name=nome, last_name="Prova", phone=telefono)
    db.add(c)
    await db.commit()
    return c


def _righe(r):
    ws = load_workbook(BytesIO(r.content)).active
    return [list(riga) for riga in ws.iter_rows(values_only=True)]


async def test_il_file_dice_chi_quando_e_come_richiamarla(
    client, db, admin_tokens, collaborator, service,
):
    anna = await _cliente(db)
    await _appuntamento(db, anna, collaborator, service, 9, note="porta la foto")

    r = await client.get(URL, headers=auth(admin_tokens),
                         params={"dal": GIORNO.isoformat(), "al": GIORNO.isoformat()})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert f'appuntamenti_{GIORNO.isoformat()}_{GIORNO.isoformat()}.xlsx' in r.headers["content-disposition"]
    intestazione, riga = _righe(r)
    assert intestazione[:7] == ["Data", "Giorno", "Inizio", "Fine", "Collaboratore", "Cliente", "Telefono"]
    assert riga[0].date() == GIORNO
    # Ora del salone: le 9 restano le 9, non le 8 (UTC d'inverno).
    assert riga[2:4] == ["09:00", "09:45"]
    assert riga[5] == "Anna Prova"
    assert riga[6] == "+393331112223"
    assert riga[7] == service.name
    assert riga[8] == "Confermato"
    assert riga[9] == "porta la foto"


async def test_annullati_e_rifiutati_restano_fuori_ordine_per_ora(
    client, db, admin_tokens, collaborator, service,
):
    anna = await _cliente(db)
    await _appuntamento(db, anna, collaborator, service, 15)
    await _appuntamento(db, anna, collaborator, service, 10)
    await _appuntamento(db, anna, collaborator, service, 11, stato=AppointmentStatus.cancelled)
    await _appuntamento(db, anna, collaborator, service, 12, stato=AppointmentStatus.rejected)
    await _appuntamento(db, anna, collaborator, service, 13, stato=AppointmentStatus.pending)

    r = await client.get(URL, headers=auth(admin_tokens),
                         params={"dal": GIORNO.isoformat(), "al": GIORNO.isoformat()})
    righe = _righe(r)[1:]
    assert [riga[2] for riga in righe] == ["10:00", "13:00", "15:00"]
    assert righe[1][8] == "Da confermare"


async def test_i_giorni_ai_bordi_sono_inclusi_gli_altri_no(
    client, db, admin_tokens, collaborator, service,
):
    anna = await _cliente(db)
    for delta in (-1, 0, 2, 3):
        await _appuntamento(db, anna, collaborator, service, 9, giorno=GIORNO + timedelta(days=delta))

    r = await client.get(URL, headers=auth(admin_tokens),
                         params={"dal": GIORNO.isoformat(), "al": (GIORNO + timedelta(days=2)).isoformat()})
    assert [riga[0].date() for riga in _righe(r)[1:]] == [GIORNO, GIORNO + timedelta(days=2)]


async def test_senza_date_da_oggi_a_trenta_giorni(client, admin_tokens):
    r = await client.get(URL, headers=auth(admin_tokens))
    assert r.status_code == 200
    assert "appuntamenti_" in r.headers["content-disposition"]


async def test_date_al_contrario_o_troppo_lontane(client, admin_tokens):
    r = await client.get(URL, headers=auth(admin_tokens), params={"dal": "2026-12-10", "al": "2026-12-01"})
    assert r.status_code == 422
    r = await client.get(URL, headers=auth(admin_tokens), params={"dal": "2026-01-01", "al": "2027-06-01"})
    assert r.status_code == 422


async def test_solo_amministratori(client, collab_tokens, client_tokens):
    """Il file ha i telefoni di tutte le clienti del periodo."""
    assert (await client.get(URL, headers=auth(collab_tokens))).status_code == 403
    assert (await client.get(URL, headers=auth(client_tokens))).status_code in (401, 403)
    assert (await client.get(URL)).status_code == 401


async def test_ogni_esportazione_finisce_nel_registro(client, admin_tokens, caplog):
    import logging
    with caplog.at_level(logging.INFO, logger="nsh.sicurezza"):
        await client.get(URL, headers=auth(admin_tokens))
    assert any(getattr(r, "evento", "") == "esportazione_appuntamenti" for r in caplog.records)
