"""
Il riepilogo della dashboard confondeva il giorno del salone col giorno UTC.

`GET /dashboard/stats` calcolava «oggi/settimana/mese/anno» a partire da
`datetime.now(timezone.utc)`, non dal giorno del salone. Fra la mezzanotte e
l'alba a Roma (l'ora esatta dipende dalla stagione: fino alle 01:00 d'inverno,
fino alle 02:00 d'estate) il giorno UTC è ancora ieri: un incasso della sera
tardi compariva nel riepilogo di ieri, che nessuno riapre più, e spariva da
quello di oggi. Le spese avevano lo stesso difetto una seconda volta nella
stessa funzione: confrontavano `Expense.date` (un giorno di calendario, senza
fuso) con `.date()` di un istante UTC invece che col giorno del salone.

I test bloccano `tempo.adesso()` — il solo punto da cui l'endpoint legge
"adesso" dopo la correzione — su un istante fisso di prima mattina a Roma:
deterministico, non serve aspettare la notte vera né dipende da quando gira
la suite.

Riferimento: `TODO_notifiche.md`, «Difetti minori» del 2026-09-22.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.client import Client
from app.models.expense import Expense
from app.models.payment import Payment, PaymentMethod
from app.utils.tempo import SALONE

pytestmark = pytest.mark.asyncio

# 23:30 UTC del 15 giugno = 01:30 del 16 giugno a Roma (CEST, UTC+2): il
# giorno UTC è ancora il 15, quello del salone è già il 16.
ADESSO_FINTO = datetime(2026, 6, 15, 23, 30, tzinfo=timezone.utc)
OGGI_SALONE = ADESSO_FINTO.astimezone(SALONE).date()  # 2026-06-16
OGGI_UTC = ADESSO_FINTO.date()  # 2026-06-15


@pytest.fixture(autouse=True)
def orologio_fisso(monkeypatch):
    """Blocca "adesso" sull'istante sopra, ovunque sia importato.

    `dashboard.py` fa `from app.utils.tempo import adesso`, cioè importa il
    *nome*, non il modulo: sostituire `tempo.adesso` non basta, va sostituito
    anche l'attributo `adesso` dentro `dashboard` stesso.
    """
    import app.utils.tempo as tempo
    import app.api.admin.dashboard as dashboard
    monkeypatch.setattr(tempo, "adesso", lambda: ADESSO_FINTO)
    monkeypatch.setattr(dashboard, "adesso", lambda: ADESSO_FINTO)


class TestRiepilogoOggiUsaIlGiornoDelSalone:
    async def test_incasso_di_tarda_notte_conta_in_oggi(
        self, client, db, admin_tokens, client_account
    ):
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        db.add(Payment(
            client_id=cliente.id, amount=77.0,
            method=PaymentMethod.cash, date=ADESSO_FINTO,
        ))
        await db.commit()

        resp = await client.get(
            "/api/admin/dashboard/stats?period=today",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_revenue"] == pytest.approx(77.0), (
            f"un incasso delle 01:30 a Roma ({OGGI_SALONE}) deve contare nel "
            f"riepilogo di 'oggi', anche se in UTC è ancora {OGGI_UTC}"
        )

    async def test_incasso_di_ieri_sera_resta_fuori(
        self, client, db, admin_tokens, client_account
    ):
        """Il confine dev'essere quello giusto, non solo spostato: un incasso
        della sera prima (20:00 a Roma del 15 giugno, ben prima di
        mezzanotte là) non deve comparire nel riepilogo di oggi."""
        cliente = (await db.execute(
            select(Client).where(Client.account_id == client_account.id)
        )).scalar_one()

        db.add(Payment(
            client_id=cliente.id, amount=999.0,
            method=PaymentMethod.cash,
            date=ADESSO_FINTO.replace(hour=18, minute=0),  # 20:00 CEST a Roma, 15 giugno
        ))
        await db.commit()

        resp = await client.get(
            "/api/admin/dashboard/stats?period=today",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_revenue"] == pytest.approx(0.0), (
            "un incasso di ieri sera a Roma non deve comparire nel riepilogo "
            "di oggi solo perché la finestra si è allargata"
        )

    async def test_spesa_datata_col_giorno_utc_non_conta_in_oggi(
        self, client, db, admin_tokens
    ):
        db.add(Expense(
            amount=15.0, category="altro",
            description="datata col giorno UTC", date=OGGI_UTC,
        ))
        await db.commit()

        resp = await client.get(
            "/api/admin/dashboard/stats?period=today",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_expenses"] == pytest.approx(0.0), (
            "una spesa datata col giorno di calendario UTC (che qui è 'ieri' "
            "per il salone) non deve contare nel riepilogo di 'oggi'"
        )

    async def test_spesa_datata_col_giorno_del_salone_conta_in_oggi(
        self, client, db, admin_tokens
    ):
        db.add(Expense(
            amount=42.0, category="altro",
            description="datata col giorno del salone", date=OGGI_SALONE,
        ))
        await db.commit()

        resp = await client.get(
            "/api/admin/dashboard/stats?period=today",
            headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_expenses"] == pytest.approx(42.0), (
            "una spesa datata col giorno del salone deve contare in 'oggi', "
            "anche se quel giorno non è ancora iniziato in UTC"
        )
