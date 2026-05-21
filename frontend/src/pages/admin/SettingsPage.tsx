import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBookingConfig, updateBookingConfig } from '@/services/api'
import { Check, MessageCircle, Info } from 'lucide-react'

const PLACEHOLDER_VARS = '{nome}, {data}, {ora}, {collaboratore}'

const DEFAULT_BOOKING_MSG =
  'Ciao {nome}! La tua prenotazione da New Style Hair è confermata per il {data} alle {ora} con {collaboratore}. A presto! 💇'
const DEFAULT_REMINDER_MSG =
  'Ciao {nome}! Ti ricordiamo il tuo appuntamento da New Style Hair il {data} alle {ora} con {collaboratore}. A presto! 💇'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data: config } = useQuery({ queryKey: ['booking-config'], queryFn: getBookingConfig })
  const [saved, setSaved] = useState(false)

  const [form, setForm] = useState({
    is_enabled: true,
    min_advance_hours: 2,
    max_advance_days: 30,
    min_cancel_hours: 24,
    slot_duration_minutes: 30,
    closed_weekdays: [0, 1] as number[],
    whatsapp_enabled: false,
    whatsapp_reminder_hours: 24,
    whatsapp_booking_message: '',
    whatsapp_reminder_message: '',
  })

  useEffect(() => {
    if (config) {
      setForm({
        is_enabled: config.is_enabled,
        min_advance_hours: config.min_advance_hours,
        max_advance_days: config.max_advance_days,
        min_cancel_hours: config.min_cancel_hours,
        slot_duration_minutes: config.slot_duration_minutes,
        closed_weekdays: config.closed_weekdays ?? [0, 1],
        whatsapp_enabled: config.whatsapp_enabled,
        whatsapp_reminder_hours: config.whatsapp_reminder_hours,
        whatsapp_booking_message: config.whatsapp_booking_message ?? '',
        whatsapp_reminder_message: config.whatsapp_reminder_message ?? '',
      })
    }
  }, [config])

  const updateMut = useMutation({
    mutationFn: updateBookingConfig,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['booking-config'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateMut.mutate({
      ...form,
      whatsapp_booking_message: form.whatsapp_booking_message || null,
      whatsapp_reminder_message: form.whatsapp_reminder_message || null,
    })
  }

  const set = <K extends keyof typeof form>(k: K, v: typeof form[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold">Impostazioni</h1>

      {/* ── Prenotazione online ─────────────────────────────────── */}
      <div className="card p-5">
        <h3 className="font-semibold mb-4">Prenotazione online</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <div className={`relative w-11 h-6 rounded-full transition-colors ${form.is_enabled ? 'bg-primary' : 'bg-gray-300'}`}>
              <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${form.is_enabled ? 'translate-x-5' : ''}`} />
            </div>
            <input
              type="checkbox" hidden
              checked={form.is_enabled}
              onChange={e => set('is_enabled', e.target.checked)}
            />
            <div>
              <span className="text-sm font-medium">Prenotazione online abilitata</span>
              <p className="text-xs text-muted-foreground">I clienti possono prenotare dal portale pubblico</p>
            </div>
          </label>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label block mb-1">Anticipo minimo (ore)</label>
              <input className="input" type="number" min="0" max="72"
                value={form.min_advance_hours}
                onChange={e => set('min_advance_hours', Number(e.target.value))} />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 2 = non prenotabile nelle prossime 2h</p>
            </div>
            <div>
              <label className="label block mb-1">Anticipo massimo (giorni)</label>
              <input className="input" type="number" min="1" max="365"
                value={form.max_advance_days}
                onChange={e => set('max_advance_days', Number(e.target.value))} />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 30 = prenotabile fino a 30gg avanti</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label block mb-1">Preavviso cancellazione (ore)</label>
              <input className="input" type="number" min="0" max="168"
                value={form.min_cancel_hours}
                onChange={e => set('min_cancel_hours', Number(e.target.value))} />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 24 = cancellazione con 24h di anticipo</p>
            </div>
            <div>
              <label className="label block mb-1">Durata slot (minuti)</label>
              <select className="input" value={form.slot_duration_minutes}
                onChange={e => set('slot_duration_minutes', Number(e.target.value))}>
                <option value="15">15 minuti</option>
                <option value="30">30 minuti</option>
                <option value="60">60 minuti</option>
              </select>
            </div>
          </div>

          {/* ── Giorni di chiusura ─────────────────────────────── */}
          <div className="border-t border-border pt-4">
            <label className="label block mb-2">Giorni di chiusura del salone</label>
            <div className="flex gap-2 flex-wrap">
              {[
                { label: 'Dom', value: 0 },
                { label: 'Lun', value: 1 },
                { label: 'Mar', value: 2 },
                { label: 'Mer', value: 3 },
                { label: 'Gio', value: 4 },
                { label: 'Ven', value: 5 },
                { label: 'Sab', value: 6 },
              ].map(({ label, value }) => {
                const active = form.closed_weekdays.includes(value)
                return (
                  <button
                    key={value}
                    type="button"
                    onClick={() => set(
                      'closed_weekdays',
                      active
                        ? form.closed_weekdays.filter(d => d !== value)
                        : [...form.closed_weekdays, value]
                    )}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      active
                        ? 'bg-red-500/15 border-red-500/50 text-red-400'
                        : 'border-border hover:bg-muted text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
            <p className="text-xs text-muted-foreground mt-1">I giorni selezionati appaiono in rosso nel calendario</p>
          </div>

          {/* ── WhatsApp ───────────────────────────────────────── */}
          <div className="border-t border-border pt-4 space-y-4">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-4 h-4 text-emerald-500" />
              <h4 className="font-medium text-sm">Notifiche WhatsApp</h4>
            </div>

            {/* Toggle */}
            <label className="flex items-center gap-3 cursor-pointer">
              <div className={`relative w-11 h-6 rounded-full transition-colors ${form.whatsapp_enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}>
                <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${form.whatsapp_enabled ? 'translate-x-5' : ''}`} />
              </div>
              <input type="checkbox" hidden
                checked={form.whatsapp_enabled}
                onChange={e => set('whatsapp_enabled', e.target.checked)} />
              <div>
                <span className="text-sm font-medium">Abilita notifiche WhatsApp</span>
                <p className="text-xs text-muted-foreground">
                  Richiede credenziali Twilio nelle variabili d'ambiente
                </p>
              </div>
            </label>

            {form.whatsapp_enabled && (
              <div className="space-y-4 pl-1">
                {/* Reminder hours */}
                <div>
                  <label className="label block mb-1">Anticipo reminder (ore)</label>
                  <input className="input" type="number" min="1" max="168"
                    value={form.whatsapp_reminder_hours}
                    onChange={e => set('whatsapp_reminder_hours', Number(e.target.value))} />
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Es: 24 = messaggio inviato 24h prima dell'appuntamento
                  </p>
                </div>

                {/* Variable legend */}
                <div className="flex items-start gap-1.5 text-xs text-muted-foreground bg-muted/50 rounded-md p-2.5">
                  <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span>
                    Variabili disponibili nei messaggi: <code className="font-mono">{PLACEHOLDER_VARS}</code>
                  </span>
                </div>

                {/* Booking confirmation message */}
                <div>
                  <label className="label block mb-1">Messaggio conferma prenotazione</label>
                  <textarea
                    className="input min-h-[80px] resize-y text-sm"
                    placeholder={DEFAULT_BOOKING_MSG}
                    value={form.whatsapp_booking_message}
                    onChange={e => set('whatsapp_booking_message', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Inviato subito quando l'appuntamento viene confermato
                  </p>
                </div>

                {/* Reminder message */}
                <div>
                  <label className="label block mb-1">Messaggio reminder</label>
                  <textarea
                    className="input min-h-[80px] resize-y text-sm"
                    placeholder={DEFAULT_REMINDER_MSG}
                    value={form.whatsapp_reminder_message}
                    onChange={e => set('whatsapp_reminder_message', e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Inviato {form.whatsapp_reminder_hours}h prima dell'appuntamento
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-3 pt-2">
            <button type="submit" disabled={updateMut.isPending} className="btn-primary disabled:opacity-60">
              {updateMut.isPending ? 'Salvataggio...' : 'Salva impostazioni'}
            </button>
            {saved && (
              <span className="flex items-center gap-1 text-sm text-emerald-600 font-medium">
                <Check className="w-4 h-4" /> Salvato
              </span>
            )}
          </div>
        </form>
      </div>

      {/* Twilio setup hint */}
      <div className="card p-4 border-amber-200 bg-amber-50">
        <p className="text-xs font-semibold text-amber-800 mb-1">Configurazione Twilio</p>
        <p className="text-xs text-amber-700">
          Per abilitare WhatsApp imposta le seguenti variabili d'ambiente sul server:
        </p>
        <ul className="text-xs text-amber-700 mt-1 space-y-0.5 font-mono">
          <li>TWILIO_ACCOUNT_SID</li>
          <li>TWILIO_AUTH_TOKEN</li>
          <li>TWILIO_WHATSAPP_FROM (es. whatsapp:+14155238886)</li>
        </ul>
        <p className="text-xs text-amber-600 mt-1">
          In sviluppo senza credenziali, i messaggi vengono loggati in console (stub mode).
        </p>
      </div>
    </div>
  )
}
