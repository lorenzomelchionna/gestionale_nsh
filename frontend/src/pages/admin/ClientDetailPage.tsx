import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { ArrowLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { getClient, getClientAppointments } from '@/services/api'
import clsx from 'clsx'

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const clientId = Number(id)

  const { data: client } = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => getClient(clientId),
  })

  const { data: appointments } = useQuery({
    queryKey: ['client-appointments', clientId],
    queryFn: () => getClientAppointments(clientId),
  })

  if (!client) return <div className="p-8 text-muted-foreground">Caricamento...</div>

  const completedAppts = appointments?.filter(a => a.status === 'completed') ?? []
  const totalSpent = completedAppts.reduce((sum, a) => sum + (a.total_price ?? 0), 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/admin/clients" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">{client.first_name} {client.last_name}</h1>
        {client.account_id && (
          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">Account online</span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Info card */}
        <div className="card p-4 space-y-2 md:col-span-2">
          <h3 className="font-semibold text-sm mb-3">Informazioni</h3>
          <Row label="Telefono" value={client.phone ?? '–'} />
          <Row label="Email" value={client.email ?? '–'} />
          <Row label="Data nascita" value={client.birth_date ? format(parseISO(client.birth_date), 'dd MMMM yyyy', { locale: it }) : '–'} />
          {client.notes && (
            <div>
              <span className="text-xs text-muted-foreground">Note:</span>
              <p className="text-sm mt-0.5 p-2 bg-muted rounded-md">{client.notes}</p>
            </div>
          )}
        </div>

        {/* Stats */}
        <div className="space-y-3">
          <div className="card p-4 text-center">
            <p className="text-3xl font-bold text-primary">{completedAppts.length}</p>
            <p className="text-sm text-muted-foreground">visite totali</p>
          </div>
          <div className="card p-4 text-center">
            <p className="text-3xl font-bold text-primary">€{totalSpent.toFixed(0)}</p>
            <p className="text-sm text-muted-foreground">spesa totale</p>
          </div>
        </div>
      </div>

      {/* Appointments history */}
      <div>
        <h3 className="font-semibold mb-3">Storico appuntamenti</h3>
        <div className="card overflow-hidden">
          {!appointments?.length ? (
            <p className="p-6 text-center text-muted-foreground text-sm">Nessun appuntamento</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Data</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Collaboratore</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Stato</th>
                  <th className="text-left px-4 py-2 font-medium text-muted-foreground text-xs">Totale</th>
                </tr>
              </thead>
              <tbody>
                {appointments.map(a => (
                  <tr key={a.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5">
                      {format(parseISO(a.start_time), 'dd/MM/yyyy HH:mm')}
                    </td>
                    <td className="px-4 py-2.5">{a.collaborator_name}</td>
                    <td className="px-4 py-2.5">
                      <span className={clsx('status-badge', `status-${a.status}`)}>{a.status}</span>
                    </td>
                    <td className="px-4 py-2.5 font-medium">€{(a.total_price ?? 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-muted-foreground w-28 flex-shrink-0">{label}:</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
