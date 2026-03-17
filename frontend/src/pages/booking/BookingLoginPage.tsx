import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { clientLogin } from '@/services/publicApi'

export default function BookingLoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useClientAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await clientLogin(email, password)
      login(tokens.access_token, email)
      navigate('/booking/account')
    } catch {
      setError('Email o password non validi')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Accedi</h2>
        <p className="text-muted-foreground mt-1">Area riservata clienti</p>
      </div>
      <div className="card p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label block mb-1">Email</label>
            <input type="email" className="input" required value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label block mb-1">Password</label>
            <input type="password" className="input" required value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          {error && <p className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded">{error}</p>}
          <button type="submit" disabled={loading} className="btn-primary w-full disabled:opacity-60">
            {loading ? 'Accesso...' : 'Accedi'}
          </button>
        </form>
        <p className="text-sm text-center mt-4 text-muted-foreground">
          Non hai un account?{' '}
          <Link to="/booking/register" className="text-primary hover:underline">Registrati</Link>
        </p>
      </div>
    </div>
  )
}
