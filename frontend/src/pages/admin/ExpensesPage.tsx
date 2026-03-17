import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, X, Trash2 } from 'lucide-react'
import { getExpenses, createExpense, deleteExpense } from '@/services/api'

const CATEGORIES = ['Affitto', 'Forniture', 'Utenze', 'Acquisto prodotti', 'Marketing', 'Altro']

export default function ExpensesPage() {
  const qc = useQueryClient()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [dateFrom, setDateFrom] = useState(today.slice(0, 7) + '-01')
  const [dateTo, setDateTo] = useState(today)
  const [showCreate, setShowCreate] = useState(false)

  const { data } = useQuery({
    queryKey: ['expenses', dateFrom, dateTo],
    queryFn: () => getExpenses({ date_from: dateFrom, date_to: dateTo }),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['expenses'] })
  const createMut = useMutation({ mutationFn: createExpense, onSuccess: () => { inv(); setShowCreate(false) } })
  const deleteMut = useMutation({ mutationFn: deleteExpense, onSuccess: inv })

  const expenses = data?.items ?? []
  const total = expenses.reduce((s, e) => s + e.amount, 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Spese</h1>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Nuova spesa
        </button>
      </div>

      <div className="flex gap-3 flex-wrap items-end">
        <div>
          <label className="label block mb-1 text-xs">Dal</label>
          <input type="date" className="input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="label block mb-1 text-xs">Al</label>
          <input type="date" className="input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </div>
        <div className="card px-4 py-2 ml-auto">
          <span className="text-xs text-muted-foreground">Totale spese: </span>
          <span className="font-bold text-red-600">€{total.toFixed(2)}</span>
        </div>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/50">
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Data</th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Descrizione</th>
              <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Categoria</th>
              <th className="text-right px-4 py-2 font-medium text-muted-foreground text-xs">Importo</th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {expenses.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">Nessuna spesa nel periodo</td></tr>
            )}
            {expenses.map(e => (
              <tr key={e.id} className="border-b border-border last:border-0 hover:bg-muted/20">
                <td className="px-4 py-2.5">{format(parseISO(e.date), 'dd/MM/yyyy')}</td>
                <td className="px-4 py-2.5 font-medium">{e.description}</td>
                <td className="px-4 py-2.5">
                  <span className="text-xs bg-muted px-2 py-0.5 rounded">{e.category}</span>
                </td>
                <td className="px-4 py-2.5 text-right font-semibold text-red-600">€{e.amount.toFixed(2)}</td>
                <td className="px-4 py-2.5">
                  <button
                    onClick={() => deleteMut.mutate(e.id)}
                    className="text-muted-foreground hover:text-red-500"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <ExpenseFormModal
          onClose={() => setShowCreate(false)}
          onSave={(d) => createMut.mutate(d)}
          loading={createMut.isPending}
        />
      )}
    </div>
  )
}

function ExpenseFormModal({ onClose, onSave, loading }: any) {
  const [form, setForm] = useState({
    description: '', amount: '', category: 'Forniture',
    date: format(new Date(), 'yyyy-MM-dd'), notes: '',
  })
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Nuova spesa</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave({ ...form, amount: Number(form.amount) }) }} className="p-4 space-y-3">
          <div>
            <label className="label block mb-1">Descrizione *</label>
            <input className="input" required value={form.description} onChange={e => setForm({...form, description: e.target.value})} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Importo (€) *</label>
              <input className="input" type="number" step="0.01" min="0.01" required value={form.amount} onChange={e => setForm({...form, amount: e.target.value})} />
            </div>
            <div>
              <label className="label block mb-1">Data *</label>
              <input className="input" type="date" required value={form.date} onChange={e => setForm({...form, date: e.target.value})} />
            </div>
          </div>
          <div>
            <label className="label block mb-1">Categoria</label>
            <select className="input" value={form.category} onChange={e => setForm({...form, category: e.target.value})}>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
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
