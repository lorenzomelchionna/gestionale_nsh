import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, Eye, Users } from 'lucide-react'
import { getProducts, previewMessage, sendMessage } from '@/services/api'
import type { MessageFilter, FilterType } from '@/types'
import clsx from 'clsx'

const FILTER_OPTIONS: { value: FilterType; label: string }[] = [
  { value: 'all',            label: 'Tutti i clienti' },
  { value: 'product_buyers', label: 'Acquirenti di un prodotto' },
  { value: 'inactive',       label: 'Clienti inattivi' },
  { value: 'birthday_month', label: 'Compleanno nel mese' },
]

const MONTHS = [
  'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
  'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre',
]

export default function MessagingPage() {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [filter, setFilter] = useState<MessageFilter>({ type: 'all' })
  const [previewResult, setPreviewResult] = useState<{ count: number; recipients: { id: number; first_name: string; last_name: string; email: string | null }[] } | null>(null)
  const [sendResult, setSendResult] = useState<{ sent: number; skipped: number; errors: number } | null>(null)

  const { data: productsData } = useQuery({
    queryKey: ['products'],
    queryFn: () => getProducts({ active_only: true }),
  })
  const products = productsData?.items ?? []

  const previewMut = useMutation({
    mutationFn: () => previewMessage({ subject, body, filter }),
    onSuccess: (data) => { setPreviewResult(data); setSendResult(null) },
  })

  const sendMut = useMutation({
    mutationFn: () => sendMessage({ subject, body, filter }),
    onSuccess: (data) => { setSendResult(data); setPreviewResult(null) },
  })

  const canSend = subject.trim() && body.trim()

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">Messaggi ai clienti</h1>

      <div className="card p-5 space-y-4">
        <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide">Destinatari</h2>

        {/* Filter type */}
        <div className="grid grid-cols-2 gap-2">
          {FILTER_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFilter({ type: opt.value })}
              className={clsx(
                'px-3 py-2 rounded-lg border text-sm text-left transition-colors',
                filter.type === opt.value
                  ? 'border-primary bg-primary/10 text-primary font-medium'
                  : 'border-border hover:bg-muted'
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Filter params */}
        {filter.type === 'product_buyers' && (
          <div>
            <label className="label block mb-1">Prodotto</label>
            <select
              className="input"
              value={filter.product_id ?? ''}
              onChange={e => setFilter({ ...filter, product_id: e.target.value ? Number(e.target.value) : undefined })}
            >
              <option value="">Seleziona prodotto…</option>
              {products.map(p => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
        )}

        {filter.type === 'inactive' && (
          <div>
            <label className="label block mb-1">Inattivi da almeno (giorni)</label>
            <input
              type="number" min={1} className="input w-32"
              value={filter.inactive_days ?? 90}
              onChange={e => setFilter({ ...filter, inactive_days: Number(e.target.value) })}
            />
          </div>
        )}

        {filter.type === 'birthday_month' && (
          <div>
            <label className="label block mb-1">Mese di compleanno</label>
            <select
              className="input"
              value={filter.birthday_month ?? ''}
              onChange={e => setFilter({ ...filter, birthday_month: e.target.value ? Number(e.target.value) : undefined })}
            >
              <option value="">Seleziona mese…</option>
              {MONTHS.map((m, i) => (
                <option key={i + 1} value={i + 1}>{m}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="card p-5 space-y-4">
        <h2 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide">Messaggio</h2>
        <div>
          <label className="label block mb-1">Oggetto</label>
          <input
            className="input"
            placeholder="Es. Offerta speciale per te!"
            value={subject}
            onChange={e => setSubject(e.target.value)}
          />
        </div>
        <div>
          <label className="label block mb-1">Testo</label>
          <textarea
            className="input"
            rows={5}
            placeholder="Scrivi qui il messaggio…"
            value={body}
            onChange={e => setBody(e.target.value)}
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        <button
          className="btn-secondary flex items-center gap-2"
          disabled={!canSend || previewMut.isPending}
          onClick={() => previewMut.mutate()}
        >
          <Eye className="w-4 h-4" />
          {previewMut.isPending ? 'Caricamento…' : 'Anteprima destinatari'}
        </button>
        <button
          className="btn-primary flex items-center gap-2"
          disabled={!canSend || sendMut.isPending}
          onClick={() => sendMut.mutate()}
        >
          <Send className="w-4 h-4" />
          {sendMut.isPending ? 'Invio in corso…' : 'Invia messaggio'}
        </button>
      </div>

      {/* Preview result */}
      {previewResult && (
        <div className="card p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Users className="w-4 h-4 text-primary" />
            <span>{previewResult.count} destinatari trovati</span>
          </div>
          {previewResult.count > 0 && (
            <div className="divide-y divide-border">
              {previewResult.recipients.slice(0, 10).map(r => (
                <div key={r.id} className="py-1.5 flex items-center justify-between text-sm">
                  <span>{r.first_name} {r.last_name}</span>
                  <span className="text-muted-foreground text-xs">{r.email ?? 'nessuna email'}</span>
                </div>
              ))}
              {previewResult.count > 10 && (
                <p className="pt-2 text-xs text-muted-foreground">…e altri {previewResult.count - 10}</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Send result */}
      {sendResult && (
        <div className="card p-4 space-y-1 text-sm">
          <p className="text-emerald-600 font-medium">Messaggio inviato!</p>
          <p>Inviati: <span className="font-medium">{sendResult.sent}</span></p>
          {sendResult.skipped > 0 && (
            <p className="text-amber-600">Saltati (senza email): {sendResult.skipped}</p>
          )}
          {sendResult.errors > 0 && (
            <p className="text-red-600">Errori: {sendResult.errors}</p>
          )}
        </div>
      )}
    </div>
  )
}
