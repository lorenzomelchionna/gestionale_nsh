import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, ChevronRight, Users, Phone, Mail } from 'lucide-react'
import { getClients, createClient } from '@/services/api'
import type { Client } from '@/types'
import Sheet from '@/components/ui/Sheet'
import { PageHeader, SearchInput, EmptyState, SkeletonList, Pagination } from '@/components/ui'

export default function ClientsPage() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [showCreate, setShowCreate] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['clients', page, search],
    queryFn: () => getClients({ page, search }),
  })

  const createMut = useMutation({
    mutationFn: createClient,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['clients'] }); setShowCreate(false) },
  })

  const clients = data?.items ?? []

  return (
    <div className="space-y-5">
      <PageHeader
        title="Clienti"
        subtitle={data ? `${data.total} in archivio` : undefined}
        action={
          <button onClick={() => setShowCreate(true)} className="btn-primary">
            <Plus className="w-4 h-4" /> Nuovo cliente
          </button>
        }
      />

      <SearchInput
        value={search}
        onChange={v => { setSearch(v); setPage(1) }}
        placeholder="Cerca per nome, telefono, email..."
      />

      {isLoading ? (
        <SkeletonList rows={5} />
      ) : clients.length === 0 ? (
        <div className="card">
          <EmptyState
            icon={Users}
            title={search ? 'Nessun risultato' : 'Nessun cliente'}
            description={
              search
                ? 'Prova con un altro nome, numero o email.'
                : 'Aggiungi il primo cliente per iniziare.'
            }
            action={
              !search && (
                <button onClick={() => setShowCreate(true)} className="btn-primary">
                  <Plus className="w-4 h-4" /> Nuovo cliente
                </button>
              )
            }
          />
        </div>
      ) : (
        <>
          {/* Phones: tappable cards. A 3-column table forces horizontal
              scrolling on a 375px screen, so the row becomes a card instead. */}
          <div className="space-y-2 sm:hidden">
            {clients.map(client => (
              <Link
                key={client.id}
                to={`/admin/clients/${client.id}`}
                className="card-interactive flex items-center gap-3 p-3.5"
              >
                <Avatar client={client} />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-foreground truncate flex items-center gap-1.5">
                    {client.first_name} {client.last_name}
                    {client.account_id && <OnlineTag />}
                  </p>
                  <div className="flex items-center gap-3 mt-0.5 text-[13px] text-muted-foreground">
                    {client.phone && (
                      <span className="flex items-center gap-1 truncate">
                        <Phone className="w-3 h-3 shrink-0" /> {client.phone}
                      </span>
                    )}
                    {!client.phone && client.email && (
                      <span className="flex items-center gap-1 truncate">
                        <Mail className="w-3 h-3 shrink-0" /> {client.email}
                      </span>
                    )}
                    {!client.phone && !client.email && <span>Nessun contatto</span>}
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground shrink-0" />
              </Link>
            ))}
            {data && (
              <div className="card">
                <Pagination
                  page={page}
                  pages={data.pages}
                  total={data.total}
                  unit="clienti"
                  onChange={setPage}
                />
              </div>
            )}
          </div>

          {/* Tablet and up: the table reads better with the extra width. */}
          <div className="card overflow-hidden hidden sm:block">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nome</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Telefono</th>
                  <th className="text-left px-4 py-3 font-medium text-muted-foreground">Email</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody>
                {clients.map(client => (
                  <tr
                    key={client.id}
                    className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">
                      <span className="flex items-center gap-2">
                        {client.first_name} {client.last_name}
                        {client.account_id && <OnlineTag />}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{client.phone ?? '–'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{client.email ?? '–'}</td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/admin/clients/${client.id}`}
                        className="text-muted-foreground hover:text-foreground inline-flex"
                        aria-label={`Apri scheda di ${client.first_name}`}
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {data && (
              <Pagination
                page={page}
                pages={data.pages}
                total={data.total}
                unit="clienti"
                onChange={setPage}
              />
            )}
          </div>
        </>
      )}

      {showCreate && (
        <ClientFormModal
          onClose={() => setShowCreate(false)}
          onSave={(payload) => createMut.mutate(payload)}
          loading={createMut.isPending}
        />
      )}
    </div>
  )
}

function Avatar({ client }: { client: Client }) {
  return (
    <div className="w-10 h-10 rounded-full bg-primary/12 flex items-center justify-center shrink-0">
      <span className="text-primary text-[13px] font-semibold">
        {client.first_name?.[0]?.toUpperCase()}
        {client.last_name?.[0]?.toUpperCase()}
      </span>
    </div>
  )
}

function OnlineTag() {
  return (
    <span className="text-[10px] font-semibold bg-info/12 text-info px-1.5 py-0.5 rounded shrink-0">
      online
    </span>
  )
}

function ClientFormModal({ client, onClose, onSave, loading }: {
  client?: Client
  onClose: () => void
  onSave: (data: Partial<Client>) => void
  loading: boolean
}) {
  const [form, setForm] = useState({
    first_name: client?.first_name ?? '',
    last_name: client?.last_name ?? '',
    phone: client?.phone ?? '',
    email: client?.email ?? '',
    birth_date: client?.birth_date ?? '',
    notes: client?.notes ?? '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      ...form,
      birth_date: form.birth_date || undefined,
      phone: form.phone || undefined,
      email: form.email || undefined,
    })
  }

  return (
    <Sheet
      onClose={onClose}
      title={client ? 'Modifica cliente' : 'Nuovo cliente'}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">
            Annulla
          </button>
          <button type="submit" form="client-form" disabled={loading} className="btn-primary btn-sm">
            {loading ? 'Salvataggio...' : 'Salva'}
          </button>
        </>
      }
    >
      <form id="client-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Nome *</label>
            <input
              className="input"
              required
              autoCapitalize="words"
              value={form.first_name}
              onChange={e => setForm({ ...form, first_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Cognome *</label>
            <input
              className="input"
              required
              autoCapitalize="words"
              value={form.last_name}
              onChange={e => setForm({ ...form, last_name: e.target.value })}
            />
          </div>
        </div>
        <div>
          <label className="label">Telefono</label>
          <input
            className="input"
            type="tel"
            inputMode="tel"
            placeholder="+39 333 1234567"
            value={form.phone}
            onChange={e => setForm({ ...form, phone: e.target.value })}
          />
          <p className="text-xs text-muted-foreground mt-1.5">
            Con prefisso internazionale, per le notifiche WhatsApp.
          </p>
        </div>
        <div>
          <label className="label">Email</label>
          <input
            className="input"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            value={form.email}
            onChange={e => setForm({ ...form, email: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Data di nascita</label>
          <input
            className="input"
            type="date"
            value={form.birth_date ?? ''}
            onChange={e => setForm({ ...form, birth_date: e.target.value })}
          />
        </div>
        <div>
          <label className="label">Note</label>
          <textarea
            className="input"
            rows={3}
            value={form.notes}
            onChange={e => setForm({ ...form, notes: e.target.value })}
          />
        </div>
      </form>
    </Sheet>
  )
}
