import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { ArrowLeft, Phone, Mail, CalendarDays } from 'lucide-react'
import { getClient, getClientAppointments } from '@/services/api'
import { SkeletonList } from '@/components/ui'
import clsx from 'clsx'

const STATUS_LABELS: Record<string, string> = {
  pending: 'In attesa',
  confirmed: 'Confermato',
  rejected: 'Rifiutato',
  rescheduled: 'Riprogrammato',
  completed: 'Completato',
  cancelled: 'Annullato',
}

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>()
  const clientId = Number(id)

  const { data: client, isLoading } = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => getClient(clientId),
  })

  const { data: appointments } = useQuery({
    queryKey: ['client-appointments', clientId],
    queryFn: () => getClientAppointments(clientId),
  })

  if (isLoading || !client) return <SkeletonList rows={3} />

  const completedAppts = appointments?.filter(a => a.status === 'completed') ?? []
  const totalSpent = completedAppts.reduce((sum, a) => sum + (a.total_price ?? 0), 0)

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Link to="/admin/clients" className="btn-icon -ml-2" aria-label="Torna ai clienti">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <div className="min-w-0">
          <h1 className="text-title font-bold truncate">
            {client.first_name} {client.last_name}
          </h1>
          {client.account_id && (
            <span className="text-[10px] font-semibold bg-info/12 text-info px-1.5 py-0.5 rounded">
              account online
            </span>
          )}
        </div>
      </div>

      {/* Stats first: on a phone these are the numbers you actually open the
          page for, so they sit above the contact details. */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-primary tabular-nums">{completedAppts.length}</p>
          <p className="text-[13px] text-muted-foreground mt-0.5">visite totali</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-primary tabular-nums">€{totalSpent.toFixed(0)}</p>
          <p className="text-[13px] text-muted-foreground mt-0.5">spesa totale</p>
        </div>
      </div>

      <div className="card divide-y divide-border">
        <ContactRow
          icon={Phone}
          value={client.phone}
          href={client.phone ? `tel:${client.phone}` : undefined}
        />
        <ContactRow
          icon={Mail}
          value={client.email}
          href={client.email ? `mailto:${client.email}` : undefined}
        />
        <ContactRow
          icon={CalendarDays}
          value={client.birth_date ? format(parseISO(client.birth_date), 'd MMMM yyyy', { locale: it }) : null}
        />
        {client.notes && (
          <div className="p-4">
            <p className="text-xs text-muted-foreground mb-1">Note</p>
            <p className="text-sm">{client.notes}</p>
          </div>
        )}
      </div>

      <section className="space-y-2">
        <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-1">
          Storico appuntamenti
        </h2>
        {!appointments?.length ? (
          <div className="card p-6 text-center text-muted-foreground text-sm">
            Nessun appuntamento
          </div>
        ) : (
          <div className="card divide-y divide-border overflow-hidden">
            {appointments.map(a => (
              <div key={a.id} className="p-4 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-foreground tabular-nums">
                    {format(parseISO(a.start_time), 'dd/MM/yyyy')}
                    <span className="text-muted-foreground font-normal">
                      {' · '}{format(parseISO(a.start_time), 'HH:mm')}
                    </span>
                  </p>
                  <p className="text-[13px] text-muted-foreground truncate mt-0.5">
                    {a.collaborator_name}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-medium tabular-nums">€{(a.total_price ?? 0).toFixed(2)}</p>
                  <span className={clsx('status-badge mt-1', `status-${a.status}`)}>
                    {STATUS_LABELS[a.status] ?? a.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

/** Contact rows are tap-to-call / tap-to-mail on a phone. */
function ContactRow({ icon: Icon, value, href }: {
  icon: React.ComponentType<{ className?: string }>
  value?: string | null
  href?: string
}) {
  const content = (
    <>
      <Icon className="w-4 h-4 text-muted-foreground shrink-0" />
      <span className={clsx('truncate', value ? 'text-foreground' : 'text-muted-foreground')}>
        {value ?? '–'}
      </span>
    </>
  )
  const className = 'flex items-center gap-3 p-4 text-sm w-full'
  return href
    ? <a href={href} className={clsx(className, 'hover:bg-muted/40 transition-colors')}>{content}</a>
    : <div className={className}>{content}</div>
}
