import { Fragment, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Scissors } from 'lucide-react'
import { getServices, createService, updateService } from '@/services/api'
import type { Service } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'
import clsx from 'clsx'

const CATEGORIES = ['Taglio', 'Colore', 'Trattamenti', 'Styling', 'Altro']

export default function ServicesPage() {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [selected, setSelected] = useState<Service | null>(null)

  const { data, isLoading } = useQuery({ queryKey: ['services'], queryFn: () => getServices() })
  const inv = () => qc.invalidateQueries({ queryKey: ['services'] })

  const createMut = useMutation({
    mutationFn: createService,
    onSuccess: () => { inv(); setShowForm(false) },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Service> }) => updateService(id, data),
    onSuccess: () => { inv(); setShowForm(false) },
  })

  const services = data?.items ?? []
  // Keep the configured category order, then append anything with an
  // unrecognised category so no service silently disappears from the list.
  const knownGroups = CATEGORIES.map(cat => ({
    category: cat,
    items: services.filter(s => s.category === cat),
  }))
  const other = services.filter(s => !CATEGORIES.includes(s.category ?? ''))
  const byCategory = [
    ...knownGroups,
    ...(other.length ? [{ category: 'Senza categoria', items: other }] : []),
  ].filter(g => g.items.length > 0)

  const openNew = () => { setSelected(null); setShowForm(true) }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Servizi e listino"
        subtitle={services.length ? `${services.length} servizi` : undefined}
        action={
          <button onClick={openNew} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo servizio
          </button>
        }
      />

      {isLoading ? (
        <SkeletonList rows={4} />
      ) : services.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Scissors}
            title="Nessun servizio"
            description="Crea il listino per poter fissare appuntamenti."
            action={
              <button onClick={openNew} className="btn-primary">
                <Plus className="w-4 h-4" /> Nuovo servizio
              </button>
            }
          />
        </div>
      ) : (
        /* One ledger for the whole listino rather than a panel per category:
           the categories are band rows inside it, so every price in the salon
           still lines up down a single column. Only three columns show on a
           phone, which is what kept the old table from fitting there. */
        <div className="panel table-scroll">
          <table className="ledger [&_tbody_tr:last-child_td]:border-b-0">
            <thead>
              <tr>
                <th>Servizio</th>
                <th className="num">Durata</th>
                <th className="num">Prezzo</th>
                <th className="w-px" />
              </tr>
            </thead>
            <tbody>
              {byCategory.map(({ category, items }) => (
                <Fragment key={category}>
                  <tr>
                    <td colSpan={4} className="bg-band border-y border-rule py-1.5">
                      <span className="kicker">{category}</span>
                    </td>
                  </tr>
                  {items.map(s => (
                    <tr
                      key={s.id}
                      onClick={() => { setSelected(s); setShowForm(true) }}
                      className="cursor-pointer"
                    >
                      <td>
                        <div className="flex items-baseline gap-2.5">
                          <span className={clsx(!s.is_active && 'text-ink-3 line-through')}>
                            {s.name}
                          </span>
                          {s.bookable_online && (
                            <span className="kicker text-primary-dark shrink-0">online</span>
                          )}
                          {!s.is_active && <span className="kicker shrink-0">non attivo</span>}
                        </div>
                        {s.description && (
                          <p className="text-[13px] text-ink-3 line-clamp-1 mt-0.5">
                            {s.description}
                          </p>
                        )}
                      </td>
                      <td className="num text-muted-foreground whitespace-nowrap">
                        {s.duration_slots * 30} min
                      </td>
                      <td className="num">
                        <span className="amount">€{s.price.toFixed(2)}</span>
                      </td>
                      <td className="w-px">
                        <button
                          onClick={() => { setSelected(s); setShowForm(true) }}
                          className="btn-icon"
                          aria-label={`Modifica ${s.name}`}
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <ServiceFormModal
          service={selected ?? undefined}
          onClose={() => setShowForm(false)}
          onSave={(payload) =>
            selected ? updateMut.mutate({ id: selected.id, data: payload }) : createMut.mutate(payload)
          }
          loading={createMut.isPending || updateMut.isPending}
        />
      )}
    </div>
  )
}

function ServiceFormModal({ service, onClose, onSave, loading }: {
  service?: Service
  onClose: () => void
  onSave: (d: Partial<Service>) => void
  loading: boolean
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
    <Sheet
      onClose={onClose}
      title={service ? 'Modifica servizio' : 'Nuovo servizio'}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="service-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="service-form"
        onSubmit={(e) => { e.preventDefault(); onSave(form) }}
        className="space-y-4"
      >
        <div>
          <label className="label">Nome *</label>
          <input
            className="input"
            required
            value={form.name}
            onChange={e => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Descrizione</label>
          <input
            className="input"
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Prezzo (€) *</label>
            <input
              className="input"
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              required
              value={form.price}
              onChange={e => setForm({ ...form, price: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Durata</label>
            <input
              className="input"
              type="number"
              inputMode="numeric"
              min="1"
              max="20"
              required
              value={form.duration_slots}
              onChange={e => setForm({ ...form, duration_slots: Number(e.target.value) })}
            />
            <p className="note tabular-nums mt-1.5">
              {form.duration_slots} slot = {form.duration_slots * 30} minuti
            </p>
          </div>
        </div>
        <div>
          <label className="label">Categoria</label>
          <select
            className="input"
            value={form.category}
            onChange={e => setForm({ ...form, category: e.target.value })}
          >
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="space-y-2 pt-1">
          <Toggle
            label="Prenotabile online"
            description="Visibile ai clienti nel portale prenotazioni"
            checked={form.bookable_online}
            onChange={v => setForm({ ...form, bookable_online: v })}
          />
          <Toggle
            label="Attivo"
            description="Disattiva per nasconderlo senza eliminarlo"
            checked={form.is_active}
            onChange={v => setForm({ ...form, is_active: v })}
          />
        </div>
      </form>
    </Sheet>
  )
}

/** Full-row switch — a 16px checkbox is far below a comfortable tap target. */
export function Toggle({ label, description, checked, onChange }: {
  label: string
  description?: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="w-full flex items-center gap-3 p-3 border border-border bg-field hover:bg-foreground/[0.05] transition-colors text-left"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-foreground">{label}</span>
        {description && <span className="block text-xs text-ink-3 mt-0.5">{description}</span>}
      </span>
      {/* A square shuttle in a ruled track: the switch is a marker sliding in
          a box, not a pill. */}
      <span
        className={clsx(
          'relative w-10 h-5 border transition-colors shrink-0',
          checked ? 'border-primary bg-primary/10' : 'border-border bg-surface'
        )}
      >
        <span
          className={clsx(
            'absolute top-[3px] left-[3px] w-3 h-3 transition-transform',
            checked ? 'bg-primary translate-x-5' : 'bg-border'
          )}
        />
      </span>
    </button>
  )
}
