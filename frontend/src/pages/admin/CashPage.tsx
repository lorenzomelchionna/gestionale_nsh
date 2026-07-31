import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, Wallet } from 'lucide-react'
import { getPayments, createPayment } from '@/services/api'
import type { Payment } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState } from '@/components/ui'

const METHOD_LABELS: Record<string, string> = { contanti: 'Contanti', carta: 'Carta', misto: 'Misto' }
const TYPE_LABELS: Record<string, string> = { servizio: 'Servizio', prodotto: 'Prodotto' }

/** The tender is named, not colour-coded: the register owns a single hue. */
function MethodLabel({ method }: { method: string }) {
  return (
    <span className="font-heading text-[12px] uppercase tracking-[0.12em] text-muted-foreground">
      {METHOD_LABELS[method]}
    </span>
  )
}

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
    <div className="space-y-5">
      <PageHeader
        title="Cassa"
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Registra incasso
          </button>
        }
      />

      {/* Filters */}
      <div className="grid grid-cols-2 gap-3 sm:max-w-md">
        <div>
          <label className="label">Dal</label>
          <input type="date" className="input" value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="label">Al</label>
          <input type="date" className="input" value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </div>
      </div>

      {/* Summary — one panel divided into cells, not three floating cards. The
          total still spans the row on phones, where three side-by-side euro
          figures wrap mid-number. */}
      <div className="panel grid grid-cols-2 sm:grid-cols-3">
        <div className="col-span-2 sm:col-span-1 px-4 py-3.5 border-b border-rule-soft sm:border-b-0 sm:border-r">
          <span className="kicker">Totale incassato</span>
          <p className="font-heading text-[28px] leading-none tabular-nums text-foreground mt-2">
            €{total.toFixed(2)}
          </p>
        </div>
        <div className="px-4 py-3.5 border-r border-rule-soft">
          <span className="kicker">Contanti</span>
          <p className="font-heading text-[22px] leading-none tabular-nums text-ink-2 mt-2">
            €{cash.toFixed(2)}
          </p>
        </div>
        <div className="px-4 py-3.5">
          <span className="kicker">Carta</span>
          <p className="font-heading text-[22px] leading-none tabular-nums text-ink-2 mt-2">
            €{card.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Phones: ruled rows. The five-column ledger needs real width to read. */}
      <div className="panel sm:hidden">
        {payments.length === 0 ? (
          <EmptyState icon={Wallet} title="Nessun incasso nel periodo" />
        ) : (
          <>
            <div className="divide-y divide-rule-soft">
              {payments.map(p => (
                <div key={p.id} className="px-4 py-3.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="text-foreground truncate">{TYPE_LABELS[p.type]}</p>
                    <span className="tabular-nums text-foreground shrink-0">€{p.amount.toFixed(2)}</span>
                  </div>
                  <div className="flex items-baseline gap-2.5 mt-1 flex-wrap">
                    <MethodLabel method={p.method} />
                    <span className="text-xs text-ink-3 tabular-nums">
                      {format(parseISO(p.date), 'dd/MM/yyyy HH:mm')}
                    </span>
                    {p.method === 'misto' && p.cash_amount != null && p.card_amount != null && (
                      <span className="text-xs text-muted-foreground tabular-nums">
                        €{p.cash_amount.toFixed(2)} + €{p.card_amount.toFixed(2)}
                      </span>
                    )}
                  </div>
                  {p.notes && <p className="text-[13px] text-muted-foreground mt-1.5">{p.notes}</p>}
                </div>
              ))}
            </div>
            <div className="bg-band border-t border-rule px-4 py-3 flex items-baseline justify-between">
              <span className="kicker">Totale incassato</span>
              <span className="amount">€{total.toFixed(2)}</span>
            </div>
          </>
        )}
      </div>

      {/* The register itself, from sm up: banded head, hairline rows, a summed foot. */}
      <div className="panel hidden sm:block table-scroll">
        <table className="ledger">
          <thead>
            <tr>
              <th>Data</th>
              <th>Tipo</th>
              <th>Metodo</th>
              <th className="!text-right">Importo</th>
              <th>Note</th>
            </tr>
          </thead>
          <tbody>
            {payments.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <p className="note text-center py-5">Nessun incasso nel periodo</p>
                </td>
              </tr>
            )}
            {payments.map(p => (
              <tr key={p.id}>
                <td className="tabular-nums text-ink-2 whitespace-nowrap">
                  {format(parseISO(p.date), 'dd/MM/yyyy HH:mm')}
                </td>
                <td>{TYPE_LABELS[p.type]}</td>
                <td>
                  <div className="flex items-baseline gap-2">
                    <MethodLabel method={p.method} />
                    {p.method === 'misto' && p.cash_amount != null && p.card_amount != null && (
                      <span className="text-xs text-ink-3 tabular-nums whitespace-nowrap">
                        €{p.cash_amount.toFixed(2)} + €{p.card_amount.toFixed(2)}
                      </span>
                    )}
                  </div>
                </td>
                <td className="num">€{p.amount.toFixed(2)}</td>
                <td className="text-muted-foreground">{p.notes ?? '–'}</td>
              </tr>
            ))}
          </tbody>
          {payments.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan={3} className="border-t border-rule">
                  <span className="kicker">Totale incassato</span>
                </td>
                <td className="num border-t border-rule">
                  <span className="amount">€{total.toFixed(2)}</span>
                </td>
                <td className="border-t border-rule" />
              </tr>
            </tfoot>
          )}
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
    <Sheet
      onClose={onClose}
      title="Registra incasso"
      size="sm"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="payment-form" disabled={loading} className="btn-primary btn-sm">
            Salva
          </button>
        </>
      }
    >
      <form id="payment-form" onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label">Metodo</label>
          <select className="input" value={form.method} onChange={e => set('method', e.target.value)}>
            <option value="contanti">Contanti</option>
            <option value="carta">Carta</option>
            <option value="misto">Misto (contanti + carta)</option>
          </select>
        </div>

        {isMisto ? (
          /* Split payment: two sub-amounts, total computed automatically */
          <div className="space-y-2.5">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label">Contanti (€) *</label>
                <input
                  className="input"
                  type="number" step="0.01" min="0.01" required
                  placeholder="0.00"
                  value={form.cashAmount}
                  onChange={e => set('cashAmount', e.target.value)}
                />
              </div>
              <div>
                <label className="label">Carta (€) *</label>
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
              <p className="flex items-baseline justify-between gap-3 border-t border-rule-soft pt-2.5">
                <span className="kicker">Totale</span>
                <span className="amount">€{Number(form.amount).toFixed(2)}</span>
              </p>
            )}
          </div>
        ) : (
          <div>
            <label className="label">Importo (€) *</label>
            <input
              className="input" type="number" step="0.01" min="0.01" required
              value={form.amount}
              onChange={e => set('amount', e.target.value)}
            />
          </div>
        )}

        <div>
          <label className="label">Tipo</label>
          <select className="input" value={form.type} onChange={e => set('type', e.target.value)}>
            <option value="servizio">Servizio</option>
            <option value="prodotto">Prodotto</option>
          </select>
        </div>
        <div>
          <label className="label">Note</label>
          <input className="input" value={form.notes} onChange={e => set('notes', e.target.value)} />
        </div>

        {error && (
          <p role="alert" className="text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5">
            {error}
          </p>
        )}
      </form>
    </Sheet>
  )
}
