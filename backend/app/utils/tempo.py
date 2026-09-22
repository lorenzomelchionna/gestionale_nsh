"""
L'ora del salone e l'istante in cui accade.

Sono due cose diverse e il progetto le ha confuse a lungo. «Le nove» è un'ora
di orologio: sta negli orari di lavoro, nei permessi, nei testi dei messaggi.
L'istante in cui in salone sono le nove è un altro oggetto, e cambia due volte
l'anno perché l'Italia passa da UTC+1 a UTC+2.

Il database conserva **istanti** (`timestamptz`), che è la scelta giusta: un
istante è confrontabile con `now()`, ordinabile e non ambiguo. La conversione
fra le due forme deve avvenire ai confini, e questo modulo è quel confine.

Fino al 2026-09-17 la conversione non c'era proprio: `availability.py`
costruiva gli slot con `combine(data, ora, tzinfo=utc)` e i messaggi
formattavano `start_time` con `strftime` senza convertire. Così l'ora del
salone veniva scritta e riletta come se fosse UTC, e il risultato era che il
portale offriva orari spostati di due ore d'estate e che ogni email annunciava
alla cliente un orario due ore prima di quello in agenda.

**Nota sul cambio dell'ora.** `istante()` sulle ore ambigue (l'ultima domenica
di ottobre, quando le 02:30 esistono due volte) sceglie la prima occorrenza, e
su quelle inesistenti (l'ultima domenica di marzo) sposta in avanti. Non è una
scelta ponderata: è il comportamento di `zoneinfo`, e va bene perché quelle ore
cadono sempre a salone chiuso. Se un giorno il salone lavorasse di notte,
questo commento diventerebbe un bug.
"""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

#: Il fuso in cui vive il salone. Unica fonte: non leggere `TZ` dal processo,
#: che su Railway è UTC e sul Mac di chi sviluppa è Europe/Rome — due
#: comportamenti diversi per lo stesso codice.
SALONE = ZoneInfo("Europe/Rome")


def istante(giorno: date, ora: time) -> datetime:
    """L'istante reale in cui in salone, quel giorno, sono le `ora`.

    È la funzione da usare per trasformare un orario di lavoro, un permesso o
    uno slot in qualcosa che si possa salvare o confrontare con `adesso()`.
    """
    return datetime.combine(giorno, ora, tzinfo=SALONE).astimezone(timezone.utc)


def ora_salone(momento: datetime) -> datetime:
    """Lo stesso istante, letto con l'orologio appeso in salone.

    I valori senza fuso vengono considerati UTC, che è ciò che restituisce
    asyncpg per le colonne `timestamptz` e quindi il caso normale qui dentro.
    """
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(SALONE)


def minuti_salone(momento: datetime) -> int:
    """Minuti dalla mezzanotte del salone.

    È la griglia su cui ragiona il calcolo della disponibilità: orari di
    lavoro, permessi e appuntamenti devono finire tutti sulla stessa scala,
    altrimenti si confrontano numeri che misurano cose diverse.
    """
    locale = ora_salone(momento)
    return locale.hour * 60 + locale.minute


def adesso() -> datetime:
    """L'istante attuale. Esiste per non spargere `datetime.now(utc)` in giro
    e per avere un solo punto da sostituire nei test."""
    return datetime.now(timezone.utc)


def oggi_salone() -> date:
    """La data di oggi in salone.

    `date.today()` darebbe la data del processo: su Railway è UTC, quindi
    fra mezzanotte e le due di notte risponderebbe «ieri».
    """
    return ora_salone(adesso()).date()


def istante_da_ingresso(valore: datetime) -> datetime:
    """Un istante che arriva da fuori — un filtro di data scritto da un
    browser, un campo di un form — non da database.

    Qui la convenzione è l'opposto di `ora_salone()`: un valore senza fuso
    non è UTC, sono cifre di orologio del salone, perché chi le ha scritte
    lavora in un browser nel fuso di Roma. `AppointmentsPage.tsx`,
    `CalendarPage.tsx` e `CashPage.tsx` mandano `"2026-06-22T00:00:00"`
    intendendo mezzanotte a Roma; letto come UTC senza questa conversione
    diventa mezzanotte a Roma **meno l'offset**, e un filtro per «22 giugno»
    include ore della notte del 21 e perde le prime ore del 22.

    Con un fuso esplicito nel valore, si converte semplicemente in UTC — è
    lo stesso confine che `booking.py` attraversa già per `start_time`.
    """
    if valore.tzinfo is None:
        return istante(valore.date(), valore.time())
    return valore.astimezone(timezone.utc)


def colonna_ora_salone(colonna):
    """Una colonna `timestamptz` letta nel fuso del salone lato database,
    da usare dentro `func.date()` o `extract()` per raggruppare per giorno,
    mese o anno del salone — non per confrontare: quello resta un istante,
    va confrontato con un altro istante, non con questa espressione.

    `func.date(Payment.date)` e `extract('month', Payment.date)` truncano
    e affettano usando il `TimeZone` di **sessione** del database, che su
    Railway è UTC: un incasso delle 01:00 a Roma finiva raggruppato nel
    giorno prima. `AT TIME ZONE` converte l'istante in un orario locale
    esplicito prima del taglio, indipendente da quella variabile.
    """
    return colonna.op("AT TIME ZONE")(SALONE.key)
