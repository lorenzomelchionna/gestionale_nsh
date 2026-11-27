import { VERSIONE } from '@/config/version'
import { cancellaCopia } from './copia'

/**
 * Accende e spegne il service worker (`public/sw.js`), che fa partire il
 * gestionale anche senza internet.
 *
 * Solo dal gestionale, mai dal portale: le clienti non ne hanno bisogno, e
 * un worker installato sui loro telefoni sarebbe un pezzo in più da cui
 * dipende il sito. Solo nel build di produzione: in sviluppo Vite serve i
 * file in un altro modo, e una cache in mezzo farebbe vedere codice vecchio.
 */
export function accendiOffline(): void {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator)) return
  navigator.serviceWorker
    .register(`/sw.js?v=${encodeURIComponent(VERSIONE)}`, { scope: '/' })
    .catch(() => undefined) // senza, il gestionale funziona come prima
}

/** All'uscita: niente copia dell'agenda, niente worker, niente cache. I dati
    delle clienti non restano su un dispositivo da cui si è usciti. */
export async function spegniOffline(): Promise<void> {
  cancellaCopia()
  try {
    if ('serviceWorker' in navigator) {
      const registrazioni = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrazioni.map(r => r.unregister()))
    }
    if ('caches' in window) {
      const nomi = await caches.keys()
      await Promise.all(nomi.filter(n => n.startsWith('nsh-gestionale-')).map(n => caches.delete(n)))
    }
  } catch { /* storage bloccato: non c'era niente */ }
}
