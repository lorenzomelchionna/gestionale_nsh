import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, X } from 'lucide-react'
import { getPayments, createPayment } from '@/services/api'
import type { Payment } from '@/types'

const METHOD_LABELS: Record<string, string> = { contanti: 'Contanti', carta: 'Carta', misto: 'Misto' }
const TYPE_LABELS: Record<string, string> = { servizio: 'Servizio', prodotto: 'Prodotto' }

/** Ricava la quota contanti effettiva di un pagamento (inclusi i misti). */
function effectiveCash(p: Payment): number {
  if (p.method === 'contanti') return p.amount
  if (p.method === 'misto' && p.cash_amount != null) return p.cash_amount
  return 0
}

/** Ricava la quota carta effettiva di un pagamento (inclusi i misti). */
function effectiveCard(p: Payment): number {
  if (p.method === 'carta') return p.amount
  if (p.method === 'misto' && p.card_amount != null) return p.card_amount
  return 0
}

export default function CashPage() {
  const qc = useQueryClient()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [dateFrom, setDateFrom] = useState(today)
  const [dateTo, setDateTo] = useState(today)
  const [showCreate, setShowCreate] = useState(false)

  const { data } = useQuery({
    queryKey: ['payments', dateFrom, dateTo],
    queryFn: () => getPayments({ date_from: dateFrom + 'T00:00:00', date_to: dateTo + 'T23:59:59' }),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['payments'] })
  const createMut = useMutation({ mutationFn: createPayment, onSuccess: () => { inv(); setShowCreate(false) } })

  const payments = data?.items ?? []
  const total = payments.reduce((s, p) => s + p.amount, 0)
  const cash  = payments.reduce((s, p) => s + effectiveCash(p), 0)
  const card  = payments.reduce((s, p) => s + effectiveCard(p), 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Cassa</h1>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Registra incasso
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <div>
          <label className="label block mb-1 text-xs">Dal</label>
          <input type="date" className="input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="label block mb-1 text-xs">Al</label>
          <input type="date" className="input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-foreground">€{total.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-1">Totale incassato</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-emerald-600">€{cash.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-1">Contanti (incl. misto)</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-blue-600">€{card.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-1">Carta (incl. misto)</p>
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Data</th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Tipo</th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Metodo</th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-xs">Importo</th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Note</th>
            </tr>
          </thead>
          <tbody>
            {payments.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">Nessun incasso nel periodo</td></tr>
            )}
            {payments.map(p => (
              <tr key={p.id} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5">{format(parseISO(p.date), 'dd/MM/yyyy HH:mm')}</td>
                <td className="px-4 py-2.5">{TYPE_LABELS[p.type]}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      p.method === 'contanti' ? 'bg-emerald-100 text-emerald-700'
                      : p.method === 'carta' ? 'bg-blue-100 text-blue-700'
                      : 'bg-purple-100 text-purple-700'
                    }`}>
                      {METHOD_LABELS[p.method]}
                    </span>
                    {p.method === 'misto' && p.cash_amount != null && p.card_amount != null && (
                      <span className="text-xs text-muted-foreground">
                        €{p.cash_amount.toFixed(2)} + €{p.card_amount.toFixed(2)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right font-semibold">€{p.amount.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-muted-foreground">{p.notes ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <PaymentFormModal
          onClose={() => setShowCreate(false)}
          onSave={(d) => createMut.mutate(d)}
          loading={createMut.isPending}
          error={createMut.error ? String((createMut.error as any)?.response?.data?.detail ?? 'Errore') : null}
        />
      )}
    </div>
  )
}

interface FormData {
  amount: string
  method: string
  type: string
  notes: string
  cashAmount: string
  cardAmount: string
}

function PaymentFormModal({ onClose, onSave, loading, error }: {
  onClose: () => void
  onSave: (d: any) => void
  loading: boolean
  error: string | null
}) {
  const [form, setForm] = useState<FormData>({
    amount: '', method: 'contanti', type: 'servizio', notes: '',
    cashAmount: '', cardAmount: '',
  })

  const set = (k: keyof FormData, v: string) => {
    setForm(prev => {
      const next = { ...prev, [k]: v }
      // Se cambia uno dei due sotto-importi, aggiorna il totale automaticamente
      if ((k === 'cashAmount' || k === 'cardAmount') && next.method === 'misto') {
        const c = parseFloat(next.cashAmount) || 0
        const ca = parseFloat(next.cardAmount) || 0
        next.amount = (c + ca).toFixed(2)
      }
      return next
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const payload: any = {
      amount: Number(form.amount),
      method: form.method,
      type: form.type,
      notes: form.notes || undefined,
    }
    if (form.method === 'misto') {
      payload.cash_amount = Number(form.cashAmount)
      payload.card_amount = Number(form.cardAmount)
    }
    onSave(payload)
  }

  const isMisto = form.method === 'misto'

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Registra incasso</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Metodo</label>
            <select className="input" value={form.method} onChange={e => set('method', e.target.value)}>
              <option value="contanti">Contanti</option>
              <option value="carta">Carta</option>
              <option value="misto">Misto (contanti + carta)</option>
            </select>
          </div>

          {isMisto ? (
            /* Split payment: two sub-amounts, total computed automatically */
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label block mb-1 text-xs">Contanti (€) *</label>
                  <input
                    className="input"
                    type="number" step="0.01" min="0.01" required
                    placeholder="0.00"
                    value={form.cashAmount}
                    onChange={e => set('cashAmount', e.target.value)}
                  />
                </div>
                <div>
                  <label className="label block mb-1 text-xs">Carta (€) *</label>
                  <input
                    className="input"
                    type="number" step="0.01" min="0.01" required
                    placeholder="0.00"
                    value={form.cardAmount}
                    onChange={e => set('cardAmount', e.target.value)}
                  />
                </div>
              </div>
              {form.amount && (
                <p className="text-xs text-muted-foreground">
                  Totale: <span className="font-semibold text-foreground">€{Number(form.amount).toFixed(2)}</span>
                </p>
              )}
            </div>
          ) : (
            <div>
              <label className="label block mb-1">Importo (€) *</label>
              <input
                className="input" type="number" step="0.01" min="0.01" required
                value={form.amount}
                onChange={e => set('amount', e.target.value)}
              />
            </div>
          )}

          <div>
            <label className="label block mb-1">Tipo</label>
            <select className="input" value={form.type} onChange={e => set('type', e.target.value)}>
              <option value="servizio">Servizio</option>
              <option value="prodotto">Prodotto</option>
            </select>
          </div>
          <div>
            <label className="label block mb-1">Note</label>
            <input className="input" value={form.notes} onChange={e => set('notes', e.target.value)} />
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Annulla</button>
            <button type="submit" disabled={loading} className="btn-primary text-sm">Salva</button>
          </div>
        </form>
      </div>
    </div>
  )
}
