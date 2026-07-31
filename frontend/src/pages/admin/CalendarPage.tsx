import React, { useState, useMemo, useCallback, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  format, addDays, startOfWeek, isSameDay, parseISO, addMinutes, differenceInMinutes,
  startOfMonth, getDaysInMonth, isWithinInterval, startOfDay, endOfDay, addMonths, subMonths
} from 'date-fns'
import { it } from 'date-fns/locale'
import {
  ChevronLeft, ChevronRight, ChevronDown, Plus, Check, X,
  Calendar as CalendarIcon,
} from 'lucide-react'
import {
  getAppointments, getCollaborators, confirmAppointment,
  rejectAppointment, completeAppointment, cancelAppointment,
  createAppointment, getClients, getServices, updateAppointment, getAbsences, getBookingConfig
} from '@/services/api'
import type { Appointment, Collaborator } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { EmptyState, Segmented } from '@/components/ui'
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

const STATUS_LABELS: Record<string, string> = {
  pending:     'In attesa',
  confirmed:   'Confermato',
  rejected:    'Rifiutato',
  rescheduled: 'Riprogrammato',
  completed:   'Completato',
  cancelled:   'Annullato',
}

// Round date up to the next slot boundary (default 30 min).
function roundUpToSlot(d: Date, slotMin = 30): Date {
  const r = new Date(d)
  r.setSeconds(0, 0)
  const m = r.getMinutes()
  const remainder = m % slotMin
  if (remainder !== 0) r.setMinutes(m + (slotMin - remainder))
  return r
}

/**
 * Find the first free slot for a collaborator, starting from `from`.
 * Skips appointments in non-terminal status. Honors working hours.
 * If the candidate slot overlaps an existing appt, jumps to its end + round up.
 * Wraps to next day's START_HOUR if past END_HOUR.
 */
function computeFirstAvailableSlot(
  appointments: Appointment[],
  collaboratorId: number,
  from: Date,
  slotMin = 30,
): Date {
  const active = appointments
    .filter(a =>
      a.collaborator_id === collaboratorId &&
      !TERMINAL_STATUSES.includes(a.status)
    )
    .sort((a, b) => parseISO(a.start_time).getTime() - parseISO(b.start_time).getTime())

  let candidate = roundUpToSlot(from, slotMin)
  if (candidate.getHours() < START_HOUR) {
    candidate.setHours(START_HOUR, 0, 0, 0)
  }
  while (candidate.getHours() >= END_HOUR) {
    candidate = addDays(candidate, 1)
    candidate.setHours(START_HOUR, 0, 0, 0)
  }

  // Push past any overlapping appointment
  let changed = true
  let safety = 50
  while (changed && safety-- > 0) {
    changed = false
    const slotEnd = addMinutes(candidate, slotMin)
    for (const a of active) {
      const aStart = parseISO(a.start_time)
      const aEnd = parseISO(a.end_time)
      // Overlap test
      if (candidate < aEnd && slotEnd > aStart) {
        candidate = roundUpToSlot(aEnd, slotMin)
        if (candidate.getHours() >= END_HOUR) {
          candidate = addDays(candidate, 1)
          candidate.setHours(START_HOUR, 0, 0, 0)
        }
        changed = true
        break
      }
    }
  }
  return candidate
}

/**
 * Status is drawn, not coloured.
 *
 * The columns used to be washed in each collaborator's own hue, which brought
 * a second and third palette into a register that owns one. The block now
 * carries its state in its edge — filled for served, ruled for agreed,
 * pencilled dashed while a decision is pending, struck once it leaves the
 * book — and the collaborator is named in the band above the column instead.
 */
const APPT_BLOCK: Record<string, string> = {
  completed:   'bg-primary/10 border border-rule-soft border-l-2 border-l-primary text-foreground',
  confirmed:   'bg-field border border-border border-l-2 border-l-primary text-foreground',
  pending:     'bg-surface border border-dashed border-primary text-primary-dark',
  rescheduled: 'bg-band border border-border text-ink-2',
  cancelled:   'border border-border text-ink-3 line-through',
  rejected:    'border border-border text-ink-3 line-through',
}

const apptBlock = (status: string) => APPT_BLOCK[status] ?? APPT_BLOCK.confirmed

const LEGEND: { status: string; label: string }[] = [
  { status: 'completed', label: 'Completato' },
  { status: 'confirmed', label: 'Confermato' },
  { status: 'pending',   label: 'Da confermare' },
  { status: 'cancelled', label: 'Annullato' },
]

type ViewMode = 'day' | 'week'

/** The key to the grid: each state shown as the shape it actually takes. */
function StatusLegend() {
  return (
    <div className="hidden lg:flex items-center gap-5 flex-wrap">
      <span className="kicker">Stati</span>
      {LEGEND.map(({ status, label }) => (
        <span key={status} className="flex items-center gap-2">
          <span className={clsx('w-7 h-3 shrink-0', apptBlock(status))} aria-hidden="true" />
          <span className="text-[11px] text-ink-3">{label}</span>
        </span>
      ))}
    </div>
  )
}

/**
 * The current time, ruled across the column with a square dot on the gutter
 * side. Read at render: the grid already re-renders on every refetch, and a
 * dedicated timer would add a moving part for a line nobody reads to the minute.
 */
function NowRule({ date, timeToY }: { date: Date; timeToY: (d: Date) => number }) {
  const now = new Date()
  if (!isSameDay(date, now)) return null
  const y = timeToY(now)
  if (y < 0 || y > (END_HOUR - START_HOUR) * HOUR_HEIGHT) return null
  return (
    <div
      className="absolute left-0 right-0 z-20 pointer-events-none"
      style={{ top: y }}
      aria-hidden="true"
    >
      <span className="block h-px bg-primary" />
      <span className="absolute left-0 -top-[2px] w-[5px] h-[5px] bg-primary" />
    </div>
  )
}

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

  const { data: bookingConfig } = useQuery({
    queryKey: ['booking-config'],
    queryFn: getBookingConfig,
  })

  // Cancelled/rejected appointments free up their slot: hide them so the
  // calendar slot becomes clickable again for a new booking.
  const appointments = (apptsData?.items ?? []).filter(
    a => a.status !== 'cancelled' && a.status !== 'rejected'
  )
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
  const cancelMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) => cancelAppointment(id, reason),
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

  const openCreate = () => {
    const collabId = selectedCollaboratorId ?? collaborators[0]?.id
    if (collabId) {
      const firstSlot = computeFirstAvailableSlot(appointments, collabId, new Date())
      setNewApptSlot({ date: firstSlot, collaboratorId: collabId })
    }
    setShowCreateModal(true)
  }

  return (
    <div className="flex flex-col h-full gap-3 lg:gap-4">
      {/* Toolbar — stacks into rows on phones so nothing is pushed off-screen. */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-3 min-w-0">
          {/* One bordered unit rather than three loose buttons: stepping a day
              and returning to today are the same control. */}
          <div className="flex items-stretch h-10 border border-border shrink-0">
            <button
              onClick={() => navigate(-1)}
              className="w-9 flex items-center justify-center text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-colors"
              aria-label="Precedente"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setCurrentDate(new Date())}
              className="px-3.5 border-x border-border font-heading text-[11px] uppercase tracking-[0.12em] text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-colors"
            >
              Oggi
            </button>
            <button
              onClick={() => navigate(1)}
              className="w-9 flex items-center justify-center text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground transition-colors"
              aria-label="Successivo"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          {/* first-letter, not `capitalize`: Italian month names stay lowercase. */}
          <h2 className="font-heading text-[19px] leading-tight tracking-[0.03em] text-foreground tabular-nums truncate first-letter:uppercase">
            {viewMode === 'day'
              ? format(currentDate, 'EEE d MMMM yyyy', { locale: it })
              : `${format(days[0], 'd MMM', { locale: it })} – ${format(days[days.length - 1], 'd MMM yyyy', { locale: it })}`
            }
          </h2>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {/* Day/week toggle is desktop-only: the mobile agenda is always
              a single day, and a week of columns is unreadable at 375px. */}
          <Segmented
            className="hidden lg:flex"
            value={viewMode}
            onChange={setViewMode}
            options={[
              { value: 'day', label: 'Giorno' },
              { value: 'week', label: 'Settimana' },
            ]}
          />

          <select
            className="input !min-h-[2.5rem] h-10 text-[13px] py-1.5 flex-1 lg:flex-none lg:w-48"
            value={selectedCollaboratorId ?? ''}
            onChange={e => setSelectedCollaboratorId(e.target.value ? Number(e.target.value) : null)}
            aria-label="Filtra per collaboratore"
          >
            <option value="">Tutti i collaboratori</option>
            {collaborators.map(c => (
              <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
            ))}
          </select>

          <button onClick={openCreate} className="btn-primary btn-sm shrink-0">
            <Plus className="w-4 h-4" />
            <span className="hidden sm:inline">Nuovo</span>
          </button>
        </div>
      </div>

      <StatusLegend />

      {/* Mobile: chronological agenda instead of a squeezed time grid. */}
      <AgendaView
        date={currentDate}
        appointments={appointments}
        collaborators={visibleCollabs}
        onAppointmentClick={setSelectedAppointment}
        onCreate={openCreate}
      />

      {/* Desktop: full time grid with drag & drop. */}
      <div className="card flex-1 overflow-auto hidden lg:block">
        <div className="flex">
          {/* Time gutter — the band runs across it so the header reads as one strip. */}
          <div className="w-14 flex-shrink-0">
            <div className="h-14 band" /> {/* header spacer */}
            <div className="relative" style={{ height: (END_HOUR - START_HOUR) * HOUR_HEIGHT }}>
              {Array.from({ length: END_HOUR - START_HOUR }, (_, i) => (
                <div
                  key={i}
                  className="absolute right-2 text-[10px] text-ink-3 tabular-nums -translate-y-2"
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
          onCancel={(reason) => cancelMut.mutate({ id: selectedAppointment.id, reason })}
          onInvalidate={invalidate}
        />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateAppointmentModal
          initialSlot={newApptSlot}
          collaborators={collaborators}
          closedWeekdays={bookingConfig?.closed_weekdays ?? [0, 1]}
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
          <Sheet
            onClose={() => setPendingMove(null)}
            title="Sposta appuntamento"
            size="sm"
            footer={
              <>
                <button className="btn-secondary btn-sm" onClick={() => setPendingMove(null)}>
                  Annulla
                </button>
                <button
                  className="btn-primary btn-sm"
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
              </>
            }
          >
            <div className="text-sm text-muted-foreground space-y-2">
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
          </Sheet>
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
    <div className="flex-1 min-w-[120px] border-l border-rule">
      {/* Header — the band names the column; the rules separate it. */}
      <div className="h-14 band px-2.5 flex flex-col justify-center overflow-hidden">
        <span className="font-heading text-[15px] leading-tight tracking-[0.03em] text-foreground truncate">
          {collaborator.first_name}
        </span>
        <span className="text-[11px] leading-tight text-ink-3 truncate">
          {collaborator.last_name}
        </span>
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
        {/* Hour lines — full rule on the hour, soft one on the half. */}
        {Array.from({ length: (END_HOUR - START_HOUR) * 2 }, (_, i) => (
          <div
            key={i}
            className={clsx('absolute left-0 right-0 border-t', i % 2 === 0 ? 'border-rule' : 'border-rule-soft')}
            style={{ top: i * SLOT_HEIGHT }}
          />
        ))}
        <NowRule date={date} timeToY={timeToY} />
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
              className={clsx(
                'absolute left-1 right-1 px-1.5 py-0.5 overflow-hidden z-10',
                'cursor-grab active:cursor-grabbing hover:border-primary transition-colors',
                apptBlock(appt.status)
              )}
              style={{ top, height }}
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
              <p className="font-heading text-[13px] leading-tight tracking-[0.02em] truncate">
                {appt.client_name}
              </p>
              <p className="text-[10px] leading-tight truncate tabular-nums text-ink-3">
                {format(start, 'HH:mm')}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Mobile agenda ─────────────────────────────────────────────────

/**
 * Phone view of a single day: appointments as a chronological list.
 *
 * The desktop grid packs one column per collaborator, which at 375px leaves
 * each column ~80px wide and pushes later collaborators off-screen entirely.
 * A list keeps every appointment readable and tappable, and shows only the
 * hours that actually have something in them instead of 12 hours of blank grid.
 */
function AgendaView({
  date, appointments, collaborators, onAppointmentClick, onCreate,
}: {
  date: Date
  appointments: Appointment[]
  collaborators: Collaborator[]
  onAppointmentClick: (a: Appointment) => void
  onCreate: () => void
}) {
  const dayAppts = appointments
    .filter(a => isSameDay(parseISO(a.start_time), date))
    .sort((a, b) => parseISO(a.start_time).getTime() - parseISO(b.start_time).getTime())

  const collabById = new Map(collaborators.map(c => [c.id, c]))

  return (
    <div className="lg:hidden flex-1">
      {dayAppts.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={CalendarIcon}
            title="Nessun appuntamento"
            description={`Niente in programma per ${format(date, 'EEEE d MMMM', { locale: it })}.`}
            action={
              <button onClick={onCreate} className="btn-primary">
                <Plus className="w-4 h-4" /> Nuovo appuntamento
              </button>
            }
          />
        </div>
      ) : (
        <div className="space-y-2">
          {dayAppts.map(appt => {
            const start = parseISO(appt.start_time)
            const end = parseISO(appt.end_time)
            const collab = collabById.get(appt.collaborator_id)

            return (
              <button
                key={appt.id}
                onClick={() => onAppointmentClick(appt)}
                className={clsx(
                  'w-full text-left p-3.5 flex items-stretch gap-3.5 transition-colors hover:border-primary',
                  apptBlock(appt.status)
                )}
              >
                {/* Time rail */}
                <div className="flex flex-col items-end shrink-0 w-11">
                  <span className="font-heading text-[17px] leading-tight text-foreground tabular-nums">
                    {format(start, 'HH:mm')}
                  </span>
                  <span className="text-[11px] leading-tight text-ink-3 tabular-nums">
                    {format(end, 'HH:mm')}
                  </span>
                </div>

                <span className="w-px bg-rule shrink-0" aria-hidden="true" />

                <div className="min-w-0 flex-1">
                  <p className="font-heading text-[17px] leading-tight tracking-[0.02em] text-foreground truncate">
                    {appt.client_name || 'Cliente'}
                  </p>
                  {collab && (
                    <p className="text-[13px] text-ink-3 truncate mt-0.5">
                      {collab.first_name} {collab.last_name}
                    </p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <span className={clsx('status-badge', `status-${appt.status}`)}>
                      {STATUS_LABELS[appt.status] ?? appt.status}
                    </span>
                    {appt.total_price !== undefined && (
                      <span className="amount text-[13px] ml-auto">
                        €{appt.total_price.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}
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
    <div className="flex-1 min-w-[80px] border-l border-rule">
      <div className={clsx('h-14 band px-2 flex flex-col justify-center overflow-hidden', isToday && 'bg-primary/10')}>
        <span className={clsx(
          'font-heading text-[15px] leading-tight tracking-[0.03em] truncate first-letter:uppercase',
          isToday ? 'text-primary-dark' : 'text-foreground'
        )}>
          {format(date, 'EEE', { locale: it })}
        </span>
        <span className="text-[11px] leading-tight text-ink-3 tabular-nums truncate">
          {format(date, 'd MMM', { locale: it })}
        </span>
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
          <div key={i} className={clsx('absolute left-0 right-0 border-t', i % 2 === 0 ? 'border-rule' : 'border-rule-soft')} style={{ top: i * SLOT_HEIGHT }} />
        ))}
        <NowRule date={date} timeToY={timeToY} />
        {appointments.map(appt => {
          const collab = collaborators.find(c => c.id === appt.collaborator_id)
          const start = parseISO(appt.start_time)
          const end = parseISO(appt.end_time)
          const top = timeToY(start)
          const height = Math.max(durationToH(start, end), 20)
          return (
            <div
              key={appt.id}
              draggable
              className={clsx(
                'absolute left-0.5 right-0.5 px-1 py-0.5 overflow-hidden z-10',
                'cursor-grab active:cursor-grabbing hover:border-primary transition-colors',
                apptBlock(appt.status)
              )}
              style={{ top, height }}
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
              {/* The collaborator is named on the block, not signalled by a hue. */}
              <p className="font-heading text-[12px] leading-tight tracking-[0.02em] truncate">{appt.client_name}</p>
              {collab && (
                <p className="text-[9px] leading-tight truncate text-ink-3">{collab.first_name}</p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Appointment modal ─────────────────────────────────────────────

function AppointmentModal({ appointment, appointments, onClose, onConfirm, onReject, onComplete, onCancel, onInvalidate }: {
  appointment: Appointment
  appointments: Appointment[]
  onClose: () => void
  onConfirm: () => void
  onReject: (reason?: string) => void
  onComplete: () => void
  onCancel: (reason?: string) => void
  onInvalidate: () => void
}) {
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [showCancelForm, setShowCancelForm] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
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
    <Sheet onClose={onClose} title="Appuntamento" size="md">
      {/* The record itself, read as a ruled list of entries. */}
      <div className="border-t border-rule-soft">
        <Row label="Cliente" value={appointment.client_name ?? '–'} />
        <Row label="Collaboratore" value={appointment.collaborator_name ?? '–'} />
        <Row label="Orario" value={`${format(apptStart, 'dd/MM/yyyy HH:mm')} → ${format(apptEnd, 'HH:mm')}`} />
        <Row label="Totale" value={`€${(appointment.total_price ?? 0).toFixed(2)}`} />
        <Row label="Origine" value={appointment.origin === 'online' ? 'Prenotazione online' : 'Inserito dal salone'} />
        <div className="flex gap-3 py-2.5 border-b border-rule-soft">
          <span className="kicker w-28 shrink-0 pt-1">Stato</span>
          <span className={clsx('status-badge', `status-${appointment.status}`)}>
            {STATUS_LABELS[appointment.status] ?? appointment.status}
          </span>
        </div>
        {appointment.notes && <Row label="Note" value={appointment.notes} />}
      </div>

      {/* Actions */}
      <div className="pt-4 flex flex-wrap gap-2">
        {appointment.status === 'pending' && (
          <>
            <button onClick={() => { onConfirm(); onClose() }} className="btn-primary btn-sm">
              <Check className="w-4 h-4" /> Conferma
            </button>
            <button onClick={() => setShowRejectForm(true)} className="btn-danger-outline btn-sm">
              <X className="w-4 h-4" /> Rifiuta
            </button>
          </>
        )}
        {appointment.status === 'confirmed' && (
          <button onClick={() => { onComplete(); onClose() }} className="btn-primary btn-sm">
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
              }} className="btn-secondary btn-sm">
              Termina prima
            </button>
            <button onClick={() => {
                setResizeHours(String(apptEnd.getHours()))
                setResizeMinutes(String(apptEnd.getMinutes()))
                setShowResize(true)
              }} className="btn-secondary btn-sm">
              Ridimensiona
            </button>
            <button onClick={() => setShowCancelForm(true)} className="btn-danger-outline btn-sm">
              <X className="w-4 h-4" /> Annulla appuntamento
            </button>
          </>
        )}
      </div>

      {/* Early end input */}
      {showEarlyEnd && (
        <div className="mt-4 border-t border-rule pt-4 space-y-2">
          <span className="kicker">Orario di fine anticipata</span>
          <div className="flex items-center gap-1.5 flex-wrap">
            <input
              type="number" min="0" max="23" placeholder="HH"
              className="input w-16 text-center tabular-nums"
              value={earlyHours}
              onChange={e => setEarlyHours(e.target.value)}
            />
            <span className="text-ink-3">:</span>
            <input
              type="number" min="0" max="59" placeholder="MM"
              className="input w-16 text-center tabular-nums"
              value={earlyMinutes}
              onChange={e => setEarlyMinutes(e.target.value)}
            />
            <button
              className="btn-primary btn-sm ml-2"
              disabled={updateMut.isPending}
              onClick={handleSaveEarlyEnd}
            >
              {updateMut.isPending ? '...' : 'Salva'}
            </button>
            <button
              className="btn-secondary btn-sm"
              onClick={() => { setShowEarlyEnd(false); setEarlyEndError('') }}
            >
              Annulla
            </button>
          </div>
          {earlyEndError && <p className="text-xs text-danger">{earlyEndError}</p>}
          {updateMut.isError && <p className="text-xs text-danger">Errore nel salvataggio. Riprova.</p>}
        </div>
      )}

      {/* Resize input */}
      {showResize && (
        <div className="mt-4 border-t border-rule pt-4 space-y-2">
          <span className="kicker">
            Nuovo orario di fine (attuale: <span className="tabular-nums">{format(apptEnd, 'HH:mm')}</span>)
          </span>
          <div className="flex items-center gap-1.5 flex-wrap">
            <input
              type="number" min="0" max="23" placeholder="HH"
              className="input w-16 text-center tabular-nums"
              value={resizeHours}
              onChange={e => setResizeHours(e.target.value)}
            />
            <span className="text-ink-3">:</span>
            <input
              type="number" min="0" max="59" placeholder="MM"
              className="input w-16 text-center tabular-nums"
              value={resizeMinutes}
              onChange={e => setResizeMinutes(e.target.value)}
            />
            <button
              className="btn-primary btn-sm ml-2"
              disabled={updateMut.isPending}
              onClick={handleSaveResize}
            >
              {updateMut.isPending ? '...' : 'Salva'}
            </button>
            <button
              className="btn-secondary btn-sm"
              onClick={() => { setShowResize(false); setResizeError('') }}
            >
              Annulla
            </button>
          </div>
          {resizeError && <p className="text-xs text-danger">{resizeError}</p>}
          {updateMut.isError && <p className="text-xs text-danger">Errore nel salvataggio. Riprova.</p>}
        </div>
      )}

      {showRejectForm && (
        <div className="mt-4 border-t border-rule pt-4 space-y-2">
          <textarea
            className="input text-sm" rows={2}
            placeholder="Motivo rifiuto (opzionale)"
            value={rejectReason}
            onChange={e => setRejectReason(e.target.value)}
          />
          <button onClick={() => { onReject(rejectReason || undefined) }} className="btn-danger btn-sm">
            Conferma rifiuto
          </button>
        </div>
      )}

      {/* Cancel form */}
      {showCancelForm && (
        <div className="mt-4 border-t border-rule pt-4 space-y-2">
          <p className="text-sm text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5">
            Annullare questo appuntamento?
          </p>
          <textarea
            className="input text-sm"
            rows={2}
            placeholder="Motivo annullamento (opzionale)…"
            value={cancelReason}
            onChange={e => setCancelReason(e.target.value)}
          />
          <div className="flex gap-2">
            <button onClick={() => setShowCancelForm(false)} className="btn-secondary btn-sm flex-1">
              Indietro
            </button>
            <button onClick={() => { onCancel(cancelReason || undefined); onClose() }} className="btn-danger btn-sm flex-1">
              Conferma annullamento
            </button>
          </div>
        </div>
      )}
    </Sheet>
  )
}

// ── Create appointment modal ──────────────────────────────────────

function CreateAppointmentModal({ initialSlot, collaborators, closedWeekdays, onClose, onCreated }: {
  initialSlot: { date: Date; collaboratorId: number } | null
  collaborators: Collaborator[]
  closedWeekdays: number[]
  onClose: () => void
  onCreated: () => void
}) {
  const [clientSearch, setClientSearch] = useState('')
  const [clientDropdownOpen, setClientDropdownOpen] = useState(false)
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null)
  const [selectedCollabId, setSelectedCollabId] = useState<number>(
    initialSlot?.collaboratorId ?? collaborators[0]?.id ?? 0
  )
  const initDate = initialSlot?.date ?? new Date()
  const [selectedDate, setSelectedDate] = useState<Date>(initDate)
  const [calMonth, setCalMonth] = useState<Date>(startOfMonth(initDate))
  const [hours, setHours] = useState(String(initDate.getHours()))
  const [minutes, setMinutes] = useState(String(Math.floor(initDate.getMinutes() / 30) * 30))

  const startTime = useMemo(() => {
    const h = hours.padStart(2, '0')
    const m = String(minutes).padStart(2, '0')
    return format(selectedDate, `yyyy-MM-dd'T'${h}:${m}`)
  }, [selectedDate, hours, minutes])

  const [selectedServiceIds, setSelectedServiceIds] = useState<number[]>([])
  const [notes, setNotes] = useState('')
  const [confirmClosed, setConfirmClosed] = useState(false)

  const { data: clientsData } = useQuery({
    queryKey: ['clients-all'],
    queryFn: () => getClients({ page_size: 500, active_only: true }),
  })

  const { data: absencesData } = useQuery({
    queryKey: ['absences', selectedCollabId],
    queryFn: () => getAbsences(selectedCollabId),
    enabled: selectedCollabId > 0,
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

  const doCreate = () => {
    createMut.mutate({
      client_id: selectedClientId!,
      collaborator_id: selectedCollabId,
      start_time: new Date(startTime).toISOString(),
      end_time: new Date(computedEnd).toISOString(),
      service_ids: selectedServiceIds,
      notes: notes || undefined,
    })
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedClientId || !startTime || selectedServiceIds.length === 0) return
    if (isClosedDay(selectedDate) && !confirmClosed) {
      setConfirmClosed(true)
      return
    }
    doCreate()
  }

  const allClients = clientsData?.items ?? []
  const filteredClients = clientSearch.trim().length > 0
    ? allClients.filter(c => {
        const q = clientSearch.toLowerCase()
        return (
          c.first_name.toLowerCase().includes(q) ||
          c.last_name.toLowerCase().includes(q) ||
          (c.phone ?? '').includes(q)
        )
      })
    : allClients
  const selectedClient = allClients.find(c => c.id === selectedClientId) ?? null
  const services = servicesData?.items ?? []

  // Closed-day logic for mini calendar
  const selectedCollab = collaborators.find(c => c.id === selectedCollabId)
  const absences = absencesData ?? []

  const isClosedDay = (d: Date): boolean => {
    const dow = d.getDay() // 0=Sun … 6=Sat
    // Salon-wide closed days from config
    if (closedWeekdays.includes(dow)) return true
    // Collaborator absences (specific dates off)
    return absences.some(a =>
      isWithinInterval(startOfDay(d), {
        start: startOfDay(parseISO(a.start_date)),
        end: endOfDay(parseISO(a.end_date)),
      })
    )
  }

  // Build calendar grid for calMonth
  const calFirstDay = startOfMonth(calMonth)
  const daysInMonth = getDaysInMonth(calMonth)
  // Offset: Mon=0 … Sun=6
  const firstDow = (calFirstDay.getDay() + 6) % 7
  const calDays: (Date | null)[] = [
    ...Array(firstDow).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => addDays(calFirstDay, i)),
  ]

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-surface shadow-xl w-full max-w-lg my-auto">
        <div className="flex items-center justify-between p-4 border-b border-border sticky top-0 bg-surface z-10">
          <h3 className="font-heading text-lg text-foreground">Nuovo appuntamento</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Client combobox */}
          <div className="relative">
            <label className="label block mb-1">Cliente</label>
            <button
              type="button"
              className="input text-left flex items-center justify-between w-full"
              onClick={() => setClientDropdownOpen(o => !o)}
            >
              <span className={selectedClient ? '' : 'text-muted-foreground'}>
                {selectedClient
                  ? `${selectedClient.first_name} ${selectedClient.last_name}${selectedClient.phone ? ` – ${selectedClient.phone}` : ''}`
                  : 'Seleziona cliente…'}
              </span>
              <ChevronDown className="w-4 h-4 text-muted-foreground shrink-0" />
            </button>
            {clientDropdownOpen && (
              <div className="absolute z-50 mt-1 w-full bg-surface border border-border shadow-lg">
                <div className="p-2 border-b border-border">
                  <input
                    autoFocus
                    className="input text-sm py-1"
                    placeholder="Cerca per nome o telefono…"
                    value={clientSearch}
                    onChange={e => setClientSearch(e.target.value)}
                    onClick={e => e.stopPropagation()}
                  />
                </div>
                <ul className="max-h-48 overflow-y-auto">
                  {filteredClients.length === 0 && (
                    <li className="px-3 py-2 text-sm text-muted-foreground">Nessun cliente trovato</li>
                  )}
                  {filteredClients.map(c => (
                    <li
                      key={c.id}
                      className={clsx(
                        'px-3 py-2 text-sm cursor-pointer flex items-center justify-between',
                        c.id === selectedClientId ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-foreground/[0.05]'
                      )}
                      onClick={() => {
                        setSelectedClientId(c.id)
                        setClientDropdownOpen(false)
                        setClientSearch('')
                      }}
                    >
                      <span>{c.first_name} {c.last_name}</span>
                      {c.phone && <span className="text-muted-foreground text-xs">{c.phone}</span>}
                    </li>
                  ))}
                </ul>
              </div>
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

          {/* Date picker */}
          <div>
            <label className="label block mb-1">Data</label>
            <div className="border border-border overflow-hidden">
              {/* Month nav */}
              <div className="flex items-center justify-between px-3 py-2 bg-band border-b border-border">
                <button type="button" onClick={() => setCalMonth(m => subMonths(m, 1))} className="p-1 hover:bg-foreground/[0.05] rounded">
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="text-sm font-medium capitalize">
                  {format(calMonth, 'MMMM yyyy', { locale: it })}
                </span>
                <button type="button" onClick={() => setCalMonth(m => addMonths(m, 1))} className="p-1 hover:bg-foreground/[0.05] rounded">
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
              {/* Day-of-week headers */}
              <div className="grid grid-cols-7 text-center text-xs text-muted-foreground py-1 border-b border-border">
                {['Lu','Ma','Me','Gi','Ve','Sa','Do'].map(d => (
                  <span key={d}>{d}</span>
                ))}
              </div>
              {/* Days grid */}
              <div className="grid grid-cols-7 gap-y-0.5 p-1">
                {calDays.map((d, i) => {
                  if (!d) return <span key={i} />
                  const closed = isClosedDay(d)
                  const selected = isSameDay(d, selectedDate)
                  const today = isSameDay(d, new Date())
                  return (
                    <button
                      key={i}
                      type="button"
                      disabled={closed}
                      onClick={() => setSelectedDate(d)}
                      className={clsx(
                        'h-8 w-full rounded text-sm transition-colors',
                        closed && 'text-danger line-through cursor-not-allowed opacity-60',
                        !closed && selected && 'bg-primary text-white font-semibold',
                        !closed && !selected && today && 'border border-primary text-primary',
                        !closed && !selected && !today && 'hover:bg-foreground/[0.05]',
                      )}
                    >
                      {d.getDate()}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Clock time picker */}
          <div>
            <label className="label block mb-1">Ora</label>
            <div className="border border-border p-4 flex flex-col items-center gap-3">
              {/* Selected time display */}
              <div className="text-2xl font-semibold tabular-nums text-primary">
                {String(Number(hours)).padStart(2,'0')}:{String(minutes) === '0' ? '00' : '30'}
              </div>
              {/* Clock face */}
              <div className="relative w-48 h-48">
                {/* Background circle */}
                <div className="absolute inset-0 border border-border bg-muted/20" />
                {/* SVG hand */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none">
                  {(() => {
                    const idx = Number(hours) - START_HOUR
                    const angle = (idx * 30 - 90) * (Math.PI / 180)
                    const x2 = 96 + 54 * Math.cos(angle)
                    const y2 = 96 + 54 * Math.sin(angle)
                    return (
                      <>
                        <line x1={96} y1={96} x2={x2} y2={y2} stroke="var(--color-primary,#c9a84c)" strokeWidth="2" strokeLinecap="round" />
                        <circle cx={96} cy={96} r={3} fill="var(--color-primary,#c9a84c)" />
                        <circle cx={x2} cy={y2} r={4} fill="var(--color-primary,#c9a84c)" />
                      </>
                    )
                  })()}
                </svg>
                {/* Hour buttons */}
                {Array.from({ length: END_HOUR - START_HOUR }, (_, i) => i + START_HOUR).map((h, i) => {
                  const angle = (i * 30 - 90) * (Math.PI / 180)
                  const x = 96 + 72 * Math.cos(angle)
                  const y = 96 + 72 * Math.sin(angle)
                  const sel = Number(hours) === h
                  return (
                    <button
                      key={h}
                      type="button"
                      onClick={() => setHours(String(h))}
                      className={clsx(
                        'absolute w-8 h-8  text-xs font-medium transition-colors flex items-center justify-center',
                        sel ? 'bg-primary text-white shadow-sm' : 'hover:bg-foreground/[0.05] text-foreground'
                      )}
                      style={{ left: x - 16, top: y - 16 }}
                    >
                      {String(h).padStart(2,'0')}
                    </button>
                  )
                })}
              </div>
              {/* Minute toggle */}
              <div className="flex gap-2 w-full">
                {([['0', ':00'], ['30', ':30']] as const).map(([v, label]) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => setMinutes(v)}
                    className={clsx(
                      'flex-1 py-2  text-sm font-medium border transition-colors',
                      minutes === v ? 'bg-primary text-white border-primary' : 'border-border hover:bg-foreground/[0.05]'
                    )}
                  >
                    {label}
                  </button>
                ))}
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

          {confirmClosed && (
            <div className="border border-primary/50 bg-primary/10 p-3 text-sm text-primary space-y-2">
              <p className="font-medium">⚠ Il salone è chiuso in questa data. Vuoi procedere comunque?</p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmClosed(false)}
                  className="flex-1 btn-secondary text-sm py-1"
                >
                  Annulla
                </button>
                <button
                  type="button"
                  onClick={doCreate}
                  disabled={createMut.isPending}
                  className="flex-1 bg-primary hover:bg-primary text-white text-sm py-1 font-medium transition-colors disabled:opacity-60"
                >
                  {createMut.isPending ? 'Salvataggio...' : 'Sì, crea comunque'}
                </button>
              </div>
            </div>
          )}

          {!confirmClosed && (
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
          )}
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
