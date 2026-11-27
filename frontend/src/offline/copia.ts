/** Dove sta la copia offline dell'agenda (`offline/agenda.ts`). File a parte,
    senza import, perché anche `services/api.ts` la deve poter cancellare
    quando la sessione scade, e `agenda.ts` importa `api.ts`. */
export const CHIAVE_COPIA = 'nsh-agenda-offline'

export function cancellaCopia(): void {
  try { localStorage.removeItem(CHIAVE_COPIA) } catch { /* niente da cancellare */ }
}
