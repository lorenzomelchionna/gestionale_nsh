import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Send, Eye, Mail, MessageCircle } from 'lucide-react'
import { getProducts, previewMessage, sendMessage } from '@/services/api'
import type { MessageFilter, FilterType } from '@/types'
import { PageHeader } from '@/components/ui'
import clsx from 'clsx'

type Channel = 'email' | 'whatsapp' | 'both'

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

/** A titled sheet: the section named on its band, the controls underneath. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel">
      <div className="band px-5 py-3">
        <span className="kicker">{title}</span>
      </div>
      <div className="p-5 flex flex-col gap-4">{children}</div>
    </div>
  )
}

/** A squared option cell; the chosen one is marked in gold, as everywhere. */
function Option({ on, onClick, children }: {
  on: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className={clsx(
        'flex items-center justify-center gap-2 px-3 py-2.5 min-h-touch border text-[13px] transition-colors text-center',
        on
          ? 'border-primary bg-primary/10 text-primary-dark'
          : 'border-border text-muted-foreground hover:bg-foreground/[0.05]'
      )}
    >
      {children}
    </button>
  )
}

export default function MessagingPage() {
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [filter, setFilter] = useState<MessageFilter>({ type: 'all' })
  const [channel, setChannel] = useState<Channel>('both')
  const [previewResult, setPreviewResult] = useState<{ count: number; recipients: { id: number; first_name: string; last_name: string; email: string | null; phone: string | null }[] } | null>(null)
  const [sendResult, setSendResult] = useState<{ sent: number; skipped: number; errors: number; sent_email?: number; sent_whatsapp?: number } | null>(null)

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
    mutationFn: () => sendMessage({ subject, body, filter, channel }),
    onSuccess: (data) => { setSendResult(data); setPreviewResult(null) },
  })

  // WA mode: no subject required
  const canSend = body.trim() && (channel === 'whatsapp' || subject.trim())

  return (
    <div className="space-y-5 max-w-2xl">
      <PageHeader title="Messaggi ai clienti" />

      <Section title="Destinatari">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {FILTER_OPTIONS.map(opt => (
            <Option
              key={opt.value}
              on={filter.type === opt.value}
              onClick={() => setFilter({ type: opt.value })}
            >
              {opt.label}
            </Option>
          ))}
        </div>

        {filter.type === 'product_buyers' && (
          <div>
            <label className="label">Prodotto</label>
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
            <label className="label">Inattivi da almeno (giorni)</label>
            <input
              type="number" min={1} className="input w-32 tabular-nums"
              value={filter.inactive_days ?? 90}
              onChange={e => setFilter({ ...filter, inactive_days: Number(e.target.value) })}
            />
          </div>
        )}

        {filter.type === 'birthday_month' && (
          <div>
            <label className="label">Mese di compleanno</label>
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
      </Section>

      <Section title="Canale">
        <div className="grid grid-cols-3 gap-2">
          {([
            { value: 'email',    label: 'Email',    icon: Mail },
            { value: 'whatsapp', label: 'WhatsApp', icon: MessageCircle },
            { value: 'both',     label: 'Entrambi', icon: Send },
          ] as const).map(opt => {
            const Icon = opt.icon
            return (
              <Option
                key={opt.value}
                on={channel === opt.value}
                onClick={() => setChannel(opt.value)}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {opt.label}
              </Option>
            )
          })}
        </div>
        <p className="note">
          {channel === 'email' && "Solo i clienti con email riceveranno il messaggio."}
          {channel === 'whatsapp' && "Solo i clienti con telefono riceveranno il messaggio (WhatsApp deve essere abilitato in Impostazioni)."}
          {channel === 'both' && "Ogni cliente riceverà su entrambi i canali se ha email e telefono."}
        </p>
      </Section>

      <Section title="Messaggio">
        {channel !== 'whatsapp' && (
          <div>
            <label className="label">
              Oggetto {channel === 'both' && <span className="normal-case tracking-normal">(solo email)</span>}
            </label>
            <input
              className="input"
              placeholder="Es. Offerta speciale per te!"
              value={subject}
              onChange={e => setSubject(e.target.value)}
            />
          </div>
        )}
        <div>
          <label className="label">Testo</label>
          <textarea
            className="input"
            rows={5}
            placeholder={
              channel === 'whatsapp'
                ? "Scrivi qui il messaggio (WA, no HTML). Usa {nome} per personalizzare."
                : "Scrivi qui il messaggio… Usa {nome} per personalizzare."
            }
            value={body}
            onChange={e => setBody(e.target.value)}
          />
          {channel === 'whatsapp' && (
            <p className="text-xs text-ink-3 mt-1.5">
              WA non supporta HTML — il testo viene inviato così com'è.
            </p>
          )}
        </div>
      </Section>

      <div className="flex gap-2.5">
        <button
          className="btn-secondary"
          disabled={!canSend || previewMut.isPending}
          onClick={() => previewMut.mutate()}
        >
          <Eye className="w-4 h-4" />
          {previewMut.isPending ? 'Caricamento…' : 'Anteprima destinatari'}
        </button>
        <button
          className="btn-primary"
          disabled={!canSend || sendMut.isPending}
          onClick={() => sendMut.mutate()}
        >
          <Send className="w-4 h-4" />
          {sendMut.isPending ? 'Invio in corso…' : 'Invia messaggio'}
        </button>
      </div>

      {/* Who would receive it — the list is capped at ten, and says so, rather
          than quietly showing a slice as if it were the whole. */}
      {previewResult && (
        <div className="panel">
          <div className="band px-5 py-3 flex items-baseline gap-2">
            <span className="kicker">Destinatari trovati</span>
            <span className="ml-auto font-heading text-lg text-foreground tabular-nums">
              {previewResult.count}
            </span>
          </div>
          {previewResult.count > 0 && (
            <>
              {previewResult.recipients.slice(0, 10).map(r => (
                <div
                  key={r.id}
                  className="flex items-baseline justify-between gap-3 px-5 py-2.5 border-b border-rule-soft"
                >
                  <span className="text-sm text-foreground truncate">
                    {r.first_name} {r.last_name}
                  </span>
                  <span className="text-[13px] text-ink-3 truncate">
                    {r.email ?? 'nessuna email'}
                  </span>
                </div>
              ))}
              {previewResult.count > 10 && (
                <p className="ledger-foot">…e altri {previewResult.count - 10}</p>
              )}
            </>
          )}
        </div>
      )}

      {sendResult && (
        <div className="panel">
          <div className="band px-5 py-3">
            <span className="kicker">Esito dell'invio</span>
          </div>
          <div className="divide-y divide-rule-soft">
            <ResultRow label="Clienti raggiunti" value={sendResult.sent} strong />
            {sendResult.sent_email !== undefined && (
              <>
                <ResultRow label="Via email" value={sendResult.sent_email} />
                <ResultRow label="Via WhatsApp" value={sendResult.sent_whatsapp ?? 0} />
              </>
            )}
            {sendResult.skipped > 0 && (
              <ResultRow label="Saltati (senza contatti validi)" value={sendResult.skipped} />
            )}
            {sendResult.errors > 0 && (
              <ResultRow label="Errori" value={sendResult.errors} danger />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ResultRow({ label, value, strong = false, danger = false }: {
  label: string
  value: number
  strong?: boolean
  danger?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-5 py-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={clsx(
          'tabular-nums font-heading',
          strong ? 'text-[19px]' : 'text-[15px]',
          danger ? 'text-danger' : strong ? 'text-primary-dark' : 'text-foreground'
        )}
      >
        {value}
      </span>
    </div>
  )
}
