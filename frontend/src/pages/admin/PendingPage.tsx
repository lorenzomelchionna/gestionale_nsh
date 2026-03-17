import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Check, X, Clock, ArrowRight } from 'lucide-react'
import {
  getPendingAppointments, confirmAppointment,
  rejectAppointment, rescheduleAppointment
} from '@/services/api'
import { useState } from 'react'
import type { Appointment } from '@/types'

export default function PendingPage() {
  const qc = useQueryClient()
  const inv = () => qc.invalidateQueries({ queryKey: ['appointments'] })

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

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Caricamento...</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-foreground">Richieste in attesa</h1>
        {appointments && appointments.length > 0 && (
          <span className="bg-amber-100 text-amber-800 text-sm font-bold px-2 py-0.5 rounded-full">
            {appointments.length}
          </span>
        )}
      </div>

      {!appointments?.length ? (
        <div className="card p-12 text-center text-muted-foreground">
          <Clock className="w-10 h-10 mx-auto mb-3 opacity-40" />
          <p>Nessuna richiesta in attesa</p>
        </div>
      ) : (
        <div className="space-y-3">
          {appointments.map(appt => (
            <PendingCard
              key={appt.id}
              appointment={appt}
              onConfirm={() => confirmMut.mutate(appt.id)}
              onReject={(reason) => rejectMut.mutate({ id: appt.id, reason })}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function PendingCard({ appointment: a, onConfirm, onReject }: {
  appointment: Appointment
  onConfirm: () => void
  onReject: (reason?: string) => void
}) {
  const [showReject, setShowReject] = useState(false)
  const [reason, setReason] = useState('')

  return (
    <div className="card p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-foreground">{a.client_name}</span>
            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">online</span>
          </div>
          <p className="text-sm text-muted-foreground">
            {format(parseISO(a.start_time), 'EEEE d MMMM yyyy', { locale: it })} ·{' '}
            {format(parseISO(a.start_time), 'HH:mm')} – {format(parseISO(a.end_time), 'HH:mm')}
          </p>
          <p className="text-sm text-muted-foreground">Con: {a.collaborator_name}</p>
          <p className="text-sm font-medium">€{(a.total_price ?? 0).toFixed(2)}</p>
          {a.notes && <p className="text-xs text-muted-foreground italic">"{a.notes}"</p>}
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={onConfirm}
            className="flex items-center gap-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-sm px-3 py-1.5 rounded-md"
          >
            <Check className="w-4 h-4" /> Conferma
          </button>
          <button
            onClick={() => setShowReject(true)}
            className="flex items-center gap-1.5 bg-red-500 hover:bg-red-600 text-white text-sm px-3 py-1.5 rounded-md"
          >
            <X className="w-4 h-4" /> Rifiuta
          </button>
        </div>
      </div>

      {showReject && (
        <div className="mt-3 pt-3 border-t border-border space-y-2">
          <input
            className="input text-sm"
            placeholder="Motivo rifiuto (opzionale)"
            value={reason}
            onChange={e => setReason(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={() => { onReject(reason || undefined); setShowReject(false) }}
              className="btn-danger text-sm py-1"
            >
              Conferma rifiuto
            </button>
            <button onClick={() => setShowReject(false)} className="btn-secondary text-sm py-1">Annulla</button>
          </div>
        </div>
      )}
    </div>
  )
}
