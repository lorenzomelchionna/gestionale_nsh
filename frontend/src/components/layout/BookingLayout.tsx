import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom'
import { Scissors, User, LogOut } from 'lucide-react'

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

export default function BookingLayout() {
  const { token, email, logout } = useClientAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-background">
      <header className="bg-surface border-b border-border sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/booking" className="flex items-center gap-2">
            <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
              <Scissors className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-foreground">New Style Hair</span>
          </Link>
          <div className="flex items-center gap-3">
            {token ? (
              <>
                <NavLink
                  to="/booking/account"
                  className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
                >
                  <User className="w-4 h-4" />
                  <span className="hidden sm:inline">{email}</span>
                </NavLink>
                <button
                  onClick={() => { logout(); navigate('/booking') }}
                  className="text-sm text-muted-foreground hover:text-red-500"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </>
            ) : (
              <Link to="/booking/login" className="btn-primary text-sm py-1.5">
                Accedi
              </Link>
            )}
          </div>
        </div>
      </header>
      <main className="max-w-4xl mx-auto px-4 py-8">
        <Outlet />
      </main>
    </div>
  )
}
