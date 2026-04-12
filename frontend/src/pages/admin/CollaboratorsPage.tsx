import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Edit, Trash2 } from 'lucide-react'
import {
  getCollaborators, createCollaborator, updateCollaborator,
  updateCollaboratorSchedule, updateCollaboratorServices, getServices,
  getAbsences, createAbsence, deleteAbsence,
} from '@/services/api'
import type { Collaborator, CollaboratorSchedule, Absence, AbsenceType } from '@/types'
import clsx from 'clsx'

const DAYS = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']

const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
  ferie:    'Ferie',
  permesso: 'Permesso',
  malattia: 'Malattia',
  altro:    'Altro',
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Collaboratori</h1>
        <button onClick={() => { setSelected(null); setShowForm(true) }} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Nuovo
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
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
  const [tab, setTab] = useState<'info' | 'schedule' | 'services' | 'vacations'>('info')
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

  const TAB_LABELS = { info: 'Info', schedule: 'Orari', services: 'Servizi', vacations: 'Ferie' }

  return (
    <div className="card overflow-hidden">
      <div className="p-4 flex items-center gap-3" style={{ borderLeft: `4px solid ${c.color}` }}>
        <div
          className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
          style={{ backgroundColor: c.color }}
        >
          {c.first_name[0]}{c.last_name[0]}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm">{c.first_name} {c.last_name}</p>
          <p className="text-xs text-muted-foreground truncate">{c.email ?? c.phone ?? '–'}</p>
        </div>
        <div className="flex items-center gap-1">
          {!c.is_active && <span className="text-xs bg-red-100 text-red-600 px-1.5 py-0.5 rounded">inattivo</span>}
          {c.visible_online && <span className="text-xs bg-blue-100 text-blue-600 px-1.5 py-0.5 rounded">online</span>}
          <button onClick={onEdit} className="text-muted-foreground hover:text-foreground p-1">
            <Edit className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        {(['info', 'schedule', 'services', 'vacations'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              'flex-1 py-1.5 text-xs font-medium transition-colors',
              tab === t ? 'text-primary border-b-2 border-primary' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="p-3">
        {tab === 'info' && (
          <div className="space-y-1 text-xs">
            <p><span className="text-muted-foreground">Tel:</span> {c.phone ?? '–'}</p>
            <p><span className="text-muted-foreground">Email:</span> {c.email ?? '–'}</p>
          </div>
        )}

        {tab === 'schedule' && (
          <div className="space-y-1.5">
            {DAYS.map((day, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={schedules[i].working}
                  onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], working: e.target.checked } }))}
                />
                <span className="w-7 font-medium">{day}</span>
                {schedules[i].working && (
                  <>
                    <input
                      type="time"
                      className="border border-border rounded px-1 py-0.5 text-xs"
                      value={schedules[i].start}
                      onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], start: e.target.value } }))}
                    />
                    <span>–</span>
                    <input
                      type="time"
                      className="border border-border rounded px-1 py-0.5 text-xs"
                      value={schedules[i].end}
                      onChange={e => setSchedules(s => ({ ...s, [i]: { ...s[i], end: e.target.value } }))}
                    />
                  </>
                )}
              </div>
            ))}
            <button onClick={saveSchedules} className="btn-primary text-xs py-1 mt-2 w-full">
              Salva orari
            </button>
          </div>
        )}

        {tab === 'services' && (
          <div className="space-y-1.5">
            {services.map(s => (
              <label key={s.id} className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={selectedServices.includes(s.id)}
                  onChange={e => setSelectedServices(prev =>
                    e.target.checked ? [...prev, s.id] : prev.filter(id => id !== s.id)
                  )}
                />
                {s.name}
              </label>
            ))}
            <button
              onClick={() => onUpdateServices(selectedServices)}
              className="btn-primary text-xs py-1 mt-2 w-full"
            >
              Salva servizi
            </button>
          </div>
        )}

        {tab === 'vacations' && (
          <VacationsTab collaboratorId={c.id} />
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
              className="text-muted-foreground hover:text-red-500 ml-2"
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
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">{collaborator ? 'Modifica collaboratore' : 'Nuovo collaboratore'}</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave(form) }} className="p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label block mb-1">Nome *</label>
              <input className="input" required value={form.first_name} onChange={e => setForm({...form, first_name: e.target.value})} />
            </div>
            <div>
              <label className="label block mb-1">Cognome *</label>
              <input className="input" required value={form.last_name} onChange={e => setForm({...form, last_name: e.target.value})} />
            </div>
          </div>
          <div>
            <label className="label block mb-1">Telefono</label>
            <input className="input" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Email</label>
            <input className="input" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Colore calendario</label>
            <div className="flex items-center gap-2">
              <input type="color" value={form.color} onChange={e => setForm({...form, color: e.target.value})} className="h-9 w-12 rounded border border-border cursor-pointer" />
              <span className="text-sm text-muted-foreground">{form.color}</span>
            </div>
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.visible_online} onChange={e => setForm({...form, visible_online: e.target.checked})} />
              Visibile online
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={form.is_active} onChange={e => setForm({...form, is_active: e.target.checked})} />
              Attivo
            </label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" onClick={onClose} className="btn-secondary text-sm">Annulla</button>
            <button type="submit" disabled={loading} className="btn-primary text-sm disabled:opacity-60">
              {loading ? 'Salvataggio...' : 'Salva'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
