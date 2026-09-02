import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import clsx from 'clsx'
import { useAuthStore } from '@/store/authStore'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { getMe, setTokens } from '@/services/api'
import Logo from '@/components/ui/Logo'
import { INDIRIZZO, TELEFONO } from '@/config/business'
import {
  signIn, clientRegister, verifyEmail, resendVerificationCode,
} from '@/services/publicApi'

/** Deve corrispondere a `MIN_CLIENT_PASSWORD` in `schemas/client.py`. Il
 *  controllo vero sta sul server — questo esiste perché il 422 di Pydantic
 *  arriva in inglese e non dice quanti caratteri mancano. */
const MIN_PASSWORD = 10

/** Filtra il `next` della query prima di passarlo a `navigate()`.
 *
 *  Il parametro serve a riprendere una prenotazione interrotta, ma arriva
 *  dall'URL, cioè da chiunque sappia scrivere un link. Senza controllo,
 *  `?next=//sito-cattivo` portava fuori dominio **subito dopo** aver
 *  inserito le credenziali: è l'aggancio classico per una pagina che imita
 *  il salone e richiede di nuovo la password.
 *
 *  Passano solo i percorsi interni. `//` è la parte che si dimentica: per il
 *  browser `//host` è un URL assoluto con lo schema corrente, non un
 *  percorso — e così `/\host`, che alcuni browser normalizzano allo stesso
 *  modo. Un controllo che si limitasse a «inizia con /» li lascerebbe
 *  passare entrambi. */
function destinazioneInterna(valore: string | null): string | null {
  if (!valore) return null
  if (!valore.startsWith('/')) return null
  if (valore.startsWith('//') || valore.startsWith('/\\')) return null
  return valore
}

type Mode = 'signin' | 'register' | 'verify'

// Caps the date picker so a future birthday cannot be chosen at all, rather
// than being rejected only once the form is submitted.
const TODAY = new Date().toISOString().slice(0, 10)

const TITLES: Record<Mode, { title: string; sub: string }> = {
  signin: { title: 'Accesso riservato', sub: 'Inserisci le tue credenziali.' },
  register: { title: 'Crea il tuo account', sub: 'Bastano nome, telefono ed email.' },
  verify: { title: 'Conferma il tuo indirizzo', sub: 'Abbiamo mandato sei cifre alla tua email.' },
}

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
  const [confirmPassword, setConfirmPassword] = useState('')
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
  const next = destinazioneInterna(params.get('next'))

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
    // Checked here and not on the server: the second field exists to catch a
    // typo at the keyboard, and the server only ever receives one password.
    if (password.length < MIN_PASSWORD) {
      // Controllato anche qui, non solo dal server: il 422 di Pydantic arriva
      // in inglese e non dice quanti caratteri mancano.
      setError(`La password deve essere di almeno ${MIN_PASSWORD} caratteri.`)
      return
    }
    if (password !== confirmPassword) {
      setError('Le due password non coincidono. Controlla di averle scritte uguali.')
      return
    }
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
      // Registration is only finished here — the account existed before the
      // code, but this is the first moment it belongs to anyone. The greeting
      // rides along in navigation state so it shows once and not on a reload.
      navigate(next || '/booking', { state: { justRegistered: true } })
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
    setConfirmPassword('')
  }

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col lg:flex-row">
      {/* ── The plate ────────────────────────────────────────────────
          A full-height ink panel carrying the mark and what the salon is,
          so the door says whose it is before it asks for anything. On
          phones it condenses to a band; the form must stay above the fold. */}
      <div
        className="bg-chrome text-on-chrome shrink-0 pt-safe-t border-b border-border lg:border-b-0 lg:border-r px-6 py-6 flex items-center gap-4 lg:w-[34rem] lg:px-[3.25rem] lg:py-14 lg:flex-col lg:items-stretch lg:justify-between"
      >
        <Logo height={28} className="text-chrome-ink lg:!h-[5.5rem] lg:!w-[13rem]" />

        <div className="hidden lg:flex flex-col gap-5">
          <span className="w-11 h-px bg-chrome-ink" />
          <p className="font-heading text-[27px] leading-[1.4] text-on-chrome">
            Il registro del salone: appuntamenti, incassi e clienti in un unico
            posto.
          </p>
          <p className="text-sm text-chrome-dim">{INDIRIZZO.visita}</p>
        </div>

        <span className="text-xs text-chrome-dim lg:mt-0 ml-auto lg:ml-0 text-right lg:text-left">
          Assistenza {TELEFONO.visibile}
        </span>
      </div>

      {/* ── The form ─────────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-5 py-10 lg:px-24 pb-safe-b">
        <div className="w-full max-w-[400px] flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <h1 className="font-heading text-[34px] leading-tight text-foreground">
              {TITLES[mode].title}
            </h1>
            <p className="note">{TITLES[mode].sub}</p>
          </div>

          {mode === 'verify' ? (
            <VerifyForm
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
            <>
              {/* Two named options rather than a pill switch: the ledger
                  labels its choices and marks the live one with a rule. */}
              <div role="tablist" aria-label="Accedi o registrati" className="flex border-b border-rule">
                {(['signin', 'register'] as Mode[]).map(m => (
                  <button
                    key={m}
                    role="tab"
                    type="button"
                    aria-selected={mode === m}
                    onClick={() => switchMode(m)}
                    className={clsx(
                      'font-heading text-[13px] uppercase tracking-[0.12em] px-4 pb-2.5 -mb-px border-b-2 transition-colors',
                      mode === m
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-ink-3 hover:text-foreground'
                    )}
                  >
                    {m === 'signin' ? 'Accedi' : 'Registrati'}
                  </button>
                ))}
              </div>

              <form
                onSubmit={mode === 'signin' ? handleSignIn : handleRegister}
                className="flex flex-col gap-4"
              >
                {mode === 'register' && (
                  <>
                    <div className="grid grid-cols-2 gap-3.5">
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
                      minLength={mode === 'register' ? MIN_PASSWORD : undefined}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(s => !s)}
                      className="absolute right-0.5 top-1/2 -translate-y-1/2 btn-icon !w-10 !h-10"
                      aria-label={showPassword ? 'Nascondi password' : 'Mostra password'}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {mode === 'register' && (
                    <p className="text-xs text-ink-3 mt-1.5">Almeno 6 caratteri.</p>
                  )}
                </div>

                {mode === 'register' && (
                  <div>
                    <label htmlFor="confirm_password" className="label">Ripeti password</label>
                    <input
                      id="confirm_password"
                      // Same visibility toggle as the field above, so someone who
                      // chose to see what they are typing sees both.
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      className="input"
                      value={confirmPassword}
                      onChange={e => setConfirmPassword(e.target.value)}
                      placeholder="••••••••"
                      required
                    />
                    {/* Said as soon as it is knowable rather than on submit: a typo
                        is easiest to fix while the keyboard is still open. */}
                    {confirmPassword && password !== confirmPassword && (
                      <p className="text-xs text-danger mt-1.5">
                        Le due password non coincidono.
                      </p>
                    )}
                    {confirmPassword && password === confirmPassword && (
                      <p className="text-xs text-primary-dark mt-1.5">
                        Le password coincidono.
                      </p>
                    )}
                  </div>
                )}

                {/* Placed once, above the button, rather than as a hint under each
                    contact field: it explains what both of them are collected for. */}
                {mode === 'register' && (
                  <p className="text-xs text-ink-3">
                    Riceverai le comunicazioni sui tuoi appuntamenti via email e
                    WhatsApp.
                  </p>
                )}

                <ErrorNote error={error} />

                <button
                  type="submit"
                  disabled={loading || (mode === 'register' && password !== confirmPassword)}
                  className="btn-primary w-full mt-1"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {mode === 'signin' ? 'Accesso in corso…' : 'Registrazione…'}
                    </>
                  ) : mode === 'signin' ? (
                    'Entra'
                  ) : (
                    'Crea account'
                  )}
                </button>
              </form>

              <p className="text-[13px] text-ink-3 border-t border-rule pt-4">
                {mode === 'signin' ? (
                  <>
                    Non hai un account?{' '}
                    <button
                      type="button"
                      onClick={() => switchMode('register')}
                      className="text-primary-dark hover:underline"
                    >
                      Registrati
                    </button>{' '}
                    per prenotare online.
                  </>
                ) : (
                  <>Lavori nel salone? Il tuo accesso lo crea l'amministratore.</>
                )}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Error note ──────────────────────────────────────────────────── */

function ErrorNote({ error }: { error: string }) {
  if (!error) return null
  return (
    <p
      role="alert"
      className="flex items-start gap-2 text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5"
    >
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      {error}
    </p>
  )
}

interface VerifyProps {
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
function VerifyForm({
  code, setCode, notice, error, loading, onSubmit, onResend, onBack,
}: VerifyProps) {
  return (
    <>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        {/* Only what the caller set: when a send failed there is an error to
            show instead, and claiming a code is on its way would contradict it. */}
        {notice && <p className="text-[13px] text-muted-foreground">{notice}</p>}

        <div>
          <label htmlFor="code" className="label">Codice di verifica</label>
          <input
            id="code"
            className="input text-center font-heading text-3xl tracking-[0.4em] tabular-nums py-3"
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
          <p className="text-xs text-ink-3 mt-1.5">Sei cifre, valido per 15 minuti.</p>
        </div>

        <ErrorNote error={error} />

        <button
          type="submit"
          disabled={loading || code.length < 6}
          className="btn-primary w-full mt-1"
        >
          {loading ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Verifica in corso…</>
          ) : (
            'Conferma'
          )}
        </button>
      </form>

      <div className="flex items-center justify-between gap-3 border-t border-rule pt-4">
        <button
          type="button"
          onClick={onResend}
          disabled={loading}
          className="text-[13px] text-primary-dark hover:underline disabled:opacity-50"
        >
          Invia un nuovo codice
        </button>
        <button
          type="button"
          onClick={onBack}
          className="text-[13px] text-ink-3 hover:text-foreground"
        >
          Torna indietro
        </button>
      </div>
    </>
  )
}
