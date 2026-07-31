import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBookingConfig, updateBookingConfig } from '@/services/api'
import { Check } from 'lucide-react'
import { PageHeader } from '@/components/ui'
import { Toggle } from './ServicesPage'
import clsx from 'clsx'

const PLACEHOLDER_VARS = '{nome}, {data}, {ora}, {collaboratore}'

const DEFAULT_BOOKING_MSG =
  'Ciao {nome}! La tua prenotazione da New Style Hair è confermata per il {data} alle {ora} con {collaboratore}. A presto! 💇'
const DEFAULT_REMINDER_MSG =
  'Ciao {nome}! Ti ricordiamo il tuo appuntamento da New Style Hair il {data} alle {ora} con {collaboratore}. A presto! 💇'

const WEEKDAYS = [
  { label: 'Dom', value: 0 },
  { label: 'Lun', value: 1 },
  { label: 'Mar', value: 2 },
  { label: 'Mer', value: 3 },
  { label: 'Gio', value: 4 },
  { label: 'Ven', value: 5 },
  { label: 'Sab', value: 6 },
]

/** A titled sheet, the way the design lays out the settings sections. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel">
      <div className="band px-5 py-3">
        <span className="kicker">{title}</span>
      </div>
      <div className="p-5 flex flex-col gap-4">{children}</div>
    </div>
  )
}

/** A field with the note that explains it — the note sits under, in the same
    faint ink the design gives every caption. */
function Field({ label, hint, children }: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-xs text-ink-3 mt-1.5">{hint}</p>}
    </div>
  )
}

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
    <div className="max-w-2xl">
      <PageHeader title="Impostazioni" />

      {/* One form across several sheets: the sections are subjects, not steps,
          so they save together. */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-5">
        <Section title="Prenotazione online">
          <Toggle
            label="Prenotazione online abilitata"
            description="I clienti possono prenotare dal portale pubblico"
            checked={form.is_enabled}
            onChange={v => set('is_enabled', v)}
          />

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="Anticipo minimo (ore)" hint="Es: 2 = non prenotabile nelle prossime 2h">
              <input className="input tabular-nums" type="number" min="0" max="72"
                value={form.min_advance_hours}
                onChange={e => set('min_advance_hours', Number(e.target.value))} />
            </Field>
            <Field label="Anticipo massimo (giorni)" hint="Es: 30 = prenotabile fino a 30gg avanti">
              <input className="input tabular-nums" type="number" min="1" max="365"
                value={form.max_advance_days}
                onChange={e => set('max_advance_days', Number(e.target.value))} />
            </Field>
            <Field label="Preavviso cancellazione (ore)" hint="Es: 24 = cancellazione con 24h di anticipo">
              <input className="input tabular-nums" type="number" min="0" max="168"
                value={form.min_cancel_hours}
                onChange={e => set('min_cancel_hours', Number(e.target.value))} />
            </Field>
            <Field label="Durata slot (minuti)">
              <select className="input" value={form.slot_duration_minutes}
                onChange={e => set('slot_duration_minutes', Number(e.target.value))}>
                <option value="15">15 minuti</option>
                <option value="30">30 minuti</option>
                <option value="60">60 minuti</option>
              </select>
            </Field>
          </div>
        </Section>

        <Section title="Giorni di chiusura">
          {/* Seven squared cells: a closed day is struck out of the week the
              way it is struck out of the calendar. */}
          <div className="grid grid-cols-7 gap-px bg-rule-soft border border-border">
            {WEEKDAYS.map(({ label, value }) => {
              const closed = form.closed_weekdays.includes(value)
              return (
                <button
                  key={value}
                  type="button"
                  aria-pressed={closed}
                  onClick={() => set(
                    'closed_weekdays',
                    closed
                      ? form.closed_weekdays.filter(d => d !== value)
                      : [...form.closed_weekdays, value]
                  )}
                  className={clsx(
                    'py-3 font-heading text-[13px] uppercase tracking-[0.08em] transition-colors',
                    closed
                      ? 'bg-danger/[0.12] text-danger line-through'
                      : 'bg-surface text-ink-2 hover:bg-foreground/[0.05]'
                  )}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <p className="text-xs text-ink-3">
            I giorni barrati sono chiusi: il calendario non li rende prenotabili.
          </p>
        </Section>

        <Section title="Notifiche WhatsApp">
          <Toggle
            label="Abilita notifiche WhatsApp"
            description="Richiede credenziali Twilio nelle variabili d'ambiente"
            checked={form.whatsapp_enabled}
            onChange={v => set('whatsapp_enabled', v)}
          />

          {form.whatsapp_enabled && (
            <>
              <Field
                label="Anticipo reminder (ore)"
                hint="Es: 24 = messaggio inviato 24h prima dell'appuntamento"
              >
                <input className="input tabular-nums sm:w-40" type="number" min="1" max="168"
                  value={form.whatsapp_reminder_hours}
                  onChange={e => set('whatsapp_reminder_hours', Number(e.target.value))} />
              </Field>

              <p className="text-[13px] text-muted-foreground border-l-2 border-primary bg-primary/[0.08] px-3 py-2.5">
                Variabili disponibili nei messaggi:{' '}
                <code className="font-mono text-primary-dark">{PLACEHOLDER_VARS}</code>
              </p>

              <Field
                label="Messaggio conferma prenotazione"
                hint="Inviato subito quando l'appuntamento viene confermato"
              >
                <textarea
                  className="input min-h-[80px] resize-y text-sm"
                  placeholder={DEFAULT_BOOKING_MSG}
                  value={form.whatsapp_booking_message}
                  onChange={e => set('whatsapp_booking_message', e.target.value)}
                />
              </Field>

              <Field
                label="Messaggio reminder"
                hint={`Inviato ${form.whatsapp_reminder_hours}h prima dell'appuntamento`}
              >
                <textarea
                  className="input min-h-[80px] resize-y text-sm"
                  placeholder={DEFAULT_REMINDER_MSG}
                  value={form.whatsapp_reminder_message}
                  onChange={e => set('whatsapp_reminder_message', e.target.value)}
                />
              </Field>
            </>
          )}
        </Section>

        <div className="flex items-center gap-3">
          <button type="submit" disabled={updateMut.isPending} className="btn-primary">
            {updateMut.isPending ? 'Salvataggio…' : 'Salva impostazioni'}
          </button>
          {saved && (
            <span className="flex items-center gap-1.5 text-sm text-primary-dark">
              <Check className="w-4 h-4" /> Salvato
            </span>
          )}
        </div>
      </form>

      {/* Server-side setup, kept apart from the form: it is not something the
          salon can change from here. */}
      <div className="panel mt-4">
        <div className="band px-5 py-3">
          <span className="kicker">Configurazione Twilio</span>
        </div>
        <div className="p-5 flex flex-col gap-3 text-[13px] text-muted-foreground">
          <p>Per abilitare WhatsApp imposta queste variabili d'ambiente sul server:</p>
          <ul className="font-mono text-xs text-primary-dark divide-y divide-rule-soft border-y border-rule-soft">
            <li className="py-2">TWILIO_ACCOUNT_SID</li>
            <li className="py-2">TWILIO_AUTH_TOKEN</li>
            <li className="py-2">TWILIO_WHATSAPP_FROM <span className="text-ink-3">(es. whatsapp:+14155238886)</span></li>
          </ul>
          <p className="note">
            In sviluppo senza credenziali i messaggi vengono scritti in console, non inviati.
          </p>
        </div>
      </div>
    </div>
  )
}
