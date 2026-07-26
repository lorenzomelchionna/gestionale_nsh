import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { clientLogin } from '@/services/publicApi'

export default function BookingLoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
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
      <div className="text-center pt-2">
        <h2 className="text-title-lg font-bold">Accedi</h2>
        <p className="text-muted-foreground mt-1">Area riservata clienti</p>
      </div>

      <div className="card p-5 sm:p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="c-email" className="label">Email</label>
            <input
              id="c-email"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              className="input"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="c-password" className="label">Password</label>
            <div className="relative">
              <input
                id="c-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                className="input pr-12"
                required
                value={password}
                onChange={e => setPassword(e.target.value)}
              />
              <button
                type="button"
                onClick={() => setShowPassword(s => !s)}
                className="absolute right-1 top-1/2 -translate-y-1/2 btn-icon !w-10 !h-10"
                aria-label={showPassword ? 'Nascondi password' : 'Mostra password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && (
            <p role="alert" className="flex items-center gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
              <AlertCircle className="w-4 h-4 shrink-0" /> {error}
            </p>
          )}

          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Accesso...</> : 'Accedi'}
          </button>
        </form>

        <p className="text-sm text-center mt-5 text-muted-foreground">
          Non hai un account?{' '}
          <Link to="/booking/register" className="text-primary font-medium hover:underline">
            Registrati
          </Link>
        </p>
      </div>
    </div>
  )
}
