import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Check, Edit, Trash2 } from 'lucide-react'
import {
  getCollaborators, createCollaborator, updateCollaborator,
  updateCollaboratorSchedule, updateCollaboratorServices, getServices,
  getAbsences, createAbsence, deleteAbsence,
  getExtraWorkDays, createExtraWorkDay, deleteExtraWorkDay,
} from '@/services/api'
import type { Collaborator, CollaboratorSchedule, Absence, AbsenceType, ExtraWorkDay } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader } from '@/components/ui'
import { Toggle } from './ServicesPage'
import clsx from 'clsx'

const DAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']

/* The shared .input is cut for a full-page form; everything inside a
   collaborator card sits in ruled rows, so the fields take the same well at
   row height instead. */
const FIELD =
  'w-full border border-border bg-field px-2 py-1.5 text-[13px] text-foreground ' +
  'transition-colors focus:outline-none focus:border-primary'

/* Same well, sized for the two hours that close a timetable row. */
const TIME_FIELD =
  'border border-border bg-field px-1.5 py-1 text-[13px] tabular-nums text-foreground ' +
  'transition-colors focus:outline-none focus:border-primary'

const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
  ferie:    'Ferie',
  permesso: 'Permesso',
  malattia: 'Malattia',
  altro:    'Altro',
}

/**
 * A tick box with the ledger's own edge: square, hairline, filled gold when
 * set — the same treatment classical.css gives its radio.
 *
 * It stays a real `<input type="checkbox">` under the paint, so the label
 * association, the keyboard and the screen reader all keep working; only the
 * native rendering is replaced, because on macOS it comes out rounded.
 */
function SquareCheck(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="checkbox"
      className="w-4 h-4 shrink-0 cursor-pointer appearance-none border border-border bg-field transition-colors checked:border-primary checked:bg-primary checked:shadow-[inset_0_0_0_2px_hsl(var(--surface))]"
      {...props}
    />
  )
}

export default function CollaboratorsPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<Collaborator | null>(null)
  const [showForm, setShowForm] = useState(false)

  const { data } = useQuery({
    queryKey: ['collaborators'],
    queryFn: () => getCollaborators(),
  })

  const { data: servicesData } = useQuery({
    queryKey: ['services'],
    queryFn: () => getServices({ active_only: true }),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['collaborators'] })

  const createMut = useMutation({ mutationFn: createCollaborator, onSuccess: () => { inv(); setShowForm(false) } })
  const updateMut = useMutation({ mutationFn: ({ id, data }: any) => updateCollaborator(id, data), onSuccess: () => { inv(); setShowForm(false) } })
  const schedMut = useMutation({ mutationFn: ({ id, s }: any) => updateCollaboratorSchedule(id, s), onSuccess: inv })
  const svcsMut = useMutation({ mutationFn: ({ id, ids }: any) => updateCollaboratorServices(id, ids), onSuccess: inv })

  const collaborators = data?.items ?? []
  const services = servicesData?.items ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="Collaboratori"
        action={
          <button onClick={() => { setSelected(null); setShowForm(true) }} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo
          </button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {collaborators.map(c => (
          <CollaboratorCard
            key={c.id}
            collaborator={c}
            services={services}
            onEdit={() => { setSelected(c); setShowForm(true) }}
            onUpdateSchedule={(s) => schedMut.mutate({ id: c.id, s })}
            onUpdateServices={(ids) => svcsMut.mutate({ id: c.id, ids })}
          />
        ))}
      </div>

      {showForm && (
        <CollaboratorFormModal
          collaborator={selected ?? undefined}
          onClose={() => setShowForm(false)}
          onSave={(data) => selected
            ? updateMut.mutate({ id: selected.id, data })
            : createMut.mutate(data)
          }
          loading={createMut.isPending || updateMut.isPending}
        />
      )}
    </div>
  )
}

function CollaboratorCard({ collaborator: c, services, onEdit, onUpdateSchedule, onUpdateServices }: {
  collaborator: Collaborator
  services: any[]
  onEdit: () => void
  onUpdateSchedule: (s: Partial<CollaboratorSchedule>[]) => void
  onUpdateServices: (ids: number[]) => void
}) {
  const [tab, setTab] = useState<'info' | 'schedule' | 'services' | 'vacations' | 'extra'>('info')
  const [schedules, setSchedules] = useState<Record<number, { start: string; end: string; working: boolean }>>(
    Object.fromEntries(
      DAYS.map((_, i) => {
        const s = c.schedules.find(s => s.day_of_week === i)
        return [i, {
          start: s?.start_time?.slice(0, 5) ?? '09:00',
          end: s?.end_time?.slice(0, 5) ?? '19:00',
          working: s?.is_working ?? (i < 6),
        }]
      })
    )
  )
  const [selectedServices, setSelectedServices] = useState<number[]>(c.service_ids)

  const saveSchedules = () => {
    onUpdateSchedule(
      Object.entries(schedules).map(([day, s]) => ({
        day_of_week: Number(day),
        start_time: s.working ? s.start : undefined,
        end_time: s.working ? s.end : undefined,
        is_working: s.working,
      }))
    )
  }

  const TAB_LABELS = { info: 'Info', schedule: 'Orari', services: 'Servizi', vacations: 'Ferie', extra: 'Straord.' }

  return (
    <div className="panel">
      {/* The colour is the one the calendar paints this collaborator with, so
          it stays on the card — as a rule down the edge and as the ground of a
          squared initials cell. */}
      <div className="band flex items-center gap-3 px-3.5 py-3" style={{ borderLeft: `4px solid ${c.color}` }}>
        <div
          className="w-9 h-9 border border-border flex items-center justify-center shrink-0 font-heading text-[13px] tracking-[0.06em] text-white"
          style={{ backgroundColor: c.color }}
        >
          {c.first_name[0]}{c.last_name[0]}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-heading text-[15px] tracking-[0.03em] text-foreground truncate">
            {c.first_name} {c.last_name}
          </p>
          <p className="text-xs text-ink-3 truncate">{c.email ?? c.phone ?? '–'}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {!c.is_active && (
            <span className="status-badge border border-border text-ink-3">inattivo</span>
          )}
          {c.visible_online && <span className="status-badge status-confirmed">online</span>}
          <button onClick={onEdit} className="btn-icon !w-9 !h-9 -mr-1.5">
            <Edit className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tabs — a rule under the live section, the way a register marks the
          page it is open at. */}
      <div className="flex border-b border-rule">
        {(['info', 'schedule', 'services', 'vacations', 'extra'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'flex-1 px-1 py-2 -mb-px border-b-2 transition-colors whitespace-nowrap',
              'font-heading text-[11px] uppercase tracking-[0.08em]',
              tab === t
                ? 'border-primary text-foreground'
                : 'border-transparent text-ink-3 hover:text-foreground'
            )}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="p-3.5">
        {tab === 'info' && (
          <div className="divide-y divide-rule-soft">
            <div className="flex items-baseline gap-3 py-1.5">
              <span className="kicker w-14 shrink-0">Tel:</span>
              <span className="text-[13px] text-ink-2 tabular-nums truncate">{c.phone ?? '–'}</span>
            </div>
            <div className="flex items-baseline gap-3 py-1.5">
              <span className="kicker w-14 shrink-0">Email:</span>
              <span className="text-[13px] text-ink-2 truncate">{c.email ?? '–'}</span>
            </div>
          </div>
        )}

        {/* The week as a timetable: one ruled line per day, the day named on
            the left and its hours closing the row on the right, so a glance
            down the column reads the shift pattern. */}
        {tab === 'schedule' && (
          <div>
            <div className="divide-y divide-rule-soft border-y border-rule-soft">
              {DAYS.map((day, i) => (
                <div key={i} className="flex items-center gap-2.5 py-1.5">
                  <SquareCheck
                    checked={schedules[i].working}
                    onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], working: e.target.checked } }))}
                  />
                  <span className="kicker w-8 shrink-0">{day}</span>
                  {schedules[i].working ? (
                    <div className="ml-auto flex items-center gap-1.5">
                      <input
                        type="time"
                        className={TIME_FIELD}
                        value={schedules[i].start}
                        onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], start: e.target.value } }))}
                      />
                      <span className="text-ink-3">–</span>
                      <input
                        type="time"
                        className={TIME_FIELD}
                        value={schedules[i].end}
                        onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], end: e.target.value } }))}
                      />
                    </div>
                  ) : (
                    /* A day off still gets its line, so the seven rows stay
                       aligned as a timetable rather than collapsing. */
                    <span className="ml-auto text-[13px] text-ink-3">–</span>
                  )}
                </div>
              ))}
            </div>
            <button onClick={saveSchedules} className="btn-primary btn-sm w-full mt-3">
              Salva orari
            </button>
          </div>
        )}

        {tab === 'services' && (
          <div>
            <div className="divide-y divide-rule-soft border-y border-rule-soft">
              {services.map(s => (
                <label key={s.id} className="flex items-center gap-2.5 py-2 cursor-pointer">
                  <SquareCheck
                    checked={selectedServices.includes(s.id)}
                    onChange={e => setSelectedServices(prev =>
                      e.target.checked ? [...prev, s.id] : prev.filter(id => id !== s.id)
                    )}
                  />
                  <span className="text-[13px] text-ink-2">{s.name}</span>
                </label>
              ))}
            </div>
            <button
              onClick={() => onUpdateServices(selectedServices)}
              className="btn-primary btn-sm w-full mt-3"
            >
              Salva servizi
            </button>
          </div>
        )}

        {tab === 'vacations' && (
          <VacationsTab collaboratorId={c.id} />
        )}

        {tab === 'extra' && (
          <ExtraDaysTab collaboratorId={c.id} />
        )}
      </div>
    </div>
  )
}

function VacationsTab({ collaboratorId }: { collaboratorId: number }) {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [type, setType] = useState<AbsenceType>('ferie')
  const [notes, setNotes] = useState('')

  const { data: absences = [], isLoading } = useQuery({
    queryKey: ['absences', collaboratorId],
    queryFn: () => getAbsences(collaboratorId),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['absences', collaboratorId] })

  const createMut = useMutation({
    mutationFn: () => createAbsence({
      collaborator_id: collaboratorId,
      start_date: startDate,
      end_date: endDate,
      type,
      notes: notes || undefined,
    }),
    onSuccess: () => {
      inv()
      setShowForm(false)
      setStartDate('')
      setEndDate('')
      setNotes('')
      setType('ferie')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteAbsence(id),
    onSuccess: inv,
  })

  const formatDate = (d: string) => {
    const [y, m, day] = d.split('-')
    return `${day}/${m}/${y}`
  }

  return (
    <div className="space-y-2">
      {isLoading && <p className="text-xs text-muted-foreground">Caricamento…</p>}

      {/* Lista assenze */}
      {absences.length === 0 && !isLoading && (
        <p className="text-xs text-muted-foreground italic">Nessuna assenza registrata.</p>
      )}
      <div className="space-y-1.5">
        {absences.map(a => (
          <div key={a.id} className="flex items-center justify-between bg-muted rounded px-2 py-1.5 text-xs">
            <div>
              <span className="font-medium">{ABSENCE_TYPE_LABELS[a.type]}</span>
              <span className="text-muted-foreground ml-1.5">
                {formatDate(a.start_date)} – {formatDate(a.end_date)}
              </span>
              {a.notes && <span className="text-muted-foreground ml-1.5 italic">({a.notes})</span>}
            </div>
            <button
              onClick={() => deleteMut.mutate(a.id)}
              disabled={deleteMut.isPending}
              className="text-muted-foreground hover:text-danger ml-2"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Form nuova assenza */}
      {showForm ? (
        <div className="border border-border rounded p-2 space-y-2 mt-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-0.5">Dal</label>
              <input
                type="date"
                className="border border-border rounded px-1.5 py-1 text-xs w-full"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-0.5">Al</label>
              <input
                type="date"
                className="border border-border rounded px-1.5 py-1 text-xs w-full"
                value={endDate}
                onChange={e => setEndDate(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-0.5">Tipo</label>
            <select
              className="border border-border rounded px-1.5 py-1 text-xs w-full"
              value={type}
              onChange={e => setType(e.target.value as AbsenceType)}
            >
              {(Object.entries(ABSENCE_TYPE_LABELS) as [AbsenceType, string][]).map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-0.5">Note (opzionale)</label>
            <input
              type="text"
              className="border border-border rounded px-1.5 py-1 text-xs w-full"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="es. ferie estive"
            />
          </div>
          <div className="flex gap-1.5">
            <button
              className="btn-primary text-xs py-1 flex-1"
              disabled={!startDate || !endDate || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? '…' : 'Salva'}
            </button>
            <button
              className="btn-secondary text-xs py-1"
              onClick={() => setShowForm(false)}
            >
              Annulla
            </button>
          </div>
        </div>
      ) : (
        <button
          className="btn-secondary text-xs py-1 w-full mt-1 flex items-center justify-center gap-1"
          onClick={() => setShowForm(true)}
        >
          <Plus className="w-3 h-3" /> Aggiungi assenza
        </button>
      )}
    </div>
  )
}

function ExtraDaysTab({ collaboratorId }: { collaboratorId: number }) {
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [date, setDate] = useState('')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('18:00')
  const [notes, setNotes] = useState('')

  const { data: extraDays = [], isLoading } = useQuery({
    queryKey: ['extra-days', collaboratorId],
    queryFn: () => getExtraWorkDays(collaboratorId),
  })

  const inv = () => qc.invalidateQueries({ queryKey: ['extra-days', collaboratorId] })

  const createMut = useMutation({
    mutationFn: () => createExtraWorkDay({
      collaborator_id: collaboratorId,
      date,
      start_time: startTime,
      end_time: endTime,
      notes: notes || undefined,
    }),
    onSuccess: () => {
      inv()
      setShowForm(false)
      setDate('')
      setStartTime('09:00')
      setEndTime('18:00')
      setNotes('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteExtraWorkDay(id),
    onSuccess: inv,
  })

  const formatDate = (d: string) => {
    const [y, m, day] = d.split('-')
    return `${day}/${m}/${y}`
  }

  return (
    <div className="space-y-2">
      {isLoading && <p className="text-xs text-muted-foreground">Caricamento…</p>}

      {extraDays.length === 0 && !isLoading && (
        <p className="text-xs text-muted-foreground italic">Nessun giorno straordinario registrato.</p>
      )}

      <div className="space-y-1.5">
        {extraDays.map(e => (
          <div key={e.id} className="flex items-center justify-between bg-muted rounded px-2 py-1.5 text-xs">
            <div>
              <span className="font-medium">{formatDate(e.date)}</span>
              <span className="text-muted-foreground ml-1.5">
                {e.start_time.slice(0, 5)} – {e.end_time.slice(0, 5)}
              </span>
              {e.notes && <span className="text-muted-foreground ml-1.5 italic">({e.notes})</span>}
            </div>
            <button
              onClick={() => deleteMut.mutate(e.id)}
              disabled={deleteMut.isPending}
              className="text-muted-foreground hover:text-danger ml-2"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {showForm ? (
        <div className="border border-border rounded p-2 space-y-2 mt-2">
          <div>
            <label className="text-xs text-muted-foreground block mb-0.5">Data</label>
            <input
              type="date"
              className="border border-border rounded px-1.5 py-1 text-xs w-full"
              value={date}
              onChange={e => setDate(e.target.value)}
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-muted-foreground block mb-0.5">Dalle</label>
              <input
                type="time"
                className="border border-border rounded px-1.5 py-1 text-xs w-full"
                value={startTime}
                onChange={e => setStartTime(e.target.value)}
              />
            </div>
            <div>
              <label className="text-xs text-muted-foreground block mb-0.5">Alle</label>
              <input
                type="time"
                className="border border-border rounded px-1.5 py-1 text-xs w-full"
                value={endTime}
                onChange={e => setEndTime(e.target.value)}
              />
            </div>
          </div>
          <div>
            <label className="text-xs text-muted-foreground block mb-0.5">Note (opzionale)</label>
            <input
              type="text"
              className="border border-border rounded px-1.5 py-1 text-xs w-full"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="es. apertura straordinaria"
            />
          </div>
          <div className="flex gap-1.5">
            <button
              className="btn-primary text-xs py-1 flex-1"
              disabled={!date || !startTime || !endTime || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? '…' : 'Salva'}
            </button>
            <button
              className="btn-secondary text-xs py-1"
              onClick={() => setShowForm(false)}
            >
              Annulla
            </button>
          </div>
        </div>
      ) : (
        <button
          className="btn-secondary text-xs py-1 w-full mt-1 flex items-center justify-center gap-1"
          onClick={() => setShowForm(true)}
        >
          <Plus className="w-3 h-3" /> Aggiungi giorno straordinario
        </button>
      )}
    </div>
  )
}

function CollaboratorFormModal({ collaborator, onClose, onSave, loading }: {
  collaborator?: Collaborator
  onClose: () => void
  onSave: (data: Partial<Collaborator>) => void
  loading: boolean
}) {
  const [form, setForm] = useState({
    first_name: collaborator?.first_name ?? '',
    last_name: collaborator?.last_name ?? '',
    phone: collaborator?.phone ?? '',
    email: collaborator?.email ?? '',
    color: collaborator?.color ?? '#C8A96E',
    visible_online: collaborator?.visible_online ?? true,
    is_active: collaborator?.is_active ?? true,
  })

  return (
    <Sheet
      onClose={onClose}
      title={collaborator ? 'Modifica collaboratore' : 'Nuovo collaboratore'}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button type="submit" form="collab-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form
        id="collab-form"
        onSubmit={(e) => { e.preventDefault(); onSave(form) }}
        className="space-y-4"
      >
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Nome *</label>
            <input
              className="input" required autoCapitalize="words"
              value={form.first_name}
              onChange={e => setForm({ ...form, first_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Cognome *</label>
            <input
              className="input" required autoCapitalize="words"
              value={form.last_name}
              onChange={e => setForm({ ...form, last_name: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="label">Telefono</label>
          <input
            className="input" type="tel" inputMode="tel"
            value={form.phone}
            onChange={e => setForm({ ...form, phone: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Email</label>
          <input
            className="input" type="email" inputMode="email" autoCapitalize="none"
            value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Colore calendario</label>
          <div className="flex items-center gap-3">
            <input
              type="color"
              value={form.color}
              onChange={e => setForm({ ...form, color: e.target.value })}
              className="h-11 w-14 border border-border cursor-pointer bg-surface"
            />
            <span className="text-sm text-muted-foreground font-mono">{form.color}</span>
          </div>
        </div>

        <div className="space-y-2 pt-1">
          <Toggle
            label="Visibile online"
            description="Selezionabile dai clienti nel portale"
            checked={form.visible_online}
            onChange={v => setForm({ ...form, visible_online: v })}
          />
          <Toggle
            label="Attivo"
            checked={form.is_active}
            onChange={v => setForm({ ...form, is_active: v })}
          />
        </div>
      </form>
    </Sheet>
  )
}
