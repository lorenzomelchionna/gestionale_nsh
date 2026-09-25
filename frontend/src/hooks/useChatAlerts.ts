import { useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { getChatUnreadCount, type ChatLatest } from '@/services/api'

/**
 * Avvisa quando arriva un messaggio WhatsApp, finché il gestionale è aperto.
 *
 * Richiesta di Flavia del 25/09: «sennò non mi accorgo quando arrivano». Il
 * messaggio arrivava subito, ma niente lo diceva: il numero sul menu si
 * aggiornava ogni 30 secondi, e con la scheda in secondo piano per niente.
 *
 * Tre segnali, dal più discreto:
 *   - il numero dei non letti nel titolo della scheda, «(2) New Style Hair»;
 *   - un suono breve;
 *   - una notifica del computer, se consentita e se non si sta già guardando
 *     la chat; cliccandola si apre quella conversazione.
 *
 * Non si basa sul numero dei non letti: una conversazione lasciata aperta si
 * segna letta a ogni aggiornamento, e quel numero non salirebbe mai proprio
 * per chi si sta seguendo. Guarda invece l'id dell'ultimo messaggio arrivato,
 * che cresce sempre.
 *
 * A gestionale chiuso non avvisa: per quello servono le notifiche push.
 */

const TITOLO = 'New Style Hair'
// Condiviso fra le schede aperte: senza, due schede suonerebbero due volte.
const CHIAVE_ULTIMO_AVVISATO = 'nsh-chat-ultimo-avvisato'

export function useChatAlerts() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const visto = useRef<number | null>(null)

  const query = useQuery({
    queryKey: ['chat-unread'],
    queryFn: getChatUnreadCount,
    refetchInterval: 10_000,
    // Il punto è proprio la scheda in secondo piano: senza questo, TanStack
    // smette di chiedere finché non ci si torna sopra.
    refetchIntervalInBackground: true,
  })
  const data = query.data

  useEffect(() => sbloccaAudioAlPrimoGesto(), [])

  useEffect(() => {
    if (!data) return
    const ultimo = data.ultimo
    // Al primo giro si prende nota e basta: quello che è arrivato prima di
    // aprire il gestionale lo dice già il numero sul menu.
    if (visto.current === null) {
      visto.current = ultimo?.id ?? 0
      return
    }
    if (!ultimo || ultimo.id <= visto.current) return
    visto.current = ultimo.id

    qc.invalidateQueries({ queryKey: ['conversations'] })
    qc.invalidateQueries({ queryKey: ['conversation', ultimo.conversation_id] })

    if (!primaSchedaAdAvvisare(ultimo.id)) return
    suona()
    const staGuardando =
      document.visibilityState === 'visible' && location.pathname.startsWith('/admin/chat')
    if (!staGuardando) notifica(ultimo, id => navigate(`/admin/chat?c=${id}`))
    // `location` fuori dalle dipendenze di proposito: l'avviso scatta su un
    // messaggio nuovo, non su un cambio di pagina.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, qc, navigate])

  const unread = data?.unread ?? 0
  useEffect(() => {
    document.title = unread > 0 ? `(${unread}) ${TITOLO}` : TITOLO
    return () => { document.title = TITOLO }
  }, [unread])

  return unread
}

function primaSchedaAdAvvisare(id: number): boolean {
  try {
    const gia = Number(localStorage.getItem(CHIAVE_ULTIMO_AVVISATO) ?? 0)
    if (gia >= id) return false
    localStorage.setItem(CHIAVE_ULTIMO_AVVISATO, String(id))
  } catch {
    // Senza localStorage (navigazione privata) ogni scheda avvisa da sé.
  }
  return true
}

function notifica(ultimo: ChatLatest, apri: (conversationId: number) => void) {
  if (!('Notification' in window) || Notification.permission !== 'granted') return
  try {
    const n = new Notification(`WhatsApp · ${ultimo.display_name}`, {
      body: ultimo.preview || 'Nuovo messaggio',
      icon: '/favicon.svg',
      // Più messaggi della stessa persona sostituiscono la notifica invece
      // di impilarsene una per messaggio.
      tag: `chat-${ultimo.conversation_id}`,
    })
    n.onclick = () => {
      window.focus()
      apri(ultimo.conversation_id)
      n.close()
    }
  } catch {
    // Alcuni browser (Chrome su Android) vogliono le notifiche dal service
    // worker: lì arriveranno con le push, qui si rinuncia in silenzio.
  }
}

// ── Suono ─────────────────────────────────────────────────────────

let audio: AudioContext | null = null

/** I browser non fanno suonare una pagina finché qualcuno non la tocca:
    il contesto audio si crea al primo clic o tasto, e resta pronto. */
function sbloccaAudioAlPrimoGesto() {
  const sblocca = () => {
    try {
      audio ??= new AudioContext()
      void audio.resume()
    } catch {
      // Niente audio: restano titolo e notifica.
    }
  }
  window.addEventListener('pointerdown', sblocca, { once: true })
  window.addEventListener('keydown', sblocca, { once: true })
  return () => {
    window.removeEventListener('pointerdown', sblocca)
    window.removeEventListener('keydown', sblocca)
  }
}

/** Due note brevi, generate qui: nessun file audio da scaricare. */
function suona() {
  if (!audio || audio.state !== 'running') return
  const t = audio.currentTime
  for (const [freq, start] of [[880, 0], [1320, 0.14]] as const) {
    const osc = audio.createOscillator()
    const gain = audio.createGain()
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.0001, t + start)
    gain.gain.exponentialRampToValueAtTime(0.2, t + start + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + start + 0.18)
    osc.connect(gain).connect(audio.destination)
    osc.start(t + start)
    osc.stop(t + start + 0.2)
  }
}
