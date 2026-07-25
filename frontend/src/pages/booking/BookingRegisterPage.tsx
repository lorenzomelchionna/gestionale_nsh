import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Loader2 } from 'lucide-react'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { clientRegister } from '@/services/publicApi'

export default function BookingRegisterPage() {
  const [form, setForm] = useState({
    first_name: '', last_name: '', phone: '', email: '', password: ''
  })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useClientAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await clientRegister(form)
      login(tokens.access_token, form.email)
      navigate('/booking/account')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? 'Errore durante la registrazione')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto space-y-6">
      <div className="text-center pt-2">
        <h2 className="text-title-lg font-bold">Registrati</h2>
        <p className="text-muted-foreground mt-1">Crea il tuo account per prenotare</p>
      </div>

      <div className="card p-5 sm:p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Nome *</label>
              <input
                className="input"
                required
                autoComplete="given-name"
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
                autoComplete="family-name"
                autoCapitalize="words"
                value={form.last_name}
                onChange={e => setForm({ ...form, last_name: e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="label">Telefono *</label>
            <input
              className="input"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              placeholder="+39 333 1234567"
              required
              value={form.phone}
              onChange={e => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Email *</label>
            <input
              className="input"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              required
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Password *</label>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              required
              minLength={6}
              value={form.password}
              onChange={e => setForm({ ...form, password: e.target.value })}
            />
            <p className="text-xs text-muted-foreground mt-1.5">Almeno 6 caratteri.</p>
          </div>

          {error && (
            <p role="alert" className="flex items-center gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Registrazione...</> : 'Crea account'}
          </button>
        </form>

        <p className="text-sm text-center mt-5 text-muted-foreground">
          Hai già un account?{' '}
          <Link to="/booking/login" className="text-primary font-medium hover:underline">
            Accedi
          </Link>
        </p>
      </div>
    </div>
  )
}
