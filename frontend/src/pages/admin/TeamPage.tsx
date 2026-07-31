import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { Plus, KeyRound, Users, AlertTriangle, Check } from 'lucide-react'
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

  // The two renderings of a row below take the same handlers; building them
  // once keeps the phone list and the table from drifting apart.
  const rowProps = (m: TeamMember) => ({
    member: m,
    isMe: m.id === me?.id,
    busy: updateMut.isPending,
    onToggleActive: () =>
      updateMut.mutate({ id: m.id, data: { is_active: !m.is_active } }),
    onReset: () => setResetting(m),
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
        className="card-interactive w-full px-4 py-3.5 flex items-center gap-3.5 text-left"
      >
        <span className="w-9 h-9 border border-border flex items-center justify-center shrink-0">
          <KeyRound className="w-4 h-4 text-primary" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block font-heading text-[15px] tracking-[0.04em] text-foreground">
            Cambia la mia password
          </span>
          <span className="block text-[13px] text-muted-foreground truncate">{me?.email}</span>
        </span>
      </button>

      {isLoading ? (
        <SkeletonList rows={3} />
      ) : team.length === 0 ? (
        <div className="panel">
          <EmptyState icon={Users} title="Nessun accesso configurato" />
        </div>
      ) : (
        <div className="panel">
          {/* Phones keep the row treatment: five columns plus two buttons
              would only force the page sideways. */}
          <div className="sm:hidden divide-y divide-rule-soft">
            {team.map(m => <MemberCard key={m.id} {...rowProps(m)} />)}
          </div>

          <div className="hidden sm:block table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Account</th>
                  <th>Ruolo</th>
                  <th>Creato</th>
                  <th>Stato</th>
                  <th className="text-right"><span className="sr-only">Azioni</span></th>
                </tr>
              </thead>
              {/* The panel edge closes the last line, so the row rule would double it. */}
              <tbody className="[&_tr:last-child_td]:border-b-0">
                {team.map(m => <MemberLine key={m.id} {...rowProps(m)} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {updateMut.isError && <ErrorNote error={updateMut.error} />}

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

interface RowProps {
  member: TeamMember
  isMe: boolean
  busy: boolean
  onToggleActive: () => void
  onReset: () => void
}

const roleLabel = (m: TeamMember) =>
  m.role === 'admin' ? 'Amministratore' : 'Collaboratore'

/** The two actions on a row, shared by the phone card and the table line.
    Deactivating yourself, or the last admin, is refused by the API — the row
    for your own account hides it so the option never looks available. */
function RowActions({ isMe, busy, onToggleActive, onReset, member: m }: RowProps) {
  return (
    <>
      <button onClick={onReset} className="btn-secondary btn-sm">
        <KeyRound className="w-3.5 h-3.5" /> Password
      </button>
      {!isMe && (
        <button
          onClick={onToggleActive}
          disabled={busy}
          className={m.is_active ? 'btn-danger-outline btn-sm' : 'btn-secondary btn-sm'}
        >
          {m.is_active ? 'Disattiva' : 'Riattiva'}
        </button>
      )}
    </>
  )
}

/** Phone rendering: the same five facts, stacked instead of ruled across. */
function MemberCard(props: RowProps) {
  const { member: m, isMe } = props
  return (
    <div className={clsx('px-4 py-3.5 flex flex-col gap-2.5', !m.is_active && 'opacity-60')}>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-heading text-[15px] tracking-[0.03em] text-foreground truncate">
          {m.email}
        </span>
        {isMe && <span className="status-badge status-confirmed">tu</span>}
        {!m.is_active && <span className="status-badge status-cancelled">disattivato</span>}
      </div>
      <div className="flex items-baseline gap-2 text-[13px] text-muted-foreground">
        <span>{roleLabel(m)}</span>
        {m.collaborator_name && <span className="text-ink-3">· {m.collaborator_name}</span>}
        <span className="ml-auto text-xs text-ink-3 tabular-nums shrink-0">
          {format(parseISO(m.created_at), 'dd/MM/yyyy')}
        </span>
      </div>
      <div className="flex gap-2">
        <RowActions {...props} />
      </div>
    </div>
  )
}

/** Table rendering: account, role, date opened, state, actions. */
function MemberLine(props: RowProps) {
  const { member: m, isMe } = props
  return (
    <tr className={clsx(!m.is_active && 'opacity-60')}>
      <td>
        <span className="flex items-baseline gap-2">
          <span className="font-heading text-[15px] tracking-[0.03em] text-foreground">
            {m.email}
          </span>
          {isMe && <span className="status-badge status-confirmed">tu</span>}
        </span>
      </td>
      <td className="text-muted-foreground">
        {roleLabel(m)}
        {m.collaborator_name && <span className="text-ink-3"> · {m.collaborator_name}</span>}
      </td>
      <td className="text-ink-3 tabular-nums">
        {format(parseISO(m.created_at), 'dd/MM/yyyy')}
      </td>
      <td>
        <span className={m.is_active ? 'status-badge status-confirmed' : 'status-badge status-cancelled'}>
          {m.is_active ? 'attivo' : 'disattivato'}
        </span>
      </td>
      <td>
        <span className="flex justify-end gap-2">
          <RowActions {...props} />
        </span>
      </td>
    </tr>
  )
}

/** A failed change, said on the spot rather than in a toast that scrolls away. */
function ErrorNote({ error }: { error: unknown }) {
  return (
    <p
      role="alert"
      className="flex items-start gap-2 text-[13px] text-danger border-l-2 border-danger bg-danger/[0.08] px-3 py-2.5"
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      {errorText(error)}
    </p>
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
          <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
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
        <div className="flex items-start gap-2.5 text-[13px] bg-primary/10 text-primary-dark dark:text-primary px-3 py-2.5">
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
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
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
        <div className="flex items-start gap-2.5 text-[13px] bg-primary/10 text-primary-dark dark:text-primary px-3 py-2.5">
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
            <p role="alert" className="flex items-start gap-2 text-[13px] text-danger bg-danger/10 px-3 py-2.5">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              {errorText(mut.error)}
            </p>
          )}
        </form>
      )}
    </Sheet>
  )
}
