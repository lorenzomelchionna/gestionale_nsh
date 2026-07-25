import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, Trash2, TrendingDown } from 'lucide-react'
import { getExpenses, createExpense, deleteExpense } from '@/services/api'
import type { Expense } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'

const CATEGORIES = ['Affitto', 'Forniture', 'Utenze', 'Acquisto prodotti', 'Marketing', 'Altro']

export default function ExpensesPage() {
  const qc = useQueryClient()
  const today = format(new Date(), 'yyyy-MM-dd')
  const [dateFrom, setDateFrom] = useState(today.slice(0, 7) + '-01')
  const [dateTo, setDateTo] = useState(today)
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['expenses', dateFrom, dateTo],
    queryFn: () => getExpenses({ date_from: dateFrom, date_to: dateTo }),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['expenses'] })
  const createMut = useMutation({
    mutationFn: createExpense,
    onSuccess: () => { inv(); setShowCreate(false) },
  })
  const deleteMut = useMutation({ mutationFn: deleteExpense, onSuccess: inv })

  const expenses = data?.items ?? []
  const total = expenses.reduce((s, e) => s + e.amount, 0)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Spese"
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuova spesa
          </button>
        }
      />

      {/* Period filters stack on phones; the total gets its own full-width row. */}
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Dal</label>
            <input type="date" className="input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="label">Al</label>
            <input type="date" className="input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
          </div>
        </div>
        <div className="card px-4 py-3 flex items-baseline justify-between">
          <span className="text-[13px] text-muted-foreground">Totale spese</span>
          <span className="font-bold text-danger tabular-nums">€{total.toFixed(2)}</span>
        </div>
      </div>

      {isLoading ? (
        <SkeletonList rows={4} />
      ) : expenses.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={TrendingDown}
            title="Nessuna spesa nel periodo"
            description="Cambia le date o registra una nuova spesa."
          />
        </div>
      ) : (
        <div className="card divide-y divide-border overflow-hidden">
          {expenses.map(e => (
            <div key={e.id} className="p-4 flex items-start gap-3">
              <div className="min-w-0 flex-1">
                <p className="font-medium text-foreground truncate">{e.description}</p>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-xs bg-muted px-2 py-0.5 rounded">{e.category}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {format(parseISO(e.date), 'dd/MM/yyyy')}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="font-semibold text-danger tabular-nums">€{e.amount.toFixed(2)}</span>
                <button
                  onClick={() => deleteMut.mutate(e.id)}
                  className="btn-icon !w-9 !h-9 hover:text-danger"
                  aria-label={`Elimina spesa ${e.description}`}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

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

function ExpenseFormModal({ onClose, onSave, loading }: {
  onClose: () => void
  onSave: (d: Partial<Expense>) => void
  loading: boolean
}) {
  const [form, setForm] = useState({
    description: '', amount: '', category: 'Forniture',
    date: format(new Date(), 'yyyy-MM-dd'), notes: '',
  })

  return (
    <Sheet
      onClose={onClose}
      title="Nuova spesa"
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="expense-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="expense-form"
        onSubmit={(e) => { e.preventDefault(); onSave({ ...form, amount: Number(form.amount) }) }}
        className="space-y-4"
      >
        <div>
          <label className="label">Descrizione *</label>
          <input
            className="input"
            required
            value={form.description}
            onChange={e => setForm({ ...form, description: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Importo (€) *</label>
            <input
              className="input" type="number" inputMode="decimal" step="0.01" min="0.01" required
              value={form.amount}
              onChange={e => setForm({ ...form, amount: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Data *</label>
            <input
              className="input" type="date" required
              value={form.date}
              onChange={e => setForm({ ...form, date: e.target.value })}
            />
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
      </form>
    </Sheet>
  )
}
