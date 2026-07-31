import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Bell, Trash2, Clock, UserCheck } from 'lucide-react'
import {
  getWaitlist, notifyWaitlistEntry, fulfilWaitlistEntry, deleteWaitlistEntry,
} from '@/services/api'
import type { WaitlistEntryWithNames, WaitlistStatus } from '@/types'
import { PageHeader, EmptyState, SkeletonList, Segmented } from '@/components/ui'

const STATUS_LABEL: Record<WaitlistStatus, string> = {
  waiting: 'In attesa',
  notified: 'Notificato',
  fulfilled: 'Soddisfatto',
  cancelled: 'Annullato',
}

/* The four states borrow the appointment badges rather than inventing a second
   set: waiting is pencilled in, notified agreed, fulfilled posted, cancelled
   struck out — the same four marks the register uses everywhere else. */
const STATUS_BADGE: Record<WaitlistStatus, string> = {
  waiting: 'status-pending',
  notified: 'status-confirmed',
  fulfilled: 'status-completed',
  cancelled: 'status-cancelled',
}

type Filter = WaitlistStatus | 'all'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'all', label: 'Tutti' },
  { value: 'waiting', label: 'In attesa' },
  { value: 'notified', label: 'Notificati' },
  { value: 'fulfilled', label: 'Soddisfatti' },
  { value: 'cancelled', label: 'Annullati' },
]

export default function WaitlistPage() {
  const qc = useQueryClient()
  const inv = () => qc.invalidateQueries({ queryKey: ['waitlist'] })

  const [statusFilter, setStatusFilter] = useState<Filter>('all')

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['waitlist', statusFilter],
    queryFn: () => getWaitlist(statusFilter === 'all' ? undefined : statusFilter),
    refetchInterval: 30_000,
  })

  const notifyMut = useMutation({ mutationFn: notifyWaitlistEntry, onSuccess: inv })
  const fulfilMut = useMutation({ mutationFn: fulfilWaitlistEntry, onSuccess: inv })
  const deleteMut = useMutation({ mutationFn: deleteWaitlistEntry, onSuccess: inv })

  const waitingCount = entries.filter(e => e.status === 'waiting').length

  if (isLoading) return <SkeletonList rows={3} />

  return (
    <div className="space-y-5">
      <PageHeader
        title="Lista d'attesa"
        subtitle={waitingCount > 0 ? `${waitingCount} in attesa` : undefined}
      />

      <Segmented options={FILTERS} value={statusFilter} onChange={setStatusFilter} />

      {entries.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={Clock}
            title="Lista d'attesa vuota"
            description="Le iscrizioni dei clienti compaiono qui."
          />
        </div>
      ) : (
        <div className="flex flex-col gap-3.5">
          {entries.map(entry => (
            <WaitlistRow
              key={entry.id}
              entry={entry}
              onNotify={() => notifyMut.mutate(entry.id)}
              onFulfil={() => fulfilMut.mutate(entry.id)}
              onDelete={() => deleteMut.mutate(entry.id)}
              isLoading={notifyMut.isPending || fulfilMut.isPending || deleteMut.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** A small-caps label over the fact it names — the design's way of laying out
    the particulars of a request. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="flex flex-col gap-1.5 min-w-0">
      <span className="kicker">{label}</span>
      <span className="text-[15px] text-foreground truncate">{children}</span>
    </span>
  )
}

function WaitlistRow({
  entry: e,
  onNotify,
  onFulfil,
  onDelete,
  isLoading,
}: {
  entry: WaitlistEntryWithNames
  onNotify: () => void
  onFulfil: () => void
  onDelete: () => void
  isLoading: boolean
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="panel flex items-stretch">
      {/* A gold bar down the edge marks an entry that is still someone's turn. */}
      <div
        className={e.status === 'waiting' || e.status === 'notified' ? 'w-[3px] bg-primary shrink-0' : 'w-[3px] bg-rule shrink-0'}
        aria-hidden="true"
      />

      <div className="flex-1 min-w-0 flex flex-col lg:flex-row lg:items-stretch">
        <div className="flex-1 min-w-0 px-5 py-4 flex flex-col gap-3">
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="font-heading text-[21px] tracking-[0.03em] text-foreground">
              {e.client_name}
            </span>
            <span className={`status-badge ${STATUS_BADGE[e.status]}`}>
              {STATUS_LABEL[e.status]}
            </span>
            <span className="note ml-auto tabular-nums shrink-0">
              iscritto il {format(parseISO(e.created_at), 'd MMM yyyy HH:mm', { locale: it })}
            </span>
          </div>

          <div className="flex gap-8 flex-wrap">
            <Fact label="Servizio">{e.service_name}</Fact>
            <Fact label="Operatore">
              {e.collaborator_name ?? <span className="italic text-ink-3">chiunque</span>}
            </Fact>
            <Fact label="Quando">
              {e.preferred_date ? (
                <span className="tabular-nums">
                  {format(parseISO(e.preferred_date), 'd MMMM yyyy', { locale: it })}
                </span>
              ) : (
                <span className="italic text-ink-3">prima disponibilità</span>
              )}
            </Fact>
            {e.notified_at && (
              <Fact label="Notificato">
                <span className="tabular-nums">
                  {format(parseISO(e.notified_at), 'd MMM HH:mm', { locale: it })}
                </span>
              </Fact>
            )}
          </div>

          {e.notes && <p className="note">{e.notes}</p>}
        </div>

        {/* Actions sit in their own column behind a rule, the way the design
            separates what you can do from what you are reading. */}
        <div className="shrink-0 flex lg:flex-col justify-center gap-2.5 px-5 py-4 border-t lg:border-t-0 lg:border-l border-rule-soft">
          {confirmDelete ? (
            <>
              <button
                onClick={() => { onDelete(); setConfirmDelete(false) }}
                disabled={isLoading}
                className="btn-danger btn-sm flex-1 lg:flex-none"
              >
                Conferma
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="btn-secondary btn-sm flex-1 lg:flex-none"
              >
                Annulla
              </button>
            </>
          ) : (
            <>
              {e.status === 'waiting' && (
                <button
                  onClick={onNotify}
                  disabled={isLoading}
                  className="btn-primary btn-sm flex-1 lg:flex-none"
                >
                  <Bell className="w-3.5 h-3.5" /> Notifica
                </button>
              )}
              {(e.status === 'waiting' || e.status === 'notified') && (
                <button
                  onClick={onFulfil}
                  disabled={isLoading}
                  className="btn-accent btn-sm flex-1 lg:flex-none"
                >
                  <UserCheck className="w-3.5 h-3.5" /> Soddisfatto
                </button>
              )}
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={isLoading}
                className="btn-icon !w-10 !h-10 hover:text-danger shrink-0 self-center"
                aria-label="Rimuovi dalla lista"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
