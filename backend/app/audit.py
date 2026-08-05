"""Gli eventi che vale la pena poter ricostruire dopo.

Due cose distinte, che stanno insieme perché rispondono alla stessa domanda.

La prima è il **registro degli accessi**: una riga per richiesta, con chi,
cosa, e com'è andata. È la parte noiosa ed è quella che conta davvero — dopo
un furto di credenziali la domanda non è «qualcuno è entrato?» ma «ha aperto
le schede di quali clienti?», e a quella risponde solo l'elenco delle
richieste fatte con quel token.

La seconda sono gli **eventi di sicurezza**: login riusciti e falliti, token
rifiutati, permessi negati, password reimpostate. Sono pochi e nominati uno per
uno, così si cercano per nome invece che per frase.

Perché i nomi degli eventi sono costanti e non stringhe scritte a mano nel
punto in cui servono: una ricerca nei log vale quanto la costanza con cui è
stato scritto ciò che si cerca. `login_fallito` scritto in un punto e
`failed_login` in un altro sono due eventi diversi per chi cerca, e quello che
non trova è proprio quello che gli serviva.
"""
import logging
import re
import time
import uuid
from typing import Optional

from starlette.requests import Request

from app.logging_config import attore, id_richiesta, maschera_email

accessi = logging.getLogger("nsh.accessi")
sicurezza = logging.getLogger("nsh.sicurezza")

# ── Nomi degli eventi ─────────────────────────────────────────────────
LOGIN_OK = "login_riuscito"
LOGIN_KO = "login_fallito"
LOGIN_BLOCCATO = "login_bloccato"          # credenziali giuste, account chiuso
TOKEN_RIFIUTATO = "token_rifiutato"
PERMESSO_NEGATO = "permesso_negato"
LIMITE_SUPERATO = "limite_superato"
REGISTRAZIONE = "registrazione"
EMAIL_VERIFICATA = "email_verificata"
VERIFICA_FALLITA = "verifica_fallita"
RESET_CHIESTO = "reset_password_chiesto"
RESET_ESEGUITO = "reset_password_eseguito"

# Richieste che non finiscono nel registro: il check di salute di Railway
# arriva ogni pochi secondi per sempre, e un registro fatto per il 99% di
# quello smette di essere leggibile — cioè smette di servire.
NON_REGISTRATE = frozenset({"/health"})


def evento(nome: str, livello: int = logging.INFO, **campi) -> None:
    """Scrive un evento di sicurezza.

    I campi finiscono nel JSON come attributi separati, quindi si filtrano.
    Non passare mai qui password, token o codici: il filtro in
    `logging_config` li toglierebbe comunque, ma contarci è il modo di
    scoprire un giorno che quel filtro aveva un buco.
    """
    sicurezza.log(livello, nome, extra={"evento": nome, **campi})


def login_riuscito(*, tipo: str, id_account: int, email: str) -> None:
    evento(LOGIN_OK, tipo=tipo, id_account=id_account, email=maschera_email(email))


def login_fallito(*, email: str, motivo: str) -> None:
    """Un tentativo andato male.

    `WARNING` e non `INFO`: uno non dice niente, trenta di fila dallo stesso
    indirizzo sono l'unico segnale che il salone ha di essere sotto attacco, e
    a `INFO` starebbero in mezzo a tutto il resto.

    L'indirizzo è mascherato perché qui, più che altrove, può essere di
    qualcuno che non c'entra: chi prova password a caso scrive gli indirizzi
    che ha, non i nostri.
    """
    evento(LOGIN_KO, logging.WARNING, email=maschera_email(email), motivo=motivo)


def accesso_negato(*, motivo: str, percorso: str, livello: int = logging.WARNING) -> None:
    evento(PERMESSO_NEGATO, livello, motivo=motivo, percorso=percorso)


def token_rifiutato(*, motivo: str) -> None:
    """Un token che non va bene per questa porta.

    Vale la pena guardarlo: `tipo_sbagliato` significa che qualcuno ha
    presentato un token cliente su una rotta dello staff, ed è esattamente la
    forma che aveva l'escalation cliente→admin già trovata in questo codice.
    """
    evento(TOKEN_RIFIUTATO, logging.WARNING, motivo=motivo)


def imposta_attore(tipo: str, id_soggetto: int) -> None:
    """Registra chi è, così le righe successive di questa richiesta lo dicono.

    Chiamata dalle dipendenze di autenticazione: è il momento in cui l'identità
    passa da «un token» a «questa persona», e da lì in poi ogni riga scritta
    durante la richiesta la porta con sé — compresa quella finale del
    registro accessi, che viene scritta dopo.
    """
    attore.set(f"{tipo}:{id_soggetto}")


# Un id di richiesta finisce in un header di risposta, quindi non può
# contenere quello che gli pare: un `\r\n` in mezzo spezzerebbe la risposta in
# due (header injection). Passa solo ciò che un identificativo può essere.
_ID_PULITO = re.compile(r"[^A-Za-z0-9._-]")


class RegistroAccessi:
    """Una riga per richiesta servita.

    Sta come middleware, cioè fuori dai singoli endpoint, perché un registro
    che dipende dal fatto che ogni endpoint si ricordi di scrivere la sua riga
    è un registro con dei buchi — e i buchi cadono sempre sugli endpoint
    aggiunti in fretta, che sono anche quelli meno guardati.

    **Middleware ASGI e non `BaseHTTPMiddleware`**, che sarebbe stato più
    corto da scrivere. Il motivo è tutto il valore di questo file:
    `BaseHTTPMiddleware` esegue l'applicazione in un task separato, e le
    `ContextVar` impostate là dentro non tornano indietro. Cioè l'`attore`,
    che le dipendenze di autenticazione scrivono mentre servono la richiesta,
    qui sarebbe sempre `anonimo` — e un registro accessi che non sa dire *chi*
    è un elenco di URL, non una traccia. Con un middleware ASGI l'applicazione
    gira nello stesso task e il valore si vede.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in NON_REGISTRATE:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        percorso = scope.get("path", "")
        metodo = scope.get("method", "?")

        # Un id per richiesta, per cucire insieme le righe che ne parlano.
        # Se il proxy ne ha già messo uno si tiene quello, così la traccia non
        # si spezza al confine — ripulito e troncato, perché è un valore che
        # arriva da fuori.
        arrivato = request.headers.get("x-request-id") or ""
        identificativo = _ID_PULITO.sub("", arrivato)[:32] or uuid.uuid4().hex

        segno_id = id_richiesta.set(identificativo)
        segno_attore = attore.set("anonimo")
        inizio = time.perf_counter()
        stato = {"codice": 500}

        async def invia(messaggio):
            if messaggio["type"] == "http.response.start":
                stato["codice"] = messaggio["status"]
                intestazioni = list(messaggio.get("headers", []))
                intestazioni.append((b"x-request-id", identificativo.encode()))
                messaggio = {**messaggio, "headers": intestazioni}
            await send(messaggio)

        try:
            try:
                await self.app(scope, receive, invia)
            except Exception:
                # Il gestore globale in main.py risponde 500 al chiamante; qui
                # resta la traccia che *quella* richiesta è quella esplosa.
                # Prima non c'era: senza Sentry configurato un 500 non lasciava
                # niente dietro di sé.
                accessi.exception(
                    "richiesta interrotta da un errore",
                    extra={
                        "metodo": metodo,
                        "percorso": percorso,
                        "ip": _ip(request),
                        "stato": 500,
                        "durata_ms": round((time.perf_counter() - inizio) * 1000, 1),
                    },
                )
                raise

            accessi.log(
                # Un 500 è un guasto, un 4xx è qualcuno a cui è stato detto di
                # no: il primo va guardato, il secondo va contato. Il resto è
                # traffico.
                logging.ERROR if stato["codice"] >= 500
                else logging.WARNING if stato["codice"] >= 400
                else logging.INFO,
                "richiesta servita",
                extra={
                    "metodo": metodo,
                    # Senza query string di proposito: i token di reset e i
                    # parametri di ricerca ci passano dentro, e un log non è il
                    # posto dove archiviarli.
                    "percorso": percorso,
                    "stato": stato["codice"],
                    "durata_ms": round((time.perf_counter() - inizio) * 1000, 1),
                    "ip": _ip(request),
                },
            )
        finally:
            # Dopo la riga del registro, non prima: scritta a contesto già
            # azzerato uscirebbe senza id di richiesta e senza attore, cioè
            # senza le due sole cose per cui il registro esiste.
            id_richiesta.reset(segno_id)
            _ripristina(segno_attore)


def _ripristina(segno) -> None:
    """`attore` viene impostato dentro le dipendenze di autenticazione. Se per
    qualsiasi motivo quel `set` è avvenuto in un contesto diverso da questo,
    `reset` solleva `ValueError` — e un log non deve mai far fallire la
    richiesta che sta descrivendo."""
    try:
        attore.reset(segno)
    except ValueError:
        attore.set("anonimo")


def _ip(request: Request) -> str:
    """Chi ha chiamato, con la stessa lettura usata dai limiti di frequenza.

    Riusa `client_ip` invece di rifare il ragionamento: quella funzione porta
    dietro la correzione su `X-Forwarded-For` costata un rilascio (Railway
    accoda un nodo interno che cambia a ogni richiesta), e due letture diverse
    dello stesso header vorrebbero dire che il log dice un indirizzo e il
    blocco ne conta un altro.
    """
    from app.rate_limit import client_ip

    try:
        return client_ip(request)
    except Exception:
        return "sconosciuto"


def ip_di(request: Optional[Request]) -> str:
    return _ip(request) if request is not None else "sconosciuto"
