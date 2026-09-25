import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO, addMinutes } from 'date-fns'
import { it } from 'date-fns/locale'
import { Check, CalendarX, Loader2 } from 'lucide-react'
import {
  publicGetServices, publicGetCollaborators, publicGetAvailability, bookAppointment,
  requestGuestCode, bookAsGuest,
} from '@/services/publicApi'
import AvailabilityCalendar from '@/components/booking/AvailabilityCalendar'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { TELEFONO } from '@/config/business'
import { Link, useNavigate } from 'react-router-dom'
import type { Service, Collaborator } from '@/types'
import clsx from 'clsx'

type Step = 'service' | 'collaborator' | 'datetime' | 'confirm' | 'done'

const ORDER: Step[] = ['service', 'collaborator', 'datetime', 'confirm']
const STEP_LABELS: Record<string, string> = {
  service: 'Servizi',
  collaborator: 'Con chi',
  datetime: 'Quando',
  confirm: 'Conferma',
}

/** Half an hour to a slot. */
const MINUTES_PER_SLOT = 30

type ApiError = { response?: { status?: number; data?: { detail?: unknown } } }

/** Il messaggio del server, quando è una frase; un 422 di validazione arriva
    come elenco di oggetti e non si mostra così com'è. */
function detailOf(e: unknown, fallback: string): string {
  const detail = (e as ApiError)?.response?.data?.detail
  return typeof detail === 'string' ? detail : fallback
}

export default function BookingFlowPage() {
  const [step, setStep] = useState<Step>('service')
  // In the order the client tapped them. That order is the one the services
  // run in, it changes processing times, and the same array goes to both the
  // availability query and the booking — so the two cannot disagree.
  const [selectedServices, setSelectedServices] = useState<Service[]>([])
  const [selectedCollab, setSelectedCollab] = useState<Collaborator | null>(null)
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedSlot, setSelectedSlot] = useState('')
  const navigate = useNavigate()
  const qc = useQueryClient()
  const token = useClientAuth(s => s.token)

  // Senza account: chi è, e il codice WhatsApp che lo dimostra. Il codice è
  // del numero — cambiare numero dopo averlo chiesto lo rende inutile, quindi
  // si torna a chiederne uno.
  const [guest, setGuest] = useState({ first_name: '', last_name: '', phone: '' })
  const [guestCode, setGuestCode] = useState('')
  const [codeSentTo, setCodeSentTo] = useState('')
  const [codeNotice, setCodeNotice] = useState('')
  const [bookedAsGuest, setBookedAsGuest] = useState(false)
  const codeSent = codeSentTo !== '' && codeSentTo === guest.phone.trim()
  const guestReady = guest.first_name.trim() !== '' && guest.last_name.trim() !== '' && guest.phone.trim() !== ''

  const { data: services } = useQuery({
    queryKey: ['public-services'],
    queryFn: publicGetServices,
  })

  const { data: collaborators } = useQuery({
    queryKey: ['public-collaborators'],
    queryFn: publicGetCollaborators,
    enabled: step === 'collaborator' || step === 'datetime',
  })

  const serviceIds = selectedServices.map(s => s.id)
  const totalSlots = selectedServices.reduce((n, s) => n + s.duration_slots, 0)
  const totalPrice = selectedServices.reduce((n, s) => n + s.price, 0)

  const { data: slots, isLoading: slotsLoading } = useQuery({
    queryKey: ['public-slots', serviceIds, selectedCollab?.id, selectedDate],
    queryFn: () => publicGetAvailability({
      service_ids: serviceIds,
      collaborator_id: selectedCollab!.id,
      target_date: selectedDate,
    }),
    enabled: serviceIds.length > 0 && !!selectedCollab && !!selectedDate,
  })

  // 409 means the server refused the slot — usually because someone booked
  // it while this page was open. The list on screen is the stale thing, so
  // reload it and drop the selection: without this the only visible move is
  // pressing the same button again and failing again.
  const onSlotRefused = (e: ApiError) => {
    if (e?.response?.status === 409) {
      setSelectedSlot('')
      setStep('datetime')
      qc.invalidateQueries({ queryKey: ['public-slots'] })
    }
  }

  const bookMut = useMutation({
    mutationFn: bookAppointment,
    onSuccess: () => { setBookedAsGuest(false); setStep('done') },
    onError: onSlotRefused,
  })

  const codeMut = useMutation({
    mutationFn: requestGuestCode,
    onSuccess: (res, sent) => {
      setGuestCode('')
      if (res.whatsapp_sent) {
        setCodeSentTo(sent.phone)
        setCodeNotice(`Ti abbiamo mandato un codice su WhatsApp al ${sent.phone}.`)
      } else {
        setCodeSentTo('')
        setCodeNotice('')
      }
    },
  })

  // Il codice non si spende se l'orario è stato preso nel frattempo: il
  // server lo controlla dopo l'orario, quindi resta buono per sceglierne un altro.
  const guestBookMut = useMutation({
    mutationFn: bookAsGuest,
    onSuccess: () => { setBookedAsGuest(true); setGuestCode(''); setCodeSentTo(''); setStep('done') },
    onError: onSlotRefused,
  })

  // Only who does every chosen service: an appointment has one collaborator.
  const availableCollabs = (collaborators ?? []).filter(
    c => serviceIds.length > 0 && serviceIds.every(id => c.service_ids.includes(id))
  )

  const toggleService = (svc: Service) =>
    setSelectedServices(prev =>
      prev.some(s => s.id === svc.id) ? prev.filter(s => s.id !== svc.id) : [...prev, svc]
    )

  // A changed selection can invalidate what came after it: the collaborator
  // may not do the new service, the slot may no longer fit.
  const continueFromServices = () => {
    setSelectedCollab(null)
    setSelectedDate('')
    setSelectedSlot('')
    setStep('collaborator')
  }

  const handleBook = () => {
    if (serviceIds.length === 0 || !selectedCollab || !selectedSlot) return
    const start = parseISO(selectedSlot)
    if (!token) {
      guestBookMut.mutate({
        first_name: guest.first_name.trim(),
        last_name: guest.last_name.trim(),
        phone: guest.phone.trim(),
        code: guestCode,
        collaborator_id: selectedCollab.id,
        start_time: start.toISOString(),
        service_ids: serviceIds,
      })
      return
    }
    const end = addMinutes(start, totalSlots * MINUTES_PER_SLOT)
    bookMut.mutate({
      client_id: 0, // resolved server-side from the token
      collaborator_id: selectedCollab.id,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      service_ids: serviceIds,
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
            {bookedAsGuest ? ' su WhatsApp.' : ' via email e WhatsApp.'}
          </p>
          {/* Senza account non c'è un'area personale da cui disdire: si fa
              come per chi prenota al telefono. */}
          {bookedAsGuest && (
            <p className="text-muted-foreground mt-3 max-w-xs mx-auto text-sm">
              Per disdire o spostarlo contatta il salone al{' '}
              <a href={`tel:${TELEFONO.tel}`} className="text-primary-dark underline tabular-nums whitespace-nowrap">
                {TELEFONO.visibile}
              </a>
              . Se crei un account con lo stesso nome e numero, lo ritrovi lì.
            </p>
          )}
        </div>
        <div className="flex flex-col sm:flex-row gap-2.5 w-full sm:w-auto">
          {bookedAsGuest ? (
            <button onClick={() => navigate('/login?registrati')} className="btn-primary sm:px-7">
              Crea un account
            </button>
          ) : (
            <button onClick={() => navigate('/booking/account')} className="btn-primary sm:px-7">
              Vai all'area personale
            </button>
          )}
          <button
            onClick={() => {
              setStep('service'); setSelectedServices([]); setSelectedCollab(null)
              setSelectedDate(''); setSelectedSlot('')
              // Nome e numero restano: è la stessa persona che prenota ancora.
              codeMut.reset(); guestBookMut.reset(); setCodeNotice('')
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
        <div className="flex flex-col gap-4">
        <p className="note">Puoi sceglierne più di uno: si fanno nello stesso appuntamento, uno dopo l'altro.</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {(services ?? []).filter(s => s.bookable_online).map(s => {
            const scelto = selectedServices.some(x => x.id === s.id)
            return (
            <button
              key={s.id}
              type="button"
              onClick={() => toggleService(s)}
              aria-pressed={scelto}
              className={clsx(
                'panel p-5 text-left flex flex-col gap-2 transition-colors',
                scelto
                  ? 'border-primary bg-primary/10'
                  : 'hover:border-primary hover:bg-primary/10'
              )}
            >
              <span className="flex items-start justify-between gap-3">
                <span className="font-heading text-[21px] leading-tight tracking-[0.03em] text-foreground">
                  {s.name}
                </span>
                <span
                  className={clsx(
                    'w-6 h-6 shrink-0 border flex items-center justify-center',
                    scelto ? 'bg-primary border-primary text-white' : 'border-border'
                  )}
                  aria-hidden
                >
                  {scelto && <Check className="w-4 h-4" />}
                </span>
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
            )
          })}
        </div>

        {/* Stays in view at the bottom: with the list longer than the screen,
            the way on would otherwise be below the fold. Sits on top of the
            client tab bar, which is fixed at the very bottom — `bottom-0` would
            put it underneath. Without an account there is no tab bar, and
            `bottom-tabbar` would leave it floating a bar's height too high. */}
        <div
          className={clsx(
            'sticky -mx-4 px-4 py-3 bg-background/95 backdrop-blur border-t border-rule flex items-center gap-3',
            token ? 'bottom-tabbar' : 'bottom-0',
          )}
        >
          <span className="flex-1 text-sm text-muted-foreground tabular-nums">
            {selectedServices.length === 0
              ? 'Scegli almeno un servizio'
              : `${selectedServices.length} ${selectedServices.length === 1 ? 'servizio' : 'servizi'} · ${totalSlots * MINUTES_PER_SLOT} min · €${totalPrice.toFixed(2)}`}
          </span>
          <button
            type="button"
            onClick={continueFromServices}
            disabled={selectedServices.length === 0}
            className="btn-primary disabled:opacity-50"
          >
            Continua
          </button>
        </div>
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
              {selectedServices.length > 1
                ? 'Nessuno fa tutti questi servizi insieme. Prova a toglierne uno, o a prenotarli in due appuntamenti.'
                : 'Nessuno è al momento disponibile per questo servizio.'}
            </p>
          )}
        </div>
      )}

      {/* Step: DateTime */}
      {step === 'datetime' && (
        <div className="flex flex-col gap-6">
          {serviceIds.length > 0 && selectedCollab && (
            <AvailabilityCalendar
              serviceIds={serviceIds}
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
      {step === 'confirm' && serviceIds.length > 0 && selectedCollab && selectedSlot && (
        <div className="flex flex-col gap-4">
          <div className="panel">
            <Row
              label={selectedServices.length > 1 ? 'Servizi' : 'Servizio'}
              value={selectedServices.map(s => s.name).join(' + ')}
            />
            <Row label="Con" value={`${selectedCollab.first_name} ${selectedCollab.last_name}`} />
            <Row
              label="Data"
              value={format(parseISO(selectedDate), 'EEEE d MMMM yyyy', { locale: it })}
              numeric
            />
            <Row
              label="Orario"
              value={`${format(parseISO(selectedSlot), 'HH:mm')} – ${format(addMinutes(parseISO(selectedSlot), totalSlots * MINUTES_PER_SLOT), 'HH:mm')}`}
              numeric
            />
            <Row
              label="Durata"
              value={`${totalSlots * MINUTES_PER_SLOT} minuti`}
              numeric
            />
            {/* The price closes the panel on its own band, like the total on a
                receipt. */}
            <div className="flex items-baseline justify-between gap-3 px-5 py-4 bg-band">
              <span className="kicker">Prezzo</span>
              <span className="font-heading text-[26px] leading-none tabular-nums text-primary-dark">
                €{totalPrice.toFixed(2)}
              </span>
            </div>
          </div>

          {!token && (
            <div className="panel px-5 py-4 flex flex-col gap-4">
              <div className="flex flex-col gap-1.5">
                <span className="kicker">I tuoi dati</span>
                <p className="text-[13px] text-muted-foreground">
                  Non serve un account: nome, cognome e il numero WhatsApp su cui
                  ti mandiamo un codice.{' '}
                  <Link to="/login?next=%2Fbooking%2Fnew" className="text-primary-dark hover:underline">
                    Hai un account? Accedi
                  </Link>
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label htmlFor="guest_first_name" className="label">Nome</label>
                  <input
                    id="guest_first_name"
                    className="input"
                    autoComplete="given-name"
                    value={guest.first_name}
                    onChange={e => setGuest(g => ({ ...g, first_name: e.target.value }))}
                  />
                </div>
                <div>
                  <label htmlFor="guest_last_name" className="label">Cognome</label>
                  <input
                    id="guest_last_name"
                    className="input"
                    autoComplete="family-name"
                    value={guest.last_name}
                    onChange={e => setGuest(g => ({ ...g, last_name: e.target.value }))}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="guest_phone" className="label">Telefono (WhatsApp)</label>
                <input
                  id="guest_phone"
                  className="input"
                  type="tel"
                  inputMode="tel"
                  autoComplete="tel"
                  placeholder="333 123 4567"
                  value={guest.phone}
                  onChange={e => setGuest(g => ({ ...g, phone: e.target.value }))}
                />
              </div>

              {!codeSent ? (
                <button
                  type="button"
                  onClick={() => codeMut.mutate({
                    first_name: guest.first_name.trim(),
                    last_name: guest.last_name.trim(),
                    phone: guest.phone.trim(),
                  })}
                  disabled={!guestReady || codeMut.isPending}
                  className="btn-secondary w-full disabled:opacity-50"
                >
                  {codeMut.isPending
                    ? <><Loader2 className="w-4 h-4 animate-spin" /> Invio del codice…</>
                    : 'Ricevi il codice su WhatsApp'}
                </button>
              ) : (
                <div>
                  {codeNotice && <p className="text-[13px] text-muted-foreground mb-2">{codeNotice}</p>}
                  <label htmlFor="guest_code" className="label">Codice ricevuto</label>
                  <input
                    id="guest_code"
                    className="input text-center font-heading text-3xl tracking-[0.4em] tabular-nums py-3"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="[0-9]*"
                    maxLength={6}
                    autoFocus
                    placeholder="000000"
                    value={guestCode}
                    onChange={e => setGuestCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  />
                  <div className="flex items-center justify-between gap-3 mt-1.5">
                    <p className="text-xs text-ink-3">Sei cifre, valido per 15 minuti.</p>
                    <button
                      type="button"
                      onClick={() => codeMut.mutate({
                        first_name: guest.first_name.trim(),
                        last_name: guest.last_name.trim(),
                        phone: guest.phone.trim(),
                      })}
                      disabled={codeMut.isPending}
                      className="text-[13px] text-primary-dark hover:underline disabled:opacity-50"
                    >
                      Invia un nuovo codice
                    </button>
                  </div>
                </div>
              )}

              {codeMut.isSuccess && !codeMut.data.whatsapp_sent && (
                <p role="alert" className="text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5">
                  Non siamo riusciti a mandarti il codice. Riprova tra un minuto o
                  chiama il salone al {TELEFONO.visibile}.
                </p>
              )}
              {codeMut.isError && (
                <p role="alert" className="text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5">
                  {detailOf(codeMut.error, 'Controlla nome, cognome e numero e riprova.')}
                </p>
              )}
            </div>
          )}

          <p className="note">
            {token
              ? 'La prenotazione verrà confermata dal salone. Ti avvisiamo via email e WhatsApp.'
              : 'La prenotazione verrà confermata dal salone. Ti avvisiamo su WhatsApp; per disdire o spostarla contatti il salone.'}
          </p>

          <button
            onClick={handleBook}
            disabled={token
              ? bookMut.isPending
              : guestBookMut.isPending || !codeSent || guestCode.length < 6}
            className="btn-primary w-full disabled:opacity-50"
          >
            {bookMut.isPending || guestBookMut.isPending
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Invio richiesta…</>
              : 'Invia richiesta'}
          </button>

          {(token ? bookMut : guestBookMut).isError && (
            <p
              role="alert"
              className="text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5"
            >
              {detailOf((token ? bookMut : guestBookMut).error, 'Errore durante la prenotazione')}
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
