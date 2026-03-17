import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getBookingConfig, updateBookingConfig } from '@/services/api'
import { Check } from 'lucide-react'

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
  })

  useEffect(() => {
    if (config) {
      setForm({
        is_enabled: config.is_enabled,
        min_advance_hours: config.min_advance_hours,
        max_advance_days: config.max_advance_days,
        min_cancel_hours: config.min_cancel_hours,
        slot_duration_minutes: config.slot_duration_minutes,
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
    updateMut.mutate(form)
  }

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="text-2xl font-bold">Impostazioni</h1>

      <div className="card p-5">
        <h3 className="font-semibold mb-4">Prenotazione online</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <label className="flex items-center gap-3 cursor-pointer">
            <div className={`relative w-11 h-6 rounded-full transition-colors ${form.is_enabled ? 'bg-primary' : 'bg-gray-300'}`}>
              <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${form.is_enabled ? 'translate-x-5' : ''}`} />
            </div>
            <input
              type="checkbox"
              hidden
              checked={form.is_enabled}
              onChange={e => setForm({...form, is_enabled: e.target.checked})}
            />
            <div>
              <span className="text-sm font-medium">Prenotazione online abilitata</span>
              <p className="text-xs text-muted-foreground">I clienti possono prenotare dal portale pubblico</p>
            </div>
          </label>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label block mb-1">Anticipo minimo (ore)</label>
              <input
                className="input"
                type="number"
                min="0"
                max="72"
                value={form.min_advance_hours}
                onChange={e => setForm({...form, min_advance_hours: Number(e.target.value)})}
              />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 2 = non si può prenotare per le prossime 2 ore</p>
            </div>
            <div>
              <label className="label block mb-1">Anticipo massimo (giorni)</label>
              <input
                className="input"
                type="number"
                min="1"
                max="365"
                value={form.max_advance_days}
                onChange={e => setForm({...form, max_advance_days: Number(e.target.value)})}
              />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 30 = prenotabile fino a 30 giorni avanti</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label block mb-1">Preavviso cancellazione (ore)</label>
              <input
                className="input"
                type="number"
                min="0"
                max="168"
                value={form.min_cancel_hours}
                onChange={e => setForm({...form, min_cancel_hours: Number(e.target.value)})}
              />
              <p className="text-xs text-muted-foreground mt-0.5">Es: 24 = il cliente deve cancellare con 24h di anticipo</p>
            </div>
            <div>
              <label className="label block mb-1">Durata slot (minuti)</label>
              <select
                className="input"
                value={form.slot_duration_minutes}
                onChange={e => setForm({...form, slot_duration_minutes: Number(e.target.value)})}
              >
                <option value="15">15 minuti</option>
                <option value="30">30 minuti</option>
                <option value="60">60 minuti</option>
              </select>
            </div>
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
    </div>
  )
}
