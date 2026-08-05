"""L'impianto dei log: dove vanno, che forma hanno, cosa non devono contenere.

Fino a oggi `backend/app/` non aveva una sola riga di logging. Le uniche tracce
erano una ventina di `print()` sparsi nelle notifiche, che finiscono sì nello
stdout di Railway ma senza livello, senza data, senza modo di dire a quale
richiesta appartengano. Tutto il resto era silenzio: un 500 spariva senza
lasciare niente, un login sbagliato non si distingueva da uno riuscito, e un
accesso con un token rubato non si distingueva da nessun'altra cosa.

Perché è un problema di sicurezza e non di comodità: l'art. 33 GDPR chiede di
notificare una violazione entro 72 ore **dicendo quali dati sono stati
toccati**. Senza log quella frase non si può scrivere. Non "è difficile":
proprio non ci sono i dati per scriverla, e in un gestionale di salone i dati
in questione sono nomi, telefoni, date di nascita e note sulle clienti.

Tre scelte che vale la pena spiegare.

**Su stdout, non su file.** Railway raccoglie lo stdout del processo; un file
dentro il container sparirebbe al prossimo deploy, che qui capita a ogni push.

**JSON in produzione, testo in sviluppo.** In produzione i log si filtrano
(«tutte le richieste di quell'account quel giorno»), e filtrare del testo
libero significa scrivere regex. In locale invece si leggono con gli occhi.

**Cosa non ci finisce dentro.** Un log di sicurezza è a sua volta un archivio
di dati personali: scritto male raddoppia il problema invece di risolverlo, e
un log che copia le password in chiaro è una violazione in sé. Qui gli
indirizzi email vengono mascherati e i campi che sanno di segreto vengono
sostituiti *dal filtro*, non dalla buona volontà di chi scrive la chiamata —
perché la buona volontà regge finché qualcuno non aggiunge in fretta un
`logger.info(f"payload={payload}")`.
"""
import json
import logging
import re
import sys
from contextvars import ContextVar
from typing import Any

from app.config import settings

# ── Correlazione ──────────────────────────────────────────────────────
#
# Un log utile non è un elenco di righe, è la possibilità di prendere una
# richiesta e vedere tutto quello che ha fatto. Queste due variabili di
# contesto viaggiano con la richiesta — anche attraverso gli `await`, che è il
# motivo per cui sono `ContextVar` e non variabili globali — e finiscono in
# ogni riga scritta mentre quella richiesta è in corso.

id_richiesta: ContextVar[str] = ContextVar("id_richiesta", default="-")

# Chi sta chiamando, quando è noto: `admin:3`, `client:41`, `anonimo`. È il
# campo che dopo un furto di credenziali permette di rispondere alla domanda
# vera, cioè non «qualcuno è entrato» ma «ha guardato le schede di chi».
attore: ContextVar[str] = ContextVar("attore", default="anonimo")


# ── Riduzione del danno ───────────────────────────────────────────────

# I nomi di campo che non vengono mai scritti, qualunque sia il valore.
# Confronto per sottostringa sul nome in minuscolo, così `new_password`,
# `password_hash` e `reset_token` ricadono tutti qui senza doverli elencare.
#
# `code` c'è perché il codice di verifica via email è a tutti gli effetti una
# credenziale. Ha però un costo da conoscere: un campo chiamato `status_code`
# verrebbe oscurato anche lui. Per questo i campi di questo modulo si chiamano
# `stato` e non `status_code` — la regola per chi aggiunge log è che il nome
# non contenga le parole qui sotto se il valore non è un segreto.
CAMPI_SEGRETI = (
    "password", "token", "secret", "api_key", "apikey", "authorization",
    "hash", "credential", "cookie", "otp", "codice", "code",
)

SOSTITUTO = "«omesso»"

# Rete di sicurezza sul testo del messaggio, per quello che sfugge ai campi:
# un JWT (tre blocchi base64 separati da punti) e un header Bearer.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]+")
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+")


def maschera_email(indirizzo: str | None) -> str:
    """`mario.rossi@gmail.com` → `m***i@gmail.com`.

    L'indirizzo per intero non serve e costa: serve riconoscere *quale*
    account, e per quello basta questo. Il caso che rende la maschera
    obbligatoria è il login fallito — lì l'indirizzo digitato può essere di
    una persona che con questo salone non c'entra niente, e scriverlo per
    esteso vorrebbe dire raccogliere dati di terzi in un file di log.

    Un dominio invece resta in chiaro: non identifica nessuno e distinguere
    `@gmail.com` da un dominio mai visto è utile quando si guarda una raffica
    di tentativi.
    """
    if not indirizzo or "@" not in indirizzo:
        return SOSTITUTO
    locale, _, dominio = indirizzo.partition("@")
    if len(locale) <= 2:
        return f"{locale[:1]}***@{dominio}"
    return f"{locale[0]}***{locale[-1]}@{dominio}"


def maschera_telefono(numero: str | None) -> str:
    """`+393331234567` → `+39***4567`.

    Le ultime quattro cifre bastano a farsi dire da chi chiama «sì, è il mio
    numero», che è l'unica cosa per cui serve in un log. Il prefisso resta
    perché distinguere un numero italiano da uno che non lo è vale qualcosa
    quando si guarda del traffico che non torna.
    """
    if not numero:
        return SOSTITUTO
    cifre = "".join(c for c in numero if c.isdigit())
    if len(cifre) < 4:
        return SOSTITUTO
    prefisso = "+" if numero.strip().startswith("+") else ""
    return f"{prefisso}{cifre[:2]}***{cifre[-4:]}"


def _ripulisci(valore: Any) -> Any:
    if isinstance(valore, str):
        valore = _JWT.sub(SOSTITUTO, valore)
        valore = _BEARER.sub(SOSTITUTO, valore)
    return valore


class FiltroSegreti(logging.Filter):
    """Toglie dai log quello che non deve uscirne.

    Sta come filtro e non come regola di stile perché una regola di stile la
    si dimentica. Qui invece qualunque riga passa di qui, comprese quelle che
    scriverà qualcuno fra un anno senza aver letto questo file.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for nome, valore in list(record.__dict__.items()):
            if any(s in nome.lower() for s in CAMPI_SEGRETI):
                record.__dict__[nome] = SOSTITUTO
            else:
                record.__dict__[nome] = _ripulisci(valore)

        if isinstance(record.msg, str):
            record.msg = _ripulisci(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _ripulisci(v) for k, v in record.args.items()}
            else:
                record.args = tuple(_ripulisci(a) for a in record.args)
        return True


class ContestoRichiesta(logging.Filter):
    """Appiccica id di richiesta e attore a ogni riga."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "richiesta"):
            record.richiesta = id_richiesta.get()
        if not hasattr(record, "attore"):
            record.attore = attore.get()
        return True


# Gli attributi che `LogRecord` ha sempre: tutto ciò che *non* è in questo
# elenco è un campo aggiunto da chi ha scritto la chiamata, e va nel JSON.
_STANDARD = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message", "asctime", "taskName",
}


class FormatoJson(logging.Formatter):
    """Una riga = un oggetto JSON. Per i log di produzione."""

    def format(self, record: logging.LogRecord) -> str:
        riga: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "livello": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "richiesta": getattr(record, "richiesta", "-"),
            "attore": getattr(record, "attore", "anonimo"),
        }
        for nome, valore in record.__dict__.items():
            if nome in _STANDARD or nome in riga or nome.startswith("_"):
                continue
            riga[nome] = valore
        if record.exc_info:
            riga["eccezione"] = self.formatException(record.exc_info)
        # `default=str` perché un `Decimal` o una `date` finiti in un campo non
        # devono far esplodere il logging: un log che solleva è peggio di un
        # log impreciso.
        return json.dumps(riga, ensure_ascii=False, default=str)


class FormatoLeggibile(logging.Formatter):
    """Per lo sviluppo: la stessa roba, ma da leggere con gli occhi."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s [%(richiesta)s %(attore)s] %(message)s",
                         datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extra = {
            n: v for n, v in record.__dict__.items()
            if n not in _STANDARD and n not in ("richiesta", "attore") and not n.startswith("_")
        }
        return f"{base} {extra}" if extra else base


def setup_logging() -> None:
    """Da chiamare una volta all'avvio, prima di servire richieste.

    Riconfigura il logger radice invece di aggiungersi: uvicorn ne installa uno
    suo, e senza `handlers.clear()` ogni riga uscirebbe due volte.
    """
    livello = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        FormatoLeggibile() if settings.APP_ENV == "development" else FormatoJson()
    )
    handler.addFilter(ContestoRichiesta())
    # L'ordine conta: il filtro dei segreti è l'ultimo aggiunto, quindi
    # l'ultimo a passare sul record prima che il formatter lo scriva.
    handler.addFilter(FiltroSegreti())

    radice = logging.getLogger()
    radice.handlers.clear()
    radice.addHandler(handler)
    radice.setLevel(livello)

    # uvicorn tiene un suo access log, con lo stesso contenuto del nostro ma
    # senza attore né id di richiesta. Due righe per richiesta, di cui una
    # meno utile, è solo rumore che rende più caro cercare.
    logging.getLogger("uvicorn.access").disabled = True
    for rumoroso in ("uvicorn.error", "sqlalchemy.engine", "multipart", "httpx"):
        logging.getLogger(rumoroso).setLevel(max(livello, logging.WARNING))
