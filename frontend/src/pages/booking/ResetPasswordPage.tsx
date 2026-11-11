import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { clientResetPassword } from '@/services/publicApi'
import { MIN_PASSWORD } from '@/config/password'

/** Il token del link della mail.
 *
 *  Sta dopo `#` (`/booking/reset-password#token=…`): quella parte il browser
 *  non la manda al server, quindi aprire il link non scrive il token nel
 *  registro di nginx. Si accetta anche `?token=` per i link partiti prima
 *  del 2026-11-11, che però non sono più validi comunque (2 ore). */
function leggiToken(): string {
  const dalFrammento = new URLSearchParams(window.location.hash.slice(1)).get('token')
  const dallaQuery = new URLSearchParams(window.location.search).get('token')
  return (dalFrammento || dallaQuery || '').trim()
}

type Stato = 'modulo' | 'fatto' | 'link-non-valido'

/**
 * Dove arriva il link «Password dimenticata».
 *
 * Fino al 2026-11-11 questa pagina non esisteva: il backend mandava la mail,
 * il link portava alla home del portale, e una cliente che aveva dimenticato
 * la password poteva solo telefonare al salone.
 */
export default function ResetPasswordPage() {
  // Letto una volta sola: subito dopo lo si toglie dall'indirizzo.
  const [token] = useState(leggiToken)
  const [stato, setStato] = useState<Stato>(token ? 'modulo' : 'link-non-valido')
  const [password, setPassword] = useState('')
  const [conferma, setConferma] = useState('')
  const [mostra, setMostra] = useState(false)
  const [errore, setErrore] = useState('')
  const [loading, setLoading] = useState(false)

  // Il token non resta nella barra degli indirizzi né nella cronologia: chi
  // usa lo stesso computer dopo non lo ritrova, e uno screenshot non lo mostra.
  useEffect(() => {
    if (window.location.hash || window.location.search) {
      window.history.replaceState(null, '', window.location.pathname)
    }
  }, [])

  const invia = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrore('')
    if (password.length < MIN_PASSWORD) {
      setErrore(`La password deve essere di almeno ${MIN_PASSWORD} caratteri.`)
      return
    }
    if (password !== conferma) {
      setErrore('Le due password non coincidono. Controlla di averle scritte uguali.')
      return
    }
    setLoading(true)
    try {
      await clientResetPassword(token, password)
      setStato('fatto')
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 400) {
        // Scaduto, già usato, o sostituito da una richiesta più recente: per
        // chi legge è la stessa cosa, e la strada è una sola.
        setStato('link-non-valido')
      } else if (status === 422) {
        setErrore(`La password deve essere di almeno ${MIN_PASSWORD} caratteri.`)
      } else if (status === 429) {
        setErrore('Troppi tentativi. Aspetta un minuto e riprova.')
      } else {
        setErrore('Non siamo riusciti a cambiare la password. Riprova fra poco o contatta il salone.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-[400px] mx-auto flex flex-col gap-6 py-4">
      {stato === 'fatto' ? (
        <>
          <Titolo titolo="Password cambiata" sotto="Da adesso entri con la password nuova." />
          <Link to="/login" className="btn-primary w-full">Accedi</Link>
        </>
      ) : stato === 'link-non-valido' ? (
        <>
          <Titolo
            titolo="Link non più valido"
            sotto="Il link vale 2 ore e si può usare una volta sola. Se ne hai chiesto più di uno, vale solo l'ultimo."
          />
          <Link to="/login?password-dimenticata" className="btn-primary w-full">
            Chiedi un link nuovo
          </Link>
        </>
      ) : (
        <>
          <Titolo titolo="Scegli una nuova password" sotto={`Almeno ${MIN_PASSWORD} caratteri.`} />
          <form onSubmit={invia} className="flex flex-col gap-4">
            <div>
              <label htmlFor="nuova_password" className="label">Nuova password</label>
              <div className="relative">
                <input
                  id="nuova_password"
                  type={mostra ? 'text' : 'password'}
                  autoComplete="new-password"
                  className="input pr-12"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  minLength={MIN_PASSWORD}
                  autoFocus
                  required
                />
                <button
                  type="button"
                  onClick={() => setMostra(m => !m)}
                  className="absolute right-0.5 top-1/2 -translate-y-1/2 btn-icon !w-10 !h-10"
                  aria-label={mostra ? 'Nascondi password' : 'Mostra password'}
                >
                  {mostra ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label htmlFor="conferma_password" className="label">Ripeti la nuova password</label>
              <input
                id="conferma_password"
                type={mostra ? 'text' : 'password'}
                autoComplete="new-password"
                className="input"
                value={conferma}
                onChange={e => setConferma(e.target.value)}
                required
              />
              {conferma && password !== conferma && (
                <p className="text-xs text-danger mt-1.5">Le due password non coincidono.</p>
              )}
            </div>

            {errore && (
              <p
                role="alert"
                className="flex items-start gap-2 text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5"
              >
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                {errore}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || password !== conferma}
              className="btn-primary w-full mt-1"
            >
              {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Salvataggio…</> : 'Salva la nuova password'}
            </button>
          </form>
        </>
      )}
    </div>
  )
}

function Titolo({ titolo, sotto }: { titolo: string; sotto: string }) {
  return (
    <div className="flex flex-col gap-2">
      <h1 className="font-heading text-[34px] leading-tight text-foreground">{titolo}</h1>
      <p className="note">{sotto}</p>
    </div>
  )
}
