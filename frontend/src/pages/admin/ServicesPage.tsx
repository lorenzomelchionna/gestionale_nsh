import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Edit, Scissors } from 'lucide-react'
import { getServices, createService, updateService } from '@/services/api'
import type { Service } from '@/types'

const CATEGORIES = ['Taglio', 'Colore', 'Trattamenti', 'Styling', 'Altro']

export default function ServicesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [selected, setSelected] = useState<Service | null>(null)

  const { data } = useQuery({ queryKey: ['services'], queryFn: () => getServices() })
  const inv = () => qc.invalidateQueries({ queryKey: ['services'] })

  const createMut = useMutation({ mutationFn: createService, onSuccess: () => { inv(); setShowForm(false) } })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: any) => updateService(id, data),
    onSuccess: () => { inv(); setShowForm(false) },
  })

  const services = data?.items ?? []
  const byCategory = CATEGORIES.map(cat => ({
    category: cat,
    items: services.filter(s => s.category === cat),
  })).filter(g => g.items.length > 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Servizi e listino</h1>
        <button onClick={() => { setSelected(null); setShowForm(true) }} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Nuovo servizio
        </button>
      </div>

      {byCategory.map(({ category, items }) => (
        <div key={category}>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-2">{category}</h3>
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Servizio</th>
                  <th className="text-right px-4 py-2 font-medium text-muted-foreground text-xs">Prezzo</th>
                  <th className="text-right px-4 py-2 font-medium text-muted-foreground text-xs">Durata</th>
                  <th className="text-center px-4 py-2 font-medium text-muted-foreground text-xs">Online</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {items.map(s => (
                  <tr key={s.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{s.name}</p>
                      {s.description && <p className="text-xs text-muted-foreground">{s.description}</p>}
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold">€{s.price.toFixed(2)}</td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">{s.duration_slots * 30} min</td>
                    <td className="px-4 py-2.5 text-center">
                      <span className={s.bookable_online ? 'text-emerald-600' : 'text-red-400'}>
                        {s.bookable_online ? '✓' : '–'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <button onClick={() => { setSelected(s); setShowForm(true) }} className="text-muted-foreground hover:text-foreground">
                        <Edit className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {showForm && (
        <ServiceFormModal
          service={selected ?? undefined}
          onClose={() => setShowForm(false)}
          onSave={(data) => selected ? updateMut.mutate({ id: selected.id, data }) : createMut.mutate(data)}
          loading={createMut.isPending || updateMut.isPending}
        />
      )}
    </div>
  )
}

function ServiceFormModal({ service, onClose, onSave, loading }: {
  service?: Service; onClose: () => void; onSave: (d: Partial<Service>) => void; loading: boolean
}) {
  const [form, setForm] = useState({
    name: service?.name ?? '',
    description: service?.description ?? '',
    price: service?.price ?? 0,
    duration_slots: service?.duration_slots ?? 1,
    category: service?.category ?? 'Taglio',
    bookable_online: service?.bookable_online ?? true,
    is_active: service?.is_active ?? true,
  })

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">{service ? 'Modifica servizio' : 'Nuovo servizio'}</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave(form) }} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Nome *</label>
            <input className="input" required value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Descrizione</label>
            <input className="input" value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Prezzo (€) *</label>
              <input className="input" type="number" step="0.01" min="0" required value={form.price} onChange={e => setForm({...form, price: Number(e.target.value)})} />
            </div>
            <div>
              <label className="label block mb-1">Durata (slot × 30min) *</label>
              <input className="input" type="number" min="1" max="20" required value={form.duration_slots} onChange={e => setForm({...form, duration_slots: Number(e.target.value)})} />
              <p className="text-xs text-muted-foreground mt-0.5">= {form.duration_slots * 30} minuti</p>
            </div>
          </div>
          <div>
            <label className="label block mb-1">Categoria</label>
            <select className="input" value={form.category} onChange={e => setForm({...form, category: e.target.value})}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.bookable_online} onChange={e => setForm({...form, bookable_online: e.target.checked})} />
              Prenotabile online
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm({...form, is_active: e.target.checked})} />
              Attivo
            </label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Annulla</button>
            <button type="submit" disabled={loading} className="btn-primary text-sm disabled:opacity-60">
              {loading ? 'Salvataggio...' : 'Salva'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
