import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Calendar, Users, Scissors, Package,
  DollarSign, TrendingDown, Settings, LogOut, X,
  UserCircle, Clock, MessageSquare, Moon, Sun, ClipboardList,
  MoreHorizontal, PanelLeftClose, PanelLeft,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getPendingAppointments, getWaitlist } from '@/services/api'
import clsx from 'clsx'

type Badge = 'pending' | 'waitlist'
interface NavItem {
  to: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  badge?: Badge
}

const adminNavItems: NavItem[] = [
  { to: '/admin/calendar',             icon: Calendar,        label: 'Calendario' },
  { to: '/admin/appointments/pending', icon: Clock,           label: 'In attesa',       badge: 'pending' },
  { to: '/admin/clients',              icon: Users,           label: 'Clienti' },
  { to: '/admin/dashboard',            icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/admin/waitlist',             icon: ClipboardList,   label: "Lista d'attesa",  badge: 'waitlist' },
  { to: '/admin/collaborators',        icon: UserCircle,      label: 'Collaboratori' },
  { to: '/admin/services',             icon: Scissors,        label: 'Servizi' },
  { to: '/admin/products',             icon: Package,         label: 'Prodotti' },
  { to: '/admin/cash',                 icon: DollarSign,      label: 'Cassa' },
  { to: '/admin/expenses',             icon: TrendingDown,    label: 'Spese' },
  { to: '/admin/messaging',            icon: MessageSquare,   label: 'Messaggi' },
  { to: '/admin/settings',             icon: Settings,        label: 'Impostazioni' },
]

const collaboratorNavItems: NavItem[] = [
  { to: '/admin/calendar',             icon: Calendar, label: 'Calendario' },
  { to: '/admin/appointments/pending', icon: Clock,    label: 'In attesa', badge: 'pending' },
  { to: '/admin/clients',              icon: Users,    label: 'Clienti' },
  { to: '/admin/services',             icon: Scissors, label: 'Servizi' },
]

/** Items promoted to the phone tab bar; the rest live behind "Altro". */
const MOBILE_TAB_COUNT = 4

export default function AdminLayout() {
  const { user, logout } = useAuthStore()
  const { sidebarOpen, setSidebarOpen, isDark, toggleDark } = useUIStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const isAdmin = user?.role === 'admin'
  const navItems = isAdmin ? adminNavItems : collaboratorNavItems
  const tabItems = navItems.slice(0, MOBILE_TAB_COUNT)
  const drawerItems = navItems.slice(MOBILE_TAB_COUNT)

  const { data: pending } = useQuery({
    queryKey: ['pending-appointments'],
    queryFn: getPendingAppointments,
    refetchInterval: 30_000,
  })
  const pendingCount = pending?.length ?? 0

  const { data: waitlistData } = useQuery({
    queryKey: ['waitlist', 'waiting'],
    queryFn: () => getWaitlist('waiting'),
    refetchInterval: 60_000,
    enabled: isAdmin,
  })
  const waitlistCount = waitlistData?.length ?? 0

  const countFor = (badge?: Badge) =>
    badge === 'pending' ? pendingCount : badge === 'waitlist' ? waitlistCount : 0

  // Close the drawer on navigation, otherwise it stays over the new page.
  useEffect(() => setDrawerOpen(false), [location.pathname])

  useEffect(() => {
    if (!drawerOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [drawerOpen])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  // Longest matching path wins, so /admin/clients/5 still reads "Clienti".
  const currentLabel =
    [...navItems]
      .sort((a, b) => b.to.length - a.to.length)
      .find(i => location.pathname.startsWith(i.to))?.label ?? 'New Style Hair'

  return (
    <div className="min-h-[100dvh] bg-background lg:flex lg:h-[100dvh] lg:overflow-hidden">
      {/* ── Desktop sidebar ───────────────────────────────────── */}
      <aside
        className={clsx(
          'hidden lg:flex flex-col bg-surface border-r border-border shrink-0',
          'transition-[width] duration-300',
          sidebarOpen ? 'w-64' : 'w-[4.5rem]'
        )}
      >
        <div className="flex items-center gap-3 px-4 h-16 border-b border-border">
          <div className="w-9 h-9 bg-primary rounded-lg flex items-center justify-center shrink-0">
            <Scissors className="w-4 h-4 text-primary-foreground" />
          </div>
          {sidebarOpen && (
            <span className="font-semibold text-foreground text-[15px] leading-tight truncate">
              New Style Hair
            </span>
          )}
        </div>

        <nav className="flex-1 py-3 px-2.5 space-y-0.5 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label, badge }) => {
            const count = countFor(badge)
            return (
              <NavLink
                key={to}
                to={to}
                title={sidebarOpen ? undefined : label}
                className={({ isActive }) =>
                  clsx(
                    'relative flex items-center gap-3 px-3 h-11 rounded-lg text-sm font-medium transition-colors',
                    !sidebarOpen && 'justify-center',
                    isActive
                      ? 'bg-primary/[0.12] text-primary'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )
                }
              >
                <Icon className="w-[18px] h-[18px] shrink-0" />
                {sidebarOpen && <span className="truncate">{label}</span>}
                {count > 0 && (
                  <span
                    className={clsx(
                      'bg-warning text-white text-[11px] rounded-full font-bold leading-none flex items-center justify-center',
                      sidebarOpen
                        ? 'ml-auto min-w-5 h-5 px-1.5'
                        : 'absolute top-1.5 right-1.5 w-4 h-4 text-[10px]'
                    )}
                  >
                    {count > 9 ? '9+' : count}
                  </span>
                )}
              </NavLink>
            )
          })}
        </nav>

        <div className="border-t border-border p-2.5 space-y-1">
          <div className={clsx('flex items-center gap-2.5 px-2 py-2', !sidebarOpen && 'justify-center')}>
            <div className="w-8 h-8 rounded-full bg-primary/15 flex items-center justify-center shrink-0">
              <span className="text-primary text-xs font-bold">
                {user?.email?.[0]?.toUpperCase()}
              </span>
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-[13px] font-medium text-foreground truncate">{user?.email}</p>
                <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
              </div>
            )}
          </div>
          <div className={clsx('flex gap-1', !sidebarOpen && 'flex-col items-center')}>
            <button onClick={toggleDark} className="btn-icon" title={isDark ? 'Tema chiaro' : 'Tema scuro'}>
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="btn-icon"
              title={sidebarOpen ? 'Comprimi menu' : 'Espandi menu'}
            >
              {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
            </button>
            <button onClick={handleLogout} className="btn-icon hover:text-danger" title="Esci">
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main column ───────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 lg:overflow-hidden">
        {/* Mobile top bar */}
        <header className="lg:hidden sticky top-0 z-30 bg-surface/85 backdrop-blur-md border-b border-border pt-safe-t">
          <div className="h-14 px-3 flex items-center gap-2.5">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center shrink-0">
              <Scissors className="w-4 h-4 text-primary-foreground" />
            </div>
            <h1 className="font-semibold text-foreground truncate flex-1">{currentLabel}</h1>
            <button onClick={toggleDark} className="btn-icon" aria-label="Cambia tema">
              {isDark ? <Sun className="w-[18px] h-[18px]" /> : <Moon className="w-[18px] h-[18px]" />}
            </button>
          </div>
        </header>

        {/* Desktop top bar */}
        <header className="hidden lg:flex items-center gap-4 h-16 px-6 bg-surface border-b border-border shrink-0">
          <h1 className="text-[15px] font-semibold text-foreground">{currentLabel}</h1>
          <div className="flex-1" />
          {pendingCount > 0 && (
            <NavLink
              to="/admin/appointments/pending"
              className="flex items-center gap-2 text-[13px] font-medium text-warning hover:brightness-110"
            >
              <span className="w-2 h-2 rounded-full bg-warning animate-pulse" />
              {pendingCount} {pendingCount === 1 ? 'richiesta' : 'richieste'} in attesa
            </NavLink>
          )}
        </header>

        {/* Page content — bottom padding clears the mobile tab bar. */}
        <main className="flex-1 lg:overflow-y-auto p-4 sm:p-6 pb-[calc(theme(spacing.tabbar)+1rem)] lg:pb-6">
          <Outlet />
        </main>
      </div>

      {/* ── Mobile bottom tab bar ─────────────────────────────── */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-surface/90 backdrop-blur-md border-t border-border pb-safe-b">
        <div className="h-[3.75rem] grid grid-cols-5">
          {tabItems.map(({ to, icon: Icon, label, badge }) => {
            const count = countFor(badge)
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    'flex flex-col items-center justify-center gap-1 text-[11px] font-medium transition-colors',
                    isActive ? 'text-primary' : 'text-muted-foreground'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span className="relative">
                      <Icon className={clsx('w-[22px] h-[22px]', isActive && 'stroke-[2.4]')} />
                      {count > 0 && (
                        <span className="absolute -top-1.5 -right-2 min-w-[16px] h-4 px-1 bg-warning text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                          {count > 9 ? '9+' : count}
                        </span>
                      )}
                    </span>
                    <span className="truncate max-w-full px-0.5">{label}</span>
                  </>
                )}
              </NavLink>
            )
          })}
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex flex-col items-center justify-center gap-1 text-[11px] font-medium text-muted-foreground"
          >
            <MoreHorizontal className="w-[22px] h-[22px]" />
            <span>Altro</span>
          </button>
        </div>
      </nav>

      {/* ── Mobile "Altro" drawer ─────────────────────────────── */}
      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div
            className="absolute inset-0 bg-black/50 animate-fade-in"
            onClick={() => setDrawerOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Menu"
            className="absolute bottom-0 inset-x-0 bg-elevated rounded-t-2xl shadow-sheet animate-slide-up max-h-[85dvh] flex flex-col"
          >
            <div className="pt-3 pb-1 flex justify-center shrink-0">
              <span className="h-1 w-9 rounded-full bg-border" />
            </div>
            <div className="flex items-center justify-between px-5 py-3 shrink-0">
              <div className="min-w-0">
                <p className="font-semibold text-foreground truncate">{user?.email}</p>
                <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
              </div>
              <button onClick={() => setDrawerOpen(false)} className="btn-icon -mr-2" aria-label="Chiudi">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto overscroll-contain px-3 pb-2">
              {drawerItems.length > 0 ? (
                <div className="grid grid-cols-3 gap-2">
                  {drawerItems.map(({ to, icon: Icon, label, badge }) => {
                    const count = countFor(badge)
                    return (
                      <NavLink
                        key={to}
                        to={to}
                        className={({ isActive }) =>
                          clsx(
                            'relative flex flex-col items-center justify-center gap-2 p-3 rounded-xl text-center transition-colors',
                            isActive ? 'bg-primary/[0.12] text-primary' : 'bg-muted/60 text-foreground'
                          )
                        }
                      >
                        <Icon className="w-5 h-5" />
                        <span className="text-[11px] font-medium leading-tight">{label}</span>
                        {count > 0 && (
                          <span className="absolute top-2 right-2 min-w-[16px] h-4 px-1 bg-warning text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                            {count > 9 ? '9+' : count}
                          </span>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground text-center py-6">
                  Tutte le sezioni sono nella barra in basso.
                </p>
              )}
            </div>

            <div className="shrink-0 border-t border-border p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
              <button onClick={handleLogout} className="btn-outline w-full !text-danger">
                <LogOut className="w-4 h-4" /> Esci
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
