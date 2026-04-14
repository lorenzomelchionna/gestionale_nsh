// ── Auth ──────────────────────────────────────────────────────────

export type UserRole = 'admin' | 'collaborator'

export interface User {
  id: number
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// ── Collaborator ──────────────────────────────────────────────────

export interface CollaboratorSchedule {
  id: number
  collaborator_id: number
  day_of_week: number
  start_time: string | null
  end_time: string | null
  is_working: boolean
}

export interface Collaborator {
  id: number
  first_name: string
  last_name: string
  phone: string | null
  email: string | null
  photo_url: string | null
  is_active: boolean
  visible_online: boolean
  color: string
  created_at: string
  schedules: CollaboratorSchedule[]
  service_ids: number[]
}

// ── Client ────────────────────────────────────────────────────────

export interface Client {
  id: number
  first_name: string
  last_name: string
  phone: string | null
  email: string | null
  birth_date: string | null
  notes: string | null
  is_active: boolean
  account_id: number | null
  created_at: string
}

// ── Service ───────────────────────────────────────────────────────

export interface Service {
  id: number
  name: string
  description: string | null
  price: number
  duration_slots: number
  category: string
  bookable_online: boolean
  is_active: boolean
  created_at: string
}

// ── Appointment ───────────────────────────────────────────────────

export type AppointmentStatus =
  | 'pending'
  | 'confirmed'
  | 'rejected'
  | 'rescheduled'
  | 'completed'
  | 'cancelled'

export type AppointmentOrigin = 'salon' | 'online'

export interface AppointmentServiceItem {
  id: number
  service_id: number
  price_snapshot: number
}

export interface Appointment {
  id: number
  client_id: number
  collaborator_id: number
  start_time: string
  end_time: string
  status: AppointmentStatus
  origin: AppointmentOrigin
  notes: string | null
  visit_notes: string | null
  rejection_reason: string | null
  alternative_time: string | null
  reminder_sent: boolean
  created_at: string
  appointment_services: AppointmentServiceItem[]
  // enriched fields
  client_name?: string
  collaborator_name?: string
  total_price?: number
  service_names?: string[]
}

// ── Product ───────────────────────────────────────────────────────

export interface Product {
  id: number
  name: string
  description: string | null
  purchase_price: number
  sale_price: number
  category: string
  quantity: number
  min_quantity: number
  photo_url: string | null
  is_active: boolean
  created_at: string
}

export type MovementType = 'carico' | 'scarico' | 'vendita'

export interface ProductMovement {
  id: number
  product_id: number
  type: MovementType
  quantity: number
  notes: string | null
  appointment_id: number | null
  created_at: string
}

// ── Payment ───────────────────────────────────────────────────────

export type PaymentMethod = 'contanti' | 'carta' | 'misto'
export type PaymentType = 'servizio' | 'prodotto'

export interface Payment {
  id: number
  client_id: number | null
  appointment_id: number | null
  amount: number
  method: PaymentMethod
  type: PaymentType
  date: string
  notes: string | null
}

// ── Expense ───────────────────────────────────────────────────────

export interface Expense {
  id: number
  description: string
  amount: number
  category: string
  date: string
  notes: string | null
  created_at: string
}

// ── Absence ───────────────────────────────────────────────────────

export type AbsenceType = 'ferie' | 'permesso' | 'malattia' | 'altro'

export interface Absence {
  id: number
  collaborator_id: number
  start_date: string
  end_date: string
  type: AbsenceType
  notes: string | null
  created_at: string
}

// ── ExtraWorkDay ──────────────────────────────────────────────────

export interface ExtraWorkDay {
  id: number
  collaborator_id: number
  date: string
  start_time: string
  end_time: string
  notes: string | null
  created_at: string
}

// ── BookingConfig ─────────────────────────────────────────────────

export interface BookingConfig {
  id: number
  is_enabled: boolean
  min_advance_hours: number
  max_advance_days: number
  min_cancel_hours: number
  slot_duration_minutes: number
  updated_at: string
}

// ── Pagination ────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

// ── Dashboard ─────────────────────────────────────────────────────

export interface DashboardStats {
  period: string
  total_revenue: number
  cash_revenue: number
  card_revenue: number
  service_revenue: number
  product_revenue: number
  total_expenses: number
  net_margin: number
  appointment_count: number
  pending_appointments: number
}


// ── Messaging ─────────────────────────────────────────────────────

export type FilterType = 'all' | 'product_buyers' | 'inactive' | 'birthday_month'

export interface MessageFilter {
  type: FilterType
  product_id?: number
  inactive_days?: number
  birthday_month?: number
}

export interface SendMessageRequest {
  subject: string
  body: string
  filter: MessageFilter
}

export interface MessageRecipient {
  id: number
  first_name: string
  last_name: string
  email: string | null
  phone: string | null
}

export interface PreviewResponse {
  count: number
  recipients: MessageRecipient[]
}

export interface SendResponse {
  sent: number
  skipped: number
  errors: number
}
