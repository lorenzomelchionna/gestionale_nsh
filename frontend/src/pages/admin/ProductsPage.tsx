import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, AlertTriangle, PackagePlus } from 'lucide-react'
import { getProducts, createProduct, addProductMovement } from '@/services/api'
import type { Product } from '@/types'

export default function ProductsPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [movementProduct, setMovementProduct] = useState<Product | null>(null)

  const { data } = useQuery({ queryKey: ['products'], queryFn: () => getProducts() })
  const inv = () => qc.invalidateQueries({ queryKey: ['products'] })

  const createMut = useMutation({ mutationFn: createProduct, onSuccess: () => { inv(); setShowCreate(false) } })
  const moveMut = useMutation({ mutationFn: addProductMovement, onSuccess: () => { inv(); setMovementProduct(null) } })

  const products = data?.items ?? []
  const lowStockProducts = products.filter(p => p.quantity <= p.min_quantity)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Prodotti / Magazzino</h1>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Nuovo prodotto
        </button>
      </div>

      {lowStockProducts.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-amber-600" />
          <p className="text-sm text-amber-800 font-medium">
            {lowStockProducts.length} prodott{lowStockProducts.length > 1 ? 'i' : 'o'} sotto scorta minima:
            {' '}{lowStockProducts.map(p => p.name).join(', ')}
          </p>
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="text-left px-4 py-3 font-medium text-muted-foreground text-xs">Prodotto</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground text-xs">Acquisto</th>
              <th className="text-right px-4 py-3 font-medium text-muted-foreground text-xs">Vendita</th>
              <th className="text-center px-4 py-3 font-medium text-muted-foreground text-xs">Qtà</th>
              <th className="w-16" />
            </tr>
          </thead>
          <tbody>
            {products.map(p => (
              <tr key={p.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                <td className="px-4 py-2.5">
                  <p className="font-medium">{p.name}</p>
                  <p className="text-xs text-muted-foreground">{p.category}</p>
                </td>
                <td className="px-4 py-2.5 text-right">€{p.purchase_price.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-right">€{p.sale_price.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-center">
                  <span className={`font-semibold ${p.quantity <= p.min_quantity ? 'text-amber-600' : 'text-foreground'}`}>
                    {p.quantity}
                  </span>
                  <span className="text-xs text-muted-foreground"> / min {p.min_quantity}</span>
                </td>
                <td className="px-4 py-2.5">
                  <button
                    onClick={() => setMovementProduct(p)}
                    className="text-muted-foreground hover:text-primary"
                    title="Carica/scarica"
                  >
                    <PackagePlus className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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

function ProductFormModal({ onClose, onSave, loading }: any) {
  const [form, setForm] = useState({
    name: '', description: '', purchase_price: 0, sale_price: 0,
    category: 'Shampoo', quantity: 0, min_quantity: 2,
  })
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Nuovo prodotto</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave(form) }} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Nome *</label>
            <input className="input" required value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Categoria</label>
            <input className="input" value={form.category} onChange={e => setForm({...form, category: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Prezzo acquisto</label>
              <input className="input" type="number" step="0.01" min="0" value={form.purchase_price} onChange={e => setForm({...form, purchase_price: Number(e.target.value)})} />
            </div>
            <div>
              <label className="label block mb-1">Prezzo vendita</label>
              <input className="input" type="number" step="0.01" min="0" value={form.sale_price} onChange={e => setForm({...form, sale_price: Number(e.target.value)})} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Quantità iniziale</label>
              <input className="input" type="number" min="0" value={form.quantity} onChange={e => setForm({...form, quantity: Number(e.target.value)})} />
            </div>
            <div>
              <label className="label block mb-1">Scorta minima</label>
              <input className="input" type="number" min="0" value={form.min_quantity} onChange={e => setForm({...form, min_quantity: Number(e.target.value)})} />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Annulla</button>
            <button type="submit" disabled={loading} className="btn-primary text-sm">Salva</button>
          </div>
        </form>
      </div>
    </div>
  )
}

function MovementModal({ product, onClose, onSave, loading }: any) {
  const [form, setForm] = useState({ type: 'carico', quantity: 1, notes: '' })
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Movimento – {product.name}</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave({ product_id: product.id, ...form, quantity: Number(form.quantity) }) }} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Tipo</label>
            <select className="input" value={form.type} onChange={e => setForm({...form, type: e.target.value})}>
              <option value="carico">Carico</option>
              <option value="scarico">Scarico</option>
              <option value="vendita">Vendita</option>
            </select>
          </div>
          <div>
            <label className="label block mb-1">Quantità</label>
            <input className="input" type="number" min="1" value={form.quantity} onChange={e => setForm({...form, quantity: e.target.value as any})} />
          </div>
          <div>
            <label className="label block mb-1">Note</label>
            <input className="input" value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Annulla</button>
            <button type="submit" disabled={loading} className="btn-primary text-sm">Salva</button>
          </div>
        </form>
      </div>
    </div>
  )
}
