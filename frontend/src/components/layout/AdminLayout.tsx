import { useEffect, useState } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Calendar, Users, Scissors, Package,
  DollarSign, TrendingDown, Settings, LogOut, X,
  UserCircle, Clock, MessageSquare, ClipboardList, ShieldCheck,
  PanelLeftClose, PanelLeft, Search, CalendarSearch, Gift,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getPendingAppointments, getWaitlist, getChatUnreadCount } from '@/services/api'
import { INDIRIZZO } from '@/config/business'
import Logo from '@/components/ui/Logo'
import clsx from 'clsx'

type Badge = 'pending' | 'waitlist' | 'chat'
interface NavItem {
  to: string
  icon: React.ComponentType<{ className?: string }>
  label: string
  badge?: Badge
}
/** The rail is filed by subject, the way the sections of a register are. */
interface NavGroup {
  title: string
  items: NavItem[]
}

const adminNav: NavGroup[] = [
  {
    title: 'Giornata',
    items: [
      { to: '/admin/calendar',             icon: Calendar,      label: 'Calendario' },
      { to: '/admin/appointments/pending', icon: Clock,         label: 'In attesa',      badge: 'pending' },
      { to: '/admin/chat',                 icon: MessageSquare, label: 'Chat',           badge: 'chat' },
      { to: '/admin/waitlist',             icon: ClipboardList, label: "Lista d'attesa", badge: 'waitlist' },
    ],
  },
  {
    title: 'Registro',
    items: [
      { to: '/admin/clients',   icon: Users,           label: 'Clienti' },
      { to: '/admin/appointments/all', icon: CalendarSearch, label: 'Appuntamenti' },
      { to: '/admin/cash',      icon: DollarSign,      label: 'Cassa' },
      { to: '/admin/gift-cards', icon: Gift,          label: 'Buoni regalo' },
      { to: '/admin/expenses',  icon: TrendingDown,    label: 'Spese' },
      { to: '/admin/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
    ],
  },
  {
    title: 'Salone',
    items: [
      { to: '/admin/collaborators', icon: UserCircle, label: 'Collaboratori' },
      { to: '/admin/services',      icon: Scissors,   label: 'Servizi' },
      { to: '/admin/products',      icon: Package,    label: 'Prodotti' },
    ],
  },
  {
    title: 'Gestione',
    items: [
      { to: '/admin/messaging', icon: MessageSquare, label: 'Messaggi' },
      { to: '/admin/team',      icon: ShieldCheck,   label: 'Team e accessi' },
      { to: '/admin/settings',  icon: Settings,      label: 'Impostazioni' },
    ],
  },
]

/** Collaborators reach five sections. The rest of the register is not theirs. */
const collaboratorNav: NavGroup[] = [
  {
    title: 'Giornata',
    items: [
      { to: '/admin/calendar',             icon: Calendar,      label: 'Calendario' },
      { to: '/admin/appointments/pending', icon: Clock,         label: 'In attesa', badge: 'pending' },
      { to: '/admin/chat',                 icon: MessageSquare, label: 'Chat',      badge: 'chat' },
    ],
  },
  {
    title: 'Salone',
    items: [
      { to: '/admin/clients',  icon: Users,    label: 'Clienti' },
      { to: '/admin/appointments/all', icon: CalendarSearch, label: 'Appuntamenti' },
      { to: '/admin/services', icon: Scissors, label: 'Servizi' },
    ],
  },
]

/** Items promoted to the phone tab bar; the rest live behind "Altro". */
const MOBILE_TAB_COUNT = 4

export default function AdminLayout() {
  const { user, logout } = useAuthStore()
  const { sidebarOpen, setSidebarOpen, isDark, toggleDark } = useUIStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [term, setTerm] = useState('')

  const isAdmin = user?.role === 'admin'
  const groups = isAdmin ? adminNav : collaboratorNav
  const navItems = groups.flatMap(g => g.items)
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

  const { data: chatUnread } = useQuery({
    queryKey: ['chat-unread'],
    queryFn: getChatUnreadCount,
    refetchInterval: 30_000,
  })
  const chatCount = chatUnread?.unread ?? 0

  const countFor = (badge?: Badge) =>
    badge === 'pending' ? pendingCount
    : badge === 'waitlist' ? waitlistCount
    : badge === 'chat' ? chatCount
    : 0

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

  // The search field in the bar hands off to the clients archive, which is
  // the one index in the app that searches by name, phone and email at once.
  const runSearch = (e: React.FormEvent) => {
    e.preventDefault()
    const q = term.trim()
    if (!q) return
    navigate(`/admin/clients?q=${encodeURIComponent(q)}`)
    setTerm('')
  }

  // Longest matching path wins, so /admin/clients/5 still reads "Clienti".
  const currentLabel =
    [...navItems]
      .sort((a, b) => b.to.length - a.to.length)
      .find(i => location.pathname.startsWith(i.to))?.label ?? 'New Style Hair'

  return (
    <div className="min-h-[100dvh] bg-background lg:flex lg:flex-col lg:h-[100dvh] lg:overflow-hidden">
      {/* ── The dark bar ───────────────────────────────────────────
          Runs the full width above both rail and page, the way the header
          of a bound register runs across the spread. */}
      <header className="hidden lg:flex items-center gap-5 h-14 px-[22px] bg-chrome shrink-0">
        <Logo height={26} className="text-chrome-ink" />
        <span className="text-xs text-chrome-dim border-l border-chrome-ink/20 pl-5 whitespace-nowrap">
          {INDIRIZZO.visita}
        </span>

        <form onSubmit={runSearch} className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-chrome-dim pointer-events-none" />
          <input
            type="search"
            value={term}
            onChange={e => setTerm(e.target.value)}
            placeholder="Cerca cliente per nome, telefono, email…"
            aria-label="Cerca cliente"
            className="w-[320px] bg-on-chrome/[0.07] border border-chrome-ink/20 text-on-chrome placeholder:text-chrome-dim text-[13px] pl-9 pr-3 py-2 outline-none focus:border-primary transition-colors"
          />
        </form>

        <div className="flex-1" />

        {pendingCount > 0 && (
          <NavLink
            to="/admin/appointments/pending"
            className="font-heading text-xs uppercase tracking-[0.1em] text-primary border border-primary px-3 py-1.5 hover:bg-primary/15 transition-colors whitespace-nowrap"
          >
            {pendingCount} {pendingCount === 1 ? 'richiesta' : 'richieste'} in attesa
          </NavLink>
        )}

        <ThemeSwitch isDark={isDark} onToggle={toggleDark} />

        <span className="text-[13px] text-chrome-dim whitespace-nowrap">
          {user?.email}
          {' · '}
          <button onClick={handleLogout} className="text-chrome-ink hover:underline">
            esci
          </button>
        </span>
      </header>

      <div className="lg:flex lg:flex-1 lg:min-h-0">
        {/* ── Desktop rail ───────────────────────────────────────── */}
        <aside
          className={clsx(
            'hidden lg:flex flex-col bg-surface border-r border-rule shrink-0 overflow-y-auto',
            'transition-[width] duration-300',
            sidebarOpen ? 'w-[236px]' : 'w-[4.5rem]'
          )}
        >
          <nav className={clsx('flex-1 flex flex-col gap-5', sidebarOpen ? 'py-5' : 'py-3 px-2.5')}>
            {groups.map(group => (
              <div key={group.title} className="flex flex-col">
                {sidebarOpen && <div className="kicker px-5 pb-2">{group.title}</div>}
                {group.items.map(({ to, icon: Icon, label, badge }) => {
                  const count = countFor(badge)
                  return (
                    <NavLink
                      key={to}
                      to={to}
                      title={sidebarOpen ? undefined : label}
                      className={({ isActive }) =>
                        clsx(
                          'relative flex items-center gap-2.5 transition-colors',
                          sidebarOpen
                            ? 'justify-between px-5 py-2.5 border-l-2'
                            : 'justify-center h-11 border-l-2',
                          isActive
                            ? 'border-primary bg-primary/10'
                            : 'border-transparent hover:bg-foreground/[0.05]'
                        )
                      }
                    >
                      {({ isActive }) =>
                        sidebarOpen ? (
                          <>
                            <span
                              className={clsx(
                                'font-heading text-[15px] tracking-[0.04em] truncate',
                                isActive ? 'text-foreground' : 'text-ink-2'
                              )}
                            >
                              {label}
                            </span>
                            {count > 0 && (
                              <span
                                className={clsx(
                                  'text-[11px] tabular-nums shrink-0',
                                  isActive ? 'text-primary-dark' : 'text-ink-3'
                                )}
                              >
                                {count}
                              </span>
                            )}
                          </>
                        ) : (
                          <>
                            <Icon
                              className={clsx(
                                'w-[18px] h-[18px] shrink-0',
                                isActive ? 'text-primary' : 'text-muted-foreground'
                              )}
                            />
                            {count > 0 && (
                              <span className="absolute top-1.5 right-1.5 text-[10px] tabular-nums text-primary-dark">
                                {count}
                              </span>
                            )}
                          </>
                        )
                      }
                    </NavLink>
                  )
                })}
              </div>
            ))}
          </nav>

          <div className="mt-auto border-t border-rule px-5 py-3.5 flex items-center gap-2">
            {sidebarOpen && (
              <span className="text-[11px] leading-snug text-ink-3 capitalize">
                {user?.role === 'admin' ? 'Amministratore' : 'Collaboratore'}
              </span>
            )}
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="btn-icon ml-auto"
              title={sidebarOpen ? 'Comprimi menu' : 'Espandi menu'}
            >
              {sidebarOpen ? <PanelLeftClose className="w-4 h-4" /> : <PanelLeft className="w-4 h-4" />}
            </button>
          </div>
        </aside>

        {/* ── Main column ─────────────────────────────────────────── */}
        <div className="flex-1 flex flex-col min-w-0 lg:overflow-hidden">
          {/* Phone: the same dark bar, condensed to the section name. */}
          <header className="lg:hidden sticky top-0 z-30 bg-chrome pt-safe-t">
            <div className="h-14 px-4 flex items-center gap-3">
              <Logo height={20} className="text-chrome-ink" />
              <h1 className="font-heading text-[17px] tracking-[0.03em] text-chrome-ink truncate flex-1 border-l border-chrome-ink/25 pl-3">
                {currentLabel}
              </h1>
              <ThemeSwitch isDark={isDark} onToggle={toggleDark} compact />
            </div>
          </header>

          {/* Page content — bottom padding clears the mobile tab bar. */}
          <main className="flex-1 lg:overflow-y-auto p-4 sm:p-6 pb-[calc(theme(spacing.tabbar)+1rem)] lg:pb-6">
            <Outlet />
          </main>
        </div>
      </div>

      {/* ── Mobile bottom tab bar ─────────────────────────────────
          Set in the display face, no icons: the design carries navigation
          typographically, and five words fit where five icons crowd. */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-surface border-t border-rule pb-safe-b">
        <div className="h-[3.75rem] grid grid-cols-5">
          {tabItems.map(({ to, label, badge }) => {
            const count = countFor(badge)
            return (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  clsx(
                    'relative flex items-center justify-center px-1 -mt-px border-t-2 transition-colors',
                    isActive ? 'border-primary' : 'border-transparent'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      className={clsx(
                        'font-heading text-[11px] uppercase tracking-[0.06em] text-center leading-tight',
                        isActive ? 'text-primary' : 'text-ink-3'
                      )}
                    >
                      {label}
                    </span>
                    {count > 0 && (
                      <span className="absolute top-2.5 right-2 text-[10px] tabular-nums text-primary-dark">
                        {count}
                      </span>
                    )}
                  </>
                )}
              </NavLink>
            )
          })}
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex items-center justify-center -mt-px border-t-2 border-transparent font-heading text-[11px] uppercase tracking-[0.06em] text-ink-3"
          >
            Altro
          </button>
        </div>
      </nav>

      {/* ── Mobile "Altro" sheet ──────────────────────────────────
          Two ruled columns, as drawn: a contact sheet of the sections that
          did not fit the bar. */}
      {drawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div
            className="absolute inset-0 bg-chrome/60 animate-fade-in"
            onClick={() => setDrawerOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Altre sezioni"
            className="absolute bottom-0 inset-x-0 bg-surface border-t border-border shadow-sheet animate-slide-up max-h-[85dvh] flex flex-col"
          >
            <div className="flex items-baseline gap-3 px-5 py-3.5 border-b border-rule shrink-0">
              <span className="font-heading text-lg tracking-[0.06em] text-foreground">Altre sezioni</span>
              <div className="flex-1" />
              <button onClick={() => setDrawerOpen(false)} className="btn-icon -mr-2" aria-label="Chiudi">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto overscroll-contain">
              {drawerItems.length > 0 ? (
                <div className="grid grid-cols-2 gap-px bg-rule-soft">
                  {drawerItems.map(({ to, label, badge }) => {
                    const count = countFor(badge)
                    return (
                      <NavLink
                        key={to}
                        to={to}
                        className={({ isActive }) =>
                          clsx(
                            'flex items-center justify-between gap-2 px-[18px] py-4 min-h-touch',
                            isActive ? 'bg-primary/10' : 'bg-surface'
                          )
                        }
                      >
                        {({ isActive }) => (
                          <>
                            <span
                              className={clsx(
                                'font-heading text-[15px] tracking-[0.04em]',
                                isActive ? 'text-primary' : 'text-ink-2'
                              )}
                            >
                              {label}
                            </span>
                            {count > 0 && (
                              <span className="text-[11px] tabular-nums text-ink-3">{count}</span>
                            )}
                          </>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              ) : (
                <p className="note text-center py-6 px-5">
                  Tutte le sezioni sono nella barra in basso.
                </p>
              )}
            </div>

            <div className="shrink-0 border-t border-rule p-4 pb-[max(1rem,env(safe-area-inset-bottom))] flex flex-col gap-1">
              <span className="text-sm text-foreground truncate">{user?.email}</span>
              <span className="text-xs text-ink-3">
                {user?.role === 'admin' ? 'Amministratore' : 'Collaboratore'}
              </span>
              <button onClick={handleLogout} className="btn-danger-outline w-full mt-2.5">
                <LogOut className="w-4 h-4" /> Esci
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Theme switch ──────────────────────────────────────────────────
   Named options rather than a sun/moon toggle: the design labels both
   states so the current one is readable without decoding an icon. */

function ThemeSwitch({
  isDark,
  onToggle,
  compact = false,
}: {
  isDark: boolean
  onToggle: () => void
  compact?: boolean
}) {
  if (compact) {
    return (
      <button
        onClick={onToggle}
        className="font-heading text-[11px] uppercase tracking-[0.1em] text-chrome-dim border border-chrome-ink/25 px-2 py-1.5 shrink-0"
      >
        {isDark ? 'Chiaro' : 'Scuro'}
      </button>
    )
  }
  return (
    <div className="flex border border-chrome-ink/25 shrink-0" role="group" aria-label="Tema">
      {(['Chiaro', 'Scuro'] as const).map(label => {
        const on = (label === 'Scuro') === isDark
        return (
          <button
            key={label}
            onClick={() => { if (!on) onToggle() }}
            aria-pressed={on}
            className={clsx(
              'font-heading text-[11px] uppercase tracking-[0.12em] px-3 py-1.5 transition-colors',
              'border-l border-chrome-ink/25 first:border-l-0',
              on ? 'bg-chrome-ink text-chrome' : 'text-chrome-dim hover:text-on-chrome'
            )}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
