import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { differenceInMinutes, format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Clock, CalendarDays, User, Check, X } from 'lucide-react'
import {
  getPendingAppointments, confirmAppointment, rejectAppointment,
} from '@/services/api'
import type { Appointment } from '@/types'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'

export default function PendingPage() {
  const qc = useQueryClient()
  const inv = () => {
    qc.invalidateQueries({ queryKey: ['appointments'] })
    qc.invalidateQueries({ queryKey: ['pending-appointments'] })
  }

  const { data: appointments, isLoading } = useQuery({
    queryKey: ['pending-appointments'],
    queryFn: getPendingAppointments,
    refetchInterval: 30_000,
  })

  const confirmMut = useMutation({ mutationFn: confirmAppointment, onSuccess: inv })
  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => rejectAppointment(id, reason),
    onSuccess: inv,
  })

  const count = appointments?.length ?? 0

  return (
    <div className="space-y-5">
      <PageHeader
        title="Richieste in attesa"
        subtitle={count > 0 ? `${count} da gestire` : undefined}
      />

      {isLoading ? (
        <SkeletonList rows={3} />
      ) : count === 0 ? (
        <div className="card">
          <EmptyState
            icon={Clock}
            title="Nessuna richiesta in attesa"
            description="Le prenotazioni online da confermare compaiono qui."
          />
        </div>
      ) : (
        <div className="space-y-3">
          {appointments!.map(appt => (
            <PendingCard
              key={appt.id}
              appointment={appt}
              busy={confirmMut.isPending || rejectMut.isPending}
              onConfirm={() => confirmMut.mutate(appt.id)}
              onReject={(reason) => rejectMut.mutate({ id: appt.id, reason })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PendingCard({ appointment: a, busy, onConfirm, onReject }: {
  appointment: Appointment
  busy: boolean
  onConfirm: () => void
  onReject: (reason?: string) => void
}) {
  const [showReject, setShowReject] = useState(false)
  const [reason, setReason] = useState('')

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-foreground">{a.client_name}</span>
            <span className="text-[10px] font-semibold bg-info/12 text-info px-1.5 py-0.5 rounded">
              online
            </span>
            {a.replaces_appointment_id && (
              <span className="text-[10px] font-semibold bg-warning/15 text-warning px-1.5 py-0.5 rounded">
                modifica
              </span>
            )}
          </div>
          {/* Una richiesta di modifica (2026-10-13): il «prima», così si decide
              senza cercarlo in calendario. Fino alla conferma vale quello;
              confermando, quello si annulla. */}
          {a.replaces_appointment_id && a.replaces_start_time && (
            <p className="text-[12px] text-muted-foreground border-l-2 border-warning/60 pl-2">
              Al posto di:{' '}
              <span className="line-through decoration-ink-3/60">
                {format(parseISO(a.replaces_start_time), "EEE d MMM 'alle' HH:mm", { locale: it })}
                {a.replaces_collaborator_name && ` · ${a.replaces_collaborator_name}`}
                {a.replaces_service_names?.length ? ` · ${a.replaces_service_names.join(' + ')}` : ''}
              </span>
              <br />
              Confermando, l'appuntamento di prima viene annullato; rifiutando, resta.
            </p>
          )}
          <p className="text-[13px] text-muted-foreground flex items-start gap-1.5">
            <CalendarDays className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>
              {format(parseISO(a.start_time), 'EEEE d MMMM', { locale: it })}
              <span className="text-foreground font-medium">
                {' · '}
                {format(parseISO(a.start_time), 'HH:mm')}–{format(parseISO(a.end_time), 'HH:mm')}
              </span>
            </span>
          </p>
          <p className="text-[13px] text-muted-foreground flex items-center gap-1.5">
            <User className="w-3.5 h-3.5 shrink-0" />
            {a.collaborator_name}
          </p>
          {a.notes && (
            <p className="text-xs text-muted-foreground italic border-l-2 border-border pl-2 mt-2">
              {a.notes}
            </p>
          )}
        </div>
        <span className="text-base font-bold text-foreground tabular-nums shrink-0">
          €{(a.total_price ?? 0).toFixed(2)}
        </span>
      </div>

      {/* Actions go full-width side by side on phones — both stay thumb-sized. */}
      {!showReject && (
        <div className="flex gap-2 mt-4">
          <button
            onClick={onConfirm}
            disabled={busy}
            className="btn-primary btn-sm flex-1 !bg-action hover:!bg-action"
          >
            <Check className="w-4 h-4" /> Conferma
          </button>
          <button
            onClick={() => setShowReject(true)}
            disabled={busy}
            className="btn-outline btn-sm flex-1 !text-danger"
          >
            <X className="w-4 h-4" /> Rifiuta
          </button>
        </div>
      )}

      {showReject && (
        <div className="mt-4 pt-4 border-t border-border space-y-3">
          <div>
            <label className="label">Motivo del rifiuto (opzionale)</label>
            <input
              className="input"
              placeholder="Es. orario non disponibile"
              value={reason}
              onChange={e => setReason(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { onReject(reason || undefined); setShowReject(false) }}
              disabled={busy}
              className="btn-danger btn-sm flex-1"
            >
              Conferma rifiuto
            </button>
            <button
              onClick={() => { setShowReject(false); setReason('') }}
              className="btn-secondary btn-sm flex-1"
            >
              Annulla
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
