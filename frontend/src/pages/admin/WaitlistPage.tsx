import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Bell, CheckCircle, Trash2, Clock, UserCheck, Filter } from 'lucide-react'
import {
  getWaitlist, notifyWaitlistEntry, fulfilWaitlistEntry, deleteWaitlistEntry,
} from '@/services/api'
import type { WaitlistEntryWithNames, WaitlistStatus } from '@/types'

const STATUS_LABEL: Record<WaitlistStatus, string> = {
  waiting: 'In attesa',
  notified: 'Notificato',
  fulfilled: 'Soddisfatto',
  cancelled: 'Annullato',
}

const STATUS_COLOR: Record<WaitlistStatus, string> = {
  waiting: 'bg-amber-100 text-amber-800',
  notified: 'bg-blue-100 text-blue-700',
  fulfilled: 'bg-emerald-100 text-emerald-700',
  cancelled: 'bg-gray-100 text-gray-500',
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

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Caricamento...</div>

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-foreground">Lista d'attesa</h1>
          {waitingCount > 0 && (
            <span className="bg-amber-100 text-amber-800 text-sm font-bold px-2 py-0.5 rounded-full">
              {waitingCount}
            </span>
          )}
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-muted-foreground" />
          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as WaitlistStatus | '')}
            className="input text-sm py-1.5 pr-8"
          >
            <option value="">Tutti</option>
            <option value="waiting">In attesa</option>
            <option value="notified">Notificati</option>
            <option value="fulfilled">Soddisfatti</option>
            <option value="cancelled">Annullati</option>
          </select>
        </div>
      </div>

      {entries.length === 0 ? (
        <div className="card p-12 text-center text-muted-foreground">
          <Clock className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p>Nessuna iscrizione in lista d'attesa</p>
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
      <div className="flex items-start justify-between gap-4 flex-wrap">
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

        {/* Actions */}
        <div className="flex gap-2 flex-shrink-0 flex-wrap">
          {e.status === 'waiting' && (
            <button
              onClick={onNotify}
              disabled={isLoading}
              className="flex items-center gap-1.5 bg-blue-500 hover:bg-blue-600 text-white text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
            >
              <Bell className="w-4 h-4" /> Notifica
            </button>
          )}
          {(e.status === 'waiting' || e.status === 'notified') && (
            <button
              onClick={onFulfil}
              disabled={isLoading}
              className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm px-3 py-1.5 rounded-md disabled:opacity-50"
            >
              <UserCheck className="w-4 h-4" /> Soddisfatto
            </button>
          )}
          {confirmDelete ? (
            <div className="flex gap-1.5">
              <button
                onClick={() => { onDelete(); setConfirmDelete(false) }}
                disabled={isLoading}
                className="btn-danger text-sm py-1 px-2"
              >
                Conferma
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="btn-secondary text-sm py-1 px-2"
              >
                Annulla
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              disabled={isLoading}
              className="flex items-center gap-1.5 text-red-500 hover:text-red-700 text-sm px-2 py-1.5 disabled:opacity-50"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
