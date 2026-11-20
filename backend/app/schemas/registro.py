from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class VoceRegistro(BaseModel):
    """Una riga del registro dei messaggi, come la legge la pagina."""
    id: int
    creato_il: datetime
    canale: str
    tipo: str
    tipo_etichetta: str
    destinatario: str
    client_id: Optional[int] = None
    cliente_nome: Optional[str] = None
    appointment_id: Optional[int] = None
    oggetto: Optional[str] = None
    testo: Optional[str] = None
    formato: Optional[str] = None
    stato: str
    errore: Optional[str] = None
    stato_aggiornato_il: Optional[datetime] = None
