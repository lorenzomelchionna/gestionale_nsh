"""
Il costo di bcrypt in produzione, guardato da fuori.

Esiste per una ragione precisa: `conftest.py` **abbassa bcrypt a 4 round** per
tutta la suite, perché a 12 round un hash costa 188 ms e i test ne fanno
migliaia — era quasi tutto il tempo di esecuzione.

Quella scorciatoia è sicura solo finché resta confinata ai test. Se un giorno
qualcuno abbassasse i round nel codice vero — per far girare più veloce un
seed, per copia-incolla da qui, per qualunque motivo — **nessun altro test se
ne accorgerebbe**: la password giusta continuerebbe a entrare e quella
sbagliata a essere respinta, che è tutto ciò che gli altri test guardano.

Il costo di bcrypt non è una prestazione, è la difesa: è ciò che rende
impraticabile provare le password una per una su un archivio rubato. Dodici
round significa circa un decimo di secondo per tentativo; quattro significa
meno di un millesimo, cioè migliaia di volte più tentativi al secondo per chi
attacca.

Questo file legge la configurazione **dell'applicazione**, non quella
sostituita nei test, e fallisce se scende sotto la soglia.
"""
import importlib

import pytest

# Soglia scelta, non ereditata: 12 è il default di passlib oggi ed è
# considerato adeguato. Va alzata quando le macchine diventano più veloci, non
# abbassata quando la suite sembra lenta — per quello c'è già `conftest`.
ROUND_MINIMI = 12


def _contesto_di_produzione():
    """Il `CryptContext` come lo costruisce l'applicazione.

    `conftest` sostituisce `app.utils.auth.pwd_context` all'avvio della suite,
    quindi leggerlo direttamente restituirebbe la versione a 4 round e questo
    test si autoingannerebbe. Il modulo viene riletto dal sorgente.
    """
    modulo = importlib.import_module("app.utils.auth")
    sorgente = importlib.util.find_spec("app.utils.auth")
    fresco = importlib.util.module_from_spec(sorgente)
    sorgente.loader.exec_module(fresco)
    assert fresco is not modulo
    return fresco.pwd_context


def test_la_produzione_usa_almeno_dodici_round():
    contesto = _contesto_di_produzione()
    hash_prodotto = contesto.hash("una-password-qualunque")

    # Il costo sta nell'hash stesso: `$2b$12$...`
    parti = hash_prodotto.split("$")
    assert parti[1].startswith("2"), f"schema inatteso: {parti[1]}"
    round_usati = int(parti[2])

    assert round_usati >= ROUND_MINIMI, (
        f"bcrypt in produzione gira a {round_usati} round, sotto il minimo di "
        f"{ROUND_MINIMI}. Se è stato abbassato per far correre i test, la "
        f"strada è `conftest.py`, che lo abbassa solo lì."
    )


def test_i_test_invece_girano_al_costo_minimo():
    """L'altra metà: se un giorno la scorciatoia in `conftest` sparisse, la
    suite tornerebbe lenta di colpo e senza spiegazione. Questo test dice
    dov'è la leva."""
    from app.utils import auth

    hash_di_test = auth.pwd_context.hash("una-password-qualunque")
    round_usati = int(hash_di_test.split("$")[2])

    assert round_usati < ROUND_MINIMI, (
        "i test stanno girando al costo di produzione: la suite ci mette "
        "minuti invece di secondi. Vedi la nota in `conftest.py`."
    )


@pytest.mark.asyncio
async def test_le_password_continuano_a_funzionare():
    """La scorciatoia non deve cambiare il comportamento, solo il costo."""
    from app.utils.auth import hash_password, verify_password

    hash_prodotto = await hash_password("password-giusta-1234")
    assert await verify_password("password-giusta-1234", hash_prodotto)
    assert not await verify_password("password-sbagliata", hash_prodotto)
