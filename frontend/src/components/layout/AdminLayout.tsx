import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Calendar, Users, Scissors, Package,
  DollarSign, TrendingDown, Settings, LogOut, Bell, Menu, X,
  UserCircle, Clock, MessageSquare, Moon, Sun
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getPendingAppointments } from '@/services/api'
import clsx from 'clsx'

const navItems = [
  { to: '/admin/dashboard',              icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/admin/calendar',               icon: Calendar,        label: 'Calendario' },
  { to: '/admin/appointments/pending',   icon: Clock,           label: 'In attesa',  badge: true },
  { to: '/admin/clients',                icon: Users,           label: 'Clienti' },
  { to: '/admin/collaborators',          icon: UserCircle,      label: 'Collaboratori' },
  { to: '/admin/services',               icon: Scissors,        label: 'Servizi' },
  { to: '/admin/products',               icon: Package,         label: 'Prodotti' },
  { to: '/admin/cash',                   icon: DollarSign,      label: 'Cassa' },
  { to: '/admin/expenses',               icon: TrendingDown,    label: 'Spese' },
  { to: '/admin/messaging',              icon: MessageSquare,   label: 'Messaggi' },
  { to: '/admin/settings',               icon: Settings,        label: 'Impostazioni' },
]

export default function AdminLayout() {
  const { user, logout } = useAuthStore()
  const { sidebarOpen, setSidebarOpen, isDark, toggleDark } = useUIStore()
  const navigate = useNavigate()

  const { data: pending } = useQuery({
    queryKey: ['pending-appointments'],
    queryFn: getPendingAppointments,
    refetchInterval: 30_000,
  })
  const pendingCount = pending?.length ?? 0

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Sidebar */}
      <aside
        className={clsx(
          'flex flex-col bg-surface border-r border-border transition-all duration-300 z-20',
          sidebarOpen ? 'w-60' : 'w-16'
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-4 py-5 border-b border-border">
          <div className="w-8 h-8 bg-primary rounded-md flex items-center justify-center flex-shrink-0">
            <Scissors className="w-4 h-4 text-white" />
          </div>
          {sidebarOpen && (
            <span className="font-semibold text-foreground text-sm leading-tight">
              New Style Hair
            </span>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
          {navItems.map(({ to, icon: Icon, label, badge }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors relative',
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                )
              }
            >
              <Icon className="w-4 h-4 flex-shrink-0" />
              {sidebarOpen && <span>{label}</span>}
              {badge && pendingCount > 0 && (
                <span className={clsx(
                  'bg-amber-500 text-white text-xs rounded-full font-bold leading-none flex items-center justify-center',
                  sidebarOpen ? 'ml-auto w-5 h-5' : 'absolute top-1 right-1 w-4 h-4 text-[10px]'
                )}>
                  {pendingCount > 9 ? '9+' : pendingCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="border-t border-border p-3">
          <div className={clsx('flex items-center gap-2', sidebarOpen ? '' : 'justify-center')}>
            <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center flex-shrink-0">
              <span className="text-primary text-xs font-bold">
                {user?.email?.[0]?.toUpperCase()}
              </span>
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-foreground truncate">{user?.email}</p>
                <p className="text-xs text-muted-foreground capitalize">{user?.role}</p>
              </div>
            )}
          </div>
          <button
            onClick={handleLogout}
            className={clsx(
              'mt-2 flex items-center gap-2 text-xs text-muted-foreground hover:text-red-500 transition-colors w-full px-2 py-1 rounded',
              sidebarOpen ? '' : 'justify-center'
            )}
          >
            <LogOut className="w-3.5 h-3.5" />
            {sidebarOpen && 'Esci'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Topbar */}
        <header className="bg-surface border-b border-border px-4 py-3 flex items-center gap-4 flex-shrink-0">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <div className="flex-1" />
          <button
            onClick={toggleDark}
            className="text-muted-foreground hover:text-foreground transition-colors p-1"
            title={isDark ? 'Passa a tema chiaro' : 'Passa a tema scuro'}
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
          {pendingCount > 0 && (
            <NavLink
              to="/admin/appointments/pending"
              className="relative flex items-center gap-1.5 text-sm text-amber-600 font-medium hover:text-amber-700"
            >
              <Bell className="w-4 h-4" />
              <span>{pendingCount} richieste in attesa</span>
            </NavLink>
          )}
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
