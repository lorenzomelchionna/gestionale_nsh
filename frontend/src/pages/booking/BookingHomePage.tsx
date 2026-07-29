import { Link } from 'react-router-dom'
import { Calendar, Scissors, Clock, ArrowRight } from 'lucide-react'
import { useClientAuth } from '@/components/layout/BookingLayout'

const STEPS = [
  { icon: Scissors, title: 'Scegli il servizio', text: 'Taglio, colore, trattamenti' },
  { icon: Calendar, title: 'Data e ora', text: 'Solo gli orari liberi' },
  { icon: Clock, title: 'Conferma', text: 'Ti avvisiamo noi' },
]

export default function BookingHomePage() {
  const { token } = useClientAuth()

  return (
    <div className="space-y-10">
      <section className="text-center pt-4 pb-2">
        <div className="w-16 h-16 bg-primary rounded-2xl flex items-center justify-center mx-auto mb-5 shadow-raised">
          <Scissors className="w-8 h-8 text-primary-foreground" />
        </div>
        <h1 className="text-title-lg font-bold text-foreground">New Style Hair</h1>
        <p className="text-muted-foreground mt-2 max-w-xs mx-auto">
          Prenota il tuo appuntamento online, in meno di un minuto.
        </p>
      </section>

      {/* Primary action sits high on the page so it is reachable without
          scrolling on a phone. */}
      <div className="space-y-2.5">
        <Link to="/booking/new" className="btn-primary w-full text-base">
          Prenota ora <ArrowRight className="w-4 h-4" />
        </Link>
        {!token && (
          <>
            <Link to="/login" className="btn-outline w-full">
              Accedi all'area personale
            </Link>
            {/* Said up front, because "Prenota ora" leads to the sign-in
                screen and an unexplained redirect reads as a dead end. */}
            <p className="text-xs text-muted-foreground text-center pt-1">
              Per prenotare serve un account: bastano nome, telefono ed email.
            </p>
          </>
        )}
        {token && (
          <Link to="/booking/account" className="btn-outline w-full">
            I miei appuntamenti
          </Link>
        )}
      </div>

      <section className="space-y-3">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider text-center">
          Come funziona
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <div key={title} className="card p-4 flex sm:flex-col items-center sm:text-center gap-3.5">
              <div className="relative w-11 h-11 rounded-xl bg-primary/12 flex items-center justify-center shrink-0">
                <Icon className="w-5 h-5 text-primary" />
                <span className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-primary text-primary-foreground text-[11px] font-bold flex items-center justify-center">
                  {i + 1}
                </span>
              </div>
              <div className="min-w-0">
                <p className="font-semibold text-sm text-foreground">{title}</p>
                <p className="text-[13px] text-muted-foreground mt-0.5">{text}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
