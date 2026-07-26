import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, AlertTriangle, PackagePlus, Package } from 'lucide-react'
import { getProducts, createProduct, addProductMovement } from '@/services/api'
import type { Product } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'
import clsx from 'clsx'

export default function ProductsPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [movementProduct, setMovementProduct] = useState<Product | null>(null)

  const { data, isLoading } = useQuery({ queryKey: ['products'], queryFn: () => getProducts() })
  const inv = () => qc.invalidateQueries({ queryKey: ['products'] })

  const createMut = useMutation({
    mutationFn: createProduct,
    onSuccess: () => { inv(); setShowCreate(false) },
  })
  const moveMut = useMutation({
    mutationFn: addProductMovement,
    onSuccess: () => { inv(); setMovementProduct(null) },
  })

  const products = data?.items ?? []
  const lowStock = products.filter(p => p.quantity <= p.min_quantity)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Prodotti"
        subtitle={products.length ? `${products.length} a magazzino` : undefined}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo prodotto
          </button>
        }
      />

      {lowStock.length > 0 && (
        <div className="bg-warning/10 border border-warning/30 rounded-xl px-4 py-3 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-warning">
              {lowStock.length} prodott{lowStock.length > 1 ? 'i' : 'o'} sotto scorta
            </p>
            <p className="text-[13px] text-muted-foreground mt-0.5">
              {lowStock.map(p => p.name).join(', ')}
            </p>
          </div>
        </div>
      )}

      {isLoading ? (
        <SkeletonList rows={4} />
      ) : products.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Package}
            title="Magazzino vuoto"
            description="Aggiungi i prodotti che rivendi o usi in salone."
            action={
              <button onClick={() => setShowCreate(true)} className="btn-primary">
                <Plus className="w-4 h-4" /> Nuovo prodotto
              </button>
            }
          />
        </div>
      ) : (
        <div className="card divide-y divide-border overflow-hidden">
          {products.map(p => {
            const low = p.quantity <= p.min_quantity
            return (
              <div key={p.id} className="p-4 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium truncate">{p.name}</p>
                  <p className="text-xs text-muted-foreground truncate">{p.category}</p>
                  <div className="flex items-center gap-3 mt-1.5 text-[13px]">
                    <span className={clsx('font-semibold tabular-nums', low ? 'text-warning' : 'text-foreground')}>
                      {p.quantity} pz
                    </span>
                    <span className="text-xs text-muted-foreground">min {p.min_quantity}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      €{p.purchase_price.toFixed(2)} → €{p.sale_price.toFixed(2)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setMovementProduct(p)}
                  className="btn-icon bg-muted/60 hover:bg-muted hover:text-primary"
                  title="Carico / scarico"
                  aria-label={`Movimento magazzino per ${p.name}`}
                >
                  <PackagePlus className="w-[18px] h-[18px]" />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {showCreate && (
        <ProductFormModal
          onClose={() => setShowCreate(false)}
          onSave={(d) => createMut.mutate(d)}
          loading={createMut.isPending}
        />
      )}

      {movementProduct && (
        <MovementModal
          product={movementProduct}
          onClose={() => setMovementProduct(null)}
          onSave={(d) => moveMut.mutate(d)}
          loading={moveMut.isPending}
        />
      )}
    </div>
  )
}

function ProductFormModal({ onClose, onSave, loading }: {
  onClose: () => void
  onSave: (d: Partial<Product>) => void
  loading: boolean
}) {
  const [form, setForm] = useState({
    name: '', description: '', purchase_price: 0, sale_price: 0,
    category: 'Shampoo', quantity: 0, min_quantity: 2,
  })

  return (
    <Sheet
      onClose={onClose}
      title="Nuovo prodotto"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="product-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="product-form"
        onSubmit={(e) => { e.preventDefault(); onSave(form) }}
        className="space-y-4"
      >
        <div>
          <label className="label">Nome *</label>
          <input className="input" required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className="label">Categoria</label>
          <input className="input" value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Prezzo acquisto</label>
            <input
              className="input" type="number" inputMode="decimal" step="0.01" min="0"
              value={form.purchase_price}
              onChange={e => setForm({ ...form, purchase_price: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Prezzo vendita</label>
            <input
              className="input" type="number" inputMode="decimal" step="0.01" min="0"
              value={form.sale_price}
              onChange={e => setForm({ ...form, sale_price: Number(e.target.value) })}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Quantità iniziale</label>
            <input
              className="input" type="number" inputMode="numeric" min="0"
              value={form.quantity}
              onChange={e => setForm({ ...form, quantity: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Scorta minima</label>
            <input
              className="input" type="number" inputMode="numeric" min="0"
              value={form.min_quantity}
              onChange={e => setForm({ ...form, min_quantity: Number(e.target.value) })}
            />
          </div>
        </div>
      </form>
    </Sheet>
  )
}

const MOVEMENT_TYPES = [
  { value: 'carico', label: 'Carico' },
  { value: 'scarico', label: 'Scarico' },
  { value: 'vendita', label: 'Vendita' },
]

function MovementModal({ product, onClose, onSave, loading }: {
  product: Product
  onClose: () => void
  onSave: (d: { product_id: number; type: string; quantity: number; notes?: string }) => void
  loading: boolean
}) {
  const [form, setForm] = useState({ type: 'carico', quantity: 1, notes: '' })

  return (
    <Sheet
      onClose={onClose}
      title="Movimento magazzino"
      description={`${product.name} · ${product.quantity} pz disponibili`}
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="movement-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="movement-form"
        onSubmit={(e) => {
          e.preventDefault()
          onSave({
            product_id: product.id,
            type: form.type,
            quantity: Number(form.quantity),
            notes: form.notes || undefined,
          })
        }}
        className="space-y-4"
      >
        <div>
          <label className="label">Tipo</label>
          {/* Three big tap targets beat a native select on a phone. */}
          <div className="grid grid-cols-3 gap-2">
            {MOVEMENT_TYPES.map(t => (
              <button
                key={t.value}
                type="button"
                onClick={() => setForm({ ...form, type: t.value })}
                className={clsx(
                  'min-h-touch rounded-lg text-sm font-medium border transition-colors',
                  form.type === t.value
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-muted-foreground hover:bg-muted'
                )}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="label">Quantità</label>
          <input
            className="input" type="number" inputMode="numeric" min="1"
            value={form.quantity}
            onChange={e => setForm({ ...form, quantity: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="label">Note</label>
          <input
            className="input"
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
      </form>
    </Sheet>
  )
}
