import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { CalendarSearch, ChevronRight, NotebookPen } from 'lucide-react'
import { getAppointments, getCollaborators, updateAppointment } from '@/services/api'
import type { Appointment } from '@/types'
import Sheet from '@/components/ui/Sheet'
import {
  PageHeader, SearchInput, Segmented, EmptyState, SkeletonList, Pagination,
} from '@/components/ui'
import clsx from 'clsx'

const STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  confirmed: 'Confermato',
  rejected: 'Rifiutato',
  rescheduled: 'Riprogrammato',
  completed: 'Completato',
  cancelled: 'Annullato',
}

const STATUS_OPTIONS = [
  { value: '', label: 'Tutti' },
  { value: 'completed', label: 'Completati' },
  { value: 'confirmed', label: 'Confermati' },
  { value: 'pending', label: 'In attesa' },
  { value: 'cancelled', label: 'Annullati' },
  { value: 'rejected', label: 'Rifiutati' },
]

/** L'archivio completo degli appuntamenti.
 *
 *  Il calendario mostra una giornata alla volta e «In attesa» un solo stato,
 *  quindi finora a «quando è venuta l'ultima volta?» non rispondeva nessuna
 *  schermata. Questa legge dallo stesso endpoint del calendario, con l'ordine
 *  invertito: qui si parte da ieri e si va indietro. */
export default function AppointmentsPage() {
  const [search, setSearch] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [collaboratorId, setCollaboratorId] = useState<number | ''>('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<Appointment | null>(null)

  // Il termine cercato aspetta che si smetta di scrivere: senza attesa ogni
  // lettera è una query, e il backend ne rifiuta comunque una sola.
  const [termine, setTermine] = useState('')
  useEffect(() => {
    const t = setTimeout(() => {
      setTermine(search.trim().length >= 2 ? search.trim() : '')
      setPage(1)
    }, 350)
    return () => clearTimeout(t)
  }, [search])

  const { data: collabsData } = useQuery({
    queryKey: ['collaborators-active'],
    queryFn: () => getCollaborators({ active_only: true }),
  })
  const collaborators = collabsData?.items ?? []

  const filtri = {
    search: termine || undefined,
    date_from: dateFrom ? `${dateFrom}T00:00:00` : undefined,
    date_to: dateTo ? `${dateTo}T23:59:59` : undefined,
    status: statusFilter || undefined,
    collaborator_id: collaboratorId === '' ? undefined : collaboratorId,
  }

  const { data, isLoading } = useQuery({
    queryKey: ['appointments-list', page, filtri],
    queryFn: () => getAppointments({ ...filtri, order: 'desc', page, page_size: 50 }),
  })

  const appointments = data?.items ?? []
  const filtrato = Boolean(
    termine || dateFrom || dateTo || statusFilter || collaboratorId !== ''
  )

  const azzera = () => {
    setSearch(''); setDateFrom(''); setDateTo('')
    setStatusFilter(''); setCollaboratorId(''); setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Appuntamenti"
        subtitle={data ? `${data.total} in archivio` : undefined}
      />

      <div className="space-y-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Cerca per nome, cognome o telefono…"
        />

        <Segmented
          options={STATUS_OPTIONS}
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
        />

        {/* Le date restano due campi espliciti e non scorciatoie tipo «ultimi
            30 giorni»: chi cerca uno storico di solito sa il mese. */}
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label className="label">Dal</label>
            <input
              type="date" className="input tabular-nums"
              value={dateFrom}
              onChange={e => { setDateFrom(e.target.value); setPage(1) }}
            />
          </div>
          <div>
            <label className="label">Al</label>
            <input
              type="date" className="input tabular-nums"
              value={dateTo}
              onChange={e => { setDateTo(e.target.value); setPage(1) }}
            />
          </div>
          <div>
            <label className="label">Collaboratore</label>
            <select
              className="input"
              value={collaboratorId}
              onChange={e => {
                setCollaboratorId(e.target.value === '' ? '' : Number(e.target.value))
                setPage(1)
              }}
            >
              <option value="">Tutti</option>
              {collaborators.map(c => (
                <option key={c.id} value={c.id}>
                  {c.first_name} {c.last_name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {filtrato && (
          <button onClick={azzera} className="btn-secondary btn-sm">
            Azzera filtri
          </button>
        )}
      </div>

      {isLoading ? (
        <SkeletonList rows={6} />
      ) : appointments.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={CalendarSearch}
            title={filtrato ? 'Nessun risultato' : 'Nessun appuntamento'}
            description={
              filtrato
                ? 'Prova con un altro nome, periodo o stato.'
                : 'Gli appuntamenti compaiono qui appena vengono registrati.'
            }
          />
        </div>
      ) : (
        <>
          {/* Telefono: una riga per appuntamento, non una tabella di sei
              colonne che uscirebbe di lato. */}
          <div className="panel sm:hidden divide-y divide-rule-soft">
            {appointments.map(a => (
              <button
                key={a.id}
                onClick={() => setSelected(a)}
                className="w-full text-left px-4 py-3.5 flex items-start justify-between gap-3 hover:bg-foreground/[0.05] transition-colors"
              >
                <div className="min-w-0">
                  <p className="font-heading text-[15px] tracking-[0.03em] text-foreground tabular-nums">
                    {format(parseISO(a.start_time), 'dd/MM/yyyy')}
                    <span className="text-ink-3">
                      {' · '}{format(parseISO(a.start_time), 'HH:mm')}
                    </span>
                  </p>
                  <p className="text-sm text-foreground truncate mt-0.5">{a.client_name}</p>
                  <p className="text-[13px] text-muted-foreground truncate">
                    {a.service_names?.length ? a.service_names.join(' + ') : '–'}
                    {a.collaborator_name && (
                      <span className="text-ink-3"> · {a.collaborator_name}</span>
                    )}
                  </p>
                  {a.visit_notes && (
                    <p className="text-[13px] italic text-ink-2 mt-1 line-clamp-2">
                      {a.visit_notes}
                    </p>
                  )}
                </div>
                <div className="text-right shrink-0 flex flex-col items-end gap-1.5">
                  <span className="amount">€{(a.total_price ?? 0).toFixed(2)}</span>
                  <span className={clsx('status-badge', `status-${a.status}`)}>
                    {STATUS_LABELS[a.status] ?? a.status}
                  </span>
                </div>
              </button>
            ))}
            {data && (
              <Pagination
                page={page} pages={data.pages} total={data.total}
                unit="appuntamenti" onChange={setPage}
              />
            )}
          </div>

          <div className="panel hidden sm:block">
            <div className="table-scroll">
              <table className="ledger">
                <thead>
                  <tr>
                    <th>Data</th>
                    <th>Cliente</th>
                    <th>Servizio</th>
                    <th>Operatore</th>
                    <th className="num">Importo</th>
                    <th className="text-right">Stato</th>
                    <th className="w-px" />
                  </tr>
                </thead>
                <tbody>
                  {appointments.map(a => (
                    <tr
                      key={a.id}
                      onClick={() => setSelected(a)}
                      className="cursor-pointer hover:bg-foreground/[0.05] transition-colors"
                    >
                      <td className="tabular-nums whitespace-nowrap">
                        {format(parseISO(a.start_time), 'dd/MM/yyyy')}
                        <span className="text-ink-3">
                          {' · '}{format(parseISO(a.start_time), 'HH:mm')}
                        </span>
                      </td>
                      <td className="text-foreground">{a.client_name}</td>
                      <td className="text-muted-foreground">
                        {a.service_names?.length ? a.service_names.join(' + ') : '–'}
                        {/* La nota sotto il servizio, che è la riga che si va
                            a cercare: «che colore le ho fatto a marzo?» */}
                        {a.visit_notes && (
                          <span className="block text-[13px] italic text-ink-2 mt-1 line-clamp-2">
                            {a.visit_notes}
                          </span>
                        )}
                      </td>
                      <td className="text-ink-3">{a.collaborator_name ?? '–'}</td>
                      <td className="num">
                        <span className="amount">€{(a.total_price ?? 0).toFixed(2)}</span>
                      </td>
                      <td className="text-right">
                        <span className={clsx('status-badge', `status-${a.status}`)}>
                          {STATUS_LABELS[a.status] ?? a.status}
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
                unit="appuntamenti" onChange={setPage}
              />
            )}
          </div>
        </>
      )}

      {selected && (
        <AppointmentSheet
          appointment={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}

/** La scheda di un appuntamento, con la sua nota modificabile.
 *
 *  Si scrive normalmente chiudendo la visita dal calendario; qui si corregge
 *  o si aggiunge dopo, che è il caso di chi se ne ricorda mezz'ora più tardi
 *  o sta rileggendo lo storico. */
function AppointmentSheet({ appointment: a, onClose }: {
  appointment: Appointment
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [nota, setNota] = useState(a.visit_notes ?? '')

  const salva = useMutation({
    // `null` e non stringa vuota: la colonna ammette NULL e «nessuna nota» è
    // una cosa sola, non due che si somigliano.
    mutationFn: () => updateAppointment(a.id, { visit_notes: nota.trim() || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments-list'] })
      qc.invalidateQueries({ queryKey: ['appointments'] })
      qc.invalidateQueries({ queryKey: ['client-appointments'] })
      onClose()
    },
  })

  const cambiata = (a.visit_notes ?? '') !== nota

  return (
    <Sheet
      onClose={onClose}
      title="Appuntamento"
      description={format(parseISO(a.start_time), "EEEE d MMMM yyyy 'alle' HH:mm", { locale: it })}
      size="md"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">
            Chiudi
          </button>
          <button
            type="button"
            onClick={() => salva.mutate()}
            disabled={!cambiata || salva.isPending}
            className="btn-primary btn-sm"
          >
            {salva.isPending ? 'Salvataggio...' : 'Salva nota'}
          </button>
        </>
      }
    >
      <div className="border-t border-rule-soft">
        <Row label="Cliente">
          <Link
            to={`/admin/clients/${a.client_id}`}
            className="text-primary-dark hover:underline"
          >
            {a.client_name || '–'}
          </Link>
        </Row>
        <Row label="Collaboratore">{a.collaborator_name || '–'}</Row>
        <Row label="Servizi">
          {a.service_names?.length ? a.service_names.join(' + ') : '–'}
        </Row>
        <Row label="Orario">
          {format(parseISO(a.start_time), 'HH:mm')} → {format(parseISO(a.end_time), 'HH:mm')}
        </Row>
        <Row label="Totale">€{(a.total_price ?? 0).toFixed(2)}</Row>
        <Row label="Stato">
          <span className={clsx('status-badge', `status-${a.status}`)}>
            {STATUS_LABELS[a.status] ?? a.status}
          </span>
        </Row>
        {a.notes && <Row label="Note">{a.notes}</Row>}
        {a.rejection_reason && <Row label="Motivo">{a.rejection_reason}</Row>}
      </div>

      <div className="pt-4 space-y-2">
        <span className="kicker flex items-center gap-1.5">
          <NotebookPen className="w-3.5 h-3.5" /> Nota della visita
        </span>
        <textarea
          className="input text-sm" rows={4}
          placeholder="Colore usato, tempi di posa, come ha reagito il capello…"
          value={nota}
          onChange={e => setNota(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          La legge solo il salone: dal portale la cliente non la vede.
        </p>
        {salva.isError && (
          <p className="text-[13px] text-danger">Salvataggio non riuscito. Riprova.</p>
        )}
      </div>
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
