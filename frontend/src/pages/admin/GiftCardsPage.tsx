import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import {
  Plus, Gift, Mail, MailCheck, Ban, ChevronRight, Copy, Check, X,
} from 'lucide-react'
import {
  getGiftCards, createGiftCard, redeemGiftCard, cancelGiftCard,
  resendGiftCardEmail, getAppointments,
} from '@/services/api'
import type { Appointment, GiftCard, GiftCardStatus } from '@/types'
import Sheet from '@/components/ui/Sheet'
import {
  PageHeader, SearchInput, Segmented, EmptyState, SkeletonList, Pagination,
} from '@/components/ui'
import clsx from 'clsx'

const STATUS_OPTIONS: { value: GiftCardStatus | ''; label: string }[] = [
  { value: '', label: 'Tutti' },
  { value: 'attiva', label: 'Attivi' },
  { value: 'esaurita', label: 'Esauriti' },
  { value: 'scaduta', label: 'Scaduti' },
  { value: 'annullata', label: 'Annullati' },
]

/** Lo stato riusa i colori già in uso per gli appuntamenti: chi legge il
 *  gestionale ha già imparato che il verde è vivo e il barrato è chiuso. */
const STATUS_CLASS: Record<GiftCardStatus, string> = {
  attiva: 'status-confirmed',
  esaurita: 'status-completed',
  scaduta: 'status-rejected',
  annullata: 'status-cancelled',
}

const IMPORTI_RAPIDI = [20, 30, 50, 100]

export default function GiftCardsPage() {
  const [search, setSearch] = useState('')
  const [termine, setTermine] = useState('')
  const [statusFilter, setStatusFilter] = useState<GiftCardStatus | ''>('')
  const [page, setPage] = useState(1)
  const [showCreate, setShowCreate] = useState(false)
  const [selected, setSelected] = useState<GiftCard | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      setTermine(search.trim().length >= 2 ? search.trim() : '')
      setPage(1)
    }, 350)
    return () => clearTimeout(t)
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['gift-cards', page, termine, statusFilter],
    queryFn: () => getGiftCards({
      search: termine || undefined,
      status: statusFilter || undefined,
      page, page_size: 50,
    }),
  })

  const cards = data?.items ?? []
  const filtrato = Boolean(termine || statusFilter)

  // Quanto il salone deve ancora: la somma dei crediti che qualcuno può
  // ancora presentare al banco. È il numero che rende una gift card diversa
  // da un incasso qualunque — quei soldi sono entrati, ma sono già promessi.
  const daOnorare = cards
    .filter(c => c.status === 'attiva')
    .reduce((somma, c) => somma + c.balance, 0)

  return (
    <div className="space-y-5">
      <PageHeader
        title="Buoni regalo"
        subtitle={data ? `${data.total} emessi` : undefined}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo buono
          </button>
        }
      />

      {daOnorare > 0 && (
        <div className="panel px-4 py-3.5 flex items-baseline justify-between gap-3">
          <span className="kicker">Credito ancora da onorare</span>
          <span className="font-heading text-[22px] text-primary-dark tabular-nums">
            €{daOnorare.toFixed(2)}
          </span>
        </div>
      )}

      <div className="space-y-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Cerca per codice, destinatario o acquirente…"
        />
        <Segmented
          options={STATUS_OPTIONS}
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
        />
      </div>

      {isLoading ? (
        <SkeletonList rows={4} />
      ) : cards.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Gift}
            title={filtrato ? 'Nessun risultato' : 'Nessun buono emesso'}
            description={
              filtrato
                ? 'Prova con un altro codice, nome o stato.'
                : 'Vendi il primo buono regalo: il codice arriva per email a chi lo riceve.'
            }
            action={
              !filtrato && (
                <button onClick={() => setShowCreate(true)} className="btn-primary">
                  <Plus className="w-4 h-4" /> Nuovo buono
                </button>
              )
            }
          />
        </div>
      ) : (
        <div className="panel">
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Codice</th>
                  <th>Destinatario</th>
                  <th className="hidden sm:table-cell">Scadenza</th>
                  <th className="num">Valore</th>
                  <th className="num">Residuo</th>
                  <th className="text-right">Stato</th>
                  <th className="w-px" />
                </tr>
              </thead>
              <tbody>
                {cards.map(c => (
                  <tr
                    key={c.id}
                    onClick={() => setSelected(c)}
                    className="cursor-pointer hover:bg-foreground/[0.05] transition-colors"
                  >
                    <td className="font-mono text-[13px] whitespace-nowrap">{c.code}</td>
                    <td>
                      <span className="text-foreground">{c.recipient_name}</span>
                      <span className="block text-[13px] text-ink-3 truncate">
                        {c.recipient_email}
                      </span>
                    </td>
                    <td className="hidden sm:table-cell tabular-nums text-muted-foreground whitespace-nowrap">
                      {format(parseISO(c.expires_at), 'dd/MM/yyyy')}
                    </td>
                    <td className="num tabular-nums text-muted-foreground">
                      €{c.initial_amount.toFixed(2)}
                    </td>
                    <td className="num">
                      <span className="amount">€{c.balance.toFixed(2)}</span>
                    </td>
                    <td className="text-right">
                      <span className={clsx('status-badge', STATUS_CLASS[c.status])}>
                        {c.status}
                      </span>
                    </td>
                    <td className="w-px text-ink-3">
                      <ChevronRight className="w-4 h-4" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && (
            <Pagination
              page={page} pages={data.pages} total={data.total}
              unit="buoni" onChange={setPage}
            />
          )}
        </div>
      )}

      {showCreate && <CreateSheet onClose={() => setShowCreate(false)} />}
      {selected && (
        <DetailSheet
          card={cards.find(c => c.id === selected.id) ?? selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

function CreateSheet({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    amount: 50,
    recipient_name: '',
    recipient_email: '',
    purchaser_name: '',
    message: '',
    payment_method: 'contanti' as 'contanti' | 'carta',
  })

  const salva = useMutation({
    mutationFn: () => createGiftCard({
      amount: Number(form.amount),
      recipient_name: form.recipient_name.trim(),
      recipient_email: form.recipient_email.trim(),
      purchaser_name: form.purchaser_name.trim() || undefined,
      message: form.message.trim() || undefined,
      payment_method: form.payment_method,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['gift-cards'] })
      // La vendita è un incasso di oggi: la cassa cambia adesso, non quando
      // il buono verrà speso.
      qc.invalidateQueries({ queryKey: ['payments'] })
      onClose()
    },
  })

  const valido =
    form.recipient_name.trim().length > 0 &&
    /\S+@\S+\.\S+/.test(form.recipient_email) &&
    form.amount >= 5

  return (
    <Sheet
      onClose={onClose}
      title="Nuovo buono regalo"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">
            Annulla
          </button>
          <button
            type="submit" form="gift-card-form"
            disabled={!valido || salva.isPending}
            className="btn-primary btn-sm"
          >
            {salva.isPending ? 'Emissione...' : 'Emetti e invia'}
          </button>
        </>
      }
    >
      <form
        id="gift-card-form"
        onSubmit={e => { e.preventDefault(); salva.mutate() }}
        className="space-y-4"
      >
        <div>
          <label className="label">Importo</label>
          {/* Quattro tagli grossi più il campo libero: al banco si vendono
              quasi sempre cifre tonde, e digitarle ogni volta è tempo perso. */}
          <div className="grid grid-cols-4 gap-2 mb-2">
            {IMPORTI_RAPIDI.map(v => (
              <button
                key={v} type="button"
                onClick={() => setForm({ ...form, amount: v })}
                className={clsx(
                  'min-h-touch border font-heading text-[13px] tabular-nums transition-colors',
                  form.amount === v
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-surface text-muted-foreground hover:bg-foreground/[0.05]'
                )}
              >
                €{v}
              </button>
            ))}
          </div>
          <input
            className="input tabular-nums" type="number" inputMode="decimal"
            step="0.01" min="5" max="1000"
            value={form.amount}
            onChange={e => setForm({ ...form, amount: Number(e.target.value) })}
          />
        </div>

        <div className="border-t border-rule pt-4 space-y-4">
          <span className="kicker">Chi lo riceve</span>
          <div>
            <label className="label">Nome *</label>
            <input
              className="input" required
              value={form.recipient_name}
              onChange={e => setForm({ ...form, recipient_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Email *</label>
            <input
              className="input" type="email" required inputMode="email"
              placeholder="dove arriva il buono"
              value={form.recipient_email}
              onChange={e => setForm({ ...form, recipient_email: e.target.value })}
            />
            {/* Detto qui perché è il punto della funzionalità, e perché è
                anche l'errore più facile da fare al banco. */}
            <p className="text-xs text-muted-foreground mt-1.5">
              Il codice arriva a questo indirizzo, non a chi paga.
            </p>
          </div>
          <div>
            <label className="label">Dedica</label>
            <textarea
              className="input min-h-[64px] resize-y" rows={2}
              placeholder="Due righe che compaiono nell'email"
              value={form.message}
              onChange={e => setForm({ ...form, message: e.target.value })}
            />
          </div>
        </div>

        <div className="border-t border-rule pt-4 space-y-4">
          <span className="kicker">Chi lo compra</span>
          <div>
            <label className="label">Nome</label>
            <input
              className="input"
              placeholder="Facoltativo, compare nell'email"
              value={form.purchaser_name}
              onChange={e => setForm({ ...form, purchaser_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Come paga</label>
            <div className="grid grid-cols-2 gap-2">
              {(['contanti', 'carta'] as const).map(m => (
                <button
                  key={m} type="button"
                  onClick={() => setForm({ ...form, payment_method: m })}
                  className={clsx(
                    'min-h-touch border font-heading text-[12px] uppercase tracking-[0.1em] transition-colors',
                    form.payment_method === m
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border bg-surface text-muted-foreground hover:bg-foreground/[0.05]'
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-1.5">
              L'incasso entra in cassa oggi. Quando il buono verrà speso non si
              registra nessun nuovo pagamento.
            </p>
          </div>
        </div>

        {salva.isError && (
          <p className="text-[13px] text-danger">{leggiErrore(salva.error)}</p>
        )}
      </form>
    </Sheet>
  )
}

function DetailSheet({ card, onClose }: { card: GiftCard; onClose: () => void }) {
  const qc = useQueryClient()
  const [importo, setImporto] = useState('')
  const [showCancel, setShowCancel] = useState(false)
  const [motivo, setMotivo] = useState('')
  const [nuovaEmail, setNuovaEmail] = useState('')
  const [copiato, setCopiato] = useState(false)
  const [cercaVisita, setCercaVisita] = useState('')
  const [visita, setVisita] = useState<Appointment | null>(null)

  const aggiorna = () => qc.invalidateQueries({ queryKey: ['gift-cards'] })

  // Cercata per nome invece che scelta da un elenco: al banco si sta
  // chiudendo una cliente precisa, e sfogliare tutti gli appuntamenti del
  // mese per trovarla sarebbe più lento che digitarne il cognome.
  const { data: visite } = useQuery({
    queryKey: ['gift-card-visite', cercaVisita],
    queryFn: () => getAppointments({
      search: cercaVisita, order: 'desc', page_size: 8,
    }),
    enabled: cercaVisita.trim().length >= 2,
  })

  const riscatta = useMutation({
    mutationFn: () => redeemGiftCard(card.id, {
      amount: Number(importo),
      appointment_id: visita?.id,
    }),
    onSuccess: () => {
      aggiorna(); setImporto(''); setVisita(null); setCercaVisita('')
    },
  })
  const storna = useMutation({
    mutationFn: () => cancelGiftCard(card.id, motivo.trim() || undefined),
    onSuccess: () => { aggiorna(); onClose() },
  })
  const rimanda = useMutation({
    mutationFn: () => resendGiftCardEmail(card.id, nuovaEmail.trim() || undefined),
    onSuccess: () => { aggiorna(); setNuovaEmail('') },
  })

  const copiaCodice = async () => {
    await navigator.clipboard.writeText(card.code)
    setCopiato(true)
    setTimeout(() => setCopiato(false), 1500)
  }

  const spendibile = card.status === 'attiva'
  const importoValido =
    Number(importo) > 0 && Number(importo) <= card.balance

  return (
    <Sheet
      onClose={onClose}
      title="Buono regalo"
      description={`Emesso il ${format(parseISO(card.created_at), 'd MMMM yyyy', { locale: it })}`}
      size="md"
    >
      <div className="border border-border bg-band px-4 py-3.5 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <span className="kicker">Codice</span>
          <p className="font-mono text-[17px] tracking-[0.08em] text-foreground mt-1 break-all">
            {card.code}
          </p>
        </div>
        <button
          type="button" onClick={copiaCodice}
          className="btn-icon hover:text-primary shrink-0"
          aria-label="Copia il codice"
        >
          {copiato ? <Check className="w-4 h-4 text-primary" /> : <Copy className="w-4 h-4" />}
        </button>
      </div>

      <div className="border-t border-rule-soft mt-4">
        <Row label="Residuo">
          <span className="amount text-[17px]">€{card.balance.toFixed(2)}</span>
          <span className="text-ink-3"> di €{card.initial_amount.toFixed(2)}</span>
        </Row>
        <Row label="Stato">
          <span className={clsx('status-badge', STATUS_CLASS[card.status])}>
            {card.status}
          </span>
        </Row>
        <Row label="Destinatario">
          {card.recipient_name}
          <span className="block text-[13px] text-ink-3">{card.recipient_email}</span>
        </Row>
        {card.purchaser_name && <Row label="Acquirente">{card.purchaser_name}</Row>}
        <Row label="Scadenza">
          {format(parseISO(card.expires_at), 'd MMMM yyyy', { locale: it })}
        </Row>
        {card.message && (
          <Row label="Dedica">
            <span className="italic">«{card.message}»</span>
          </Row>
        )}
        <Row label="Email">
          {card.email_sent_at ? (
            <span className="inline-flex items-center gap-1.5 text-[13px]">
              <MailCheck className="w-3.5 h-3.5 text-primary" />
              inviata il {format(parseISO(card.email_sent_at), 'd MMM yyyy, HH:mm', { locale: it })}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-[13px] text-danger">
              <Mail className="w-3.5 h-3.5" /> non ancora partita
            </span>
          )}
        </Row>
        {card.cancel_reason && <Row label="Motivo storno">{card.cancel_reason}</Row>}
      </div>

      {spendibile && (
        <div className="mt-4 border-t border-rule pt-4 space-y-2">
          <span className="kicker">Usa il buono</span>
          <div className="flex gap-2">
            <input
              className="input tabular-nums flex-1" type="number" inputMode="decimal"
              step="0.01" min="0.01" max={card.balance}
              placeholder={`fino a €${card.balance.toFixed(2)}`}
              value={importo}
              onChange={e => setImporto(e.target.value)}
            />
            <button
              type="button"
              onClick={() => riscatta.mutate()}
              disabled={!importoValido || riscatta.isPending}
              className="btn-primary btn-sm shrink-0"
            >
              {riscatta.isPending ? 'Scalo...' : 'Scala'}
            </button>
          </div>
          {/* L'importo si scrive perché quasi mai coincide col totale: un
              buono da 50 su un servizio da 70 ne copre 50, il resto si paga
              normalmente in cassa. */}
          <p className="text-xs text-muted-foreground">
            Scala solo la parte coperta dal buono. Il resto si incassa come sempre.
          </p>

          {/* Facoltativo, e detto: senza appuntamento il riscatto resta
              valido — capita per un prodotto, o per chi passa senza
              prenotare. Con l'appuntamento resta scritto su cosa è finito. */}
          {visita ? (
            <div className="flex items-center justify-between gap-3 border border-border bg-band px-3 py-2.5">
              <span className="text-[13px] text-foreground min-w-0 truncate">
                {format(parseISO(visita.start_time), 'dd/MM/yyyy')} · {visita.client_name}
                <span className="text-ink-3">
                  {' · '}{visita.service_names?.join(' + ') || '–'}
                </span>
              </span>
              <button
                type="button"
                onClick={() => { setVisita(null); setCercaVisita('') }}
                className="btn-icon shrink-0"
                aria-label="Togli l'appuntamento"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <input
                className="input text-sm"
                placeholder="Collega a un appuntamento (facoltativo): cerca la cliente…"
                value={cercaVisita}
                onChange={e => setCercaVisita(e.target.value)}
              />
              {(visite?.items?.length ?? 0) > 0 && (
                <div className="border border-border divide-y divide-rule-soft max-h-44 overflow-y-auto">
                  {visite!.items.map(a => (
                    <button
                      key={a.id} type="button"
                      onClick={() => setVisita(a)}
                      className="w-full text-left px-3 py-2 text-[13px] hover:bg-foreground/[0.05] transition-colors"
                    >
                      <span className="tabular-nums text-muted-foreground">
                        {format(parseISO(a.start_time), 'dd/MM/yyyy')}
                      </span>
                      {' · '}{a.client_name}
                      <span className="block text-ink-3 truncate">
                        {a.service_names?.join(' + ') || '–'}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {riscatta.isError && (
            <p className="text-[13px] text-danger">{leggiErrore(riscatta.error)}</p>
          )}
        </div>
      )}

      {card.redemptions.length > 0 && (
        <div className="mt-4 border-t border-rule pt-4">
          <span className="kicker">Come è stato speso</span>
          <div className="mt-2 divide-y divide-rule-soft">
            {card.redemptions.map(r => (
              <div key={r.id} className="flex items-baseline justify-between gap-3 py-2">
                <span className="text-[13px] text-muted-foreground tabular-nums min-w-0">
                  {format(parseISO(r.created_at), 'd MMM yyyy, HH:mm', { locale: it })}
                  {r.appointment_label && (
                    <span className="block text-[13px] text-ink-3 truncate">
                      {r.appointment_label}
                    </span>
                  )}
                </span>
                <span className="amount shrink-0">−€{r.amount.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {card.status !== 'annullata' && (
        <div className="mt-4 border-t border-rule pt-4 space-y-3">
          <div className="space-y-2">
            <span className="kicker">Rimanda l'email</span>
            <div className="flex gap-2">
              <input
                className="input flex-1" type="email" inputMode="email"
                placeholder="Altro indirizzo (facoltativo)"
                value={nuovaEmail}
                onChange={e => setNuovaEmail(e.target.value)}
              />
              <button
                type="button"
                onClick={() => rimanda.mutate()}
                disabled={rimanda.isPending}
                className="btn-secondary btn-sm shrink-0"
              >
                <Mail className="w-3.5 h-3.5" />
                {rimanda.isPending ? 'Invio...' : 'Invia'}
              </button>
            </div>
          </div>

          {!showCancel ? (
            <button
              type="button"
              onClick={() => setShowCancel(true)}
              className="btn-danger-outline btn-sm w-full"
            >
              <Ban className="w-3.5 h-3.5" /> Annulla il buono
            </button>
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5">
                Il buono non sarà più spendibile. Quello che è già stato speso
                resta scritto.
              </p>
              <input
                className="input"
                placeholder="Motivo (es. rimborsato in contanti)"
                value={motivo}
                onChange={e => setMotivo(e.target.value)}
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowCancel(false)}
                  className="btn-secondary btn-sm flex-1"
                >
                  Indietro
                </button>
                <button
                  type="button"
                  onClick={() => storna.mutate()}
                  disabled={storna.isPending}
                  className="btn-danger btn-sm flex-1"
                >
                  Conferma storno
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </Sheet>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 py-2.5 border-b border-rule-soft">
      <span className="kicker w-28 shrink-0 pt-1">{label}</span>
      <span className="text-sm text-foreground min-w-0 break-words">{children}</span>
    </div>
  )
}

function leggiErrore(e: any): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msg = detail.map((d: any) => d?.msg).filter(Boolean).join(' · ')
    if (msg) return msg
  }
  return 'Operazione non riuscita. Riprova.'
}
