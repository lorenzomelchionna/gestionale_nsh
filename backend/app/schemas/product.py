from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from app.models.product import MovementType


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    supplier: Optional[str] = None
    purchase_price: float
    sale_price: float
    category: str
    quantity: int = 0
    min_quantity: int = 2
    photo_url: Optional[str] = None
    is_active: bool = True


class ProductCreate(ProductBase):
    """I vincoli sui numeri stanno qui e **non** su `ProductBase`.

    `ProductOut` eredita da `ProductBase`, quindi un `ge=0` lì sarebbe un
    vincolo anche in lettura: se a database esistesse già una riga storta,
    a fallire non sarebbe la scrittura che la corregge — sarebbe l'elenco
    del magazzino, cioè la pagina da cui ci si accorge del problema.
    """

    purchase_price: float = Field(..., ge=0)
    sale_price: float = Field(..., ge=0)
    quantity: int = Field(0, ge=0)
    min_quantity: int = Field(0, ge=0)


class ProductUpdate(BaseModel):
    """Modifica di un prodotto già a magazzino.

    Scritto per esteso invece di ereditare da `ProductBase` per due motivi.

    `photo_url` non c'è: non è un dato che si scrive a mano, è il permalink
    del token dell'immagine, e ha già i suoi endpoint. Lasciarlo modificabile
    da qui vorrebbe dire poter far puntare la foto di un prodotto a un host
    qualsiasi, o romperla scrivendoci dentro un valore a caso.

    `quantity` non c'è: la giacenza si muove solo per carico, scarico o
    vendita, e ogni movimento lascia una riga in `product_movements`.
    Scriverla dritta da qui farebbe sparire i pezzi dal magazzino senza che
    nulla dica dove sono finiti.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    supplier: Optional[str] = None
    purchase_price: Optional[float] = Field(None, ge=0)
    sale_price: Optional[float] = Field(None, ge=0)
    category: Optional[str] = None
    min_quantity: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def no_null_su_campi_obbligatori(self):
        """`None` qui vuol dire due cose diverse a seconda della colonna.

        Su `description` e `supplier` significa «svuotalo», ed è legittimo.
        Sulle altre la colonna è NOT NULL: senza questo controllo il valore
        arriverebbe fino all'INSERT e tornerebbe un 500 dal database invece
        di un 422 che dice quale campo è sbagliato.
        """
        obbligatori = ("name", "purchase_price", "sale_price", "category",
                       "min_quantity", "is_active")
        vuoti = [c for c in obbligatori
                 if c in self.model_fields_set and getattr(self, c) is None]
        if vuoti:
            raise ValueError(f"Campi che non possono essere vuoti: {', '.join(vuoti)}")
        return self


class ProductOut(ProductBase):
    model_config = {"from_attributes": True}

    id: int
    created_at: datetime


class ProductMovementCreate(BaseModel):
    product_id: int
    type: MovementType
    quantity: int
    notes: Optional[str] = None
    appointment_id: Optional[int] = None


class ProductMovementOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_id: int
    type: MovementType
    quantity: int
    notes: Optional[str] = None
    appointment_id: Optional[int] = None
    created_at: datetime
