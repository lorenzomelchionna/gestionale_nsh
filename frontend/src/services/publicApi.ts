import axios from 'axios'
import type { Service, Collaborator, Appointment, TokenResponse, WaitlistEntry, WaitlistCreate } from '@/types'

const API_BASE = import.meta.env.VITE_API_URL || ''

const publicApi = axios.create({
  baseURL: `${API_BASE}/api/public`,
  headers: { 'Content-Type': 'application/json' },
})

// Inject client token
publicApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('client_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export const publicGetServices = () =>
  publicApi.get<Service[]>('/services').then(r => r.data)

export const publicGetCollaborators = () =>
  publicApi.get<Collaborator[]>('/collaborators').then(r => r.data)

export const publicGetAvailability = (params: {
  service_id: number; collaborator_id: number; target_date: string
}) =>
  publicApi.get<string[]>('/availability', { params }).then(r => r.data)

export const clientRegister = (data: {
  first_name: string; last_name: string; phone: string; email: string; password: string
}) =>
  publicApi.post<TokenResponse>('/auth/register', data).then(r => r.data)

export const clientLogin = (email: string, password: string) =>
  publicApi.post<TokenResponse>('/auth/login', { email, password }).then(r => r.data)

export const clientForgotPassword = (email: string) =>
  publicApi.post('/auth/forgot-password', { email }).then(r => r.data)

export const getMyAppointments = () =>
  publicApi.get<Appointment[]>('/appointments').then(r => r.data)

export const bookAppointment = (data: {
  client_id: number; collaborator_id: number;
  start_time: string; end_time: string; service_ids: number[]
}) =>
  publicApi.post<Appointment>('/appointments', data).then(r => r.data)

export const cancelMyAppointment = (id: number) =>
  publicApi.post(`/appointments/${id}/cancel`).then(r => r.data)

export const acceptAlternative = (id: number) =>
  publicApi.post(`/appointments/${id}/accept-alternative`).then(r => r.data)

export const rejectAlternative = (id: number) =>
  publicApi.post(`/appointments/${id}/reject-alternative`).then(r => r.data)

export const getMyWaitlist = () =>
  publicApi.get<WaitlistEntry[]>('/waitlist').then(r => r.data)

export const joinWaitlist = (data: WaitlistCreate) =>
  publicApi.post<WaitlistEntry>('/waitlist', data).then(r => r.data)

export const leaveWaitlist = (id: number) =>
  publicApi.delete(`/waitlist/${id}`).then(r => r.data)
