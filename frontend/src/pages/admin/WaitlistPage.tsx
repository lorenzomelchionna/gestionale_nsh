import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Bell, CheckCircle, Trash2, Clock, UserCheck, Filter } from 'lucide-react'
import {
  getWaitlist, notifyWaitlistEntry, fulfilWaitlistEntry, deleteWaitlistEntry,
} from '@/services/api'
import type { WaitlistEntryWithNames, WaitlistStatus } from '@/types'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'

const STATUS_LABEL: Record<WaitlistStatus, string> = {
  waiting: 'In attesa',
  notified: 'Notificato',
  fulfilled: 'Soddisfatto',
  cancelled: 'Annullato',
}

const STATUS_COLOR: Record<WaitlistStatus, string> = {
  waiting: 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300',
  notified: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  fulfilled: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  cancelled: 'bg-gray-100 text-gray-500 dark:bg-gray-500/15 dark:text-gray-400',
}

export default function WaitlistPage() {
  const qc = useQueryClient()
  const inv = () => qc.invalidateQueries({ queryKey: ['waitlist'] })

  const [statusFilter, setStatusFilter] = useState<WaitlistStatus | ''>('')

  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['waitlist', statusFilter],
    queryFn: () => getWaitlist(statusFilter || undefined),
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

      <div className="flex items-center gap-2">
        <Filter className="w-4 h-4 text-muted-foreground shrink-0" />
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as WaitlistStatus | '')}
          className="input !min-h-[2.5rem] text-[13px] py-1.5 flex-1 sm:max-w-xs"
          aria-label="Filtra per stato"
        >
          <option value="">Tutti</option>
          <option value="waiting">In attesa</option>
          <option value="notified">Notificati</option>
          <option value="fulfilled">Soddisfatti</option>
          <option value="cancelled">Annullati</option>
        </select>
      </div>

      {entries.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Clock}
            title="Lista d'attesa vuota"
            description="Le iscrizioni dei clienti compaiono qui."
          />
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map(entry => (
            <WaitlistCard
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

function WaitlistCard({
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
    <div className="card p-4">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="space-y-1 min-w-0">
          {/* Client + status */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-foreground">{e.client_name}</span>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_COLOR[e.status]}`}>
              {STATUS_LABEL[e.status]}
            </span>
          </div>

          {/* Service + collaborator */}
          <p className="text-sm text-muted-foreground">
            Servizio: <span className="font-medium text-foreground">{e.service_name}</span>
            {e.collaborator_name && (
              <> · Con: <span className="font-medium text-foreground">{e.collaborator_name}</span></>
            )}
            {!e.collaborator_name && <> · <span className="italic">Qualsiasi collaboratore</span></>}
          </p>

          {/* Preferred date */}
          {e.preferred_date && (
            <p className="text-sm text-muted-foreground">
              Data preferita:{' '}
              <span className="font-medium text-foreground">
                {format(parseISO(e.preferred_date), 'd MMMM yyyy', { locale: it })}
              </span>
            </p>
          )}
          {!e.preferred_date && (
            <p className="text-sm text-muted-foreground italic">Prima disponibilità</p>
          )}

          {/* Notes */}
          {e.notes && <p className="text-xs text-muted-foreground italic">"{e.notes}"</p>}

          {/* Timestamps */}
          <p className="text-xs text-muted-foreground">
            Iscritto il {format(parseISO(e.created_at), 'd MMM yyyy HH:mm', { locale: it })}
            {e.notified_at && (
              <> · Notificato il {format(parseISO(e.notified_at), 'd MMM yyyy HH:mm', { locale: it })}</>
            )}
          </p>
        </div>

        {/* Actions stretch to full width on phones so each stays tappable. */}
        <div className="flex gap-2 shrink-0 pt-1 sm:pt-0">
          {confirmDelete ? (
            <>
              <button
                onClick={() => { onDelete(); setConfirmDelete(false) }}
                disabled={isLoading}
                className="btn-danger btn-sm flex-1 sm:flex-none"
              >
                Conferma
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="btn-secondary btn-sm flex-1 sm:flex-none"
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
                  className="btn-primary btn-sm flex-1 sm:flex-none !bg-blue-600 hover:!bg-blue-700"
                >
                  <Bell className="w-4 h-4" /> Notifica
                </button>
              )}
              {(e.status === 'waiting' || e.status === 'notified') && (
                <button
                  onClick={onFulfil}
                  disabled={isLoading}
                  className="btn-primary btn-sm flex-1 sm:flex-none !bg-emerald-600 hover:!bg-emerald-700"
                >
                  <UserCheck className="w-4 h-4" /> Soddisfatto
                </button>
              )}
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={isLoading}
                className="btn-icon !w-10 !h-10 hover:text-danger shrink-0"
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
