"""
Accesso al portale creato dal salone, non dalla cliente.

Fino a qui un account esisteva solo se la cliente se lo faceva da sola:
registrazione, codice via email, verifica. Chi veniva iscritta al banco
restava una riga di anagrafica senza `account_id`, quindi senza modo di
entrare — e al banco è dove sta la maggior parte delle clienti di un salone.

**La password non è fissa.** Un valore uguale per tutte — `0000` e simili —
non è una password: è una porta aperta a chiunque conosca l'indirizzo email
di una cliente, che in un salone di quartiere è la cosa meno segreta che ci
sia. Ogni account nasce con la sua, casuale, mostrata una volta sola a chi
la sta creando.
"""
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client, ClientAccount
from app.models.user import User
from app.utils.auth import hash_password

# Stesso alfabeto dei codici gift card, per la stessa ragione: niente 0/O né
# 1/I/L, perché questa password viene **dettata al telefono o letta ad alta
# voce al banco**, e quelle coppie si sbagliano sempre. È una costante a sé e
# non un import da `gift_card`: sono due cose indipendenti che possono
# divergere, e legarle vorrebbe dire che cambiarne una cambia l'altra.
ALFABETO = "ACDEFGHJKMNPQRTUVWXY2346789"
GRUPPI = 3
LUNGHEZZA_GRUPPO = 4


class PortalAccountRefused(Exception):
    """Motivo per cui l'accesso non si può creare, in italiano, per l'operatore."""


@dataclass
class AccountCreato:
    account: ClientAccount
    password_temporanea: str


def genera_password() -> str:
    """Una password tipo `A7K2-9QX4-MT3F`.

    Dodici caratteri su un alfabeto di 27 sono circa 57 bit: fuori portata per
    chi tenta a indovinare, e comunque il login è a 10 tentativi al minuto.

    I trattini fanno parte della password e vanno digitati. Costano un carattere
    in più da battere e in cambio rendono leggibile una stringa che qualcuno
    deve ricopiare da un foglietto — che è il modo in cui questa password
    viaggia davvero.
    """
    gruppi = [
        "".join(secrets.choice(ALFABETO) for _ in range(LUNGHEZZA_GRUPPO))
        for _ in range(GRUPPI)
    ]
    return "-".join(gruppi)


async def crea(db: AsyncSession, client_id: int) -> AccountCreato:
    """Crea l'accesso al portale per una cliente già in anagrafica.

    Solleva `PortalAccountRefused` con un messaggio leggibile su ogni caso in
    cui l'account non si può creare, invece di crearne uno inutilizzabile.
    """
    client = (await db.execute(
        select(Client).where(Client.id == client_id)
    )).scalar_one_or_none()
    if client is None:
        raise LookupError("Cliente non trovato")

    if client.account_id is not None:
        raise PortalAccountRefused(
            "Questa cliente ha già un accesso al portale. Per darle una password "
            "nuova usa «Password portale»."
        )

    if not client.email:
        raise PortalAccountRefused(
            "Serve un indirizzo email sulla scheda: è quello con cui la cliente "
            "entra nel portale."
        )

    # Staff e clienti entrano dalla stessa schermata, che cerca prima fra lo
    # staff. Due account sullo stesso indirizzo vorrebbe dire che il login deve
    # indovinare quale intendevi — quindi non si crea proprio.
    staff = (await db.execute(
        select(User).where(User.email == client.email)
    )).scalar_one_or_none()
    if staff is not None:
        raise PortalAccountRefused(
            "Questo indirizzo è già usato da un accesso dello staff. "
            "Serve un'email diversa per l'accesso cliente."
        )

    esistente = (await db.execute(
        select(ClientAccount).where(ClientAccount.email == client.email)
    )).scalar_one_or_none()
    if esistente is not None:
        # Anche se non è verificato. `register` in quel caso lo sovrascrive, e
        # lì è giusto: un account non verificato non prova niente su chi possiede
        # l'indirizzo, quindi non può tenerlo in ostaggio. Qui no, perché a
        # quell'account può essere già appesa una scheda cliente creata dalla
        # registrazione: assorbirla in silenzio sposterebbe dati fra due persone
        # che il salone non ha confrontato. Il messaggio dice cosa fare.
        raise PortalAccountRefused(
            "Esiste già un account con questo indirizzo. Se è una registrazione "
            "lasciata a metà, falla completare dal portale e poi unisci le due "
            "schede; altrimenti usa un altro indirizzo."
        )

    password = genera_password()
    account = ClientAccount(
        email=client.email,
        password_hash=await hash_password(password),
        # **Verificato in partenza, e questa è la decisione che conta.**
        #
        # Senza, il login rifiuta l'account e la password appena consegnata non
        # apre niente: la verifica per email esiste per dimostrare che
        # l'indirizzo è di chi lo ha digitato, e qui a digitarlo è il salone con
        # la cliente davanti. È la stessa fiducia su cui poggiano già gli
        # accessi dello staff, che di verifica email non ne hanno affatto.
        #
        # Il prezzo: un indirizzo sbagliato di battitura diventa un account
        # funzionante intestato a un estraneo, che con «password dimenticata»
        # potrebbe entrarci. Vale la pena rileggere l'email ad alta voce prima
        # di premere il pulsante — la schermata lo ricorda.
        email_verified=True,
    )
    db.add(account)
    await db.flush()

    client.account_id = account.id
    await db.flush()

    return AccountCreato(account=account, password_temporanea=password)
