import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
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
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Errore durante la registrazione')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Registrati</h2>
        <p className="text-muted-foreground mt-1">Crea il tuo account per prenotare</p>
      </div>
      <div className="card p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Nome *</label>
              <input className="input" required value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} />
            </div>
            <div>
              <label className="label block mb-1">Cognome *</label>
              <input className="input" required value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} />
            </div>
          </div>
          <div>
            <label className="label block mb-1">Telefono *</label>
            <input className="input" type="tel" required value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Email *</label>
            <input className="input" type="email" required value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Password *</label>
            <input className="input" type="password" required minLength={6} value={form.password} onChange={e => setForm({...form, password: e.target.value})} />
          </div>
          {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded">{error}</p>}
          <button type="submit" disabled={loading} className="btn-primary w-full disabled:opacity-60">
            {loading ? 'Registrazione...' : 'Crea account'}
          </button>
        </form>
        <p className="text-sm text-center mt-4 text-muted-foreground">
          Hai già un account?{' '}
          <Link to="/booking/login" className="text-primary hover:underline">Accedi</Link>
        </p>
      </div>
    </div>
  )
}
