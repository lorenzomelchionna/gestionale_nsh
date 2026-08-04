from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
from app.models.appointment import AppointmentStatus, AppointmentOrigin


class AppointmentServiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    service_id: int
    price_snapshot: float


class AppointmentBase(BaseModel):
    client_id: int
    collaborator_id: int
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = None


class AppointmentCreate(AppointmentBase):
    service_ids: List[int]
    origin: AppointmentOrigin = AppointmentOrigin.salon


class AppointmentUpdate(BaseModel):
    collaborator_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    notes: Optional[str] = None
    visit_notes: Optional[str] = None
    service_ids: Optional[List[int]] = None


class AppointmentComplete(BaseModel):
    """Corpo facoltativo di `POST /appointments/{id}/complete`.

    La nota di visita si scrive qui perché è qui che si sa cosa scrivere: il
    colore usato, la reazione del capello, cosa rifare la volta dopo. Il campo
    esisteva da sempre nel modello e nessuna schermata lo riempiva, quindi il
    salone segnava tutto in `Client.notes` — dove la nota di oggi cancella
    quella di tre mesi fa.
    """

    visit_notes: Optional[str] = None


class AppointmentReject(BaseModel):
    reason: Optional[str] = None


class AppointmentReschedule(BaseModel):
    alternative_time: datetime


class AppointmentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    client_id: int
    collaborator_id: int
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus
    origin: AppointmentOrigin
    notes: Optional[str] = None
    visit_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    alternative_time: Optional[datetime] = None
    reminder_sent: bool
    created_at: datetime
    appointment_services: List[AppointmentServiceOut] = []


class AppointmentOutWithNames(AppointmentOut):
    """An appointment with the names and the total the caller would otherwise
    have to fetch one by one.

    Every field below defaults to empty, so an endpoint that builds this by
    hand and forgets one answers with a plausible-looking blank instead of
    failing — which is exactly how `service_names` went out empty from every
    route for as long as it existed. Build it with `from_appointment` and the
    rule stays in one place.
    """

    client_name: str = ""
    collaborator_name: str = ""
    service_names: List[str] = []
    total_price: float = 0.0

    @classmethod
    def from_appointment(cls, a) -> "AppointmentOutWithNames":
        """Project an ORM appointment, with `appointment_detail_loads()` applied
        to the query that fetched it."""
        out = cls.model_validate(a)
        out.client_name = f"{a.client.first_name} {a.client.last_name}" if a.client else ""
        out.collaborator_name = (
            f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
        )
        # Booked order, not alphabetical: "Taglio + barba" is how it was sold.
        out.service_names = [
            s.service.name for s in a.appointment_services if s.service is not None
        ]
        out.total_price = sum(s.price_snapshot for s in a.appointment_services)
        return out


class PortalAppointmentOut(BaseModel):
    """L'appuntamento come lo vede la cliente dal portale.

    Scritto come **elenco di campi permessi** e non come sottrazione da
    `AppointmentOutWithNames`, ed è la differenza che conta: così un campo
    nuovo sul modello non finisce nel portale per distrazione, ma solo se
    qualcuno lo aggiunge qui apposta.

    Due campi restano fuori e sono i due che il salone scrive per sé:

    - `visit_notes` — «colore 7.3, capello in difficoltà, la prossima volta
      niente decolorante». Finché nessuna schermata lo riempiva la fuga era
      teorica; da adesso che si scrive davvero, sarebbe la cliente a leggersi
      gli appunti interni del salone.
    - `notes` — la nota presa al momento della prenotazione, che dal
      calendario è il salone a scrivere.

    `rejection_reason` invece resta: è la spiegazione di un rifiuto, ed è
    scritta per essere letta da chi l'ha subito.
    """

    model_config = {"from_attributes": True}

    id: int
    # C'è perché è il suo: non rivela niente che la cliente non possieda già,
    # ed è il campo su cui `test_auth_boundaries` verifica che dal portale non
    # esca l'appuntamento di un'altra. Toglierlo non avrebbe chiuso niente,
    # avrebbe solo tolto la prova a un test di sicurezza.
    client_id: int
    collaborator_id: int
    start_time: datetime
    end_time: datetime
    status: AppointmentStatus
    origin: AppointmentOrigin
    rejection_reason: Optional[str] = None
    alternative_time: Optional[datetime] = None
    created_at: datetime

    collaborator_name: str = ""
    service_names: List[str] = []
    total_price: float = 0.0

    @classmethod
    def from_appointment(cls, a) -> "PortalAppointmentOut":
        out = cls.model_validate(a)
        out.collaborator_name = (
            f"{a.collaborator.first_name} {a.collaborator.last_name}" if a.collaborator else ""
        )
        out.service_names = [
            s.service.name for s in a.appointment_services if s.service is not None
        ]
        out.total_price = sum(s.price_snapshot for s in a.appointment_services)
        return out
