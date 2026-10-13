import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * La sessione della cliente sul portale, separata da quella dello staff.
 *
 * Fino al 2026-10-13 teneva solo l'access token, che scade dopo 30 minuti:
 * il refresh token che il login restituisce veniva scartato. La cliente
 * restava «collegata» a schermo per sempre, ma dopo mezz'ora ogni richiesta
 * tornava «Token non valido» — compreso «Invia richiesta», con prenotazioni
 * perse. Ora c'è anche il refresh, e `publicApi` rinnova da solo.
 *
 * I due token stanno anche in `localStorage` sotto chiavi proprie perché
 * `publicApi` li legge fuori da React, a ogni richiesta.
 */
interface ClientAuthState {
  token: string | null
  refreshToken: string | null
  email: string | null
  login: (token: string, email: string, refreshToken?: string | null) => void
  /** Dopo un rinnovo: stessa persona, token nuovi. */
  rinnova: (token: string, refreshToken: string) => void
  logout: () => void
}

export const CHIAVE_ACCESSO = 'client_token'
export const CHIAVE_RINNOVO = 'client_refresh_token'

export const useClientAuth = create<ClientAuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      email: null,
      login: (token, email, refreshToken = null) => {
        localStorage.setItem(CHIAVE_ACCESSO, token)
        if (refreshToken) localStorage.setItem(CHIAVE_RINNOVO, refreshToken)
        else localStorage.removeItem(CHIAVE_RINNOVO)
        set({ token, email, refreshToken })
      },
      rinnova: (token, refreshToken) => {
        localStorage.setItem(CHIAVE_ACCESSO, token)
        localStorage.setItem(CHIAVE_RINNOVO, refreshToken)
        set({ token, refreshToken })
      },
      logout: () => {
        localStorage.removeItem(CHIAVE_ACCESSO)
        localStorage.removeItem(CHIAVE_RINNOVO)
        set({ token: null, email: null, refreshToken: null })
      },
    }),
    { name: 'client-auth' }
  )
)
