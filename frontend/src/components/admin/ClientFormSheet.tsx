import { useState } from 'react'
import type { Client } from '@/types'
import Sheet from '@/components/ui/Sheet'

/** Only email and phone can be wrong here — the names are `required` in the
    form and the date comes from a date picker — so the message names them. */
export function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const campi = detail.map((d: { loc?: unknown[]; msg?: string }) => {
      const campo = d.loc?.[d.loc.length - 1]
      if (campo === 'email') return "L'email non è valida."
      if (campo === 'phone') return String(d.msg ?? '').replace(/^Value error, /, '')
      return 'Dati non validi: controlla i campi.'
    })
    return [...new Set(campi)].join(' ')
  }
  return 'Salvataggio non riuscito.'
}

export default function ClientFormSheet({ client, onClose, onSave, loading, error }: {
  client?: Client
  onClose: () => void
  onSave: (data: Partial<Client>) => void
  loading: boolean
  error?: unknown
}) {
  const [form, setForm] = useState({
    first_name: client?.first_name ?? '',
    last_name: client?.last_name ?? '',
    phone: client?.phone ?? '',
    email: client?.email ?? '',
    birth_date: client?.birth_date ?? '',
    notes: client?.notes ?? '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // `null`, not `undefined`: an emptied field has to reach the server as
    // "clear it". `undefined` drops out of the JSON, and the update — which
    // only touches the fields it is sent — would keep the old value.
    onSave({
      ...form,
      birth_date: form.birth_date || null,
      phone: form.phone || null,
      email: form.email || null,
    })
  }

  return (
    <Sheet
      onClose={onClose}
      title={client ? 'Modifica cliente' : 'Nuovo cliente'}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">
            Annulla
          </button>
          <button type="submit" form="client-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form id="client-form" onSubmit={handleSubmit} className="space-y-4">
        {error != null && (
          <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
            {errorText(error)}
          </p>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Nome *</label>
            <input
              className="input"
              required
              autoCapitalize="words"
              value={form.first_name}
              onChange={e => setForm({ ...form, first_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Cognome *</label>
            <input
              className="input"
              required
              autoCapitalize="words"
              value={form.last_name}
              onChange={e => setForm({ ...form, last_name: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="label">Telefono</label>
          <input
            className="input"
            type="tel"
            inputMode="tel"
            placeholder="+39 333 1234567"
            value={form.phone}
            onChange={e => setForm({ ...form, phone: e.target.value })}
          />
          <p className="text-xs text-muted-foreground mt-1.5">
            Puoi scriverlo come preferisci: senza prefisso viene completato con
            +39, il formato che serve alle notifiche WhatsApp.
          </p>
        </div>
        <div>
          <label className="label">Email</label>
          <input
            className="input"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Data di nascita</label>
          <input
            className="input"
            type="date"
            value={form.birth_date ?? ''}
            onChange={e => setForm({ ...form, birth_date: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Note</label>
          <textarea
            className="input"
            rows={3}
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
      </form>
    </Sheet>
  )
}
