import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { KeyRound, Merge, UserPlus } from 'lucide-react'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { getClient, getClientAppointments } from '@/services/api'
import type { Appointment } from '@/types'
import { SkeletonList } from '@/components/ui'
import MergeClientsSheet from '@/components/admin/MergeClientsSheet'
import ClientPasswordSheet from '@/components/admin/ClientPasswordSheet'
import ClientPortalAccountSheet from '@/components/admin/ClientPortalAccountSheet'
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
  const [showMerge, setShowMerge] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showNewAccount, setShowNewAccount] = useState(false)

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
      {/* The record is filed under the archive it came from, so the way back
          is part of the title rather than a button beside it. */}
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-2 border-b border-rule pb-3.5">
        <Link
          to="/admin/clients"
          className="font-heading text-[13px] uppercase tracking-[0.1em] text-primary-dark hover:underline"
        >
          Clienti
        </Link>
        <span className="text-ink-3">/</span>
        <h1 className="text-title text-foreground truncate">
          {client.first_name} {client.last_name}
        </h1>

        {/* Sta qui e non fra le azioni principali: unire due schede è una
            manutenzione che capita di rado, non un gesto quotidiano — e da
            qui è chiaro *quale* scheda resta, cioè quella che si sta
            guardando. */}
        <div className="flex items-center gap-2 ml-auto">
          {/* Solo per chi ha un accesso online: su una cliente da banco non
              c'è nessuna password da reimpostare, e il pulsante prometterebbe
              qualcosa che l'API rifiuta. */}
          {client.account_id ? (
            <button
              type="button"
              onClick={() => setShowPassword(true)}
              className="btn-secondary btn-sm"
              title="Reimposta la password del portale prenotazioni"
            >
              <KeyRound className="w-4 h-4" />
              Password portale
            </button>
          ) : (
            /* L'altra metà dello stesso interruttore: chi non ha un accesso
               lo può ricevere qui. I due pulsanti non compaiono mai insieme
               perché sono lo stesso posto in due momenti diversi — prima si
               crea l'accesso, dopo si rigenera la password. */
            <button
              type="button"
              onClick={() => setShowNewAccount(true)}
              className="btn-secondary btn-sm"
              title="Crea l'accesso al portale prenotazioni per questa cliente"
            >
              <UserPlus className="w-4 h-4" />
              Crea accesso portale
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowMerge(true)}
            className="btn-secondary btn-sm"
            title="Unisci una scheda duplicata in questa"
          >
            <Merge className="w-4 h-4" />
            Unisci duplicato
          </button>
        </div>
      </div>

      {showMerge && (
        <MergeClientsSheet target={client} onClose={() => setShowMerge(false)} />
      )}

      {showPassword && (
        <ClientPasswordSheet client={client} onClose={() => setShowPassword(false)} />
      )}

      {showNewAccount && (
        <ClientPortalAccountSheet
          client={client}
          onClose={() => setShowNewAccount(false)}
        />
      )}

      <div className="grid gap-4 lg:grid-cols-[22rem_1fr] items-start">
        <div className="flex flex-col gap-4">
          {/* The two numbers the page is opened for, ruled apart on one sheet. */}
          <div className="panel grid grid-cols-2">
            <div className="p-4 border-r border-rule-soft">
              <p className="font-heading text-[30px] leading-none text-foreground tabular-nums">
                {completedAppts.length}
              </p>
              <p className="kicker mt-2">Visite</p>
            </div>
            <div className="p-4">
              <p className="font-heading text-[30px] leading-none text-primary-dark tabular-nums">
                €{totalSpent.toFixed(0)}
              </p>
              <p className="kicker mt-2">Spesa totale</p>
            </div>
          </div>

          <div className="panel">
            <div className="band px-4 py-3">
              <span className="kicker">Anagrafica</span>
            </div>
            {/* Tap-to-call and tap-to-mail survive the redesign: on a phone
                this panel is how the salon actually reaches someone. */}
            <ContactRow
              label="Telefono"
              value={client.phone}
              href={client.phone ? `tel:${client.phone}` : undefined}
              numeric
            />
            <ContactRow
              label="Email"
              value={client.email}
              href={client.email ? `mailto:${client.email}` : undefined}
            />
            <ContactRow
              label="Nascita"
              value={
                client.birth_date
                  ? format(parseISO(client.birth_date), 'd MMMM yyyy', { locale: it })
                  : null
              }
              numeric
            />
            {client.notes && (
              <div className="px-4 py-3.5">
                <span className="kicker">Nota</span>
                <p className="mt-2 text-sm leading-relaxed italic text-ink-2">{client.notes}</p>
              </div>
            )}
          </div>
        </div>

        <section className="panel">
          <div className="band px-4 py-3">
            <span className="kicker">Storico appuntamenti</span>
          </div>

          {!appointments?.length ? (
            <p className="note text-center py-10 px-6">Nessun appuntamento</p>
          ) : (
            <>
              {/* Phones keep the row treatment: five columns would only force
                  the page sideways. */}
              <div className="sm:hidden divide-y divide-rule-soft">
                {appointments.map(a => (
                  <VisitRow key={a.id} appointment={a} />
                ))}
              </div>

              <div className="hidden sm:block table-scroll">
                <table className="ledger">
                  <thead>
                    <tr>
                      <th>Data</th>
                      <th>Servizio</th>
                      <th>Operatore</th>
                      <th className="text-right">Importo</th>
                      <th className="text-right">Stato</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appointments.map(a => (
                      <tr key={a.id}>
                        <td className="tabular-nums whitespace-nowrap">
                          {format(parseISO(a.start_time), 'dd/MM/yyyy')}
                          <span className="text-ink-3">
                            {' · '}{format(parseISO(a.start_time), 'HH:mm')}
                          </span>
                        </td>
                        <td className="text-muted-foreground">
                          {a.service_names?.length ? a.service_names.join(' + ') : '–'}
                        </td>
                        <td className="text-muted-foreground">
                          {a.collaborator_name ?? '–'}
                          {/* La nota sotto l'operatore e non in una colonna
                              sua: è la riga che si va a cercare — «che colore
                              le ho fatto a marzo?» — e una colonna in più
                              spingerebbe la tabella fuori pagina. */}
                          {a.visit_notes && (
                            <span className="block text-[13px] italic text-ink-2 mt-1 whitespace-pre-line">
                              {a.visit_notes}
                            </span>
                          )}
                        </td>
                        <td className="num">
                          <span className="amount">€{(a.total_price ?? 0).toFixed(2)}</span>
                        </td>
                        <td className="text-right">
                          <span className={clsx('status-badge', `status-${a.status}`)}>
                            {STATUS_LABELS[a.status] ?? a.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  {/* Only served visits are summed — the total has to match the
                      spend figure above, which counts the same thing. */}
                  <tfoot>
                    <tr>
                      <td className="font-heading uppercase tracking-[0.08em] text-foreground">
                        Totale
                      </td>
                      <td /><td />
                      <td className="num">
                        <span className="font-heading text-[17px] tabular-nums text-foreground">
                          €{totalSpent.toFixed(2)}
                        </span>
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}

/** One visit, stacked for a phone. */
function VisitRow({ appointment: a }: { appointment: Appointment }) {
  return (
    <div className="px-4 py-3.5 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <p className="font-heading text-[15px] tracking-[0.03em] text-foreground tabular-nums">
          {format(parseISO(a.start_time), 'dd/MM/yyyy')}
          <span className="text-ink-3">
            {' · '}{format(parseISO(a.start_time), 'HH:mm')}
          </span>
        </p>
        <p className="text-[13px] text-muted-foreground truncate mt-1">
          {a.service_names?.length ? a.service_names.join(' + ') : '–'}
          {a.collaborator_name && <span className="text-ink-3"> · {a.collaborator_name}</span>}
        </p>
        {a.visit_notes && (
          <p className="text-[13px] italic text-ink-2 mt-1 whitespace-pre-line">
            {a.visit_notes}
          </p>
        )}
      </div>
      <div className="text-right shrink-0 flex flex-col items-end gap-1.5">
        <span className="amount">€{(a.total_price ?? 0).toFixed(2)}</span>
        <span className={clsx('status-badge', `status-${a.status}`)}>
          {STATUS_LABELS[a.status] ?? a.status}
        </span>
      </div>
    </div>
  )
}

/** A ruled key/value line; contacts stay tappable where the device can act. */
function ContactRow({ label, value, href, numeric = false }: {
  label: string
  value?: string | null
  href?: string
  numeric?: boolean
}) {
  const content = (
    <>
      <span className="text-[13px] text-ink-3 shrink-0">{label}</span>
      <span
        className={clsx(
          'text-sm text-right truncate',
          numeric && 'tabular-nums',
          value ? 'text-foreground' : 'text-ink-3'
        )}
      >
        {value ?? '–'}
      </span>
    </>
  )
  const className =
    'flex items-baseline justify-between gap-3.5 px-4 py-3 border-b border-rule-soft w-full'
  return href
    ? <a href={href} className={clsx(className, 'hover:bg-foreground/[0.05] transition-colors')}>{content}</a>
    : <div className={className}>{content}</div>
}
