import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { CalendarPlus, Check, Sparkles } from 'lucide-react'
import Sheet from '@/components/ui/Sheet'

/**
 * Greets a client the first time they arrive with an account.
 *
 * Shown from the layout rather than a single page, because verification can
 * land someone on the booking flow instead of the home page when they were
 * sent to sign in mid-booking.
 *
 * The trigger is navigation state, which the router drops once consumed — a
 * reload or a later visit will not bring it back, and it cannot be reached by
 * typing a URL.
 */
export default function WelcomeDialog() {
  const location = useLocation()
  const navigate = useNavigate()
  const justRegistered = Boolean(
    (location.state as { justRegistered?: boolean } | null)?.justRegistered
  )
  const [open, setOpen] = useState(justRegistered)

  useEffect(() => {
    if (!justRegistered) return
    // Clear the flag straight away so going back and forward, or refreshing,
    // does not greet the same person twice.
    navigate(location.pathname + location.search, { replace: true, state: null })
  }, [justRegistered, navigate, location.pathname, location.search])

  if (!open) return null

  return (
    <Sheet open onClose={() => setOpen(false)} size="sm">
      <div className="text-center pt-2 pb-1">
        <div className="w-14 h-14 rounded-2xl bg-primary/15 flex items-center justify-center mx-auto mb-4">
          <Sparkles className="w-7 h-7 text-primary" />
        </div>

        <h2 className="text-title font-bold text-foreground">
          Benvenuto in New Style Hair
        </h2>
        <p className="text-[13px] text-muted-foreground mt-2">
          Il tuo account è attivo. Da qui puoi prenotare quando vuoi e tenere
          d'occhio i tuoi appuntamenti.
        </p>

        <ul className="text-left text-[13px] text-muted-foreground space-y-2.5 mt-5">
          <li className="flex items-start gap-2.5">
            <Check className="w-4 h-4 text-primary shrink-0 mt-0.5" />
            Scegli servizio, collaboratore e orario fra quelli liberi
          </li>
          <li className="flex items-start gap-2.5">
            <Check className="w-4 h-4 text-primary shrink-0 mt-0.5" />
            Ricevi conferme e promemoria via email e WhatsApp
          </li>
          <li className="flex items-start gap-2.5">
            <Check className="w-4 h-4 text-primary shrink-0 mt-0.5" />
            Disdici o sposta un appuntamento dall'area personale
          </li>
        </ul>

        <button
          onClick={() => setOpen(false)}
          className="btn-primary w-full mt-6"
          autoFocus
        >
          <CalendarPlus className="w-4 h-4" /> Inizia
        </button>
      </div>
    </Sheet>
  )
}
