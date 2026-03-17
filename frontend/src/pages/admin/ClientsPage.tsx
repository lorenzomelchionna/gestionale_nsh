import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus, Search, User, Phone, Mail, Tag, ChevronRight } from 'lucide-react'
import { getClients, createClient, updateClient } from '@/services/api'
import type { Client } from '@/types'
import { X } from 'lucide-react'

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Clienti</h1>
        <button onClick={() => setShowCreate(true)} className="btn-primary flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Nuovo cliente
        </button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          className="input pl-9"
          placeholder="Cerca per nome, telefono, email..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
        />
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="text-center p-8 text-muted-foreground">Caricamento...</div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Nome</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Telefono</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Email</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Tag</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map(client => (
                <tr key={client.id} className="border-b border-border last:border-0 hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium">
                    {client.first_name} {client.last_name}
                    {client.account_id && <span className="ml-2 text-[10px] bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">online</span>}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{client.phone ?? '–'}</td>
                  <td className="px-4 py-3 text-muted-foreground">{client.email ?? '–'}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {client.tags.map(t => (
                        <span key={t} className="text-[10px] bg-primary/10 text-primary-dark px-2 py-0.5 rounded-full">{t}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/admin/clients/${client.id}`} className="text-muted-foreground hover:text-foreground">
                      <ChevronRight className="w-4 h-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {data && data.pages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t border-border">
              <p className="text-sm text-muted-foreground">{data.total} clienti</p>
              <div className="flex gap-1">
                {Array.from({ length: data.pages }, (_, i) => (
                  <button
                    key={i + 1}
                    onClick={() => setPage(i + 1)}
                    className={`w-8 h-8 text-sm rounded-md ${page === i + 1 ? 'bg-primary text-white' : 'hover:bg-muted'}`}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <ClientFormModal
          onClose={() => setShowCreate(false)}
          onSave={(data) => createMut.mutate(data)}
          loading={createMut.isPending}
        />
      )}
    </div>
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
    tags: client?.tags?.join(', ') ?? '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave({
      ...form,
      tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
      birth_date: form.birth_date || undefined,
      phone: form.phone || undefined,
      email: form.email || undefined,
    })
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h3 className="font-semibold">{client ? 'Modifica cliente' : 'Nuovo cliente'}</h3>
          <button onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-3">
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
            <input className="input" type="tel" value={form.phone} onChange={e => setForm({...form, phone: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Email</label>
            <input className="input" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Data di nascita</label>
            <input className="input" type="date" value={form.birth_date ?? ''} onChange={e => setForm({...form, birth_date: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Note</label>
            <textarea className="input" rows={2} value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} />
          </div>
          <div>
            <label className="label block mb-1">Tag (separati da virgola)</label>
            <input className="input" placeholder="VIP, nuovo cliente" value={form.tags} onChange={e => setForm({...form, tags: e.target.value})} />
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
