import React, { useState, useMemo, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  format, addDays, startOfWeek, isSameDay, parseISO, addMinutes, differenceInMinutes
} from 'date-fns'
import { it } from 'date-fns/locale'
import {
  ChevronLeft, ChevronRight, Plus, Check, X
} from 'lucide-react'
import {
  getAppointments, getCollaborators, confirmAppointment,
  rejectAppointment, completeAppointment,
  createAppointment, getClients, getServices, updateAppointment
} from '@/services/api'
import type { Appointment, Collaborator } from '@/types'
import clsx from 'clsx'

interface DragState {
  id: number
  durationMin: number
  collaboratorId: number
}

const SLOT_HEIGHT = 48  // px per 30-min slot
const HOUR_HEIGHT = SLOT_HEIGHT * 2
const START_HOUR = 8
const END_HOUR = 20

const TERMINAL_STATUSES = ['completed', 'cancelled', 'rejected']

function apptCardStyle(color: string, status: string): React.CSSProperties {
  return {
    backgroundColor: color + '22',
    borderLeftColor: color,
    color: color,
    opacity: TERMINAL_STATUSES.includes(status) ? 0.5 : 1,
  }
}

type ViewMode = 'day' | 'week'

export default function CalendarPage() {
  const qc = useQueryClient()
  const [viewMode, setViewMode] = useState<ViewMode>('day')
  const [currentDate, setCurrentDate] = useState(new Date())
  const [selectedCollaboratorId, setSelectedCollaboratorId] = useState<number | null>(null)
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newApptSlot, setNewApptSlot] = useState<{ date: Date; collaboratorId: number } | null>(null)
  const [pendingMove, setPendingMove] = useState<{
    id: number; start: Date; end: Date; collaboratorId: number; originalCollaboratorId: number
  } | null>(null)
  const dragState = useRef<DragState | null>(null)
  const didDrag = useRef(false)

  // Date range for query
  const dateFrom = viewMode === 'day'
    ? format(currentDate, 'yyyy-MM-dd') + 'T00:00:00'
    : format(startOfWeek(currentDate, { weekStartsOn: 1 }), 'yyyy-MM-dd') + 'T00:00:00'
  const dateTo = viewMode === 'day'
    ? format(currentDate, 'yyyy-MM-dd') + 'T23:59:59'
    : format(addDays(startOfWeek(currentDate, { weekStartsOn: 1 }), 6), 'yyyy-MM-dd') + 'T23:59:59'

  const { data: apptsData } = useQuery({
    queryKey: ['appointments', dateFrom, dateTo, selectedCollaboratorId],
    queryFn: () => getAppointments({
      date_from: dateFrom,
      date_to: dateTo,
      collaborator_id: selectedCollaboratorId ?? undefined,
      page_size: 200,
    }),
  })

  const { data: collabsData } = useQuery({
    queryKey: ['collaborators-active'],
    queryFn: () => getCollaborators({ active_only: true }),
  })

  const appointments = apptsData?.items ?? []
  const collaborators = collabsData?.items ?? []
  const visibleCollabs = selectedCollaboratorId
    ? collaborators.filter(c => c.id === selectedCollaboratorId)
    : collaborators

  // Mutations
  const invalidate = () => qc.invalidateQueries({ queryKey: ['appointments'] })

  const moveMut = useMutation({
    mutationFn: ({ id, start_time, end_time, collaborator_id }: {
      id: number; start_time: string; end_time: string; collaborator_id: number
    }) => updateAppointment(id, { start_time, end_time, collaborator_id }),
    onSuccess: invalidate,
  })

  const handleDrop = useCallback((dropDate: Date, collaboratorId: number, relativeY: number) => {
    const ds = dragState.current
    if (!ds) return
    const snappedMin = Math.floor(relativeY / SLOT_HEIGHT) * 30
    const clampedMin = Math.max(0, Math.min(snappedMin, (END_HOUR - START_HOUR) * 60 - ds.durationMin))
    const start = new Date(dropDate)
    start.setHours(START_HOUR + Math.floor(clampedMin / 60), clampedMin % 60, 0, 0)
    const end = addMinutes(start, ds.durationMin)
    setPendingMove({ id: ds.id, start, end, collaboratorId, originalCollaboratorId: ds.collaboratorId })
    dragState.current = null
  }, [])

  // Drop on top of another appointment → start exactly at its end (no snap)
  const handleDropOnAppointment = useCallback((targetAppt: Appointment) => {
    const ds = dragState.current
    if (!ds || ds.id === targetAppt.id) return
    const start = parseISO(targetAppt.end_time)
    const end = addMinutes(start, ds.durationMin)
    setPendingMove({
      id: ds.id,
      start,
      end,
      collaboratorId: targetAppt.collaborator_id,
      originalCollaboratorId: ds.collaboratorId,
    })
    dragState.current = null
  }, [])

  const confirmMut = useMutation({ mutationFn: confirmAppointment, onSuccess: invalidate })
  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => rejectAppointment(id, reason),
    onSuccess: () => { invalidate(); setSelectedAppointment(null) },
  })
  const completeMut = useMutation({
    mutationFn: completeAppointment,
    onSuccess: () => { invalidate(); setSelectedAppointment(null) },
  })

  // Navigation
  const navigate = (dir: 1 | -1) => {
    setCurrentDate(d => viewMode === 'day' ? addDays(d, dir) : addDays(d, dir * 7))
  }

  // Time → Y position
  const timeToY = (dt: Date) => {
    const totalMin = dt.getHours() * 60 + dt.getMinutes() - START_HOUR * 60
    return (totalMin / 30) * SLOT_HEIGHT
  }

  // Duration → height
  const durationToH = (start: Date, end: Date) => {
    const mins = differenceInMinutes(end, start)
    return (mins / 30) * SLOT_HEIGHT
  }

  const days = viewMode === 'day'
    ? [currentDate]
    : Array.from({ length: 6 }, (_, i) => addDays(startOfWeek(currentDate, { weekStartsOn: 1 }), i))

  // Click on empty slot
  const handleSlotClick = (date: Date, collaboratorId: number) => {
    setNewApptSlot({ date, collaboratorId })
    setShowCreateModal(true)
  }

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(-1)} className="p-1.5 hover:bg-muted rounded-md">
            <ChevronLeft className="w-5 h-5" />
          </button>
          <h2 className="text-base font-semibold min-w-[180px] text-center">
            {viewMode === 'day'
              ? format(currentDate, 'EEEE d MMMM yyyy', { locale: it })
              : `${format(days[0], 'd MMM', { locale: it })} – ${format(days[days.length - 1], 'd MMM yyyy', { locale: it })}`
            }
          </h2>
          <button onClick={() => navigate(1)} className="p-1.5 hover:bg-muted rounded-md">
            <ChevronRight className="w-5 h-5" />
          </button>
          <button onClick={() => setCurrentDate(new Date())} className="text-xs px-2 py-1 bg-muted rounded-md ml-1">
            Oggi
          </button>
        </div>

        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="flex bg-muted rounded-md p-0.5">
            {(['day', 'week'] as ViewMode[]).map(v => (
              <button
                key={v}
                onClick={() => setViewMode(v)}
                className={clsx(
                  'px-3 py-1 text-sm rounded transition-colors',
                  viewMode === v ? 'bg-surface shadow-sm font-medium' : 'text-muted-foreground'
                )}
              >
                {v === 'day' ? 'Giorno' : 'Settimana'}
              </button>
            ))}
          </div>

          {/* Collaborator filter */}
          <select
            className="input text-sm py-1.5 w-44"
            value={selectedCollaboratorId ?? ''}
            onChange={e => setSelectedCollaboratorId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Tutti i collaboratori</option>
            {collaborators.map(c => (
              <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
            ))}
          </select>

          <button onClick={() => setShowCreateModal(true)} className="btn-primary flex items-center gap-1.5 py-1.5 text-sm">
            <Plus className="w-4 h-4" />
            Nuovo
          </button>
        </div>
      </div>

      {/* Calendar grid */}
      <div className="card flex-1 overflow-auto">
        <div className="flex">
          {/* Time gutter */}
          <div className="w-12 flex-shrink-0">
            <div className="h-10 border-b border-border" /> {/* header spacer */}
            <div className="relative" style={{ height: (END_HOUR - START_HOUR) * HOUR_HEIGHT }}>
              {Array.from({ length: END_HOUR - START_HOUR }, (_, i) => (
                <div
                  key={i}
                  className="absolute right-2 text-[10px] text-muted-foreground -translate-y-2"
                  style={{ top: i * HOUR_HEIGHT }}
                >
                  {String(START_HOUR + i).padStart(2, '0')}:00
                </div>
              ))}
            </div>
          </div>

          {/* Day columns */}
          {viewMode === 'day' ? (
            // Day view: one column per collaborator
            <div className="flex flex-1 min-w-0">
              {visibleCollabs.map(collab => (
                <DayColumn
                  key={collab.id}
                  collaborator={collab}
                  date={currentDate}
                  appointments={appointments.filter(a => a.collaborator_id === collab.id)}
                  timeToY={timeToY}
                  durationToH={durationToH}
                  onSlotClick={(d) => handleSlotClick(d, collab.id)}
                  onAppointmentClick={(a) => { if (!didDrag.current) setSelectedAppointment(a); didDrag.current = false }}
                  dragState={dragState}
                  didDrag={didDrag}
                  onDrop={(relY) => handleDrop(currentDate, collab.id, relY)}
                  onDropOnAppointment={handleDropOnAppointment}
                />
              ))}
            </div>
          ) : (
            // Week view: one column per day
            <div className="flex flex-1 min-w-0">
              {days.map(day => (
                <WeekDayColumn
                  key={day.toISOString()}
                  date={day}
                  collaborators={visibleCollabs}
                  appointments={appointments.filter(a => isSameDay(parseISO(a.start_time), day))}
                  timeToY={timeToY}
                  durationToH={durationToH}
                  onSlotClick={(d) => handleSlotClick(d, visibleCollabs[0]?.id ?? 0)}
                  onAppointmentClick={(a) => { if (!didDrag.current) setSelectedAppointment(a); didDrag.current = false }}
                  dragState={dragState}
                  didDrag={didDrag}
                  onDrop={(relY, collaboratorId) => handleDrop(day, collaboratorId, relY)}
                  onDropOnAppointment={handleDropOnAppointment}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Appointment detail modal */}
      {selectedAppointment && (
        <AppointmentModal
          appointment={selectedAppointment}
          appointments={appointments}
          onClose={() => setSelectedAppointment(null)}
          onConfirm={() => confirmMut.mutate(selectedAppointment.id)}
          onReject={(reason) => rejectMut.mutate({ id: selectedAppointment.id, reason })}
          onComplete={() => completeMut.mutate(selectedAppointment.id)}
          onInvalidate={invalidate}
        />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateAppointmentModal
          initialSlot={newApptSlot}
          collaborators={collaborators}
          onClose={() => { setShowCreateModal(false); setNewApptSlot(null) }}
          onCreated={() => { invalidate(); setShowCreateModal(false); setNewApptSlot(null) }}
        />
      )}

      {/* Move confirmation modal */}
      {pendingMove && (() => {
        const fromCollab = collaborators.find(c => c.id === pendingMove.originalCollaboratorId)
        const toCollab = collaborators.find(c => c.id === pendingMove.collaboratorId)
        const collabChanged = pendingMove.collaboratorId !== pendingMove.originalCollaboratorId
        return (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-surface rounded-xl shadow-xl w-full max-w-sm p-5 space-y-4">
            <h3 className="font-semibold text-foreground">Sposta appuntamento</h3>
            <div className="text-sm text-muted-foreground space-y-1">
              <p>
                Nuovo orario:{' '}
                <span className="font-medium text-foreground">
                  {format(pendingMove.start, 'dd/MM/yyyy HH:mm')} → {format(pendingMove.end, 'HH:mm')}
                </span>
              </p>
              {collabChanged && (
                <p>
                  Collaboratore:{' '}
                  <span className="font-medium text-foreground">
                    {fromCollab?.first_name ?? '–'} → {toCollab?.first_name ?? '–'}
                  </span>
                </p>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <button
                className="btn-secondary text-sm py-1.5"
                onClick={() => setPendingMove(null)}
              >
                Annulla
              </button>
              <button
                className="btn-primary text-sm py-1.5"
                disabled={moveMut.isPending}
                onClick={() => {
                  moveMut.mutate({
                    id: pendingMove.id,
                    start_time: pendingMove.start.toISOString(),
                    end_time: pendingMove.end.toISOString(),
                    collaborator_id: pendingMove.collaboratorId,
                  }, { onSuccess: () => setPendingMove(null) })
                }}
              >
                {moveMut.isPending ? 'Salvataggio...' : 'Conferma'}
              </button>
            </div>
          </div>
        </div>
        )
      })()}
    </div>
  )
}

// ── Day column ────────────────────────────────────────────────────

function DayColumn({ collaborator, date, appointments, timeToY, durationToH, onSlotClick, onAppointmentClick, dragState, didDrag, onDrop, onDropOnAppointment }: {
  collaborator: Collaborator
  date: Date
  appointments: Appointment[]
  timeToY: (d: Date) => number
  durationToH: (s: Date, e: Date) => number
  onSlotClick: (d: Date) => void
  onAppointmentClick: (a: Appointment) => void
  dragState: React.MutableRefObject<DragState | null>
  didDrag: React.MutableRefObject<boolean>
  onDrop: (relativeY: number) => void
  onDropOnAppointment: (target: Appointment) => void
}) {
  return (
    <div className="flex-1 min-w-[120px] border-l border-border">
      {/* Header */}
      <div
        className="h-10 border-b border-border px-2 flex items-center justify-center text-xs font-medium"
        style={{ backgroundColor: collaborator.color + '20', color: collaborator.color }}
      >
        {collaborator.first_name}
      </div>
      {/* Grid */}
      <div
        className="relative"
        style={{ height: (END_HOUR - START_HOUR) * HOUR_HEIGHT }}
        onClick={(e) => {
          if (didDrag.current) { didDrag.current = false; return }
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
          const y = e.clientY - rect.top
          const totalMin = (y / SLOT_HEIGHT) * 30
          const slotMin = Math.floor(totalMin / 30) * 30
          const slotDate = new Date(date)
          slotDate.setHours(START_HOUR + Math.floor(slotMin / 60), slotMin % 60, 0, 0)
          onSlotClick(slotDate)
        }}
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
        onDrop={(e) => {
          e.preventDefault()
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
          onDrop(e.clientY - rect.top)
          didDrag.current = true
        }}
      >
        {/* Hour lines */}
        {Array.from({ length: (END_HOUR - START_HOUR) * 2 }, (_, i) => (
          <div
            key={i}
            className={clsx('absolute left-0 right-0', i % 2 === 0 ? 'border-t border-border' : 'border-t border-border/40')}
            style={{ top: i * SLOT_HEIGHT }}
          />
        ))}
        {/* Appointments */}
        {appointments.map(appt => {
          const start = parseISO(appt.start_time)
          const end = parseISO(appt.end_time)
          const top = timeToY(start)
          const height = Math.max(durationToH(start, end), 20)
          return (
            <div
              key={appt.id}
              draggable
              className="absolute left-1 right-1 rounded border-l-2 px-1.5 py-0.5 cursor-grab active:cursor-grabbing hover:brightness-95 overflow-hidden z-10"
              style={{ top, height, ...apptCardStyle(collaborator.color, appt.status) }}
              onDragStart={() => {
                didDrag.current = false
                dragState.current = {
                  id: appt.id,
                  durationMin: differenceInMinutes(end, start),
                  collaboratorId: appt.collaborator_id,
                }
              }}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'move' }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); onDropOnAppointment(appt); didDrag.current = true }}
              onClick={(e) => { e.stopPropagation(); onAppointmentClick(appt) }}
            >
              <p className="text-[11px] font-semibold leading-tight truncate">
                {appt.client_name}
              </p>
              <p className="text-[10px] leading-tight truncate opacity-80">
                {format(start, 'HH:mm')}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Week day column ───────────────────────────────────────────────

function WeekDayColumn({ date, collaborators, appointments, timeToY, durationToH, onSlotClick, onAppointmentClick, dragState, didDrag, onDrop, onDropOnAppointment }: {
  date: Date
  collaborators: Collaborator[]
  appointments: Appointment[]
  timeToY: (d: Date) => number
  durationToH: (s: Date, e: Date) => number
  onSlotClick: (d: Date) => void
  onAppointmentClick: (a: Appointment) => void
  dragState: React.MutableRefObject<DragState | null>
  didDrag: React.MutableRefObject<boolean>
  onDrop: (relativeY: number, collaboratorId: number) => void
  onDropOnAppointment: (target: Appointment) => void
}) {
  const isToday = isSameDay(date, new Date())
  return (
    <div className="flex-1 min-w-[80px] border-l border-border">
      <div className={clsx(
        'h-10 border-b border-border flex items-center justify-center text-xs font-medium',
        isToday && 'bg-primary/10 text-primary'
      )}>
        {format(date, 'EEE d', { locale: it })}
      </div>
      <div
        className="relative"
        style={{ height: (END_HOUR - START_HOUR) * HOUR_HEIGHT }}
        onClick={(e) => {
          if (didDrag.current) { didDrag.current = false; return }
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
          const y = e.clientY - rect.top
          const totalMin = (y / SLOT_HEIGHT) * 30
          const slotMin = Math.floor(totalMin / 30) * 30
          const slotDate = new Date(date)
          slotDate.setHours(START_HOUR + Math.floor(slotMin / 60), slotMin % 60, 0, 0)
          onSlotClick(slotDate)
        }}
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move' }}
        onDrop={(e) => {
          e.preventDefault()
          const rect = (e.currentTarget as HTMLElement).getBoundingClientRect()
          const collaboratorId = dragState.current?.collaboratorId ?? collaborators[0]?.id ?? 0
          onDrop(e.clientY - rect.top, collaboratorId)
          didDrag.current = true
        }}
      >
        {Array.from({ length: (END_HOUR - START_HOUR) * 2 }, (_, i) => (
          <div key={i} className={clsx('absolute left-0 right-0', i % 2 === 0 ? 'border-t border-border' : 'border-t border-border/40')} style={{ top: i * SLOT_HEIGHT }} />
        ))}
        {appointments.map(appt => {
          const collab = collaborators.find(c => c.id === appt.collaborator_id)
          const collabColor = collab?.color ?? '#C8A96E'
          const start = parseISO(appt.start_time)
          const end = parseISO(appt.end_time)
          const top = timeToY(start)
          const height = Math.max(durationToH(start, end), 20)
          return (
            <div
              key={appt.id}
              draggable
              className="absolute left-0.5 right-0.5 rounded border-l-2 px-1 py-0.5 cursor-grab active:cursor-grabbing hover:brightness-95 overflow-hidden z-10"
              style={{ top, height, ...apptCardStyle(collabColor, appt.status) }}
              onDragStart={() => {
                didDrag.current = false
                dragState.current = {
                  id: appt.id,
                  durationMin: differenceInMinutes(end, start),
                  collaboratorId: appt.collaborator_id,
                }
              }}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = 'move' }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); onDropOnAppointment(appt); didDrag.current = true }}
              onClick={(e) => { e.stopPropagation(); onAppointmentClick(appt) }}
            >
              <p className="text-[10px] font-semibold truncate">{appt.client_name}</p>
              {collab && (
                <p className="text-[9px] truncate opacity-70">{collab.first_name}</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Appointment modal ─────────────────────────────────────────────

function AppointmentModal({ appointment, appointments, onClose, onConfirm, onReject, onComplete, onInvalidate }: {
  appointment: Appointment
  appointments: Appointment[]
  onClose: () => void
  onConfirm: () => void
  onReject: (reason?: string) => void
  onComplete: () => void
  onInvalidate: () => void
}) {
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [showEarlyEnd, setShowEarlyEnd] = useState(false)
  const [earlyHours, setEarlyHours] = useState('')
  const [earlyMinutes, setEarlyMinutes] = useState('')
  const [earlyEndError, setEarlyEndError] = useState('')
  const [showResize, setShowResize] = useState(false)
  const [resizeHours, setResizeHours] = useState('')
  const [resizeMinutes, setResizeMinutes] = useState('')
  const [resizeError, setResizeError] = useState('')

  const apptStart = parseISO(appointment.start_time)
  const apptEnd = parseISO(appointment.end_time)

  const updateMut = useMutation({
    mutationFn: (data: Parameters<typeof updateAppointment>[1]) =>
      updateAppointment(appointment.id, data),
    onSuccess: () => { onInvalidate(); onClose() },
  })

  const handleSaveEarlyEnd = () => {
    setEarlyEndError('')
    const h = Number(earlyHours)
    const m = Number(earlyMinutes)
    if (earlyHours === '' || earlyMinutes === '' || isNaN(h) || isNaN(m)) {
      setEarlyEndError('Inserisci un orario valido.')
      return
    }
    // Build newEnd in local time using the same calendar day as apptStart
    const dateStr = format(apptStart, 'yyyy-MM-dd')
    const newEnd = new Date(`${dateStr}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`)
    if (newEnd <= apptStart) {
      setEarlyEndError(`L'orario deve essere dopo ${format(apptStart, 'HH:mm')}.`)
      return
    }
    if (newEnd >= apptEnd) {
      setEarlyEndError(`L'orario deve essere prima di ${format(apptEnd, 'HH:mm')}.`)
      return
    }
    updateMut.mutate({ end_time: newEnd.toISOString() })
  }

  const handleSaveResize = () => {
    setResizeError('')
    const h = Number(resizeHours)
    const m = Number(resizeMinutes)
    if (resizeHours === '' || resizeMinutes === '' || isNaN(h) || isNaN(m)) {
      setResizeError('Inserisci un orario valido.')
      return
    }
    const dateStr = format(apptStart, 'yyyy-MM-dd')
    const newEnd = new Date(`${dateStr}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`)
    if (newEnd <= apptStart) {
      setResizeError(`L'orario deve essere dopo ${format(apptStart, 'HH:mm')}.`)
      return
    }
    // Check overlaps with other appointments of the same collaborator
    const conflict = appointments.find(a => {
      if (a.id === appointment.id) return false
      if (a.collaborator_id !== appointment.collaborator_id) return false
      const aStart = parseISO(a.start_time)
      const aEnd = parseISO(a.end_time)
      return aStart < newEnd && aEnd > apptStart
    })
    if (conflict) {
      setResizeError(
        `Sovrapposizione con l'appuntamento di ${conflict.client_name} (${format(parseISO(conflict.start_time), 'HH:mm')}–${format(parseISO(conflict.end_time), 'HH:mm')}).`
      )
      return
    }
    updateMut.mutate({ end_time: newEnd.toISOString() })
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold text-foreground">Appuntamento</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <Row label="Cliente" value={appointment.client_name ?? '–'} />
          <Row label="Collaboratore" value={appointment.collaborator_name ?? '–'} />
          <Row label="Orario" value={`${format(apptStart, 'dd/MM/yyyy HH:mm')} → ${format(apptEnd, 'HH:mm')}`} />
          <Row label="Totale" value={`€${(appointment.total_price ?? 0).toFixed(2)}`} />
          <Row label="Origine" value={appointment.origin === 'online' ? 'Prenotazione online' : 'Inserito dal salone'} />
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Stato:</span>
            <span className={clsx('status-badge', `status-${appointment.status}`)}>
              {appointment.status}
            </span>
          </div>
          {appointment.notes && <Row label="Note" value={appointment.notes} />}
        </div>

        {/* Actions */}
        <div className="p-4 border-t border-border flex flex-wrap gap-2">
          {appointment.status === 'pending' && (
            <>
              <button onClick={() => { onConfirm(); onClose() }} className="btn-primary flex items-center gap-1.5 text-sm py-1.5">
                <Check className="w-4 h-4" /> Conferma
              </button>
              <button onClick={() => setShowRejectForm(true)} className="btn-danger flex items-center gap-1.5 text-sm py-1.5">
                <X className="w-4 h-4" /> Rifiuta
              </button>
            </>
          )}
          {appointment.status === 'confirmed' && (
            <button onClick={() => { onComplete(); onClose() }} className="btn-primary flex items-center gap-1.5 text-sm py-1.5">
              <Check className="w-4 h-4" /> Segna completato
            </button>
          )}
          {!['completed', 'cancelled', 'rejected'].includes(appointment.status) && !showEarlyEnd && !showResize && (
            <>
              <button onClick={() => {
                  const mid = new Date((apptStart.getTime() + apptEnd.getTime()) / 2)
                  setEarlyHours(String(mid.getHours()))
                  setEarlyMinutes(String(mid.getMinutes()))
                  setShowEarlyEnd(true)
                }} className="btn-secondary text-sm py-1.5">
                Termina prima
              </button>
              <button onClick={() => {
                  setResizeHours(String(apptEnd.getHours()))
                  setResizeMinutes(String(apptEnd.getMinutes()))
                  setShowResize(true)
                }} className="btn-secondary text-sm py-1.5">
                Ridimensiona
              </button>
            </>
          )}
        </div>

        {/* Early end input */}
        {showEarlyEnd && (
          <div className="px-4 pb-4 border-t border-border pt-3 space-y-2">
            <p className="text-xs text-muted-foreground">Orario di fine anticipata:</p>
            <div className="flex items-center gap-1">
              <input
                type="number" min="0" max="23" placeholder="HH"
                className="input w-16 text-center"
                value={earlyHours}
                onChange={e => setEarlyHours(e.target.value)}
              />
              <span className="text-muted-foreground font-medium">:</span>
              <input
                type="number" min="0" max="59" placeholder="MM"
                className="input w-16 text-center"
                value={earlyMinutes}
                onChange={e => setEarlyMinutes(e.target.value)}
              />
              <button
                className="btn-primary text-sm py-1.5 ml-2"
                disabled={updateMut.isPending}
                onClick={handleSaveEarlyEnd}
              >
                {updateMut.isPending ? '...' : 'Salva'}
              </button>
              <button
                className="btn-secondary text-sm py-1.5"
                onClick={() => { setShowEarlyEnd(false); setEarlyEndError('') }}
              >
                Annulla
              </button>
            </div>
            {earlyEndError && <p className="text-xs text-red-500">{earlyEndError}</p>}
            {updateMut.isError && <p className="text-xs text-red-500">Errore nel salvataggio. Riprova.</p>}
          </div>
        )}

        {/* Resize input */}
        {showResize && (
          <div className="px-4 pb-4 border-t border-border pt-3 space-y-2">
            <p className="text-xs text-muted-foreground">
              Nuovo orario di fine (attuale: <span className="font-medium">{format(apptEnd, 'HH:mm')}</span>):
            </p>
            <div className="flex items-center gap-1">
              <input
                type="number" min="0" max="23" placeholder="HH"
                className="input w-16 text-center"
                value={resizeHours}
                onChange={e => setResizeHours(e.target.value)}
              />
              <span className="text-muted-foreground font-medium">:</span>
              <input
                type="number" min="0" max="59" placeholder="MM"
                className="input w-16 text-center"
                value={resizeMinutes}
                onChange={e => setResizeMinutes(e.target.value)}
              />
              <button
                className="btn-primary text-sm py-1.5 ml-2"
                disabled={updateMut.isPending}
                onClick={handleSaveResize}
              >
                {updateMut.isPending ? '...' : 'Salva'}
              </button>
              <button
                className="btn-secondary text-sm py-1.5"
                onClick={() => { setShowResize(false); setResizeError('') }}
              >
                Annulla
              </button>
            </div>
            {resizeError && <p className="text-xs text-red-500">{resizeError}</p>}
            {updateMut.isError && <p className="text-xs text-red-500">Errore nel salvataggio. Riprova.</p>}
          </div>
        )}

        {showRejectForm && (
          <div className="px-4 pb-4 space-y-2">
            <textarea
              className="input text-sm" rows={2}
              placeholder="Motivo rifiuto (opzionale)"
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
            />
            <button onClick={() => { onReject(rejectReason || undefined) }} className="btn-danger text-sm py-1.5">
              Conferma rifiuto
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Create appointment modal ──────────────────────────────────────

function CreateAppointmentModal({ initialSlot, collaborators, onClose, onCreated }: {
  initialSlot: { date: Date; collaboratorId: number } | null
  collaborators: Collaborator[]
  onClose: () => void
  onCreated: () => void
}) {
  const [clientSearch, setClientSearch] = useState('')
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [selectedCollabId, setSelectedCollabId] = useState<number>(
    initialSlot?.collaboratorId ?? collaborators[0]?.id ?? 0
  )
  const [day, setDay] = useState(initialSlot ? String(initialSlot.date.getDate()) : '')
  const [month, setMonth] = useState(initialSlot ? String(initialSlot.date.getMonth() + 1) : '')
  const [year, setYear] = useState(initialSlot ? String(initialSlot.date.getFullYear()) : '')
  const [hours, setHours] = useState(initialSlot ? String(initialSlot.date.getHours()) : '')
  const [minutes, setMinutes] = useState(initialSlot ? String(Math.floor(initialSlot.date.getMinutes() / 30) * 30) : '')

  const startDate = day && month && year
    ? `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`
    : ''
  const startHour = hours !== '' && minutes !== ''
    ? `${String(hours).padStart(2,'0')}:${String(minutes).padStart(2,'0')}`
    : ''
  const startTime = startDate && startHour ? `${startDate}T${startHour}` : ''
  const [selectedServiceIds, setSelectedServiceIds] = useState<number[]>([])
  const [notes, setNotes] = useState('')

  const { data: clientsData } = useQuery({
    queryKey: ['clients-search', clientSearch],
    queryFn: () => getClients({ search: clientSearch }),
    enabled: clientSearch.length > 1,
  })

  const { data: servicesData } = useQuery({
    queryKey: ['services'],
    queryFn: () => getServices({ active_only: true }),
  })

  const createMut = useMutation({
    mutationFn: createAppointment,
    onSuccess: onCreated,
  })

  const totalSlots = useMemo(() => {
    const services = servicesData?.items ?? []
    return selectedServiceIds.reduce((sum, id) => {
      const s = services.find(s => s.id === id)
      return sum + (s?.duration_slots ?? 0)
    }, 0)
  }, [selectedServiceIds, servicesData])

  const computedEnd = useMemo(() => {
    if (!startTime || totalSlots === 0) return ''
    const start = new Date(startTime)
    return format(addMinutes(start, totalSlots * 30), "yyyy-MM-dd'T'HH:mm")
  }, [startTime, totalSlots])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedClientId || !startTime || selectedServiceIds.length === 0) return
    createMut.mutate({
      client_id: selectedClientId,
      collaborator_id: selectedCollabId,
      start_time: new Date(startTime).toISOString(),
      end_time: new Date(computedEnd).toISOString(),
      service_ids: selectedServiceIds,
      notes: notes || undefined,
    })
  }

  const clients = clientsData?.items ?? []
  const services = servicesData?.items ?? []

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-lg">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">Nuovo appuntamento</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Client search */}
          <div>
            <label className="label block mb-1">Cliente</label>
            <input
              className="input"
              placeholder="Cerca per nome o telefono..."
              value={clientSearch}
              onChange={e => { setClientSearch(e.target.value); setSelectedClientId(null) }}
            />
            {clients.length > 0 && !selectedClientId && (
              <ul className="border border-border rounded-md mt-1 max-h-36 overflow-y-auto bg-surface shadow-sm">
                {clients.map(c => (
                  <li
                    key={c.id}
                    className="px-3 py-2 text-sm hover:bg-muted cursor-pointer"
                    onClick={() => { setSelectedClientId(c.id); setClientSearch(`${c.first_name} ${c.last_name}`) }}
                  >
                    {c.first_name} {c.last_name} {c.phone && <span className="text-muted-foreground">– {c.phone}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Collaborator */}
          <div>
            <label className="label block mb-1">Collaboratore</label>
            <select
              className="input"
              value={selectedCollabId}
              onChange={e => setSelectedCollabId(Number(e.target.value))}
            >
              {collaborators.map(c => (
                <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
              ))}
            </select>
          </div>

          {/* Date/time */}
          <div className="space-y-2">
            <div>
              <label className="label block mb-1">Data inizio</label>
              <div className="flex gap-1">
                <input
                  type="number" min="1" max="31" placeholder="GG"
                  className="input w-16 text-center"
                  value={day}
                  onChange={e => setDay(e.target.value)}
                  required
                />
                <span className="self-center text-muted-foreground">/</span>
                <input
                  type="number" min="1" max="12" placeholder="MM"
                  className="input w-16 text-center"
                  value={month}
                  onChange={e => setMonth(e.target.value)}
                  required
                />
                <span className="self-center text-muted-foreground">/</span>
                <input
                  type="number" min="2024" max="2099" placeholder="AAAA"
                  className="input flex-1 text-center"
                  value={year}
                  onChange={e => setYear(e.target.value)}
                  required
                />
              </div>
            </div>
            <div>
              <label className="label block mb-1">Ora inizio</label>
              <div className="flex gap-1 items-center">
                <input
                  type="number" min="0" max="23" placeholder="HH"
                  className="input w-16 text-center"
                  value={hours}
                  onChange={e => setHours(e.target.value)}
                  required
                />
                <span className="self-center text-muted-foreground font-medium">:</span>
                <input
                  type="number" min="0" max="59" step="30" placeholder="MM"
                  className="input w-16 text-center"
                  value={minutes}
                  onChange={e => setMinutes(e.target.value)}
                  required
                />
              </div>
            </div>
          </div>

          {/* Services */}
          <div>
            <label className="label block mb-1">Servizi</label>
            <div className="grid grid-cols-2 gap-2 max-h-40 overflow-y-auto">
              {services.map(s => (
                <label key={s.id} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedServiceIds.includes(s.id)}
                    onChange={e => {
                      if (e.target.checked) setSelectedServiceIds(prev => [...prev, s.id])
                      else setSelectedServiceIds(prev => prev.filter(id => id !== s.id))
                    }}
                  />
                  <span>{s.name}</span>
                  <span className="text-muted-foreground text-xs">€{s.price} · {s.duration_slots * 30}min</span>
                </label>
              ))}
            </div>
            {totalSlots > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                Durata totale: {totalSlots * 30} min
                {computedEnd && ` → Fine: ${format(new Date(computedEnd), 'HH:mm')}`}
              </p>
            )}
          </div>

          {/* Notes */}
          <div>
            <label className="label block mb-1">Note (opzionale)</label>
            <textarea className="input" rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm py-1.5">Annulla</button>
            <button
              type="submit"
              disabled={!selectedClientId || !startTime || selectedServiceIds.length === 0 || createMut.isPending}
              className="btn-primary text-sm py-1.5 disabled:opacity-60"
            >
              {createMut.isPending ? 'Salvataggio...' : 'Crea appuntamento'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="text-xs text-muted-foreground w-24 flex-shrink-0">{label}:</span>
      <span className="text-sm font-medium text-foreground">{value}</span>
    </div>
  )
}
