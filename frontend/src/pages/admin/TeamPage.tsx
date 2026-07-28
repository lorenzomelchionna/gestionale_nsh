import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import {
  Plus, KeyRound, ShieldCheck, User as UserIcon, Users, AlertTriangle, Check,
} from 'lucide-react'
import {
  getTeam, createTeamMember, updateTeamMember, resetTeamPassword, changeOwnPassword,
  getCollaborators,
} from '@/services/api'
import type { TeamMember } from '@/types'
import { useAuthStore } from '@/store/authStore'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, EmptyState, SkeletonList } from '@/components/ui'
import { Toggle } from './ServicesPage'
import clsx from 'clsx'

const MIN_PASSWORD = 12

export default function TeamPage() {
  const qc = useQueryClient()
  const me = useAuthStore(s => s.user)
  const [showCreate, setShowCreate] = useState(false)
  const [resetting, setResetting] = useState<TeamMember | null>(null)
  const [showOwnPassword, setShowOwnPassword] = useState(false)

  const { data: team = [], isLoading } = useQuery({ queryKey: ['team'], queryFn: getTeam })
  const inv = () => qc.invalidateQueries({ queryKey: ['team'] })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<TeamMember> }) =>
      updateTeamMember(id, data),
    onSuccess: inv,
  })

  return (
    <div className="space-y-5">
      <PageHeader
        title="Team e accessi"
        subtitle={team.length ? `${team.length} account` : undefined}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo accesso
          </button>
        }
      />

      <button
        onClick={() => setShowOwnPassword(true)}
        className="card-interactive w-full p-4 flex items-center gap-3 text-left"
      >
        <div className="w-10 h-10 rounded-lg bg-primary/12 flex items-center justify-center shrink-0">
          <KeyRound className="w-[18px] h-[18px] text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">Cambia la mia password</p>
          <p className="text-[13px] text-muted-foreground truncate">{me?.email}</p>
        </div>
      </button>

      {isLoading ? (
        <SkeletonList rows={3} />
      ) : team.length === 0 ? (
        <div className="card">
          <EmptyState icon={Users} title="Nessun accesso configurato" />
        </div>
      ) : (
        <div className="card divide-y divide-border overflow-hidden">
          {team.map(m => (
            <MemberRow
              key={m.id}
              member={m}
              isMe={m.id === me?.id}
              busy={updateMut.isPending}
              onToggleActive={() =>
                updateMut.mutate({ id: m.id, data: { is_active: !m.is_active } })
              }
              onReset={() => setResetting(m)}
            />
          ))}
        </div>
      )}

      {updateMut.isError && (
        <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
          {errorText(updateMut.error)}
        </p>
      )}

      {showCreate && (
        <CreateMemberSheet onClose={() => setShowCreate(false)} onDone={inv} />
      )}
      {resetting && (
        <ResetPasswordSheet member={resetting} onClose={() => setResetting(null)} />
      )}
      {showOwnPassword && (
        <OwnPasswordSheet onClose={() => setShowOwnPassword(false)} />
      )}
    </div>
  )
}

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  // Pydantic validation errors arrive as a list of objects.
  if (Array.isArray(detail)) return 'Dati non validi: controlla i campi.'
  return 'Operazione non riuscita. Riprova.'
}

function MemberRow({ member: m, isMe, busy, onToggleActive, onReset }: {
  member: TeamMember
  isMe: boolean
  busy: boolean
  onToggleActive: () => void
  onReset: () => void
}) {
  return (
    <div className={clsx('p-4 flex items-start gap-3', !m.is_active && 'opacity-60')}>
      <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center shrink-0">
        {m.role === 'admin'
          ? <ShieldCheck className="w-[18px] h-[18px] text-primary" />
          : <UserIcon className="w-[18px] h-[18px] text-muted-foreground" />}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="font-medium text-foreground truncate">{m.email}</p>
          {isMe && (
            <span className="text-[10px] font-semibold bg-primary/12 text-primary px-1.5 py-0.5 rounded">
              tu
            </span>
          )}
          {!m.is_active && (
            <span className="text-[10px] font-semibold bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
              disattivato
            </span>
          )}
        </div>
        <p className="text-[13px] text-muted-foreground mt-0.5">
          {m.role === 'admin' ? 'Amministratore' : 'Collaboratore'}
          {m.collaborator_name && ` · ${m.collaborator_name}`}
        </p>
        <p className="text-xs text-muted-foreground mt-1">
          creato il {format(parseISO(m.created_at), 'dd/MM/yyyy')}
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 shrink-0">
        <button onClick={onReset} className="btn-outline btn-sm">
          <KeyRound className="w-4 h-4" /> Password
        </button>
        {/* Deactivating yourself, or the last admin, is refused by the API —
            hide it for your own row so the option never looks available. */}
        {!isMe && (
          <button
            onClick={onToggleActive}
            disabled={busy}
            className={clsx('btn-outline btn-sm', m.is_active && '!text-danger')}
          >
            {m.is_active ? 'Disattiva' : 'Riattiva'}
          </button>
        )}
      </div>
    </div>
  )
}

function CreateMemberSheet({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState({
    email: '', password: '', role: 'collaborator' as 'admin' | 'collaborator',
    collaborator_id: '' as string,
  })

  const { data: collabsData } = useQuery({
    queryKey: ['collaborators-active'],
    queryFn: () => getCollaborators({ active_only: true }),
  })
  const collaborators = collabsData?.items ?? []

  const mut = useMutation({
    mutationFn: () => createTeamMember({
      email: form.email,
      password: form.password,
      role: form.role,
      collaborator_id: form.collaborator_id ? Number(form.collaborator_id) : null,
    }),
    onSuccess: () => { onDone(); onClose() },
  })

  const tooShort = form.password.length > 0 && form.password.length < MIN_PASSWORD

  return (
    <Sheet
      onClose={onClose}
      title="Nuovo accesso"
      description="Crea un login per un membro dello staff"
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
          <button
            type="submit"
            form="team-form"
            disabled={mut.isPending || tooShort}
            className="btn-primary btn-sm"
          >
            {mut.isPending ? 'Creazione...' : 'Crea accesso'}
          </button>
        </>
      }
    >
      <form
        id="team-form"
        onSubmit={e => { e.preventDefault(); mut.mutate() }}
        className="space-y-4"
      >
        <div>
          <label className="label">Email *</label>
          <input
            className="input" type="email" inputMode="email" autoCapitalize="none" required
            value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
          />
        </div>

        <div>
          <label className="label">Password *</label>
          <input
            className="input" type="text" required minLength={MIN_PASSWORD}
            value={form.password}
            onChange={e => setForm({ ...form, password: e.target.value })}
          />
          <p className={clsx('text-xs mt-1.5', tooShort ? 'text-danger' : 'text-muted-foreground')}>
            Almeno {MIN_PASSWORD} caratteri. Comunicala di persona: chi la riceve
            potrà cambiarla da solo dopo il primo accesso.
          </p>
        </div>

        <div>
          <label className="label">Profilo collaboratore</label>
          <select
            className="input"
            value={form.collaborator_id}
            onChange={e => setForm({ ...form, collaborator_id: e.target.value })}
          >
            <option value="">Nessun collegamento</option>
            {collaborators.map(c => (
              <option key={c.id} value={c.id}>{c.first_name} {c.last_name}</option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground mt-1.5">
            Collega l'accesso alla scheda in agenda della persona.
          </p>
        </div>

        <Toggle
          label="Amministratore"
          description="Accesso completo: incassi, spese, dashboard e impostazioni"
          checked={form.role === 'admin'}
          onChange={v => setForm({ ...form, role: v ? 'admin' : 'collaborator' })}
        />

        {mut.isError && (
          <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
            {errorText(mut.error)}
          </p>
        )}
      </form>
    </Sheet>
  )
}

function ResetPasswordSheet({ member, onClose }: { member: TeamMember; onClose: () => void }) {
  const [password, setPassword] = useState('')
  const [done, setDone] = useState(false)

  const mut = useMutation({
    mutationFn: () => resetTeamPassword(member.id, password),
    onSuccess: () => setDone(true),
  })

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD

  return (
    <Sheet
      onClose={onClose}
      title="Reimposta password"
      description={member.email}
      size="sm"
      footer={
        done ? (
          <button onClick={onClose} className="btn-primary btn-sm">Chiudi</button>
        ) : (
          <>
            <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
            <button
              type="submit" form="reset-form"
              disabled={mut.isPending || tooShort || !password}
              className="btn-primary btn-sm"
            >
              {mut.isPending ? 'Salvataggio...' : 'Reimposta'}
            </button>
          </>
        )
      }
    >
      {done ? (
        <div className="flex items-start gap-2.5 text-[13px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded-lg px-3 py-2.5">
          <Check className="w-4 h-4 shrink-0 mt-0.5" />
          <p>Password aggiornata. Comunicala di persona: potrà cambiarla dopo l'accesso.</p>
        </div>
      ) : (
        <form
          id="reset-form"
          onSubmit={e => { e.preventDefault(); mut.mutate() }}
          className="space-y-4"
        >
          <div>
            <label className="label">Nuova password *</label>
            <input
              className="input" type="text" required minLength={MIN_PASSWORD}
              value={password}
              onChange={e => setPassword(e.target.value)}
              autoFocus
            />
            <p className={clsx('text-xs mt-1.5', tooShort ? 'text-danger' : 'text-muted-foreground')}>
              Almeno {MIN_PASSWORD} caratteri.
            </p>
          </div>
          {mut.isError && (
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
              {errorText(mut.error)}
            </p>
          )}
        </form>
      )}
    </Sheet>
  )
}

function OwnPasswordSheet({ onClose }: { onClose: () => void }) {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [done, setDone] = useState(false)

  const mut = useMutation({
    mutationFn: () => changeOwnPassword(form.current, form.next),
    onSuccess: () => setDone(true),
  })

  const tooShort = form.next.length > 0 && form.next.length < MIN_PASSWORD
  const mismatch = form.confirm.length > 0 && form.next !== form.confirm
  const canSubmit = form.current && form.next.length >= MIN_PASSWORD && form.next === form.confirm

  return (
    <Sheet
      onClose={onClose}
      title="Cambia la mia password"
      size="sm"
      footer={
        done ? (
          <button onClick={onClose} className="btn-primary btn-sm">Chiudi</button>
        ) : (
          <>
            <button type="button" onClick={onClose} className="btn-secondary btn-sm">Annulla</button>
            <button
              type="submit" form="own-password-form"
              disabled={mut.isPending || !canSubmit}
              className="btn-primary btn-sm"
            >
              {mut.isPending ? 'Salvataggio...' : 'Cambia password'}
            </button>
          </>
        )
      }
    >
      {done ? (
        <div className="flex items-start gap-2.5 text-[13px] bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded-lg px-3 py-2.5">
          <Check className="w-4 h-4 shrink-0 mt-0.5" />
          <p>Password aggiornata. Resti collegato su questo dispositivo.</p>
        </div>
      ) : (
        <form
          id="own-password-form"
          onSubmit={e => { e.preventDefault(); mut.mutate() }}
          className="space-y-4"
        >
          <div>
            <label className="label">Password attuale *</label>
            <input
              className="input" type="password" autoComplete="current-password" required
              value={form.current}
              onChange={e => setForm({ ...form, current: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Nuova password *</label>
            <input
              className="input" type="password" autoComplete="new-password"
              required minLength={MIN_PASSWORD}
              value={form.next}
              onChange={e => setForm({ ...form, next: e.target.value })}
            />
            <p className={clsx('text-xs mt-1.5', tooShort ? 'text-danger' : 'text-muted-foreground')}>
              Almeno {MIN_PASSWORD} caratteri.
            </p>
          </div>
          <div>
            <label className="label">Ripeti la nuova password *</label>
            <input
              className="input" type="password" autoComplete="new-password" required
              value={form.confirm}
              onChange={e => setForm({ ...form, confirm: e.target.value })}
            />
            {mismatch && (
              <p className="text-xs text-danger mt-1.5">Le due password non coincidono.</p>
            )}
          </div>

          {mut.isError && (
            <p role="alert" className="flex items-start gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5 rounded-lg">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              {errorText(mut.error)}
            </p>
          )}
        </form>
      )}
    </Sheet>
  )
}
