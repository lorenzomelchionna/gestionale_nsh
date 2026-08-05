"""Unire due schede che sono la stessa persona.

I duplicati nascono da due strade, e nessuna delle due è un errore da
correggere altrove.

La prima è il salone: `POST /api/admin/clients` non controlla se email o
telefono esistono già, quindi chi digita due volte la stessa cliente ottiene
due righe. Mettere un vincolo di unicità non risolverebbe — due sorelle
possono condividere un numero di casa, e rifiutare la seconda vorrebbe dire
impedire una cosa legittima per prevenirne una probabile.

La seconda è la registrazione online, ed è deliberata: `_adopt_salon_record`
collega un account alla scheda del salone solo se l'indirizzo coincide
**esattamente, maiuscole comprese**. `Mario.Rossi@…` contro `mario.rossi@…`
restano due righe. È la scelta prudente — un collegamento sbagliato consegna
a qualcuno lo storico di un'altra persona — e questo modulo è il suo
contrappeso: ciò che il codice non osa dedurre, lo decide una persona che
conosce le clienti.

**Chi sopravvive lo sceglie l'admin, non un'euristica.** Si potrebbe
immaginare «vince la più vecchia» o «vince quella con più appuntamenti», e
sarebbero entrambe ragionevoli e ogni tanto sbagliate. Siccome l'operazione
non si annulla, la scheda che resta è quella indicata nell'URL: il codice
esegue, non indovina.

Cosa rende questa fusione più delicata di un `UPDATE`: le sei tabelle che
puntano a `clients.id` si comportano in tre modi diversi, e due possono far
sparire dei dati se le si tocca nell'ordine sbagliato.

    appointments          RESTRICT, NOT NULL   blocca la cancellazione finché puntano qui
    waitlist_entries      CASCADE,  NOT NULL   sparisce con la scheda: va spostata PRIMA
    payments              SET NULL             diventerebbe un incasso senza cliente
    communications        SET NULL             storico invii orfano
    conversations         SET NULL             la chat WhatsApp si stacca
    gift_cards            SET NULL             si perde chi ha comprato il buono

Per questo qui non si cancella niente: la scheda di partenza viene svuotata
dei suoi collegamenti e poi **disattivata**, come fa già `DELETE
/api/admin/clients`. La riga resta, con una nota che dice dove è finita. Non
rende la fusione reversibile — i collegamenti si sono spostati — ma lascia
scritto che quella persona esisteva ed è diventata un'altra riga, che è
l'unica cosa che dopo serve davvero.
"""
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment
from app.models.chat import Conversation
from app.models.client import Client
from app.models.communication import Communication
from app.models.gift_card import GiftCard
from app.models.payment import Payment
from app.models.waitlist import WaitlistEntry


class MergeRefused(Exception):
    """La fusione non si può fare, con un motivo da mostrare a chi l'ha chiesta."""


# Le tabelle da spostare, con la colonna che punta al cliente. `waitlist` è in
# cima non per ordine alfabetico: è l'unica in `CASCADE`, quindi se la scheda
# sparisse prima che le sue righe siano state spostate, sparirebbero con lei.
TABELLE = (
    ("waitlist_entries", WaitlistEntry, WaitlistEntry.client_id),
    ("appointments", Appointment, Appointment.client_id),
    ("payments", Payment, Payment.client_id),
    ("communications", Communication, Communication.client_id),
    ("conversations", Conversation, Conversation.client_id),
    ("gift_cards", GiftCard, GiftCard.purchaser_client_id),
)


@dataclass
class Anteprima:
    """Cosa succederebbe, senza che succeda.

    Esiste perché l'operazione non si annulla: chi la conferma deve poter
    vedere quanti appuntamenti e quanti incassi sta spostando, e su quale
    delle due schede. Un pulsante «unisci» senza questo è un pulsante che si
    preme e si spera.
    """
    origine: Client
    destinazione: Client
    conteggi: dict[str, int] = field(default_factory=dict)
    campi_riempiti: list[str] = field(default_factory=list)
    note_unite: bool = False
    account_spostato: bool = False

    @property
    def righe_totali(self) -> int:
        return sum(self.conteggi.values())


async def _carica(db: AsyncSession, client_id: int, blocca: bool) -> Client:
    q = select(Client).where(Client.id == client_id)
    if blocca:
        # `FOR UPDATE`: fra il conteggio e lo spostamento nessun altro deve
        # poter aggiungere un appuntamento alla scheda che sta per sparire,
        # altrimenti quello resterebbe attaccato a una riga disattivata e
        # invisibile.
        q = q.with_for_update()
    riga = (await db.execute(q)).scalar_one_or_none()
    if riga is None:
        raise MergeRefused(f"Scheda {client_id} non trovata.")
    return riga


def _controlla(origine: Client, destinazione: Client) -> None:
    if origine.id == destinazione.id:
        raise MergeRefused("Le due schede sono la stessa.")

    if origine.account_id is not None and destinazione.account_id is not None:
        # Due account del portale vuol dire due persone che entrano con due
        # password diverse. Unirle ne chiuderebbe fuori una dai propri
        # appuntamenti senza dirglielo, e non è una cosa che questo endpoint
        # può decidere: prima va stabilito quale dei due account è quello
        # buono, e quello è un discorso con la cliente, non con il database.
        raise MergeRefused(
            "Entrambe le schede hanno un account del portale. "
            "Vanno unite solo dopo aver deciso quale account resta attivo."
        )


def _unisci_campi(
    origine: Client, destinazione: Client, esito: Anteprima, *, applica: bool
) -> None:
    """Riempie i buchi della destinazione con quello che sa l'origine.

    Una funzione sola con `applica`, e non una che assegna più una gemella che
    finge: sarebbero due copie delle stesse regole, e due copie divergono. Il
    giorno che qualcuno aggiungesse un campo a una sola delle due, l'anteprima
    mostrerebbe una cosa e la fusione ne farebbe un'altra — su un'operazione
    che non si annulla è il modo peggiore di sbagliare.

    Solo i buchi: un valore già presente sulla scheda che resta non viene mai
    sovrascritto. Il caso tipico è la scheda del salone, compilata a mano e
    completa, contro quella nata da una registrazione online che ha il
    telefono ma non la data di nascita.
    """
    for campo in ("phone", "email", "birth_date"):
        if not getattr(destinazione, campo) and getattr(origine, campo):
            esito.campi_riempiti.append(campo)
            if applica:
                setattr(destinazione, campo, getattr(origine, campo))

    # Le note si concatenano invece di sceglierne una. Sono testo libero
    # scritto dal salone — allergie, preferenze, «non usare il phon caldo» —
    # e scartarne metà vuol dire perdere sapere che non sta scritto altrove.
    if origine.notes and origine.notes.strip():
        gia_presente = bool(destinazione.notes and destinazione.notes.strip())
        if not gia_presente:
            esito.note_unite = True
            if applica:
                destinazione.notes = origine.notes
        elif origine.notes.strip() not in destinazione.notes:
            esito.note_unite = True
            if applica:
                destinazione.notes = (
                    f"{destinazione.notes.rstrip()}\n{origine.notes.strip()}"
                )

    if destinazione.account_id is None and origine.account_id is not None:
        esito.account_spostato = True
        if applica:
            destinazione.account_id = origine.account_id
            origine.account_id = None


async def prepara(db: AsyncSession, id_destinazione: int, id_origine: int) -> Anteprima:
    """Cosa comporterebbe la fusione. Non tocca niente."""
    destinazione = await _carica(db, id_destinazione, blocca=False)
    origine = await _carica(db, id_origine, blocca=False)
    _controlla(origine, destinazione)

    anteprima = Anteprima(origine=origine, destinazione=destinazione)
    for nome, modello, colonna in TABELLE:
        quante = (await db.execute(
            select(func.count()).select_from(modello).where(colonna == origine.id)
        )).scalar_one()
        anteprima.conteggi[nome] = quante

    _unisci_campi(origine, destinazione, anteprima, applica=False)
    return anteprima


async def esegui(db: AsyncSession, id_destinazione: int, id_origine: int) -> Anteprima:
    """Sposta tutto sulla destinazione e disattiva l'origine.

    Chiamata dentro la transazione della richiesta: o si sposta tutto, o non
    si sposta niente. Una fusione a metà lascerebbe gli appuntamenti su una
    scheda e gli incassi su un'altra, che è peggio del duplicato di partenza.
    """
    destinazione = await _carica(db, id_destinazione, blocca=True)
    origine = await _carica(db, id_origine, blocca=True)
    _controlla(origine, destinazione)

    esito = Anteprima(origine=origine, destinazione=destinazione)

    for nome, modello, colonna in TABELLE:
        risultato = await db.execute(
            update(modello)
            .where(colonna == origine.id)
            .values({colonna.key: destinazione.id})
        )
        esito.conteggi[nome] = risultato.rowcount or 0

    _unisci_campi(origine, destinazione, esito, applica=True)

    # Disattivata, non cancellata — come fa già `DELETE /api/admin/clients`.
    # La riga resta a dire che quella persona era stata registrata due volte,
    # e la nota dice dove è finita: senza, fra un anno una scheda vuota e
    # inattiva non si distingue da un errore di inserimento.
    origine.is_active = False
    traccia = f"[unita nella scheda #{destinazione.id}]"
    origine.notes = f"{origine.notes.rstrip()}\n{traccia}" if origine.notes else traccia

    await db.flush()
    return esito
