import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { format, parseISO, addMinutes } from 'date-fns'
import { it } from 'date-fns/locale'
import { Check, CalendarX, Loader2 } from 'lucide-react'
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

/** Half an hour to a slot. */
const MINUTES_PER_SLOT = 30

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
    const end = addMinutes(start, selectedService.duration_slots * MINUTES_PER_SLOT)
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
      <div className="py-10 flex flex-col items-center text-center gap-5">
        <div className="w-14 h-14 border border-primary flex items-center justify-center">
          <Check className="w-6 h-6 text-primary-dark" />
        </div>
        <div>
          <h2 className="text-title text-foreground">Richiesta inviata</h2>
          <p className="text-muted-foreground mt-2 max-w-xs mx-auto">
            Il salone confermerà il tuo appuntamento al più presto. Ti avvisiamo
            via email e WhatsApp.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2.5 w-full sm:w-auto">
          <button onClick={() => navigate('/booking/account')} className="btn-primary sm:px-7">
            Vai alla mia area
          </button>
          <button
            onClick={() => {
              setStep('service'); setSelectedService(null); setSelectedCollab(null)
              setSelectedDate(''); setSelectedSlot('')
            }}
            className="btn-secondary sm:px-7"
          >
            Prenota ancora
          </button>
        </div>
      </div>
    )
  }

  const currentIndex = ORDER.indexOf(step)

  /* Only steps already answered can be reopened. Jumping ahead would leave the
     summary quoting a choice that was never made. */
  const goTo = (target: Step) => {
    const i = ORDER.indexOf(target)
    if (i <= currentIndex) setStep(target)
  }

  return (
    <div className="flex flex-col gap-6">
      {/* The four steps named in a row, the live one in ink and the rest faint,
          over a rule that fills as the booking is answered. */}
      <div className="flex flex-col gap-3.5">
        <div className="flex items-baseline gap-4 flex-wrap">
          {ORDER.map((s, i) => {
            const done = i <= currentIndex
            return (
              <button
                key={s}
                onClick={() => goTo(s)}
                disabled={i > currentIndex}
                className={clsx(
                  'flex items-baseline gap-2',
                  i < currentIndex && 'cursor-pointer hover:opacity-70 transition-opacity',
                  i > currentIndex && 'cursor-default'
                )}
              >
                <span
                  className={clsx(
                    'text-xs tabular-nums',
                    done ? 'text-primary-dark' : 'text-ink-3'
                  )}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <span
                  className={clsx(
                    'font-heading text-[19px] tracking-[0.04em]',
                    i === currentIndex ? 'text-foreground' : 'text-ink-3'
                  )}
                >
                  {STEP_LABELS[s]}
                </span>
              </button>
            )
          })}
          <span className="ml-auto text-xs text-ink-3 tabular-nums">
            Passo {currentIndex + 1} di {ORDER.length}
          </span>
        </div>
        <div className="h-[2px] bg-rule-soft" role="presentation">
          <div
            className="h-full bg-primary transition-all duration-300"
            style={{ width: `${((currentIndex + 1) / ORDER.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Step: Service */}
      {step === 'service' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(services ?? []).filter(s => s.bookable_online).map(s => (
            <button
              key={s.id}
              onClick={() => { setSelectedService(s); setStep('collaborator') }}
              className="panel p-5 text-left flex flex-col gap-2 transition-colors
                         hover:border-primary hover:bg-primary/10"
            >
              <span className="font-heading text-[21px] leading-tight tracking-[0.03em] text-foreground">
                {s.name}
              </span>
              {s.description && (
                <span className="text-[13px] leading-relaxed text-muted-foreground">
                  {s.description}
                </span>
              )}
              <span className="flex items-baseline justify-between mt-2 pt-3 border-t border-rule-soft">
                <span className="text-[18px] tabular-nums text-primary-dark">
                  €{s.price.toFixed(2)}
                </span>
                <span className="text-xs text-ink-3 tabular-nums">
                  {s.duration_slots * MINUTES_PER_SLOT} min
                </span>
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Step: Collaborator */}
      {step === 'collaborator' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {availableCollabs.map(c => (
            <button
              key={c.id}
              onClick={() => { setSelectedCollab(c); setStep('datetime') }}
              className="panel p-5 flex items-center gap-4 text-left transition-colors
                         hover:border-primary hover:bg-primary/10"
            >
              {/* The colour the calendar paints them with, kept as a ruled cell. */}
              <span
                className="w-12 h-12 border border-border flex items-center justify-center shrink-0
                           font-heading text-lg tracking-[0.06em] text-white"
                style={{ backgroundColor: c.color }}
              >
                {c.first_name[0]}
              </span>
              <span className="font-heading text-xl leading-tight tracking-[0.03em] text-foreground">
                {c.first_name} {c.last_name}
              </span>
            </button>
          ))}
          {availableCollabs.length === 0 && (
            <p className="note sm:col-span-2">
              Nessuno è al momento disponibile per questo servizio.
            </p>
          )}
        </div>
      )}

      {/* Step: DateTime */}
      {step === 'datetime' && (
        <div className="flex flex-col gap-6">
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
                <Loader2 className="w-4 h-4 animate-spin" /> Cerco gli orari liberi…
              </p>
            ) : !slots?.length ? (
              <div className="panel py-10 px-6 text-center">
                <CalendarX className="w-7 h-7 text-ink-3 mx-auto mb-3" />
                <p className="font-heading text-xl text-foreground">Nessun orario disponibile</p>
                <p className="note mt-1.5">Prova con un altro giorno.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <span className="kicker">
                  Orari liberi · {format(parseISO(selectedDate), 'EEEE d MMMM', { locale: it })}
                </span>
                {/* A grid of large targets — wrapped inline chips were only
                    ~34px tall, below a comfortable tap size. */}
                <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                  {slots.map(slot => (
                    <button
                      key={slot}
                      onClick={() => { setSelectedSlot(slot); setStep('confirm') }}
                      className={clsx(
                        'min-h-touch text-[15px] border transition-colors tabular-nums',
                        selectedSlot === slot
                          ? 'bg-action text-action-foreground border-action'
                          : 'border-border bg-surface text-ink-2 hover:border-primary hover:text-primary-dark'
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
        <div className="flex flex-col gap-4">
          <div className="panel">
            <Row label="Servizio" value={selectedService.name} />
            <Row label="Con" value={`${selectedCollab.first_name} ${selectedCollab.last_name}`} />
            <Row
              label="Data"
              value={format(parseISO(selectedDate), 'EEEE d MMMM yyyy', { locale: it })}
              numeric
            />
            <Row
              label="Orario"
              value={`${format(parseISO(selectedSlot), 'HH:mm')} – ${format(addMinutes(parseISO(selectedSlot), selectedService.duration_slots * MINUTES_PER_SLOT), 'HH:mm')}`}
              numeric
            />
            <Row
              label="Durata"
              value={`${selectedService.duration_slots * MINUTES_PER_SLOT} minuti`}
              numeric
            />
            {/* The price closes the panel on its own band, like the total on a
                receipt. */}
            <div className="flex items-baseline justify-between gap-3 px-5 py-4 bg-band">
              <span className="kicker">Prezzo</span>
              <span className="font-heading text-[26px] leading-none tabular-nums text-primary-dark">
                €{selectedService.price.toFixed(2)}
              </span>
            </div>
          </div>

          <p className="note">
            La prenotazione verrà confermata dal salone. Ti avvisiamo via email e
            WhatsApp.
          </p>

          <button onClick={handleBook} disabled={bookMut.isPending} className="btn-primary w-full">
            {bookMut.isPending
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Invio richiesta…</>
              : 'Invia richiesta'}
          </button>

          {bookMut.isError && (
            <p
              role="alert"
              className="text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5"
            >
              {(bookMut.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
                ?? 'Errore durante la prenotazione'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ label, value, numeric = false }: {
  label: string
  value: string
  numeric?: boolean
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-5 py-3.5 border-b border-rule-soft">
      <span className="text-[13px] text-ink-3 shrink-0">{label}</span>
      <span
        className={clsx(
          'text-[15px] text-foreground text-right first-letter:uppercase',
          numeric && 'tabular-nums'
        )}
      >
        {value}
      </span>
    </div>
  )
}
