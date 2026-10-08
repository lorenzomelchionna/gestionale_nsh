import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Minus, Plus, X } from 'lucide-react'
import clsx from 'clsx'
import { getProducts } from '@/services/api'
import type { Product } from '@/types'

/** Una riga della vendita, come la si sta scrivendo: il prezzo resta testo
 *  finché non si incassa, così «15,5» si può digitare senza che l'input lo
 *  riformatti a metà. */
export interface RigaVendita {
  product: Product
  quantity: number
  price: string
}

export const prezzoRiga = (r: RigaVendita) => Number(r.price.replace(',', '.'))

/** Valida e sommabile: un prezzo che non è un numero o è negativo blocca
 *  l'incasso invece di diventare zero in silenzio. */
export const rigaValida = (r: RigaVendita) => {
  const p = prezzoRiga(r)
  return r.price.trim() !== '' && Number.isFinite(p) && p >= 0
    && r.quantity >= 1 && r.quantity <= r.product.quantity
}

export const totaleProdotti = (righe: RigaVendita[]) =>
  righe.reduce((s, r) => s + (rigaValida(r) ? r.quantity * prezzoRiga(r) : 0), 0)

/**
 * «Prodotti venduti» nell'incasso di una visita (richiesta del 2026-10-08):
 * la cliente che a fine servizio prende anche uno shampoo.
 *
 * Il prezzo parte da quello di vendita ed è modificabile, come l'importo dei
 * servizi. La quantità non va oltre la giacenza — per scelta del salone la
 * giacenza blocca, e il backend lo ricontrolla comunque: qui serve solo a
 * non far scoprire il limite al momento di premere «Incassa».
 */
export default function ProdottiVenduti({
  righe, onChange,
}: {
  righe: RigaVendita[]
  onChange: (righe: RigaVendita[]) => void
}) {
  const [cerca, setCerca] = useState('')
  const [aperto, setAperto] = useState(false)

  // La stessa chiave della pagina Prodotti («catalogo» = solo attivi):
  // condividono la cache, e l'incasso la invalida perché la giacenza cambia.
  const { data, isLoading } = useQuery({
    queryKey: ['products', 'catalogo'],
    queryFn: () => getProducts({ active_only: true }),
  })

  const giaScelti = new Set(righe.map(r => r.product.id))
  const proposte = useMemo(() => {
    const t = cerca.trim().toLowerCase()
    return (data?.items ?? [])
      .filter(p => !giaScelti.has(p.id))
      .filter(p => !t || p.name.toLowerCase().includes(t) || p.category.toLowerCase().includes(t))
      .slice(0, 8)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, cerca, righe])

  const aggiungi = (p: Product) => {
    onChange([...righe, { product: p, quantity: 1, price: Number(p.sale_price).toFixed(2) }])
    setCerca('')
    setAperto(false)
  }
  const cambia = (i: number, r: Partial<RigaVendita>) =>
    onChange(righe.map((x, j) => (j === i ? { ...x, ...r } : x)))
  const togli = (i: number) => onChange(righe.filter((_, j) => j !== i))

  return (
    <div className="space-y-2">
      <span className="label block">Prodotti venduti</span>

      {righe.map((r, i) => {
        const p = prezzoRiga(r)
        const prezzoOk = r.price.trim() !== '' && Number.isFinite(p) && p >= 0
        return (
          <div key={r.product.id} className="border border-border p-2 space-y-2">
            <div className="flex items-start gap-2">
              <span className="text-sm flex-1 min-w-0 truncate">{r.product.name}</span>
              <button
                type="button" onClick={() => togli(i)}
                className="text-ink-3 hover:text-danger"
                aria-label={`Togli ${r.product.name}`}
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex items-center border border-border" role="group" aria-label="Quantità">
                <button
                  type="button" className="px-2 py-1.5 disabled:opacity-40"
                  onClick={() => cambia(i, { quantity: r.quantity - 1 })}
                  disabled={r.quantity <= 1} aria-label="Uno in meno"
                >
                  <Minus className="w-3.5 h-3.5" />
                </button>
                <span className="w-7 text-center text-sm tabular-nums">{r.quantity}</span>
                <button
                  type="button" className="px-2 py-1.5 disabled:opacity-40"
                  onClick={() => cambia(i, { quantity: r.quantity + 1 })}
                  disabled={r.quantity >= r.product.quantity} aria-label="Uno in più"
                >
                  <Plus className="w-3.5 h-3.5" />
                </button>
              </div>
              <span className="text-xs text-ink-3">×</span>
              <input
                className={clsx('input w-24 text-sm tabular-nums', !prezzoOk && 'border-danger')}
                inputMode="decimal"
                aria-label={`Prezzo di ${r.product.name}`}
                value={r.price}
                onChange={e => cambia(i, { price: e.target.value })}
              />
              <span className="ml-auto text-sm tabular-nums">
                €{(rigaValida(r) ? r.quantity * prezzoRiga(r) : 0).toFixed(2)}
              </span>
            </div>
            <p className="text-xs text-ink-3">
              A magazzino: {r.product.quantity} pz
              {Number(r.product.sale_price) !== prezzoRiga(r) &&
                ` · listino €${Number(r.product.sale_price).toFixed(2)}`}
            </p>
          </div>
        )
      })}

      <div className="relative">
        <input
          className="input text-sm"
          placeholder={isLoading ? 'Carico i prodotti…' : 'Aggiungi un prodotto: cerca per nome'}
          value={cerca}
          onChange={e => { setCerca(e.target.value); setAperto(true) }}
          onFocus={() => setAperto(true)}
          onBlur={() => setTimeout(() => setAperto(false), 150)}
          aria-label="Cerca un prodotto da aggiungere"
        />
        {aperto && proposte.length > 0 && (
          <ul className="absolute z-20 left-0 right-0 mt-1 max-h-60 overflow-y-auto border border-border bg-surface shadow-lg" role="listbox">
            {proposte.map(p => {
              const esaurito = p.quantity < 1
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    disabled={esaurito}
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => aggiungi(p)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-primary/10 disabled:opacity-50 disabled:hover:bg-transparent flex gap-2"
                  >
                    <span className="flex-1 min-w-0 truncate">{p.name}</span>
                    <span className="text-xs text-ink-3 tabular-nums shrink-0">
                      {esaurito ? 'esaurito' : `${p.quantity} pz · €${Number(p.sale_price).toFixed(2)}`}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
        {aperto && !isLoading && cerca.trim() && proposte.length === 0 && (
          <p className="text-xs text-ink-3 mt-1">Nessun prodotto attivo con questo nome.</p>
        )}
      </div>
    </div>
  )
}
