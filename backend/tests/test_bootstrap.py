"""
`bootstrap.py` gira a ogni avvio del container (comando d'avvio del backend in `.railway/railway.ts`).

Quindi non è uno script di setup che si lancia una volta: è codice di
produzione che sta fra il container e il servizio funzionante. Se solleva,
il deploy fallisce e resta su la versione precedente.

Questi test esistono perché è successo davvero: un controllo su ADMIN_PASSWORD
messo in cima allo script — invece che nel punto in cui un admin viene creato —
ha bloccato un rilascio su cui non c'era niente di sbagliato, perché in
produzione quella variabile non è mai stata impostata e non serve: l'admin
esiste già ed è stato creato una volta sola.

La CI non lo avrebbe preso: applica le migration su un database vuoto, ma
bootstrap non lo esegue nessuno.
"""
import pytest
from sqlalchemy import select

from app.models.user import User, UserRole
from app.utils.auth import hash_password, verify_password
from bootstrap import ensure_admin

ESISTENTE = "titolare@nsh-test.it"


class TestQuandoLAdminEsisteGia:
    async def test_non_serve_nessuna_password(self, db):
        """Il caso che ha fatto fallire il deploy."""
        db.add(User(
            email=ESISTENTE,
            password_hash=await hash_password("la-password-vera-ruotata"),
            role=UserRole.admin,
        ))
        await db.commit()

        await ensure_admin(db, ESISTENTE, None)  # non deve sollevare

        utenti = (await db.execute(select(User))).scalars().all()
        assert len(utenti) == 1

    async def test_la_password_esistente_non_viene_toccata(self, db):
        db.add(User(
            email=ESISTENTE,
            password_hash=await hash_password("la-password-vera-ruotata"),
            role=UserRole.admin,
        ))
        await db.commit()

        await ensure_admin(db, ESISTENTE, "un-altra-password")

        utente = (await db.execute(select(User))).scalar_one()
        assert await verify_password("la-password-vera-ruotata", utente.password_hash), \
            "bootstrap ha riscritto la password di un admin esistente"


class TestQuandoLAdminVaCreato:
    async def test_senza_password_si_rifiuta(self, db):
        """Il repository è pubblico: la vecchia password di default la
        conoscono tutti. Meglio un deploy fermo che un admin regalato."""
        with pytest.raises(SystemExit) as e:
            await ensure_admin(db, "nuovo@nsh-test.it", None)
        assert "ADMIN_PASSWORD" in str(e.value)

        assert (await db.execute(select(User))).scalars().all() == []

    async def test_con_password_lo_crea(self, db):
        await ensure_admin(db, "nuovo@nsh-test.it", "una-password-scelta-apposta")
        await db.commit()

        utente = (await db.execute(select(User))).scalar_one()
        assert utente.email == "nuovo@nsh-test.it"
        assert utente.role == UserRole.admin
        assert await verify_password("una-password-scelta-apposta", utente.password_hash)


class TestNeiLogNienteIndirizzoPerIntero:
    """Il bootstrap gira a ogni deploy e stampa su stdout, cioè nei log di
    Railway: fino al 2026-10-08 ci scriveva l'email dell'admin in chiaro,
    unico punto dei log a non mascherarla."""

    async def test_admin_esistente(self, db, capsys):
        db.add(User(
            email=ESISTENTE,
            password_hash=await hash_password("la-password-vera-ruotata"),
            role=UserRole.admin,
        ))
        await db.commit()

        await ensure_admin(db, ESISTENTE, None)

        uscita = capsys.readouterr().out
        assert ESISTENTE not in uscita
        assert "t***e@nsh-test.it" in uscita

    async def test_admin_creato(self, db, capsys):
        await ensure_admin(db, "nuovo@nsh-test.it", "una-password-scelta-apposta")

        uscita = capsys.readouterr().out
        assert "nuovo@nsh-test.it" not in uscita
        assert "n***o@nsh-test.it" in uscita

    async def test_nel_rifiuto(self, db):
        with pytest.raises(SystemExit) as e:
            await ensure_admin(db, "nuovo@nsh-test.it", None)
        assert "nuovo@nsh-test.it" not in str(e.value)
