import axios from 'axios'
import type { Service, Collaborator, Appointment, TokenResponse, WaitlistEntry, WaitlistCreate } from '@/types'
import { CHIAVE_ACCESSO, CHIAVE_RINNOVO, useClientAuth } from '@/store/clientAuthStore'

const API_BASE = import.meta.env.VITE_API_URL || ''

// Niente `Content-Type` di default: axios lo mette da sé quando il corpo è un
// oggetto, e imporlo qui romperebbe qualunque upload di file — un corpo
// `FormData` vuole che sia il browser a scrivere l'intestazione, perché solo
// lui conosce il `boundary`. Vedi la nota estesa in `api.ts`, dove quel
// difetto è costato il caricamento delle foto prodotto.
const publicApi = axios.create({
  baseURL: `${API_BASE}/api/public`,
})

// The shared sign-in lives outside /api/public: it serves staff too, and may
// return either kind of token.
const rootApi = axios.create({
  baseURL: `${API_BASE}/api`,
})

export interface SignInResponse extends TokenResponse {
  audience: 'staff' | 'client'
  role?: string
}

/** One sign-in for everyone; `audience` says where the person belongs. */
export const signIn = (email: string, password: string) =>
  rootApi.post<SignInResponse>('/auth/login', { email, password }).then(r => r.data)

export interface DayAvailability {
  date: string
  slots: number
}

// `indexes: null` sends `service_ids=1&service_ids=2`, the form FastAPI reads
// as a list; axios's default `service_ids[]=1` would reach it as nothing.
export const publicGetAvailabilityCalendar = (params: {
  service_ids: number[]; collaborator_id: number; start_date: string; end_date: string
  /** Mentre la cliente sposta un suo appuntamento: non conta come occupato. */
  sostituisce?: number
}) =>
  publicApi
    .get<DayAvailability[]>('/availability/calendar', { params, paramsSerializer: { indexes: null } })
    .then(r => r.data)

// Inject client token
publicApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(CHIAVE_ACCESSO)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

/** Un rinnovo alla volta: se scadono insieme tre richieste, il rinnovo è uno
 *  e le altre lo aspettano, invece di consumare tre refresh in parallelo. */
let rinnovoInCorso: Promise<string> | null = null

const rinnovaSessione = (): Promise<string> => {
  if (!rinnovoInCorso) {
    const refresh = localStorage.getItem(CHIAVE_RINNOVO)
    rinnovoInCorso = (refresh
      ? axios.post<TokenResponse>(`${API_BASE}/api/public/auth/refresh`, { refresh_token: refresh })
          .then(r => {
            useClientAuth.getState().rinnova(r.data.access_token, r.data.refresh_token)
            return r.data.access_token
          })
      : Promise.reject(new Error('nessun refresh token'))
    ).finally(() => { rinnovoInCorso = null })
  }
  return rinnovoInCorso
}

/**
 * Sessione scaduta: si rinnova e si riprova, senza che la cliente se ne
 * accorga. Se non si può — refresh scaduto dopo 7 giorni, account chiuso, o
 * una sessione aperta prima del 2026-10-13, che il refresh non l'ha mai
 * salvato — si chiude la sessione e si va all'accesso con un messaggio
 * chiaro e il ritorno alla pagina da cui si veniva. Prima la cliente
 * restava lì con «Token non valido», e riprovare non serviva a niente.
 *
 * Solo per richieste partite *con* un token: un 401 senza token (il login
 * sbagliato, per dire) è una risposta da mostrare, non una sessione scaduta.
 */
publicApi.interceptors.response.use(
  res => res,
  async (error) => {
    const originale = error.config
    const conToken = Boolean(originale?.headers?.Authorization)
    if (error.response?.status !== 401 || !conToken || originale._ripetuta) {
      return Promise.reject(error)
    }
    originale._ripetuta = true
    try {
      const nuovo = await rinnovaSessione()
      originale.headers.Authorization = `Bearer ${nuovo}`
      return publicApi(originale)
    } catch {
      useClientAuth.getState().logout()
      const qui = window.location.pathname + window.location.search
      window.location.assign(`/login?sessione=scaduta&next=${encodeURIComponent(qui)}`)
      // La pagina sta per cambiare: niente messaggio d'errore nel frattempo.
      return new Promise(() => {})
    }
  },
)

export const publicGetServices = () =>
  publicApi.get<Service[]>('/services').then(r => r.data)

export const publicGetCollaborators = () =>
  publicApi.get<Collaborator[]>('/collaborators').then(r => r.data)

/** Start times for the services together, in the order they will be booked. */
export const publicGetAvailability = (params: {
  service_ids: number[]; collaborator_id: number; target_date: string
  /** Mentre la cliente sposta un suo appuntamento: non conta come occupato. */
  sostituisce?: number
}) =>
  publicApi
    .get<string[]>('/availability', { params, paramsSerializer: { indexes: null } })
    .then(r => r.data)

export interface VerificationRequired {
  email: string
  verification_required: boolean
  /** False when the code could not be mailed — the account exists regardless. */
  email_sent: boolean
}

/** Creates the account but grants no session — the emailed code does that. */
export const clientRegister = (data: {
  first_name: string; last_name: string; phone: string; email: string
  password: string; birth_date: string
}) =>
  publicApi.post<VerificationRequired>('/auth/register', data).then(r => r.data)

/** L'esito quando il numero non è ancora provato: nessun campo in comune
    con `TokenResponse`, così il chiamante distingue le due guardando se
    `access_token` c'è — vedi `PhoneVerificationRequired` nel backend. */
export interface PhoneVerificationRequired {
  phone_verification_required: true
  whatsapp_sent: boolean
  /** Il numero a cui è partito il codice, da scrivere sulla schermata;
      `null` se l'account non ne ha uno. */
  phone: string | null
}

/** La sessione arriva solo dopo *entrambi* i codici: un account che aveva
    già il telefono verificato (registrato prima di questo passo, o già
    completato) la prende qui; altrimenti la risposta dice di passare a
    `verifyPhone`. */
export const verifyEmail = (email: string, code: string) =>
  publicApi
    .post<TokenResponse | PhoneVerificationRequired>('/auth/verify-email', { email, code })
    .then(r => r.data)

export const verifyPhone = (email: string, code: string) =>
  publicApi.post<TokenResponse>('/auth/verify-phone', { email, code }).then(r => r.data)

export interface ResendResult {
  message: string
  email_sent: boolean
}

export const resendVerificationCode = (email: string) =>
  publicApi.post<ResendResult>('/auth/resend-code', { email }).then(r => r.data)

export interface PhoneResendResult {
  message: string
  whatsapp_sent: boolean
}

export const resendPhoneCode = (email: string) =>
  publicApi.post<PhoneResendResult>('/auth/resend-phone-code', { email }).then(r => r.data)

export interface PhoneChangeResult {
  whatsapp_sent: boolean
  phone: string
}

/** «Numero sbagliato? Correggilo»: manda il codice al numero nuovo, che
    passa sulla scheda solo quando il codice torna indietro. Chiede la
    password perché la sessione, a questo punto, non c'è ancora. */
export const changePhone = (email: string, password: string, phone: string) =>
  publicApi
    .post<PhoneChangeResult>('/auth/change-phone', { email, password, phone })
    .then(r => r.data)

export const clientLogin = (email: string, password: string) =>
  publicApi.post<TokenResponse>('/auth/login', { email, password }).then(r => r.data)

export const clientForgotPassword = (email: string) =>
  publicApi.post('/auth/forgot-password', { email }).then(r => r.data)

export const getMyAppointments = () =>
  publicApi.get<Appointment[]>('/appointments').then(r => r.data)

export const bookAppointment = (data: {
  client_id: number; collaborator_id: number;
  start_time: string; end_time: string; service_ids: number[]
}) =>
  publicApi.post<Appointment>('/appointments', data).then(r => r.data)

export interface GuestIdentity {
  first_name: string
  last_name: string
  phone: string
}

/** Senza account: il codice che la prenotazione chiederà, su WhatsApp.
    `whatsapp_sent: false` vuol dire che il codice c'è ma non è partito. */
export const requestGuestCode = (data: GuestIdentity) =>
  publicApi.post<{ whatsapp_sent: boolean }>('/guest/code', data).then(r => r.data)

/** Senza account: un codice, una prenotazione. La fine la calcola il server. */
export const bookAsGuest = (data: GuestIdentity & {
  code: string; collaborator_id: number; start_time: string; service_ids: number[]
}) =>
  publicApi.post<Appointment>('/guest/appointments', data).then(r => r.data)

export const cancelMyAppointment = (id: number) =>
  publicApi.post(`/appointments/${id}/cancel`).then(r => r.data)

/** Chiede di modificare un appuntamento confermato: nasce una richiesta «in
 *  attesa», e quello confermato resta valido finché il salone non accetta. */
export const requestChange = (id: number, data: {
  client_id: number; collaborator_id: number;
  start_time: string; end_time: string; service_ids: number[]
}) =>
  publicApi.post<Appointment>(`/appointments/${id}/change`, data).then(r => r.data)

export const acceptAlternative = (id: number) =>
  publicApi.post(`/appointments/${id}/accept-alternative`).then(r => r.data)

export const rejectAlternative = (id: number) =>
  publicApi.post(`/appointments/${id}/reject-alternative`).then(r => r.data)

export const getMyWaitlist = () =>
  publicApi.get<WaitlistEntry[]>('/waitlist').then(r => r.data)

export const joinWaitlist = (data: WaitlistCreate) =>
  publicApi.post<WaitlistEntry>('/waitlist', data).then(r => r.data)

export const leaveWaitlist = (id: number) =>
  publicApi.delete(`/waitlist/${id}`).then(r => r.data)
