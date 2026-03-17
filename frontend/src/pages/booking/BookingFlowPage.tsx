import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { format, parseISO, addMinutes } from 'date-fns'
import { it } from 'date-fns/locale'
import { Check, ChevronLeft } from 'lucide-react'
import { useClientAuth } from '@/components/layout/BookingLayout'
import {
  publicGetServices, publicGetCollaborators, publicGetAvailability, bookAppointment
} from '@/services/publicApi'
import { useNavigate } from 'react-router-dom'
import type { Service, Collaborator } from '@/types'

type Step = 'service' | 'collaborator' | 'datetime' | 'confirm' | 'done'

export default function BookingFlowPage() {
  const [step, setStep] = useState<Step>('service')
  const [selectedService, setSelectedService] = useState<Service | null>(null)
  const [selectedCollab, setSelectedCollab] = useState<Collaborator | null>(null)
  const [selectedDate, setSelectedDate] = useState('')
  const [selectedSlot, setSelectedSlot] = useState('')
  const { token } = useClientAuth()
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
    if (!token) { navigate('/booking/login'); return }
    if (!selectedService || !selectedCollab || !selectedSlot) return
    const start = parseISO(selectedSlot)
    const end = addMinutes(start, selectedService.duration_slots * 30)
    bookMut.mutate({
      client_id: 0, // will be resolved server-side from token
      collaborator_id: selectedCollab.id,
      start_time: start.toISOString(),
      end_time: end.toISOString(),
      service_ids: [selectedService.id],
    })
  }

  if (step === 'done') {
    return (
      <div className="text-center space-y-4 py-12">
        <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto">
          <Check className="w-8 h-8 text-emerald-600" />
        </div>
        <h2 className="text-2xl font-bold">Richiesta inviata!</h2>
        <p className="text-muted-foreground">Il salone confermerà il tuo appuntamento al più presto.</p>
        <div className="flex gap-3 justify-center">
          <button onClick={() => navigate('/booking/account')} className="btn-primary">
            Vai alla mia area
          </button>
          <button onClick={() => { setStep('service'); setSelectedService(null); setSelectedCollab(null); setSelectedDate(''); setSelectedSlot('') }} className="btn-secondary">
            Prenota ancora
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Progress */}
      <div className="flex items-center gap-2">
        {(['service', 'collaborator', 'datetime', 'confirm'] as Step[]).map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors ${
              step === s ? 'bg-primary text-white'
              : ['service', 'collaborator', 'datetime', 'confirm'].indexOf(step) > i ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
            }`}>
              {['service', 'collaborator', 'datetime', 'confirm'].indexOf(step) > i ? <Check className="w-4 h-4" /> : i + 1}
            </div>
            {i < 3 && <div className="flex-1 h-0.5 bg-border min-w-[20px]" />}
          </div>
        ))}
      </div>

      {/* Step: Service */}
      {step === 'service' && (
        <div className="space-y-4">
          <h2 className="text-xl font-bold">Scegli il servizio</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {(services ?? []).map(s => (
              <button
                key={s.id}
                onClick={() => { setSelectedService(s); setStep('collaborator') }}
                className="card p-4 text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <p className="font-semibold">{s.name}</p>
                <p className="text-sm text-muted-foreground mt-0.5">{s.description}</p>
                <div className="flex items-center gap-3 mt-2">
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
        <div className="space-y-4">
          <button onClick={() => setStep('service')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronLeft className="w-4 h-4" /> Indietro
          </button>
          <h2 className="text-xl font-bold">Scegli il collaboratore</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {availableCollabs.map(c => (
              <button
                key={c.id}
                onClick={() => { setSelectedCollab(c); setStep('datetime') }}
                className="card p-4 flex items-center gap-3 text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0"
                  style={{ backgroundColor: c.color }}
                >
                  {c.first_name[0]}
                </div>
                <div>
                  <p className="font-semibold">{c.first_name} {c.last_name}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Step: DateTime */}
      {step === 'datetime' && (
        <div className="space-y-4">
          <button onClick={() => setStep('collaborator')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronLeft className="w-4 h-4" /> Indietro
          </button>
          <h2 className="text-xl font-bold">Scegli data e orario</h2>
          <div>
            <label className="label block mb-1">Data</label>
            <input
              type="date"
              className="input max-w-xs"
              min={format(new Date(), 'yyyy-MM-dd')}
              value={selectedDate}
              onChange={e => { setSelectedDate(e.target.value); setSelectedSlot('') }}
            />
          </div>
          {selectedDate && (
            slotsLoading ? (
              <p className="text-muted-foreground text-sm">Caricamento disponibilità...</p>
            ) : !slots?.length ? (
              <p className="text-muted-foreground text-sm">Nessuno slot disponibile per questa data. Prova un altro giorno.</p>
            ) : (
              <div>
                <p className="text-sm font-medium mb-2">Orari disponibili:</p>
                <div className="flex flex-wrap gap-2">
                  {slots.map(slot => (
                    <button
                      key={slot}
                      onClick={() => { setSelectedSlot(slot); setStep('confirm') }}
                      className={`px-3 py-1.5 rounded-md text-sm font-medium border transition-colors ${
                        selectedSlot === slot
                          ? 'bg-primary text-white border-primary'
                          : 'border-border hover:border-primary hover:text-primary'
                      }`}
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
          <button onClick={() => setStep('datetime')} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronLeft className="w-4 h-4" /> Indietro
          </button>
          <h2 className="text-xl font-bold">Riepilogo prenotazione</h2>
          <div className="card p-4 space-y-3">
            <Row label="Servizio" value={selectedService.name} />
            <Row label="Con" value={`${selectedCollab.first_name} ${selectedCollab.last_name}`} />
            <Row label="Data" value={format(parseISO(selectedDate), 'EEEE d MMMM yyyy', { locale: it })} />
            <Row label="Orario" value={`${format(parseISO(selectedSlot), 'HH:mm')} – ${format(addMinutes(parseISO(selectedSlot), selectedService.duration_slots * 30), 'HH:mm')}`} />
            <Row label="Durata" value={`${selectedService.duration_slots * 30} minuti`} />
            <Row label="Prezzo" value={`€${selectedService.price.toFixed(2)}`} />
            <div className="pt-2 border-t border-border">
              <p className="text-xs text-muted-foreground">
                La prenotazione verrà confermata dal salone. Riceverai una notifica via email.
              </p>
            </div>
          </div>
          {!token && (
            <p className="text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded">
              Devi accedere o registrarti per completare la prenotazione.
            </p>
          )}
          <button
            onClick={handleBook}
            disabled={bookMut.isPending}
            className="btn-primary w-full py-3 text-base disabled:opacity-60"
          >
            {!token ? 'Accedi per prenotare' : bookMut.isPending ? 'Invio richiesta...' : 'Invia richiesta'}
          </button>
          {bookMut.isError && (
            <p className="text-sm text-red-500">{(bookMut.error as any)?.response?.data?.detail ?? 'Errore durante la prenotazione'}</p>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-muted-foreground w-20 flex-shrink-0">{label}:</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
