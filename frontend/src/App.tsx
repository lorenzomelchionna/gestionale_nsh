import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'

// Shared sign-in — staff and clients start from the same screen.
import LoginPage from '@/pages/LoginPage'

// Admin pages
import AdminLayout from '@/components/layout/AdminLayout'
import DashboardPage from '@/pages/admin/DashboardPage'
import CalendarPage from '@/pages/admin/CalendarPage'
import PendingPage from '@/pages/admin/PendingPage'
import AppointmentsPage from '@/pages/admin/AppointmentsPage'
import GiftCardsPage from '@/pages/admin/GiftCardsPage'
import ClientsPage from '@/pages/admin/ClientsPage'
import ClientDetailPage from '@/pages/admin/ClientDetailPage'
import CollaboratorsPage from '@/pages/admin/CollaboratorsPage'
import ServicesPage from '@/pages/admin/ServicesPage'
import ProductsPage from '@/pages/admin/ProductsPage'
import CashPage from '@/pages/admin/CashPage'
import ExpensesPage from '@/pages/admin/ExpensesPage'
import SettingsPage from '@/pages/admin/SettingsPage'
import MessagingPage from '@/pages/admin/MessagingPage'
import ChatPage from '@/pages/admin/ChatPage'
import TeamPage from '@/pages/admin/TeamPage'
import WaitlistPage from '@/pages/admin/WaitlistPage'

// Booking portal pages
import BookingLayout, { useClientAuth } from '@/components/layout/BookingLayout'
import BookingHomePage from '@/pages/booking/BookingHomePage'
import BookingFlowPage from '@/pages/booking/BookingFlowPage'
import BookingAccountPage from '@/pages/booking/BookingAccountPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

/**
 * Booking and the account page need a portal login.
 *
 * The gate sits in front of the flow rather than at the confirm button: being
 * bounced to sign in after choosing a service, a stylist and a time meant
 * losing all three. `next` brings them back to where they were.
 */
function RequireClient({ children }: { children: React.ReactNode }) {
  const token = useClientAuth(s => s.token)
  const location = useLocation()
  if (!token) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />
  }
  return <>{children}</>
}

function RequireAdmin({ children }: { children: React.ReactNode }) {
  const user = useAuthStore(s => s.user)
  if (user?.role !== 'admin') return <Navigate to="/admin/calendar" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* One sign-in for staff and clients alike */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/registrati" element={<Navigate to="/login?registrati" replace />} />

        {/* Admin */}
        <Route path="/admin" element={<RequireAuth><AdminLayout /></RequireAuth>}>
          <Route index element={<Navigate to="calendar" replace />} />
          <Route path="dashboard"            element={<RequireAdmin><DashboardPage /></RequireAdmin>} />
          <Route path="calendar"             element={<CalendarPage />} />
          <Route path="appointments/pending" element={<PendingPage />} />
          <Route path="appointments/all"     element={<AppointmentsPage />} />
          <Route path="clients"              element={<ClientsPage />} />
          <Route path="chat"                 element={<ChatPage />} />
          <Route path="clients/:id"          element={<ClientDetailPage />} />
          <Route path="collaborators"        element={<RequireAdmin><CollaboratorsPage /></RequireAdmin>} />
          <Route path="services"             element={<ServicesPage />} />
          <Route path="products"             element={<RequireAdmin><ProductsPage /></RequireAdmin>} />
          <Route path="cash"                 element={<RequireAdmin><CashPage /></RequireAdmin>} />
          <Route path="gift-cards"           element={<RequireAdmin><GiftCardsPage /></RequireAdmin>} />
          <Route path="expenses"             element={<RequireAdmin><ExpensesPage /></RequireAdmin>} />
          <Route path="settings"             element={<RequireAdmin><SettingsPage /></RequireAdmin>} />
          <Route path="team"                 element={<RequireAdmin><TeamPage /></RequireAdmin>} />
          <Route path="messaging"            element={<RequireAdmin><MessagingPage /></RequireAdmin>} />
          <Route path="waitlist"             element={<RequireAdmin><WaitlistPage /></RequireAdmin>} />
        </Route>

        {/* Booking portal. The home page and the price list stay open — a
            visitor can see what the salon offers before creating anything. */}
        <Route path="/booking" element={<BookingLayout />}>
          <Route index element={<BookingHomePage />} />
          <Route path="new" element={<RequireClient><BookingFlowPage /></RequireClient>} />
          <Route path="account" element={<RequireClient><BookingAccountPage /></RequireClient>} />
          {/* The portal used to have its own sign-in pages. */}
          <Route path="login" element={<Navigate to="/login" replace />} />
          <Route path="register" element={<Navigate to="/login?registrati" replace />} />
        </Route>

        {/* The salon's front door is the client portal: most visitors are
            customers, and staff reach the management area by signing in. */}
        <Route path="/" element={<Navigate to="/booking" replace />} />
        <Route path="*" element={<Navigate to="/booking" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
