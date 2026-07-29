import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Scissors, AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { useAuthStore } from '@/store/authStore'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { getMe, setTokens } from '@/services/api'
import {
  signIn, clientRegister, verifyEmail, resendVerificationCode,
} from '@/services/publicApi'

type Mode = 'signin' | 'register' | 'verify'

// Caps the date picker so a future birthday cannot be chosen at all, rather
// than being rejected only once the form is submitted.
const TODAY = new Date().toISOString().slice(0, 10)

/**
 * One door for staff and clients.
 *
 * Which of the two someone is comes back from the server, not from a choice
 * they make here — asking "are you staff or a customer?" is a question only the
 * system can answer, and getting it wrong would just be a confusing error.
 *
 * Registration creates portal accounts only. Staff logins are issued by the
 * admin from "Team e accessi", so there is nothing to choose between.
 */
export default function LoginPage() {
  const [params] = useSearchParams()
  const [mode, setMode] = useState<Mode>(
    params.get('registrati') !== null ? 'register' : 'signin'
  )
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [form, setForm] = useState({
    first_name: '', last_name: '', phone: '', birth_date: '',
  })
  const [code, setCode] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const { login: staffLogin } = useAuthStore()
  const { login: clientLogin } = useClientAuth()
  const navigate = useNavigate()

  // Where to land after signing in — set when the portal bounced someone here
  // mid-booking, so they resume instead of restarting.
  const next = params.get('next')

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await signIn(email, password)
      if (tokens.audience === 'staff') {
        setTokens(tokens)
        staffLogin(tokens, await getMe())
        navigate('/admin')
      } else {
        clientLogin(tokens.access_token, email)
        navigate(next || '/booking')
      }
    } catch (err) {
      const res = (err as { response?: { status?: number; data?: { detail?: string } } })?.response
      const detail = res?.data?.detail ?? ''
      // The password was right but the address was never confirmed. Sending
      // them to the code screen is the only useful thing to do with that.
      if (res?.status === 403 && detail.toLowerCase().includes('verificat')) {
        setMode('verify')
        setNotice('Ti abbiamo inviato un codice. Controlla la tua email.')
        resendVerificationCode(email).catch(() => {})
      } else if (res?.status === 403) {
        setError('Questo account è disattivato. Contatta il salone.')
      } else {
        setError('Email o password non validi')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await clientRegister({ ...form, email, password })
      // No session yet: the account exists but the address is unproven.
      setMode('verify')
      if (result.email_sent) {
        setNotice(`Abbiamo inviato un codice a ${email}.`)
      } else {
        // The account was created but the mail did not leave. Saying "check
        // your inbox" here would send someone to wait for nothing.
        setNotice('')
        setError(
          'Il tuo account è stato creato, ma non siamo riusciti a inviare il codice. ' +
          'Riprova fra poco con "Invia un nuovo codice", oppure contatta il salone.'
        )
      }
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail ?? 'Errore durante la registrazione')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await verifyEmail(email, code.trim())
      clientLogin(tokens.access_token, email)
      navigate(next || '/booking')
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      setError(detail ?? 'Codice non valido')
    } finally {
      setLoading(false)
    }
  }

  const handleResend = async () => {
    setError('')
    setLoading(true)
    try {
      const result = await resendVerificationCode(email)
      setCode('')
      if (result.email_sent) {
        setNotice('Ti abbiamo inviato un nuovo codice.')
      } else {
        setNotice('')
        setError(
          'Non siamo riusciti a inviare il codice. Riprova fra poco o contatta il salone.'
        )
      }
    } catch {
      setError('Non siamo riusciti a inviare il codice. Riprova fra poco.')
    } finally {
      setLoading(false)
    }
  }

  const switchMode = (m: Mode) => {
    setMode(m)
    setError('')
    setNotice('')
  }

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col justify-center items-center p-5 pt-safe-t pb-safe-b">
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-x-0 top-0 h-72 bg-gradient-to-b from-primary/[0.10] to-transparent"
      />

      <div className="relative w-full max-w-sm">
        <div className="text-center mb-7">
          <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mx-auto mb-5 shadow-raised">
            <Scissors className="w-8 h-8 text-primary-foreground" />
          </div>
          <h1 className="text-title-lg font-bold text-foreground">New Style Hair</h1>
          <p className="text-muted-foreground text-sm mt-1">
            {mode === 'signin' && 'Accedi al tuo account'}
            {mode === 'register' && 'Crea il tuo account'}
            {mode === 'verify' && 'Conferma il tuo indirizzo'}
          </p>
        </div>

        {mode === 'verify' ? (
          <VerifyCard
            email={email}
            code={code}
            setCode={setCode}
            notice={notice}
            error={error}
            loading={loading}
            onSubmit={handleVerify}
            onResend={handleResend}
            onBack={() => switchMode('signin')}
          />
        ) : (
        <div className="card p-5 sm:p-6">
          <div
            role="tablist"
            aria-label="Accedi o registrati"
            className="grid grid-cols-2 gap-1 p-1 bg-muted/40 rounded-xl mb-5"
          >
            {(['signin', 'register'] as Mode[]).map(m => (
              <button
                key={m}
                role="tab"
                type="button"
                aria-selected={mode === m}
                onClick={() => switchMode(m)}
                className={clsx(
                  'min-h-touch rounded-lg text-sm font-semibold transition-colors',
                  mode === m
                    ? 'bg-surface text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {m === 'signin' ? 'Accedi' : 'Registrati'}
              </button>
            ))}
          </div>

          <form
            onSubmit={mode === 'signin' ? handleSignIn : handleRegister}
            className="space-y-4"
          >
            {mode === 'register' && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="first_name" className="label">Nome</label>
                    <input
                      id="first_name"
                      className="input"
                      required
                      autoComplete="given-name"
                      autoCapitalize="words"
                      value={form.first_name}
                      onChange={e => setForm({ ...form, first_name: e.target.value })}
                    />
                  </div>
                  <div>
                    <label htmlFor="last_name" className="label">Cognome</label>
                    <input
                      id="last_name"
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
                  <label htmlFor="phone" className="label">Telefono</label>
                  <input
                    id="phone"
                    className="input"
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="333 1234567"
                    required
                    value={form.phone}
                    onChange={e => setForm({ ...form, phone: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="birth_date" className="label">Data di nascita</label>
                  <input
                    id="birth_date"
                    className="input"
                    type="date"
                    autoComplete="bday"
                    required
                    max={TODAY}
                    value={form.birth_date}
                    onChange={e => setForm({ ...form, birth_date: e.target.value })}
                  />
                </div>
              </>
            )}

            <div>
              <label htmlFor="email" className="label">Email</label>
              <input
                id="email"
                type="email"
                inputMode="email"
                autoComplete={mode === 'signin' ? 'username' : 'email'}
                autoCapitalize="none"
                className="input"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="nome@esempio.it"
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="label">Password</label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  className="input pr-12"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  minLength={mode === 'register' ? 6 : undefined}
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
              {mode === 'register' && (
                <p className="text-xs text-muted-foreground mt-1.5">Almeno 6 caratteri.</p>
              )}
            </div>

            {/* Placed once, above the button, rather than as a hint under each
                contact field: it explains what both of them are collected for. */}
            {mode === 'register' && (
              <p className="text-xs text-muted-foreground">
                Riceverai le comunicazioni sui tuoi appuntamenti via email e
                WhatsApp.
              </p>
            )}

            {error && (
              <p
                role="alert"
                className="flex items-start gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg"
              >
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {error}
              </p>
            )}

            <button type="submit" disabled={loading} className="btn-primary w-full">
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {mode === 'signin' ? 'Accesso in corso...' : 'Registrazione...'}
                </>
              ) : mode === 'signin' ? (
                'Accedi'
              ) : (
                'Crea account'
              )}
            </button>
          </form>
        </div>
        )}

        {mode !== 'verify' && (
          <p className="text-center text-xs text-muted-foreground mt-6">
            {mode === 'signin' ? (
              <>
                Non hai un account?{' '}
                <button
                  type="button"
                  onClick={() => switchMode('register')}
                  className="text-primary font-medium hover:underline"
                >
                  Registrati
                </button>
              </>
            ) : (
              <>Lavori nel salone? Il tuo accesso lo crea l'amministratore.</>
            )}
          </p>
        )}
      </div>
    </div>
  )
}

interface VerifyProps {
  email: string
  code: string
  setCode: (v: string) => void
  notice: string
  error: string
  loading: boolean
  onSubmit: (e: React.FormEvent) => void
  onResend: () => void
  onBack: () => void
}

/**
 * The step between creating an account and having one.
 *
 * Kept deliberately bare: at this point the person is holding a phone in one
 * hand and their inbox in the other, and anything beyond the code is in the way.
 */
function VerifyCard({
  email, code, setCode, notice, error, loading, onSubmit, onResend, onBack,
}: VerifyProps) {
  return (
    <div className="card p-5 sm:p-6">
      <form onSubmit={onSubmit} className="space-y-4">
        {/* Only what the caller set: when a send failed there is an error to
            show instead, and claiming a code is on its way would contradict it. */}
        {notice && (
          <p className="text-[13px] text-muted-foreground">{notice}</p>
        )}

        <div>
          <label htmlFor="code" className="label">Codice di verifica</label>
          <input
            id="code"
            className="input text-center text-2xl tracking-[0.4em] tabular-nums"
            // A numeric keypad on phones, and the OS offer to fill the code
            // straight from the notification.
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]*"
            maxLength={6}
            autoFocus
            required
            placeholder="000000"
            value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
          />
          <p className="text-xs text-muted-foreground mt-1.5">
            Sei cifre, valido per 15 minuti.
          </p>
        </div>

        {error && (
          <p
            role="alert"
            className="flex items-start gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || code.length < 6}
          className="btn-primary w-full"
        >
          {loading ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Verifica in corso...</>
          ) : (
            'Conferma'
          )}
        </button>
      </form>

      <div className="flex items-center justify-between gap-3 mt-5">
        <button
          type="button"
          onClick={onResend}
          disabled={loading}
          className="text-xs text-primary font-medium hover:underline disabled:opacity-50"
        >
          Invia un nuovo codice
        </button>
        <button
          type="button"
          onClick={onBack}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Torna indietro
        </button>
      </div>
    </div>
  )
}
