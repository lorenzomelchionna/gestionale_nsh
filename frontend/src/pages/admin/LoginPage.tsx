import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Scissors, AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { adminLogin, getMe, setTokens } from '@/services/api'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await adminLogin(email, password)
      setTokens(tokens)
      const user = await getMe()
      login(tokens, user)
      navigate('/admin')
    } catch {
      setError('Email o password non validi')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col justify-center items-center p-5 pt-safe-t pb-safe-b">
      {/* Soft brand wash behind the card */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-gradient-to-b from-primary/[0.10] to-transparent"
      />

      <div className="relative w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mx-auto mb-5 shadow-raised">
            <Scissors className="w-8 h-8 text-primary-foreground" />
          </div>
          <h1 className="text-title-lg font-bold text-foreground">New Style Hair</h1>
          <p className="text-muted-foreground text-sm mt-1">Gestionale salone</p>
        </div>

        <div className="card p-5 sm:p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="label">Email</label>
              <input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="username"
                autoCapitalize="none"
                className="input"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="nome@salone.it"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="label">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  className="input pr-12"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
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
              <p
                role="alert"
                className="flex items-center gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg"
              >
                <AlertCircle className="w-4 h-4 shrink-0" />
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Accesso in corso...
                </>
              ) : (
                'Accedi'
              )}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-6">
          Sei un cliente?{' '}
          <a href="/booking" className="text-primary font-medium hover:underline">
            Prenota online
          </a>
        </p>
      </div>
    </div>
  )
}
