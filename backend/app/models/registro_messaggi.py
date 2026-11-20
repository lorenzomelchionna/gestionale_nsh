"""Ogni messaggio partito verso una cliente o lo staff, email o WhatsApp.

Prende il posto di `communications` (2026-11-20), una tabella dello schema
iniziale che nessun codice aveva mai riempito.

Si scrive in tre punti soli — `whatsapp._invia`, `chat._dispatch_whatsapp`,
`email.send_email` — cioè dove il messaggio parte davvero, così un tipo di
invio aggiunto domani finisce nel registro senza che nessuno se lo ricordi.
Chi chiama dice soltanto **che cosa** sta mandando (`services.registro.invio`).

Il testo si salva solo per i tipi in `TIPI_CON_TESTO`: i codici di verifica, i
link di reset e i codici dei buoni regalo sono chiavi d'accesso, e un
registro che li conserva diventerebbe il posto da cui rubarle.

Si cancella da solo dopo `CONSERVAZIONE_GIORNI` (decisione di Lorenzo, 6 mesi):
sono dati personali di tutte le clienti.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RegistroMessaggio(Base):
    __tablename__ = "registro_messaggi"

    id: Mapped[int] = mapped_column(primary_key=True)
    creato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # «email» o «whatsapp».
    canale: Mapped[str] = mapped_column(String(16), nullable=False)
    # Cosa era: `conferma`, `promemoria`, `codice_verifica`, `risposta_chat`…
    # (`services.registro.TIPI`). `altro` per un invio che non l'ha detto.
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    # Indirizzo email o numero in E.164: chi l'ha ricevuto, anche quando non
    # corrisponde a nessuna scheda (lo staff, un ospite senza account).
    destinatario: Mapped[str] = mapped_column(String(255), nullable=False)
    client_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True
    )
    oggetto: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    testo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # WhatsApp: `template` o `testo_libero` — cambia quanto costa.
    formato: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # `inviato`, poi per WhatsApp `consegnato` / `letto` / `non_consegnato`
    # quando Twilio lo comunica; `errore` se non è partito proprio.
    stato: Mapped[str] = mapped_column(String(20), nullable=False)
    errore: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # SID Twilio o messageId Brevo: è la chiave con cui arriva lo stato.
    id_fornitore: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    stato_aggiornato_il: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    client: Mapped[Optional["Client"]] = relationship("Client", back_populates="messaggi")

    __table_args__ = (
        Index("ix_registro_messaggi_creato_il", "creato_il"),
        Index("ix_registro_messaggi_client_id", "client_id"),
        Index("ix_registro_messaggi_id_fornitore", "id_fornitore"),
    )
