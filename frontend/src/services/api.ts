import axios from 'axios'
import type {
  TokenResponse, User, Collaborator, CollaboratorSchedule,
  Client, Service, Appointment, Product, ProductMovement,
  Payment, Expense, Absence, ExtraWorkDay, BookingConfig, DashboardStats,
  PaginatedResponse,
} from '@/types'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// ── Token management ──────────────────────────────────────────────

let accessToken: string | null = localStorage.getItem('access_token')
let refreshToken: string | null = localStorage.getItem('refresh_token')

export const setTokens = (tokens: TokenResponse) => {
  accessToken = tokens.access_token
  refreshToken = tokens.refresh_token
  localStorage.setItem('access_token', tokens.access_token)
  localStorage.setItem('refresh_token', tokens.refresh_token)
}

export const clearTokens = () => {
  accessToken = null
  refreshToken = null
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
}

// Inject auth header
api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

// Auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry && refreshToken) {
      original._retry = true
      try {
        const { data } = await axios.post<TokenResponse>('/api/admin/auth/refresh', {
          refresh_token: refreshToken,
        })
        setTokens(data)
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        clearTokens()
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ── Admin Auth ────────────────────────────────────────────────────

export const adminLogin = (email: string, password: string) =>
  api.post<TokenResponse>('/admin/auth/login', { email, password }).then(r => r.data)

export const getMe = () =>
  api.get<User>('/admin/auth/me').then(r => r.data)

// ── Collaborators ─────────────────────────────────────────────────

export const getCollaborators = (params?: { page?: number; active_only?: boolean }) =>
  api.get<PaginatedResponse<Collaborator>>('/admin/collaborators', { params }).then(r => r.data)

export const getCollaborator = (id: number) =>
  api.get<Collaborator>(`/admin/collaborators/${id}`).then(r => r.data)

export const createCollaborator = (data: Partial<Collaborator>) =>
  api.post<Collaborator>('/admin/collaborators', data).then(r => r.data)

export const updateCollaborator = (id: number, data: Partial<Collaborator>) =>
  api.put<Collaborator>(`/admin/collaborators/${id}`, data).then(r => r.data)

export const deleteCollaborator = (id: number) =>
  api.delete(`/admin/collaborators/${id}`)

export const updateCollaboratorSchedule = (id: number, schedules: Partial<CollaboratorSchedule>[]) =>
  api.put<CollaboratorSchedule[]>(`/admin/collaborators/${id}/schedule`, schedules).then(r => r.data)

export const updateCollaboratorServices = (id: number, service_ids: number[]) =>
  api.put<Collaborator>(`/admin/collaborators/${id}/services`, service_ids).then(r => r.data)

// ── Clients ───────────────────────────────────────────────────────

export const getClients = (params?: { page?: number; search?: string }) =>
  api.get<PaginatedResponse<Client>>('/admin/clients', { params }).then(r => r.data)

export const getClient = (id: number) =>
  api.get<Client>(`/admin/clients/${id}`).then(r => r.data)

export const createClient = (data: Partial<Client>) =>
  api.post<Client>('/admin/clients', data).then(r => r.data)

export const updateClient = (id: number, data: Partial<Client>) =>
  api.put<Client>(`/admin/clients/${id}`, data).then(r => r.data)

export const getClientAppointments = (id: number) =>
  api.get<Appointment[]>(`/admin/clients/${id}/appointments`).then(r => r.data)

// ── Services ──────────────────────────────────────────────────────

export const getServices = (params?: { page?: number; active_only?: boolean }) =>
  api.get<PaginatedResponse<Service>>('/admin/services', { params }).then(r => r.data)

export const createService = (data: Partial<Service>) =>
  api.post<Service>('/admin/services', data).then(r => r.data)

export const updateService = (id: number, data: Partial<Service>) =>
  api.put<Service>(`/admin/services/${id}`, data).then(r => r.data)

export const deleteService = (id: number) =>
  api.delete(`/admin/services/${id}`)

// ── Appointments ──────────────────────────────────────────────────

export const getAppointments = (params?: {
  date_from?: string; date_to?: string;
  collaborator_id?: number; status?: string;
  page?: number; page_size?: number
}) =>
  api.get<PaginatedResponse<Appointment>>('/admin/appointments', { params }).then(r => r.data)

export const getPendingAppointments = () =>
  api.get<Appointment[]>('/admin/appointments/pending').then(r => r.data)

export const createAppointment = (data: {
  client_id: number; collaborator_id: number;
  start_time: string; end_time: string;
  service_ids: number[]; notes?: string
}) =>
  api.post<Appointment>('/admin/appointments', data).then(r => r.data)

export const updateAppointment = (id: number, data: Partial<Appointment> & { service_ids?: number[] }) =>
  api.put<Appointment>(`/admin/appointments/${id}`, data).then(r => r.data)

export const confirmAppointment = (id: number) =>
  api.post<Appointment>(`/admin/appointments/${id}/confirm`).then(r => r.data)

export const rejectAppointment = (id: number, reason?: string) =>
  api.post<Appointment>(`/admin/appointments/${id}/reject`, { reason }).then(r => r.data)

export const rescheduleAppointment = (id: number, alternative_time: string) =>
  api.post<Appointment>(`/admin/appointments/${id}/reschedule`, { alternative_time }).then(r => r.data)

export const completeAppointment = (id: number) =>
  api.post<Appointment>(`/admin/appointments/${id}/complete`).then(r => r.data)

export const deleteAppointment = (id: number) =>
  api.delete(`/admin/appointments/${id}`)

// ── Availability ──────────────────────────────────────────────────

export const getAvailability = (params: {
  collaborator_id: number; target_date: string; duration_slots: number
}) =>
  api.get<string[]>('/admin/availability', { params }).then(r => r.data)

// ── Products ──────────────────────────────────────────────────────

export const getProducts = (params?: { low_stock?: boolean; active_only?: boolean }) =>
  api.get<PaginatedResponse<Product>>('/admin/products', { params }).then(r => r.data)

export const createProduct = (data: Partial<Product>) =>
  api.post<Product>('/admin/products', data).then(r => r.data)

export const updateProduct = (id: number, data: Partial<Product>) =>
  api.put<Product>(`/admin/products/${id}`, data).then(r => r.data)

export const addProductMovement = (data: {
  product_id: number; type: string; quantity: number; notes?: string
}) =>
  api.post<ProductMovement>('/admin/products/movements', data).then(r => r.data)

// ── Payments ──────────────────────────────────────────────────────

export const getPayments = (params?: { date_from?: string; date_to?: string }) =>
  api.get<PaginatedResponse<Payment>>('/admin/payments', { params }).then(r => r.data)

export const createPayment = (data: {
  appointment_id?: number; client_id?: number;
  amount: number; method: string; type: string; notes?: string
}) =>
  api.post<Payment>('/admin/payments', data).then(r => r.data)

// ── Expenses ──────────────────────────────────────────────────────

export const getExpenses = (params?: { date_from?: string; date_to?: string; category?: string }) =>
  api.get<PaginatedResponse<Expense>>('/admin/expenses', { params }).then(r => r.data)

export const createExpense = (data: Partial<Expense>) =>
  api.post<Expense>('/admin/expenses', data).then(r => r.data)

export const updateExpense = (id: number, data: Partial<Expense>) =>
  api.put<Expense>(`/admin/expenses/${id}`, data).then(r => r.data)

export const deleteExpense = (id: number) =>
  api.delete(`/admin/expenses/${id}`)

// ── Absences ──────────────────────────────────────────────────────

export const getAbsences = (collaborator_id: number) =>
  api.get<Absence[]>(`/admin/absences/${collaborator_id}`).then(r => r.data)

export const createAbsence = (data: Partial<Absence>) =>
  api.post<Absence>('/admin/absences', data).then(r => r.data)

export const deleteAbsence = (id: number) =>
  api.delete(`/admin/absences/${id}`)

// ── Extra Work Days ───────────────────────────────────────────────

export const getExtraWorkDays = (collaborator_id: number) =>
  api.get<ExtraWorkDay[]>(`/admin/extra-days/${collaborator_id}`).then(r => r.data)

export const createExtraWorkDay = (data: {
  collaborator_id: number; date: string; start_time: string; end_time: string; notes?: string
}) =>
  api.post<ExtraWorkDay>('/admin/extra-days', data).then(r => r.data)

export const deleteExtraWorkDay = (id: number) =>
  api.delete(`/admin/extra-days/${id}`)

// ── Settings ──────────────────────────────────────────────────────

export const getBookingConfig = () =>
  api.get<BookingConfig>('/admin/settings/booking').then(r => r.data)

export const updateBookingConfig = (data: Partial<BookingConfig>) =>
  api.put<BookingConfig>('/admin/settings/booking', data).then(r => r.data)

// ── Dashboard ─────────────────────────────────────────────────────

export const getDashboardStats = (period: 'today' | 'week' | 'month' | 'year') =>
  api.get<DashboardStats>('/admin/dashboard/stats', { params: { period } }).then(r => r.data)

export const getRevenueChart = (days: number) =>
  api.get<{ date: string; total: number }[]>('/admin/dashboard/revenue-chart', { params: { days } }).then(r => r.data)

export interface YearlyChartEntry {
  month: string
  month_num: number
  revenue: number
  expenses: number
  net_margin: number
  appointments: number
}

export const getYearlyChart = (year?: number) =>
  api.get<YearlyChartEntry[]>('/admin/dashboard/yearly-chart', { params: year ? { year } : {} }).then(r => r.data)

// ── Messaging ─────────────────────────────────────────────────────

import type { SendMessageRequest, PreviewResponse, SendResponse } from '@/types'

export const previewMessage = (data: SendMessageRequest) =>
  api.post<PreviewResponse>('/admin/messaging/preview', data).then(r => r.data)

export const sendMessage = (data: SendMessageRequest) =>
  api.post<SendResponse>('/admin/messaging/send', data).then(r => r.data)

export default api
