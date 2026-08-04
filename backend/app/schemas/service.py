from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


def validate_processing(duration_slots: int, slots_before: int, processing: int) -> None:
    """Una posa deve stare dentro il servizio, con del lavoro prima e dopo.

    Senza lavoro prima non c'è niente da mettere in posa; senza lavoro dopo la
    posa è solo un appuntamento che finisce prima, e lasciarla passare
    segnerebbe libero l'ultimo slot mentre la cliente è ancora seduta.

    Fuori dagli schemi perché serve in due momenti diversi: alla creazione,
    dove i valori arrivano tutti insieme, e alla modifica, dove arrivano
    parziali e la regola va verificata sul risultato del merge.
    """
    if processing <= 0:
        return
    if slots_before < 1:
        raise ValueError(
            "Il tempo di posa non può iniziare subito: serve almeno mezz'ora "
            "di lavoro prima (applicazione)."
        )
    if slots_before + processing >= duration_slots:
        raise ValueError(
            "Dopo la posa deve restare del lavoro (lavaggio, piega): "
            "aumenta la durata totale o riduci la posa."
        )


class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    duration_slots: int = Field(default=1, ge=1)
    # Tempo di posa: vedi models/service.py. 0 = nessuna posa.
    processing_slots: int = Field(default=0, ge=0)
    slots_before_processing: int = Field(default=0, ge=0)
    category: str
    bookable_online: bool = True
    is_active: bool = True

    @model_validator(mode="after")
    def _posa_coerente(self):
        # Su ServiceUpdate `duration_slots` può essere None (modifica
        # parziale): lì il quadro completo ce l'ha solo l'endpoint, che
        # richiama `validate_processing` dopo aver applicato i campi.
        if self.duration_slots is None:
            return self
        validate_processing(
            self.duration_slots,
            self.slots_before_processing or 0,
            self.processing_slots or 0,
        )
        return self


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(ServiceBase):
    name: Optional[str] = None
    price: Optional[float] = None
    duration_slots: Optional[int] = Field(default=None, ge=1)
    category: Optional[str] = None


class ServiceOut(ServiceBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime
