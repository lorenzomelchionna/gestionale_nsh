import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Copy, TriangleAlert } from 'lucide-react'
import { createClientPortalAccount } from '@/services/api'
import type { Client, PortalAccountCreated } from '@/types'
import Sheet from '@/components/ui/Sheet'

function errorText(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return 'Dati non validi: controlla i campi.'
  return 'Operazione non riuscita. Riprova.'
}

/**
 * Crea l'accesso al portale per una cliente iscritta al banco.
 *
 * Due schermate in una, e la divisione non è estetica: prima si conferma
 * l'indirizzo, poi si consegna la password. In mezzo c'è la chiamata che la
 * genera, e **quella password non torna più**: a database ne resta l'hash.
 * Per questo la seconda schermata non ha un «Annulla» e chiude con un solo
 * pulsante — non c'è niente da annullare, c'è solo da averla trascritta.
 */
export default function ClientPortalAccountSheet({
  client,
  onClose,
}: {
  client: Client
  onClose: () => void
}) {
  const [creato, setCreato] = useState<PortalAccountCreated | null>(null)
  const [copiato, setCopiato] = useState(false)
  const qc = useQueryClient()

  const mut = useMutation({
    mutationFn: () => createClientPortalAccount(client.id),
    onSuccess: dati => {
      setCreato(dati)
      // La scheda ora ha `account_id`: senza questo la pagina dietro continua
      // a mostrare «crea accesso» per una cliente che l'accesso ce l'ha già.
      qc.invalidateQueries({ queryKey: ['client', client.id] })
      qc.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const copia = async () => {
    if (!creato) return
    try {
      await navigator.clipboard.writeText(creato.temp_password)
      setCopiato(true)
      setTimeout(() => setCopiato(false), 2000)
    } catch {
      // Clipboard negata (permesso o contesto non sicuro): la password è
      // comunque a schermo e selezionabile, che è il modo in cui verrà
      // trascritta comunque nella maggior parte dei casi.
    }
  }

  return (
    <Sheet
      onClose={onClose}
      title={creato ? 'Accesso creato' : 'Crea accesso al portale'}
      description={`${client.first_name} ${client.last_name}`}
      size="sm"
      footer={
        creato ? (
          <button onClick={onClose} className="btn-primary btn-sm">
            Fatto, l'ho trascritta
          </button>
        ) : (
          <>
            <button type="button" onClick={onClose} className="btn-secondary btn-sm">
              Annulla
            </button>
            <button
              type="button"
              onClick={() => mut.mutate()}
              disabled={mut.isPending || !client.email}
              className="btn-primary btn-sm"
            >
              {mut.isPending ? 'Creazione...' : 'Crea accesso'}
            </button>
          </>
        )
      }
    >
      {creato ? (
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 text-[13px] bg-primary/10 text-primary-dark dark:text-primary px-3 py-2.5">
            <Check className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              Ora può entrare nel portale con questi dati.
            </p>
          </div>

          <div>
            <label className="label">Email</label>
            <p className="text-[13px] font-mono break-all">{creato.email}</p>
          </div>

          <div>
            <label className="label">Password temporanea</label>
            <div className="flex items-center gap-2">
              {/* Grande e monospaziata: va letta ad alta voce o ricopiata a
                  mano, e i trattini fanno parte della password. */}
              <p className="text-base font-mono tracking-wide select-all flex-1">
                {creato.temp_password}
              </p>
              <button
                type="button"
                onClick={copia}
                className="btn-secondary btn-sm shrink-0"
                title="Copia negli appunti"
              >
                <Copy className="w-4 h-4" />
                {copiato ? 'Copiata' : 'Copia'}
              </button>
            </div>
          </div>

          <div className="flex items-start gap-2.5 text-[13px] bg-warning/10 text-warning px-3 py-2.5">
            <TriangleAlert className="w-4 h-4 shrink-0 mt-0.5" />
            <p>
              Trascrivila adesso: chiusa questa finestra non è più
              recuperabile. Se la perdi, usa «Password portale» per
              generarne un'altra.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {client.email ? (
            <>
              <div>
                <label className="label">Entrerà nel portale con</label>
                <p className="text-[13px] font-mono break-all">{client.email}</p>
              </div>

              {/* L'avviso è qui e non dopo, perché dopo sarebbe tardi:
                  l'account nasce già verificato — è il salone a garantire
                  l'indirizzo al posto del codice via email — quindi un
                  indirizzo sbagliato diventa un account funzionante
                  intestato a un estraneo. */}
              <div className="flex items-start gap-2.5 text-[13px] bg-warning/10 text-warning px-3 py-2.5">
                <TriangleAlert className="w-4 h-4 shrink-0 mt-0.5" />
                <p>
                  Rileggi l'indirizzo insieme a lei prima di procedere: non
                  viene verificato con un codice, quindi se è sbagliato
                  l'accesso finisce a qualcun altro.
                </p>
              </div>

              <p className="text-[13px] text-muted-foreground">
                Verrà generata una password temporanea da consegnarle. Potrà
                cambiarla dal portale dopo il primo accesso.
              </p>
            </>
          ) : (
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
              Questa scheda non ha un indirizzo email. Aggiungilo dalla
              modifica cliente: è quello con cui entra nel portale.
            </p>
          )}

          {mut.isError && (
            <p role="alert" className="text-[13px] text-danger bg-danger/10 px-3 py-2.5">
              {errorText(mut.error)}
            </p>
          )}
        </div>
      )}
    </Sheet>
  )
}
