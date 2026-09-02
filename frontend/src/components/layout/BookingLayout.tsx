import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import clsx from 'clsx'
import WelcomeDialog from '@/components/booking/WelcomeDialog'
import Logo from '@/components/ui/Logo'
import { INDIRIZZO, PARTITA_IVA, RAGIONE_SOCIALE, TELEFONO } from '@/config/business'

// Simple client auth store (separate from admin)
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface ClientAuthState {
  token: string | null
  email: string | null
  login: (token: string, email: string) => void
  logout: () => void
}

export const useClientAuth = create<ClientAuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      login: (token, email) => {
        localStorage.setItem('client_token', token)
        set({ token, email })
      },
      logout: () => {
        localStorage.removeItem('client_token')
        set({ token: null, email: null })
      },
    }),
    { name: 'client-auth' }
  )
)

const clientTabs = [
  { to: '/booking', end: true, label: 'Home' },
  { to: '/booking/new', end: false, label: 'Prenota' },
  { to: '/booking/account', end: false, label: 'Area personale' },
]

export default function BookingLayout() {
  const { token, email, logout } = useClientAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col">
      {/* The public face is paper, not chrome: the dark bar belongs to the
          staff side of the door. */}
      <header className="bg-surface border-b border-rule sticky top-0 z-30 pt-safe-t">
        <div className="max-w-3xl mx-auto px-4 h-16 flex items-center gap-4">
          <Link to="/booking" className="flex items-center gap-4 min-w-0 text-foreground">
            <Logo height={26} />
            <span className="hidden sm:inline text-[13px] text-ink-3 border-l border-border pl-4 whitespace-nowrap">
              {INDIRIZZO.visita} · {TELEFONO.visibile}
            </span>
          </Link>

          <div className="flex-1" />

          {token ? (
            <>
              <span className="hidden sm:inline text-[13px] text-muted-foreground truncate max-w-[16rem]">
                {email}
              </span>
              <button
                onClick={() => { logout(); navigate('/booking') }}
                className="btn-icon hover:text-danger"
                aria-label="Esci"
                title="Esci"
              >
                <LogOut className="w-[18px] h-[18px]" />
              </button>
            </>
          ) : (
            <Link to="/login" className="btn-accent btn-sm">
              Accedi
            </Link>
          )}
        </div>
      </header>

      {/* Bottom padding clears the client tab bar when signed in. */}
      <main
        className={clsx(
          'flex-1 w-full max-w-3xl mx-auto px-4 py-6',
          token && 'pb-[calc(theme(spacing.tabbar)+1rem)]'
        )}
      >
        <Outlet />
      </main>

      {/* Identificazione dell'attività: obbligatoria sul sito di chi ha una
          partita IVA (art. 35 DPR 633/72), e non è solo un adempimento — è
          anche il riscontro pubblico che Meta e Google cercano quando
          verificano che l'azienda dietro un profilo esista davvero.

          Sotto la barra delle schede quando c'è, altrimenti sparirebbe dietro
          i pulsanti sul telefono. */}
      <footer
        className={clsx(
          'border-t border-rule bg-surface',
          token ? 'pb-[calc(theme(spacing.tabbar)+1rem)]' : 'pb-safe-b'
        )}
      >
        <div className="max-w-3xl mx-auto px-4 py-5 text-[11px] leading-relaxed text-ink-3">
          <p className="font-medium text-ink-2">{RAGIONE_SOCIALE}</p>
          <p>{INDIRIZZO.legale}</p>
          <p>
            P.IVA / C.F. {PARTITA_IVA} ·{' '}
            <a href={`tel:${TELEFONO.tel}`} className="hover:text-foreground">
              {TELEFONO.visibile}
            </a>
          </p>
        </div>
      </footer>

      {/* Lives here rather than on the home page: verification can land someone
          on the booking flow when they were sent to sign in mid-booking. */}
      <WelcomeDialog />

      {/* Signed-in clients get thumb-level navigation; guests only ever see
          the login/booking funnel, so the bar would be noise. */}
      {token && (
        <nav className="fixed bottom-0 inset-x-0 z-30 bg-surface border-t border-rule pb-safe-b">
          <div className="max-w-3xl mx-auto h-[3.75rem] grid grid-cols-3">
            {clientTabs.map(({ to, end, label }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center justify-center -mt-px border-t-2 transition-colors',
                    isActive ? 'border-primary' : 'border-transparent'
                  )
                }
              >
                {({ isActive }) => (
                  <span
                    className={clsx(
                      'font-heading text-[11px] uppercase tracking-[0.08em]',
                      isActive ? 'text-primary' : 'text-ink-3'
                    )}
                  >
                    {label}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
      )}
    </div>
  )
}
