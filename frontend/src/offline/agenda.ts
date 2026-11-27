import axios from 'axios'
import { create } from 'zustand'
import { addDays, format } from 'date-fns'
import {
  getAbsencesInRange, getAppointmentsInRange, getBookingConfig,
  getCollaborators, getExtraDaysInRange,
} from '@/services/api'
import type {
  Absence, Appointment, BookingConfig, Collaborator, ExtraWorkDay,
} from '@/types'
import { CHIAVE_COPIA as CHIAVE } from './copia'
export { cancellaCopia } from './copia'

/**
 * L'agenda per quando in salone manca internet.
 *
 * Il 2026-11-27 la connessione del salone è caduta e il gestionale si è
 * aperto vuoto: i dati erano al sicuro sul server, ma nessuno sapeva chi
 * stava arrivando. Da allora, finché la rete c'è, il gestionale tiene in
 * questo browser una copia dei giorni vicini (ieri + i prossimi 14), e se
 * una chiamata del calendario non arriva al server la griglia si disegna da
 * lì, con un avviso in cima.
 *
 * - **Solo lettura.** Scrivere offline vorrebbe dire riconciliare con le
 *   prenotazioni che le clienti fanno intanto dal portale: no.
 * - **Dati personali.** Nomi, telefoni e note delle clienti restano su
 *   questo dispositivo: la copia si cancella all'uscita dal gestionale
 *   (`cancellaCopia`, chiamata dal logout) e non esiste sul portale.
 * - Le query che la usano hanno `networkMode: 'always'`: col default
 *   TanStack Query, se il browser sa di essere offline, non chiama neanche
 *   la funzione e la schermata resta in caricamento per sempre.
 * - Si usa solo quando il server **non risponde** (nessuna risposta, o 502,
 *   503, 504 dall'ingresso di Railway). Un errore vero dell'API resta un
 *   errore: la copia non deve nascondere un bug.
 */

const VERSIONE_COPIA = 1
export const GIORNI_PRIMA = 1
export const GIORNI_DOPO = 14
/** Ogni quanto si rinnova la copia mentre il gestionale è aperto. */
export const OGNI_MS = 5 * 60_000

export interface Copia {
  versione: number
  salvataAlle: string // ISO
  dal: string         // yyyy-MM-dd
  al: string          // yyyy-MM-dd
  appuntamenti: Appointment[]
  collaboratori?: Collaborator[]
  configurazione?: BookingConfig
  assenze?: Absence[]
  straordinari?: ExtraWorkDay[]
}

// ── Stato visibile: l'avviso in cima al gestionale ────────────────

interface StatoOffline {
  /** Il browser dice di non avere rete. */
  senzaRete: boolean
  /** Almeno una schermata sta mostrando la copia invece dei dati veri. */
  inUso: boolean
  segnaInUso: () => void
  segnaRete: (c: boolean) => void
  tornatoOnline: () => void
}

export const useOffline = create<StatoOffline>()(set => ({
  senzaRete: typeof navigator !== 'undefined' ? !navigator.onLine : false,
  inUso: false,
  segnaInUso: () => set({ inUso: true }),
  segnaRete: (c: boolean) => set({ senzaRete: !c }),
  tornatoOnline: () => set({ inUso: false, senzaRete: false }),
}))

// ── Lettura e scrittura ───────────────────────────────────────────

export function leggiCopia(): Copia | null {
  try {
    const grezza = localStorage.getItem(CHIAVE)
    if (!grezza) return null
    const copia = JSON.parse(grezza) as Copia
    return copia.versione === VERSIONE_COPIA ? copia : null
  } catch {
    return null
  }
}

/** Il server non ha risposto: rete assente o ingresso di Railway giù. */
export function erroreDiRete(e: unknown): boolean {
  if (!axios.isAxiosError(e)) return false
  if (!e.response) return true
  return [502, 503, 504].includes(e.response.status)
}

/** Rinnova la copia. Ogni pezzo per conto suo: un collaboratore non può
    leggere la configurazione, e non per questo perde l'agenda. */
export async function salvaCopia(oggi = new Date()): Promise<boolean> {
  const dal = format(addDays(oggi, -GIORNI_PRIMA), 'yyyy-MM-dd')
  const al = format(addDays(oggi, GIORNI_DOPO), 'yyyy-MM-dd')
  const [appuntamenti, collaboratori, configurazione, assenze, straordinari] = await Promise.allSettled([
    getAppointmentsInRange({ date_from: `${dal}T00:00:00`, date_to: `${al}T23:59:59` }),
    getCollaborators({ active_only: true }),
    getBookingConfig(),
    getAbsencesInRange(dal, al),
    getExtraDaysInRange(dal, al),
  ])
  // Senza appuntamenti la copia non serve: resta quella di prima.
  if (appuntamenti.status !== 'fulfilled') return false
  const valore = <T,>(r: PromiseSettledResult<T>) => (r.status === 'fulfilled' ? r.value : undefined)
  const precedente = leggiCopia()
  const copia: Copia = {
    versione: VERSIONE_COPIA,
    salvataAlle: new Date().toISOString(),
    dal, al,
    appuntamenti: appuntamenti.value.items,
    collaboratori: valore(collaboratori)?.items ?? precedente?.collaboratori,
    configurazione: valore(configurazione) ?? precedente?.configurazione,
    assenze: valore(assenze) ?? precedente?.assenze,
    straordinari: valore(straordinari) ?? precedente?.straordinari,
  }
  try {
    localStorage.setItem(CHIAVE, JSON.stringify(copia))
  } catch {
    return false // spazio pieno o storage bloccato: meglio niente copia che una rotta
  }
  useOffline.getState().tornatoOnline()
  return true
}

/**
 * La chiamata al server, e se il server non risponde la stessa risposta
 * presa dalla copia. `daCopia` restituisce `undefined` quando la copia non
 * ha quel dato: allora resta l'errore, come prima.
 */
export async function conRiserva<T>(
  chiamata: () => Promise<T>,
  daCopia: (copia: Copia) => T | undefined,
): Promise<T> {
  try {
    return await chiamata()
  } catch (e) {
    if (!erroreDiRete(e)) throw e
    const copia = leggiCopia()
    const dati = copia ? daCopia(copia) : undefined
    if (dati === undefined) throw e
    useOffline.getState().segnaInUso()
    return dati
  }
}

// ── Filtri, come li farebbe il server ─────────────────────────────

/** Gli appuntamenti che iniziano fra `da` e `a` (orari locali del salone,
    `yyyy-MM-ddTHH:mm:ss` come li manda il calendario). */
export function appuntamentiFra(copia: Copia, da: string, a: string, collaboratore?: number) {
  const inizio = new Date(da).getTime()
  const fine = new Date(a).getTime()
  const items = copia.appuntamenti.filter(x => {
    const t = new Date(x.start_time).getTime()
    return t >= inizio && t <= fine && (collaboratore == null || x.collaborator_id === collaboratore)
  })
  return { items, total: items.length, page: 1, page_size: items.length, pages: 1 }
}

export function assenzeFra(copia: Copia, da: string, a: string) {
  return copia.assenze?.filter(x => x.start_date <= a && x.end_date >= da)
}

export function straordinariFra(copia: Copia, da: string, a: string) {
  return copia.straordinari?.filter(x => x.date >= da && x.date <= a)
}

/** Il giorno `yyyy-MM-dd` è dentro la copia? Fuori, la griglia vuota
    direbbe «nessun appuntamento» quando invece non lo sappiamo. */
export function copre(copia: Copia, giorno: string) {
  return giorno >= copia.dal && giorno <= copia.al
}
