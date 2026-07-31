import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Link } from 'react-router-dom'
import { X, Check } from 'lucide-react'
import {
  getMyAppointments, cancelMyAppointment, acceptAlternative, rejectAlternative,
  getMyWaitlist, leaveWaitlist,
} from '@/services/publicApi'
import clsx from 'clsx'
import type { Appointment, WaitlistEntry } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  confirmed: 'Confermato',
  rejected: 'Rifiutato',
  rescheduled: 'Proposta alternativa',
  completed: 'Completato',
  cancelled: 'Annullato',
}

export default function BookingAccountPage() {
  // Signed-in state is guaranteed by RequireClient on the route; the old
  // in-render redirect also broke the rules-of-hooks order below it.
  const qc = useQueryClient()

  const { data: appointments, isLoading } = useQuery({
    queryKey: ['my-appointments'],
    queryFn: getMyAppointments,
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['my-appointments'] })
  const cancelMut = useMutation({ mutationFn: cancelMyAppointment, onSuccess: inv })
  const acceptMut = useMutation({ mutationFn: acceptAlternative, onSuccess: inv })
  const rejectMut = useMutation({ mutationFn: rejectAlternative, onSuccess: inv })

  const { data: waitlist = [] } = useQuery({
    queryKey: ['my-waitlist'],
    queryFn: getMyWaitlist,
  })
  const invWaitlist = () => qc.invalidateQueries({ queryKey: ['my-waitlist'] })
  const leaveMut = useMutation({ mutationFn: leaveWaitlist, onSuccess: invWaitlist })

  const activeWaitlist = waitlist.filter(w => w.status === 'waiting' || w.status === 'notified')

  const now = new Date()
  const upcoming = appointments?.filter(a =>
    ['pending', 'confirmed', 'rescheduled'].includes(a.status) && parseISO(a.start_time) > now
  ) ?? []
  const past = appointments?.filter(a =>
    a.status === 'completed' || parseISO(a.start_time) <= now
  ) ?? []

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-3 border-b border-rule pb-3.5">
        <h1 className="text-title-lg text-foreground">La mia area</h1>
        <Link to="/booking/new" className="btn-accent btn-sm">
          Nuova prenotazione
        </Link>
      </div>

      {/* A proposed time is the one thing on this page that asks something of
          the client, so it leads and it is the only gold-edged panel. */}
      {upcoming.filter(a => a.status === 'rescheduled').map(a => (
        <div key={a.id} className="panel border-primary bg-primary/10 p-5 flex flex-col gap-2.5">
          <span className="kicker text-primary-dark">Nuovo orario proposto</span>
          <p className="font-heading text-[19px] leading-snug tracking-[0.03em] text-foreground first-letter:uppercase">
            {format(parseISO(a.alternative_time!), 'EEEE d MMMM', { locale: it })} alle{' '}
            <span className="tabular-nums">
              {format(parseISO(a.alternative_time!), 'HH:mm')}
            </span>
            {a.collaborator_name && `, con ${a.collaborator_name}`}
          </p>
          <div className="flex gap-2 mt-1">
            <button
              onClick={() => acceptMut.mutate(a.id)}
              className="btn-primary btn-sm flex-1"
            >
              <Check className="w-3.5 h-3.5" /> Accetta
            </button>
            <button
              onClick={() => rejectMut.mutate(a.id)}
              className="btn-danger-outline btn-sm flex-1"
            >
              <X className="w-3.5 h-3.5" /> Rifiuta
            </button>
          </div>
        </div>
      ))}

      <section className="flex flex-col gap-3">
        <span className="kicker">Prossimi</span>
        {isLoading ? (
          <p className="note">Caricamento…</p>
        ) : upcoming.filter(a => a.status !== 'rescheduled').length === 0 ? (
          <p className="note">Nessun appuntamento in programma.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {upcoming.filter(a => a.status !== 'rescheduled').map(a => (
              <AppointmentCard
                key={a.id}
                appointment={a}
                onCancel={() => cancelMut.mutate(a.id)}
              />
            ))}
          </div>
        )}
      </section>

      {activeWaitlist.length > 0 && (
        <section className="flex flex-col gap-3">
          <span className="kicker">Lista d'attesa</span>
          <div className="flex flex-col gap-2.5">
            {activeWaitlist.map(w => (
              <WaitlistCard
                key={w.id}
                entry={w}
                onLeave={() => leaveMut.mutate(w.id)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Past visits are a record, not a list of things to act on — they read
          as ruled lines rather than as panels. */}
      {past.length > 0 && (
        <section className="flex flex-col gap-3">
          <span className="kicker">Storico</span>
          <div className="flex flex-col">
            {past.slice(0, 10).map(a => (
              <div
                key={a.id}
                className="flex items-baseline gap-3 py-3 border-b border-rule-soft last:border-b-0"
              >
                <span className="flex-1 min-w-0 text-[13px] leading-relaxed text-ink-2">
                  <span className="tabular-nums first-letter:uppercase">
                    {format(parseISO(a.start_time), 'd MMM yyyy', { locale: it })}
                    {' · '}
                    {format(parseISO(a.start_time), 'HH:mm')}
                  </span>
                  <br />
                  <span className="text-ink-3">{a.collaborator_name}</span>
                </span>
                <span className="text-[13px] tabular-nums text-muted-foreground shrink-0">
                  {a.total_price !== undefined ? `€${a.total_price.toFixed(2)}` : '–'}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function WaitlistCard({ entry: w, onLeave }: { entry: WaitlistEntry; onLeave: () => void }) {
  const notified = w.status === 'notified'
  return (
    <div
      className={clsx(
        'panel px-5 py-4 flex items-center justify-between gap-4',
        notified && 'border-primary bg-primary/10'
      )}
    >
      <div className="min-w-0 flex flex-col gap-1">
        {notified && (
          <span className="kicker text-primary-dark">Si è liberato un posto</span>
        )}
        <span className="font-heading text-[17px] tracking-[0.03em] text-foreground">
          {w.preferred_date
            ? <span className="tabular-nums">
                {format(parseISO(w.preferred_date), 'd MMMM yyyy', { locale: it })}
              </span>
            : 'Prima disponibilità'}
        </span>
        {w.notes && <span className="note">{w.notes}</span>}
        <span className="text-xs text-ink-3 tabular-nums">
          iscritto il {format(parseISO(w.created_at), 'd MMM yyyy', { locale: it })}
        </span>
      </div>
      <button
        onClick={onLeave}
        className="text-[13px] text-danger hover:underline shrink-0"
      >
        Rimuovi
      </button>
    </div>
  )
}

function AppointmentCard({ appointment: a, onCancel }: { appointment: Appointment; onCancel?: () => void }) {
  const canCancel = onCancel && a.status === 'confirmed'
  return (
    <div className="panel px-5 py-4 flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-heading text-[19px] leading-tight tracking-[0.03em] text-foreground first-letter:uppercase">
          {format(parseISO(a.start_time), 'EEEE d MMMM', { locale: it })}
          <span className="text-ink-3 tabular-nums">
            {' · '}{format(parseISO(a.start_time), 'HH:mm')}
          </span>
        </span>
        <span className={clsx('status-badge shrink-0', `status-${a.status}`)}>
          {STATUS_LABELS[a.status]}
        </span>
      </div>

      <div className="flex items-baseline justify-between gap-3">
        {/* The API declares `service_names` but never fills it, so the person
            is the only thing there is to name here. */}
        <span className="text-[13px] text-muted-foreground truncate">
          {a.collaborator_name}
        </span>
        {a.total_price !== undefined && (
          <span className="text-[15px] tabular-nums text-primary-dark shrink-0">
            €{a.total_price.toFixed(2)}
          </span>
        )}
      </div>

      {canCancel && (
        <button onClick={onCancel} className="btn-danger-outline btn-sm w-full mt-2.5">
          Annulla appuntamento
        </button>
      )}
    </div>
  )
}
