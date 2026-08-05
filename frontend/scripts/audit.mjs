/**
 * `npm audit` con una lista di esclusioni motivate.
 *
 * `npm audit` da solo non sa escludere un singolo avviso: ha `--audit-level`,
 * che è una soglia di gravità, non una decisione su un caso specifico. Alzare
 * la soglia per far tacere una voce fa tacere anche tutte le altre della stessa
 * gravità — cioè si perde molto più di quello che si voleva perdere.
 *
 * Qui invece le esclusioni stanno in `.npm-audit-ignore`, una per riga e
 * ognuna con scritto sopra il perché, esattamente come `.pip-audit-ignore` fa
 * per il backend. Le due metà della sicurezza delle dipendenze si leggono
 * allo stesso modo.
 *
 * Uscita: 0 se non resta niente sopra la soglia, 1 altrimenti.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const RADICE = join(dirname(fileURLToPath(import.meta.url)), '..')
const SOGLIA = ['high', 'critical']

function esclusioni() {
  const file = join(RADICE, '.npm-audit-ignore')
  if (!existsSync(file)) return new Set()
  return new Set(
    readFileSync(file, 'utf8')
      .split('\n')
      .map((riga) => riga.trim())
      .filter((riga) => riga && !riga.startsWith('#')),
  )
}

function rapporto() {
  try {
    // `npm audit` esce con codice diverso da zero quando trova qualcosa, e
    // `execFileSync` lo tratta come un errore: il JSON è comunque nello
    // stdout dell'eccezione. Va letto da lì, altrimenti si scambia «ha
    // trovato vulnerabilità» per «il comando è fallito».
    return JSON.parse(
      execFileSync('npm', ['audit', '--json', '--omit=dev'], {
        cwd: RADICE,
        encoding: 'utf8',
        maxBuffer: 32 * 1024 * 1024,
      }),
    )
  } catch (errore) {
    if (errore.stdout) return JSON.parse(errore.stdout)
    throw errore
  }
}

const ignorati = esclusioni()
const dati = rapporto()
const rimasti = []
const taciuti = []

for (const [nome, voce] of Object.entries(dati.vulnerabilities ?? {})) {
  if (!SOGLIA.includes(voce.severity)) continue

  for (const via of voce.via) {
    // Le stringhe in `via` sono rimandi ad altri pacchetti, non avvisi.
    if (typeof via !== 'object') continue
    const codice = (via.url ?? '').split('/').pop()
    const riga = `${nome}  ${voce.severity}  ${codice}  ${via.title ?? ''}`
    if (ignorati.has(codice)) taciuti.push(riga)
    else rimasti.push(riga)
  }
}

if (taciuti.length) {
  console.log('Esclusi da .npm-audit-ignore (con motivazione nel file):')
  for (const riga of taciuti) console.log('  ' + riga)
  console.log('')
}

if (rimasti.length) {
  console.error(`Vulnerabilità da sistemare (${SOGLIA.join('/')}):`)
  for (const riga of rimasti) console.error('  ' + riga)
  process.exit(1)
}

console.log(`Nessuna vulnerabilità ${SOGLIA.join('/')} nel codice spedito al browser.`)
