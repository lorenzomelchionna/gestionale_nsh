"""Vendere prodotti: scalarli dal magazzino con un movimento «vendita».

Due strade arrivano qui, con le stesse regole: l'«Incassa» di una visita
(richiesta del 2026-10-08) e la Cassa, per chi entra solo a comprare
(2026-10-09). L'incasso resta di chi chiama — a una visita va un pagamento
a parte, in Cassa è il pagamento che si sta registrando — ma giacenza,
movimenti e controlli stanno in un posto solo, così le due strade non
possono divergere.
"""
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import MovementType, Product, ProductMovement
from app.schemas.product import ProdottoVenduto


def righe_sommate(righe: Iterable[ProdottoVenduto]) -> dict[int, tuple[int, float]]:
    """`product_id → (quantità, prezzo unitario)`.

    Due righe dello stesso prodotto sono una riga sola: il controllo della
    giacenza va fatto sul totale, non su ciascuna metà. Vale il prezzo della
    prima riga.
    """
    out: dict[int, tuple[int, float]] = {}
    for r in righe:
        q, prezzo = out.get(r.product_id, (0, r.unit_price))
        out[r.product_id] = (q + r.quantity, prezzo)
    return out


def totale_righe(righe: Iterable[ProdottoVenduto]) -> float:
    return round(sum(q * prezzo for q, prezzo in righe_sommate(righe).values()), 2)


async def scala_venduti(
    db: AsyncSession,
    righe: list[ProdottoVenduto],
    *,
    appointment_id: Optional[int],
    nota: str,
) -> tuple[float, str]:
    """Scala i prodotti e registra i movimenti; restituisce totale e descrizione.

    La giacenza blocca, per scelta del salone (2026-10-08): più di quanti ne
    risultano non se ne vendono — 409 col nome del prodotto. Se il conto non
    torna si corregge prima con un carico; un magazzino che va sotto zero
    smette di dire qualcosa. Chi chiama sta dentro la transazione della
    richiesta, quindi un rifiuto annulla anche il resto (l'incasso).
    """
    righe_ok = righe_sommate(righe)
    # Bloccati in ordine di id: due vendite insieme sullo stesso shampoo
    # leggerebbero entrambe «2 pz» e li venderebbero entrambe. L'ordine fisso
    # evita lo stallo fra due vendite che si contendono gli stessi prodotti.
    prodotti = {
        p.id: p for p in (await db.execute(
            select(Product).where(Product.id.in_(righe_ok)).order_by(Product.id).with_for_update()
        )).scalars()
    }
    totale = 0.0
    descrizione = []
    for product_id, (quantita, prezzo) in righe_ok.items():
        p = prodotti.get(product_id)
        if p is None or not p.is_active:
            raise HTTPException(status_code=400, detail="Prodotto non disponibile per la vendita")
        if p.quantity < quantita:
            raise HTTPException(
                status_code=409,
                detail=f"Quantità insufficiente: {p.name} — a magazzino {p.quantity}, richiesti {quantita}.",
            )
        p.quantity -= quantita
        db.add(ProductMovement(
            product_id=p.id, type=MovementType.sale, quantity=quantita,
            appointment_id=appointment_id, notes=nota,
        ))
        totale += quantita * prezzo
        descrizione.append(f"{quantita}× {p.name}")
    return round(totale, 2), ", ".join(descrizione)
