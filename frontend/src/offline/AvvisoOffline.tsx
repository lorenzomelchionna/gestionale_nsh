import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { format, isToday, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { WifiOff } from 'lucide-react'
import { OGNI_MS, leggiCopia, salvaCopia, useOffline } from './agenda'
import { accendiOffline } from './registra'

/**
 * Tiene aggiornata la copia offline dell'agenda mentre il gestionale è
 * aperto: subito, ogni 5 minuti, e appena torna la rete. Un hook e non un
 * timer nel modulo, così vive esattamente quanto la sessione nel gestionale.
 */
export function useAgendaOffline() {
  const qc = useQueryClient()
  const segnaRete = useOffline(s => s.segnaRete)

  useEffect(() => {
    accendiOffline()
    const aggiorna = () => { if (navigator.onLine) void salvaCopia() }
    aggiorna()
    const timer = window.setInterval(aggiorna, OGNI_MS)
    const online = () => {
      segnaRete(true)
      aggiorna()
      // Le schermate che stavano mostrando la copia tornano ai dati veri.
      void qc.invalidateQueries()
    }
    const offline = () => segnaRete(false)
    window.addEventListener('online', online)
    window.addEventListener('offline', offline)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener('online', online)
      window.removeEventListener('offline', offline)
    }
  }, [qc, segnaRete])
}

function quando(iso: string) {
  const d = parseISO(iso)
  return isToday(d) ? `alle ${format(d, 'HH:mm')} di oggi` : `il ${format(d, 'd MMMM', { locale: it })} alle ${format(d, 'HH:mm')}`
}

/** La fascia in cima al gestionale quando si sta lavorando senza server. */
export function AvvisoOffline() {
  const { senzaRete, inUso } = useOffline()
  if (!senzaRete && !inUso) return null
  const copia = leggiCopia()

  return (
    <div role="status" className="flex items-start gap-3 border-b border-primary bg-primary/15 px-4 py-2.5 text-[13px] text-foreground sm:items-center">
      <WifiOff className="w-4 h-4 shrink-0 text-primary mt-0.5 sm:mt-0" />
      {copia ? (
        <span>
          <strong>Senza connessione.</strong> Stai vedendo l'agenda salvata su questo dispositivo{' '}
          {quando(copia.salvataAlle)} (dal {format(parseISO(copia.dal), 'd/M')} al{' '}
          {format(parseISO(copia.al), 'd/M')}). Le prenotazioni arrivate dopo non ci sono, e
          finché non torna internet non si può modificare niente.
        </span>
      ) : (
        <span>
          <strong>Senza connessione</strong>, e su questo dispositivo non c'è una copia
          dell'agenda. Prova con l'hotspot del telefono.
        </span>
      )}
    </div>
  )
}
