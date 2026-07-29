import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { format, parseISO, addMinutes } from 'date-fns'
import { it } from 'date-fns/locale'
import { Check, ChevronLeft, CalendarX, Loader2 } from 'lucide-react'
import {
  publicGetServices, publicGetCollaborators, publicGetAvailability, bookAppointment
} from '@/services/publicApi'
import AvailabilityCalendar from '@/components/booking/AvailabilityCalendar'
import { useNavigate } from 'react-router-dom'
import type { Service, Collaborator } from '@/types'
import clsx from 'clsx'

type Step = 'service' | 'collaborator' | 'datetime' | 'confirm' | 'done'

const ORDER: Step[] = ['service', 'collaborator', 'datetime', 'confirm']
const STEP_LABELS: Record<string, string> = {
  service: 'Servizio',
  collaborator: 'Con chi',
  datetime: 'Quando',
  confirm: 'Conferma',
}

export default function BookingFlowPage() {
  const [step, setStep] = useState<Step>('service')
  const [selectedService, setSelectedService] = useState<Service | null>(null)
  const [selectedCollab, setSelectedCollab] = useState<Collaborator | null>(null)
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedSlot, setSelectedSlot] = useState('')
  const navigate = useNavigate()

  const { data: services } = useQuery({
    queryKey: ['public-services'],
    queryFn: publicGetServices,
  })

  const { data: collaborators } = useQuery({
    queryKey: ['public-collaborators'],
    queryFn: publicGetCollaborators,
    enabled: step === 'collaborator' || step === 'datetime',
  })

  const { data: slots, isLoading: slotsLoading } = useQuery({
    queryKey: ['public-slots', selectedService?.id, selectedCollab?.id, selectedDate],
    queryFn: () => publicGetAvailability({
      service_id: selectedService!.id,
      collaborator_id: selectedCollab!.id,
      target_date: selectedDate,
    }),
    enabled: !!selectedService && !!selectedCollab && !!selectedDate,
  })

  const bookMut = useMutation({
    mutationFn: bookAppointment,
    onSuccess: () => setStep('done'),
  })

  const availableCollabs = selectedService
    ? (collaborators ?? []).filter(c => c.service_ids.includes(selectedService.id))
    : []

  const handleBook = () => {
    // Being signed in is guaranteed by RequireClient on the route — the flow is
    // no longer reachable without an account, so there is nothing to check here.
    if (!selectedService || !selectedCollab || !selectedSlot) return
    const start = parseISO(selectedSlot)
    const end = addMinutes(start, selectedService.duration_slots * 30)
    bookMut.mutate({
      client_id: 0, // resolved server-side from the token
      collaborator_id: selectedCollab.id,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      service_ids: [selectedService.id],
    })
  }

  if (step === 'done') {
    return (
      <div className="text-center space-y-5 py-10">
        <div className="w-16 h-16 bg-emerald-500/15 rounded-full flex items-center justify-center mx-auto">
          <Check className="w-8 h-8 text-emerald-600 dark:text-emerald-400" />
        </div>
        <div>
          <h2 className="text-title font-bold">Richiesta inviata</h2>
          <p className="text-muted-foreground mt-2 max-w-xs mx-auto">
            Il salone confermerà il tuo appuntamento al più presto. Riceverai una notifica.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2.5 sm:justify-center pt-2">
          <button onClick={() => navigate('/booking/account')} className="btn-primary">
            Vai alla mia area
          </button>
          <button
            onClick={() => {
              setStep('service'); setSelectedService(null); setSelectedCollab(null)
              setSelectedDate(''); setSelectedSlot('')
            }}
            className="btn-outline"
          >
            Prenota ancora
          </button>
        </div>
      </div>
    )
  }

  const currentIndex = ORDER.indexOf(step)

  return (
    <div className="space-y-5">
      {/* Progress: a labelled bar reads better on a narrow screen than four
          numbered circles joined by connectors. */}
      <div>
        <div className="flex items-baseline justify-between mb-2">
          <p className="text-sm font-semibold text-foreground">{STEP_LABELS[step]}</p>
          <p className="text-xs text-muted-foreground tabular-nums">
            Passo {currentIndex + 1} di {ORDER.length}
          </p>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-300"
            style={{ width: `${((currentIndex + 1) / ORDER.length) * 100}%` }}
          />
        </div>
      </div>

      {step !== 'service' && (
        <button
          onClick={() => setStep(ORDER[currentIndex - 1])}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground -ml-1"
        >
          <ChevronLeft className="w-4 h-4" /> Indietro
        </button>
      )}

      {/* Step: Service */}
      {step === 'service' && (
        <div className="space-y-3">
          <h2 className="text-title font-bold">Scegli il servizio</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {(services ?? []).map(s => (
              <button
                key={s.id}
                onClick={() => { setSelectedService(s); setStep('collaborator') }}
                className="card-interactive p-4 text-left"
              >
                <p className="font-semibold text-foreground">{s.name}</p>
                {s.description && (
                  <p className="text-[13px] text-muted-foreground mt-0.5">{s.description}</p>
                )}
                <div className="flex items-baseline gap-3 mt-2.5">
                  <span className="text-primary font-bold">€{s.price.toFixed(2)}</span>
                  <span className="text-xs text-muted-foreground">{s.duration_slots * 30} min</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step: Collaborator */}
      {step === 'collaborator' && (
        <div className="space-y-3">
          <h2 className="text-title font-bold">Con chi preferisci?</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {availableCollabs.map(c => (
              <button
                key={c.id}
                onClick={() => { setSelectedCollab(c); setStep('datetime') }}
                className="card-interactive p-4 flex items-center gap-3 text-left"
              >
                <div
                  className="w-11 h-11 rounded-full flex items-center justify-center text-white font-bold shrink-0"
                  style={{ backgroundColor: c.color }}
                >
                  {c.first_name[0]}
                </div>
                <p className="font-semibold text-foreground">
                  {c.first_name} {c.last_name}
                </p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step: DateTime */}
      {step === 'datetime' && (
        <div className="space-y-4">
          <h2 className="text-title font-bold">Data e orario</h2>

          {selectedService && selectedCollab && (
            <AvailabilityCalendar
              serviceId={selectedService.id}
              collaboratorId={selectedCollab.id}
              value={selectedDate}
              onChange={date => { setSelectedDate(date); setSelectedSlot('') }}
            />
          )}

          {selectedDate && (
            slotsLoading ? (
              <p className="flex items-center gap-2 text-muted-foreground text-sm">
                <Loader2 className="w-4 h-4 animate-spin" /> Cerco gli orari liberi...
              </p>
            ) : !slots?.length ? (
              <div className="card p-6 text-center">
                <CalendarX className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                <p className="font-medium text-foreground">Nessun orario disponibile</p>
                <p className="text-[13px] text-muted-foreground mt-1">
                  Prova con un altro giorno.
                </p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-medium mb-2.5">Orari disponibili</p>
                {/* A grid of large targets — wrapped inline chips were only
                    ~34px tall, below a comfortable tap size. */}
                <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
                  {slots.map(slot => (
                    <button
                      key={slot}
                      onClick={() => { setSelectedSlot(slot); setStep('confirm') }}
                      className={clsx(
                        'min-h-touch rounded-lg text-sm font-semibold border transition-colors tabular-nums',
                        selectedSlot === slot
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-border bg-surface hover:border-primary hover:text-primary'
                      )}
                    >
                      {format(parseISO(slot), 'HH:mm')}
                    </button>
                  ))}
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* Step: Confirm */}
      {step === 'confirm' && selectedService && selectedCollab && selectedSlot && (
        <div className="space-y-4">
          <h2 className="text-title font-bold">Riepilogo</h2>
          <div className="card divide-y divide-border">
            <Row label="Servizio" value={selectedService.name} />
            <Row label="Con" value={`${selectedCollab.first_name} ${selectedCollab.last_name}`} />
            <Row
              label="Data"
              value={format(parseISO(selectedDate), 'EEEE d MMMM yyyy', { locale: it })}
            />
            <Row
              label="Orario"
              value={`${format(parseISO(selectedSlot), 'HH:mm')} – ${format(addMinutes(parseISO(selectedSlot), selectedService.duration_slots * 30), 'HH:mm')}`}
            />
            <Row label="Durata" value={`${selectedService.duration_slots * 30} minuti`} />
            <Row label="Prezzo" value={`€${selectedService.price.toFixed(2)}`} emphasis />
          </div>

          <p className="text-xs text-muted-foreground">
            La prenotazione verrà confermata dal salone. Riceverai una notifica.
          </p>

          <button onClick={handleBook} disabled={bookMut.isPending} className="btn-primary w-full">
            {bookMut.isPending
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Invio richiesta...</>
              : 'Invia richiesta'}
          </button>

          {bookMut.isError && (
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
              {(bookMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                ?? 'Errore durante la prenotazione'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ label, value, emphasis }: { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-4 py-3">
      <span className="text-[13px] text-muted-foreground shrink-0">{label}</span>
      <span
        className={clsx(
          'text-right',
          emphasis ? 'font-bold text-primary' : 'font-medium text-foreground text-sm'
        )}
      >
        {value}
      </span>
    </div>
  )
}
