import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, X } from 'lucide-react'
import { getPayments, createPayment } from '@/services/api'
import type { Payment } from '@/types'

const METHOD_LABELS: Record<string, string> = { contanti: 'Contanti', carta: 'Carta', misto: 'Misto' }
const TYPE_LABELS: Record<string, string> = { servizio: 'Servizio', prodotto: 'Prodotto' }

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
  const cash = payments.filter(p => p.method === 'contanti').reduce((s, p) => s + p.amount, 0)
  const card = payments.filter(p => p.method === 'carta').reduce((s, p) => s + p.amount, 0)

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
          <p className="text-xs text-muted-foreground mt-1">Contanti</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-blue-600">€{card.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-1">Carta</p>
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
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    p.method === 'contanti' ? 'bg-emerald-100 text-emerald-700'
                    : p.method === 'carta' ? 'bg-blue-100 text-blue-700'
                    : 'bg-purple-100 text-purple-700'
                  }`}>
                    {METHOD_LABELS[p.method]}
                  </span>
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
        />
      )}
    </div>
  )
}

function PaymentFormModal({ onClose, onSave, loading }: any) {
  const [form, setForm] = useState({ amount: '', method: 'contanti', type: 'servizio', notes: '' })
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Registra incasso</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave({ ...form, amount: Number(form.amount) }) }} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Importo (€) *</label>
            <input className="input" type="number" step="0.01" min="0.01" required value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Metodo</label>
            <select className="input" value={form.method} onChange={e => setForm({...form, method: e.target.value})}>
              <option value="contanti">Contanti</option>
              <option value="carta">Carta</option>
              <option value="misto">Misto</option>
            </select>
          </div>
          <div>
            <label className="label block mb-1">Tipo</label>
            <select className="input" value={form.type} onChange={e => setForm({...form, type: e.target.value})}>
              <option value="servizio">Servizio</option>
              <option value="prodotto">Prodotto</option>
            </select>
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
