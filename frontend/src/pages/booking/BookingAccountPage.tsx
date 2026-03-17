import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Link, useNavigate } from 'react-router-dom'
import { Calendar, X, Check } from 'lucide-react'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { getMyAppointments, cancelMyAppointment, acceptAlternative, rejectAlternative } from '@/services/publicApi'
import clsx from 'clsx'
import type { Appointment } from '@/types'

const STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  confirmed: 'Confermato',
  rejected: 'Rifiutato',
  rescheduled: 'Proposta alternativa',
  completed: 'Completato',
  cancelled: 'Cancellato',
}

export default function BookingAccountPage() {
  const { token } = useClientAuth()
  const navigate = useNavigate()
  const qc = useQueryClient()

  if (!token) {
    navigate('/booking/login')
    return null
  }

  const { data: appointments, isLoading } = useQuery({
    queryKey: ['my-appointments'],
    queryFn: getMyAppointments,
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['my-appointments'] })
  const cancelMut = useMutation({ mutationFn: cancelMyAppointment, onSuccess: inv })
  const acceptMut = useMutation({ mutationFn: acceptAlternative, onSuccess: inv })
  const rejectMut = useMutation({ mutationFn: rejectAlternative, onSuccess: inv })

  const now = new Date()
  const upcoming = appointments?.filter(a =>
    ['pending', 'confirmed', 'rescheduled'].includes(a.status) && parseISO(a.start_time) > now
  ) ?? []
  const past = appointments?.filter(a =>
    a.status === 'completed' || parseISO(a.start_time) <= now
  ) ?? []

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">La mia area</h2>
        <Link to="/booking/new" className="btn-primary text-sm py-1.5">
          Nuova prenotazione
        </Link>
      </div>

      {/* Rescheduled – action required */}
      {upcoming.filter(a => a.status === 'rescheduled').map(a => (
        <div key={a.id} className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm font-semibold text-blue-900 mb-1">Il salone ha proposto un orario alternativo</p>
          <p className="text-sm text-blue-800">
            <strong>{a.collaborator_name}</strong> –{' '}
            {format(parseISO(a.alternative_time!), 'EEEE d MMMM HH:mm', { locale: it })}
          </p>
          <div className="flex gap-2 mt-3">
            <button
              onClick={() => acceptMut.mutate(a.id)}
              className="flex items-center gap-1 bg-emerald-500 hover:bg-emerald-600 text-white text-sm px-3 py-1.5 rounded-md"
            >
              <Check className="w-3.5 h-3.5" /> Accetta
            </button>
            <button
              onClick={() => rejectMut.mutate(a.id)}
              className="flex items-center gap-1 bg-red-500 hover:bg-red-600 text-white text-sm px-3 py-1.5 rounded-md"
            >
              <X className="w-3.5 h-3.5" /> Rifiuta
            </button>
          </div>
        </div>
      ))}

      {/* Upcoming */}
      <section>
        <h3 className="font-semibold mb-3 flex items-center gap-2">
          <Calendar className="w-4 h-4 text-primary" /> Prossimi appuntamenti
        </h3>
        {isLoading ? (
          <p className="text-muted-foreground text-sm">Caricamento...</p>
        ) : upcoming.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nessun appuntamento in programma</p>
        ) : (
          <div className="space-y-3">
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

      {/* Past */}
      {past.length > 0 && (
        <section>
          <h3 className="font-semibold mb-3 text-muted-foreground">Storico</h3>
          <div className="space-y-2">
            {past.slice(0, 10).map(a => (
              <AppointmentCard key={a.id} appointment={a} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function AppointmentCard({ appointment: a, onCancel }: { appointment: Appointment; onCancel?: () => void }) {
  const isPast = a.status === 'completed' || a.status === 'cancelled' || a.status === 'rejected'
  return (
    <div className={clsx('card p-4 flex items-center justify-between gap-4', isPast && 'opacity-70')}>
      <div className="space-y-0.5">
        <p className="font-semibold text-sm">{a.collaborator_name}</p>
        <p className="text-sm text-muted-foreground">
          {format(parseISO(a.start_time), 'EEEE d MMMM HH:mm', { locale: it })}
        </p>
        {a.total_price !== undefined && (
          <p className="text-xs text-muted-foreground">€{a.total_price.toFixed(2)}</p>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className={clsx('status-badge', `status-${a.status}`)}>
          {STATUS_LABELS[a.status]}
        </span>
        {onCancel && a.status === 'confirmed' && (
          <button onClick={onCancel} className="text-xs text-red-500 hover:text-red-700">
            Cancella
          </button>
        )}
      </div>
    </div>
  )
}
