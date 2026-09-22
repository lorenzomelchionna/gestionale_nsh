"""
Il codice a sei cifre condiviso da email e WhatsApp.

Stessa lunghezza, stessa scadenza, stesso tetto ai tentativi — cambiano solo
il canale che lo consegna e le colonne che lo tengono a database
(`email_verification.py` legge/scrive `verification_*`,
`phone_verification.py` legge/scrive `phone_verification_*`, entrambe su
`ClientAccount`). Tenere qui la sola parte davvero identica evita che le due
copie prendano a divergere una spanna alla volta — un `CODE_TTL_MINUTES`
cambiato in un file e non nell'altro, per esempio, che il template WhatsApp
Authentication (`code_expiration_minutes`) non saprebbe più rispecchiare.

Il resto — `issue_code`/`check_code`/`VerificationError` — resta duplicato
apposta nei due moduli invece di essere generalizzato qui: i messaggi
d'errore sono diversi ("indirizzo" contro "numero"), e un'unica funzione
parametrizzata sui nomi dei campi (`getattr`/`setattr` con stringhe) si legge
peggio di due funzioni brevi ed esplicite.
"""
import secrets

CODE_LENGTH = 6
CODE_TTL_MINUTES = 15
# Six digits is a million possibilities; five tries keeps a blind guess at
# roughly one in two hundred thousand, and a wrong code is cheap to resend.
MAX_ATTEMPTS = 5


def generate_code() -> str:
    """A zero-padded numeric code, from a generator meant for secrets."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"
