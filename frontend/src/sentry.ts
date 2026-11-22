import * as Sentry from '@sentry/react'
import type { Breadcrumb, ErrorEvent } from '@sentry/react'

/**
 * Sentry nel browser: gli errori che rompono una pagina, al gestionale o a una
 * cliente sul portale, arrivano per email invece di diventare «non funziona».
 *
 * Si accende solo se il build ha `VITE_SENTRY_DSN` (variabile del servizio
 * frontend su Railway, letta al build dal Dockerfile). In sviluppo resta spento.
 *
 * Cosa non parte, come lato server (`backend/app/osservabilita.py`):
 * - query string e frammento degli URL: il link di reset porta il token in
 *   `#token=`, le ricerche portano i nomi delle clienti in `?cerca=`;
 * - corpi delle richieste e IP: `sendDefaultPii` resta spento;
 * - email e telefoni nei testi (messaggi d'errore, righe di console),
 *   mascherati come nei log;
 * - niente Session Replay e niente tracciamento: registrerebbero lo schermo,
 *   cioè le schede delle clienti.
 */

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g
// Nove cifre o più, con spazi o trattini: un telefono. Id e anni restano.
const TELEFONO = /\+?\d(?:[\s-]?\d){8,}/g
const JWT = /\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]+/g
const SEGRETI = /password|token|secret|authorization|cookie|codice|code|otp/i
// `password=…`, `token: …` dentro un testo libero.
const COPPIA_SEGRETA = /\b(password|token|secret|codice|code|otp)(\s*[=:]\s*)[^\s&,;]+/gi

function mascheraEmail(indirizzo: string): string {
  const [locale, dominio] = indirizzo.split('@')
  return locale.length <= 2 ? `${locale[0]}***@${dominio}` : `${locale[0]}***${locale[locale.length - 1]}@${dominio}`
}

function mascheraTelefono(numero: string): string {
  const cifre = numero.replace(/\D/g, '')
  return `${numero.trim().startsWith('+') ? '+' : ''}${cifre.slice(0, 2)}***${cifre.slice(-4)}`
}

function testo(s: string): string {
  return s
    .replace(JWT, '«omesso»')
    .replace(COPPIA_SEGRETA, '$1$2«omesso»')
    .replace(EMAIL, mascheraEmail)
    .replace(TELEFONO, mascheraTelefono)
}

/** Un URL senza query e frammento: il percorso basta a capire la pagina. */
export function senzaParametri(url: string): string {
  return url.split(/[?#]/, 1)[0]
}

/** Toglie i dati personali da qualunque pezzo dell'evento, ricorsivamente. */
export function ripulisci<T>(valore: T, chiave = ''): T {
  if (chiave && SEGRETI.test(chiave)) return '«omesso»' as T
  if (typeof valore === 'string') {
    return (/^(https?:)?\/\//.test(valore) || chiave === 'url' || chiave === 'from' || chiave === 'to'
      ? testo(senzaParametri(valore))
      : testo(valore)) as T
  }
  if (Array.isArray(valore)) return valore.map(v => ripulisci(v)) as T
  if (valore && typeof valore === 'object') {
    return Object.fromEntries(
      Object.entries(valore as Record<string, unknown>).map(([k, v]) => [k, ripulisci(v, k)]),
    ) as T
  }
  return valore
}

export function preparaEvento(evento: ErrorEvent): ErrorEvent | null {
  if (evento.request) {
    delete evento.request.query_string
    delete evento.request.cookies
    delete evento.request.data
    if (evento.request.url) evento.request.url = senzaParametri(evento.request.url)
  }
  delete evento.user
  return ripulisci(evento)
}

export function preparaBreadcrumb(crumb: Breadcrumb): Breadcrumb | null {
  return ripulisci(crumb)
}

export function avviaSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return
  Sentry.init({
    dsn,
    release: `gestionale-nsh@${__APP_VERSION__}`,
    environment: import.meta.env.MODE,
    sendDefaultPii: false,
    // Solo errori: niente tracciamento delle prestazioni né registrazione
    // dello schermo.
    tracesSampleRate: 0,
    beforeSend: preparaEvento,
    beforeBreadcrumb: preparaBreadcrumb,
  })
}
