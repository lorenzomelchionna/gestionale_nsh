import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'

// Admin pages
import LoginPage from '@/pages/admin/LoginPage'
import AdminLayout from '@/components/layout/AdminLayout'
import DashboardPage from '@/pages/admin/DashboardPage'
import CalendarPage from '@/pages/admin/CalendarPage'
import PendingPage from '@/pages/admin/PendingPage'
import ClientsPage from '@/pages/admin/ClientsPage'
import ClientDetailPage from '@/pages/admin/ClientDetailPage'
import CollaboratorsPage from '@/pages/admin/CollaboratorsPage'
import ServicesPage from '@/pages/admin/ServicesPage'
import ProductsPage from '@/pages/admin/ProductsPage'
import CashPage from '@/pages/admin/CashPage'
import ExpensesPage from '@/pages/admin/ExpensesPage'
import SettingsPage from '@/pages/admin/SettingsPage'
import MessagingPage from '@/pages/admin/MessagingPage'

// Booking portal pages
import BookingLayout from '@/components/layout/BookingLayout'
import BookingHomePage from '@/pages/booking/BookingHomePage'
import BookingLoginPage from '@/pages/booking/BookingLoginPage'
import BookingRegisterPage from '@/pages/booking/BookingRegisterPage'
import BookingFlowPage from '@/pages/booking/BookingFlowPage'
import BookingAccountPage from '@/pages/booking/BookingAccountPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(s => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Admin */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/admin" element={<RequireAuth><AdminLayout /></RequireAuth>}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="appointments/pending" element={<PendingPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/:id" element={<ClientDetailPage />} />
          <Route path="collaborators" element={<CollaboratorsPage />} />
          <Route path="services" element={<ServicesPage />} />
          <Route path="products" element={<ProductsPage />} />
          <Route path="cash" element={<CashPage />} />
          <Route path="expenses" element={<ExpensesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="messaging" element={<MessagingPage />} />
        </Route>

        {/* Booking portal */}
        <Route path="/booking" element={<BookingLayout />}>
          <Route index element={<BookingHomePage />} />
          <Route path="login" element={<BookingLoginPage />} />
          <Route path="register" element={<BookingRegisterPage />} />
          <Route path="new" element={<BookingFlowPage />} />
          <Route path="account" element={<BookingAccountPage />} />
        </Route>

        {/* Root redirect */}
        <Route path="/" element={<Navigate to="/admin" replace />} />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
