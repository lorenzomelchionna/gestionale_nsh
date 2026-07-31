import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useClientAuth } from '@/components/layout/BookingLayout'
import { publicGetServices } from '@/services/publicApi'

/** Half an hour to a slot — the same unit the booking flow converts with, so
    the price list and the summary quote the same duration. */
const MINUTES_PER_SLOT = 30

export default function BookingHomePage() {
  const { token } = useClientAuth()

  const { data: services } = useQuery({
    queryKey: ['public-services'],
    queryFn: publicGetServices,
  })

  const listino = (services ?? []).filter(s => s.bookable_online)

  return (
    <div className="flex flex-col gap-10 py-2">
      {/* The salon says who it is before it asks for anything: the trade, the
          year, then the invitation. */}
      <section className="flex flex-col gap-4">
        <span className="kicker">Special haircut salon · dal 2016</span>
        <h1 className="font-heading text-[clamp(2.25rem,1.6rem+3vw,3.5rem)] leading-[1.06] text-foreground max-w-[28rem]">
          Prenota il tuo posto in poltrona
        </h1>
        <p className="text-base leading-relaxed text-muted-foreground max-w-[26rem]">
          Scegli il servizio, la persona e l'orario. Ti confermiamo noi, di
          solito entro un'ora.
        </p>

        {/* Primary action sits high on the page so it is reachable without
            scrolling on a phone. */}
        <div className="flex flex-col sm:flex-row gap-2.5 mt-2">
          <Link to="/booking/new" className="btn-primary sm:px-8">
            Prenota ora
          </Link>
          <Link
            to={token ? '/booking/account' : '/login'}
            className="btn-secondary sm:px-7"
          >
            {token ? 'I miei appuntamenti' : 'La mia area'}
          </Link>
        </div>

        {/* Said up front, because "Prenota ora" leads to the sign-in screen and
            an unexplained redirect reads as a dead end. */}
        {!token && (
          <p className="note">
            Per prenotare serve un account: bastano nome, telefono ed email.
          </p>
        )}
      </section>

      {/* The price list, set as one: name, what it involves, and what it costs
          closing the line — the way it hangs on the wall. */}
      {listino.length > 0 && (
        <section className="flex flex-col gap-4">
          <span className="kicker border-b border-rule pb-2.5">Listino</span>
          <div className="flex flex-col">
            {listino.map(s => (
              <div
                key={s.id}
                className="flex items-baseline gap-4 py-3.5 border-b border-rule-soft last:border-b-0"
              >
                <div className="flex-1 min-w-0 flex flex-col gap-1">
                  <span className="font-heading text-[19px] leading-tight tracking-[0.03em] text-foreground">
                    {s.name}
                  </span>
                  <span className="text-[13px] text-ink-3">
                    {s.description ? `${s.description} · ` : ''}
                    <span className="tabular-nums">
                      {s.duration_slots * MINUTES_PER_SLOT} min
                    </span>
                  </span>
                </div>
                <span className="text-[17px] tabular-nums text-primary-dark shrink-0">
                  €{s.price.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
