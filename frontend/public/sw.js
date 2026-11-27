/*
 * Service worker del gestionale: apre la pagina anche senza internet.
 *
 * Nato dal 2026-11-27, quando in salone è mancata la rete e il gestionale si
 * è aperto vuoto. I dati offline li tiene l'app (`src/offline/agenda.ts`);
 * questo file fa solo in modo che l'app *parta*: senza, ricaricare la pagina
 * offline dà la pagina d'errore del browser e la copia salvata resta
 * irraggiungibile.
 *
 * Cosa fa, e niente di più:
 * - le pagine (navigazioni): prima la rete, salvando ogni volta la pagina
 *   ricevuta, e se la rete non risponde l'ultima salvata;
 * - `/assets/…` (nomi con l'hash, non cambiano mai): dalla cache se ci sono,
 *   altrimenti dalla rete e poi in cache;
 * - tutto il resto, `/api/` compresa, non lo tocca: passa com'è.
 *
 * Lo registra solo il gestionale (`src/offline/registra.ts`), non il portale
 * delle clienti, e lo toglie all'uscita. La versione arriva nell'URL
 * (`/sw.js?v=1.8.1`): a ogni rilascio è un worker nuovo, che butta la cache
 * della versione prima.
 *
 * INTERRUTTORE D'EMERGENZA: se un giorno questo file facesse danni, si
 * sostituisce il suo contenuto con
 *   self.addEventListener('install', () => self.skipWaiting())
 *   self.addEventListener('activate', e => e.waitUntil(
 *     caches.keys().then(k => Promise.all(k.map(c => caches.delete(c))))
 *       .then(() => self.registration.unregister())))
 * e si rilascia: ogni browser che lo ha installato se ne libera da solo.
 */

const VERSIONE = new URL(self.location.href).searchParams.get('v') || 'dev'
const CACHE = `nsh-gestionale-${VERSIONE}`

/** La pagina e i file che nomina (il bundle e il foglio di stile). */
async function salvaGuscio() {
  const cache = await caches.open(CACHE)
  const risposta = await fetch('/index.html', { cache: 'no-cache' })
  if (!risposta.ok) return
  const html = await risposta.clone().text()
  await cache.put('/index.html', risposta)
  const file = [...new Set(html.match(/\/assets\/[^"'\s>]+/g) || [])]
  await Promise.all(file.map(f => cache.add(f).catch(() => undefined)))
}

self.addEventListener('install', evento => {
  evento.waitUntil(salvaGuscio().catch(() => undefined).then(() => self.skipWaiting()))
})

self.addEventListener('activate', evento => {
  evento.waitUntil(
    caches.keys()
      .then(nomi => Promise.all(
        nomi.filter(n => n.startsWith('nsh-gestionale-') && n !== CACHE).map(n => caches.delete(n)),
      ))
      .then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', evento => {
  const richiesta = evento.request
  if (richiesta.method !== 'GET') return
  const url = new URL(richiesta.url)
  if (url.origin !== self.location.origin) return

  if (richiesta.mode === 'navigate') {
    evento.respondWith(
      fetch(richiesta).then(risposta => {
        // L'ultima pagina vista è quella da usare offline: nomina il bundle
        // che il browser ha appena caricato (e che finisce in cache sotto).
        if (risposta.ok && (risposta.headers.get('content-type') || '').includes('text/html')) {
          const copia = risposta.clone()
          caches.open(CACHE).then(c => c.put('/index.html', copia))
        }
        return risposta
      }).catch(async () => {
        const salvata = await caches.match('/index.html', { cacheName: CACHE, ignoreVary: true })
        return salvata || Response.error()
      }),
    )
    return
  }

  if (url.pathname.startsWith('/assets/')) {
    evento.respondWith(
      // `ignoreVary`: il bundle è un modulo con `crossorigin`, quindi la pagina
      // lo chiede con un'intestazione `Origin` che la copia salvata da
      // `salvaGuscio` non aveva. Con `Vary: Origin` sulla risposta la cache
      // non lo riconosceva, e offline la pagina restava bianca.
      caches.match(richiesta, { cacheName: CACHE, ignoreVary: true }).then(trovata => trovata || fetch(richiesta).then(risposta => {
        if (risposta.ok) {
          const copia = risposta.clone()
          caches.open(CACHE).then(c => c.put(richiesta, copia))
        }
        return risposta
      })),
    )
  }
  // Tutto il resto (API, icone, manifest): il browser fa da sé.
})
