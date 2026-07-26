import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom'
import { Scissors, User, LogOut, Home, CalendarPlus } from 'lucide-react'
import clsx from 'clsx'

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
  { to: '/booking', end: true, icon: Home, label: 'Home' },
  { to: '/booking/new', end: false, icon: CalendarPlus, label: 'Prenota' },
  { to: '/booking/account', end: false, icon: User, label: 'Area mia' },
]

export default function BookingLayout() {
  const { token, email, logout } = useClientAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-[100dvh] bg-background flex flex-col">
      <header className="bg-surface/85 backdrop-blur-md border-b border-border sticky top-0 z-30 pt-safe-t">
        <div className="max-w-3xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
          <Link to="/booking" className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center shrink-0">
              <Scissors className="w-4 h-4 text-primary-foreground" />
            </div>
            <span className="font-semibold text-foreground truncate">New Style Hair</span>
          </Link>
          {token ? (
            <button
              onClick={() => { logout(); navigate('/booking') }}
              className="btn-icon hover:text-danger"
              aria-label="Esci"
              title={email ?? 'Esci'}
            >
              <LogOut className="w-[18px] h-[18px]" />
            </button>
          ) : (
            <Link to="/booking/login" className="btn-primary btn-sm">
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

      {/* Signed-in clients get thumb-level navigation; guests only ever see
          the login/booking funnel, so the bar would be noise. */}
      {token && (
        <nav className="fixed bottom-0 inset-x-0 z-30 bg-surface/90 backdrop-blur-md border-t border-border pb-safe-b">
          <div className="max-w-3xl mx-auto h-[3.75rem] grid grid-cols-3">
            {clientTabs.map(({ to, end, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  clsx(
                    'flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors',
                    isActive ? 'text-primary' : 'text-muted-foreground'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={clsx('w-[22px] h-[22px]', isActive && 'stroke-[2.4]')} />
                    <span>{label}</span>
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </nav>
      )}
    </div>
  )
}
