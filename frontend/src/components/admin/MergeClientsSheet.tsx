import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, Search } from 'lucide-react'
import { getClients, mergeClients, previewClientMerge } from '@/services/api'
import type { Client } from '@/types'
import Sheet from '@/components/ui/Sheet'

/** Nomi leggibili per le tabelle che la fusione sposta. Chi preme il pulsante
 *  non deve sapere che esiste una tabella `communications`. */
const ETICHETTE: Record<string, string> = {
  appointments: 'appuntamenti',
  payments: 'pagamenti',
  waitlist_entries: 'voci in lista d’attesa',
  communications: 'messaggi inviati',
  conversations: 'conversazioni WhatsApp',
  gift_cards: 'buoni regalo acquistati',
}

const CAMPI: Record<string, string> = {
  phone: 'telefono',
  email: 'email',
  birth_date: 'data di nascita',
}

function nome(c: Client) {
  return `${c.first_name} ${c.last_name}`
}

/**
 * Unione di due schede duplicate.
 *
 * La scheda aperta è quella che **resta**; qui si sceglie quale far confluire
 * dentro. È la stessa scelta che fa l'API — la destinazione sta nell'URL — e
 * non c'è nessuna euristica che decide al posto dell'operatore: «vince la più
 * vecchia» o «vince quella con più appuntamenti» sarebbero entrambe
 * ragionevoli e ogni tanto sbagliate, e questa operazione non si annulla.
 *
 * Il pulsante di conferma resta disabilitato finché l'anteprima non è
 * arrivata. Non è pignoleria: senza vedere quanti appuntamenti e quanti
 * incassi si stanno spostando, «unisci» è un pulsante che si preme e si spera.
 */
export default function MergeClientsSheet({
  target,
  onClose,
}: {
  target: Client
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [source, setSource] = useState<Client | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data: results } = useQuery({
    queryKey: ['clients', 'merge-search', search],
    queryFn: () => getClients({ search, page_size: 8 }),
    enabled: search.trim().length >= 2,
  })

  const { data: preview, isFetching: loadingPreview, error: previewError } = useQuery({
    queryKey: ['merge-preview', target.id, source?.id],
    queryFn: () => previewClientMerge(target.id, source!.id),
    enabled: source !== null,
    retry: false,
  })

  const merge = useMutation({
    mutationFn: () => mergeClients(target.id, source!.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      queryClient.invalidateQueries({ queryKey: ['client', target.id] })
      onClose()
    },
    onError: (e: any) =>
      setError(e?.response?.data?.detail ?? 'Unione non riuscita.'),
  })

  const candidati = (results?.items ?? []).filter((c) => c.id !== target.id)
  const messaggioAnteprima =
    (previewError as any)?.response?.data?.detail ?? null

  return (
    <Sheet
      onClose={onClose}
      size="lg"
      title="Unisci schede duplicate"
      description={`Gli appuntamenti e i pagamenti della scheda scelta passeranno a ${nome(target)}.`}
      footer={
        <>
          <button type="button" onClick={onClose} className="btn-secondary btn-sm">
            Annulla
          </button>
          <button
            type="button"
            className="btn-primary btn-sm"
            // Disabilitato finché non c'è un'anteprima: confermare senza
            // averla vista è esattamente ciò che questo pannello evita.
            disabled={!preview || loadingPreview || merge.isPending}
            onClick={() => {
              setError(null)
              merge.mutate()
            }}
          >
            {merge.isPending ? 'Unione in corso…' : 'Unisci definitivamente'}
          </button>
        </>
      }
    >
      <div className="space-y-5">
        <div>
          <label className="label">Scheda da unire in questa</label>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
            <input
              className="input pl-9"
              placeholder="Cerca per nome, telefono o email…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setSource(null)
              }}
            />
          </div>

          {search.trim().length >= 2 && (
            <ul className="mt-2 border border-rule rounded divide-y divide-rule max-h-52 overflow-y-auto">
              {candidati.length === 0 && (
                <li className="px-3 py-2 text-[13px] text-ink-3">Nessun risultato.</li>
              )}
              {candidati.map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSource(c)
                      setError(null)
                    }}
                    className={`w-full text-left px-3 py-2 text-[13px] hover:bg-surface-2 ${
                      source?.id === c.id ? 'bg-surface-2 font-medium' : ''
                    }`}
                  >
                    {nome(c)}
                    <span className="text-ink-3">
                      {c.phone ? ` · ${c.phone}` : ''}
                      {c.email ? ` · ${c.email}` : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {source && (
          <div className="flex items-center gap-3 text-[13px]">
            <span className="line-through text-ink-3">{nome(source)}</span>
            <ArrowRight className="w-4 h-4 text-ink-3" />
            <span className="font-medium">{nome(target)}</span>
          </div>
        )}

        {messaggioAnteprima && (
          <p className="text-[13px] text-danger">{messaggioAnteprima}</p>
        )}

        {loadingPreview && (
          <p className="text-[13px] text-ink-3">Calcolo di cosa verrà spostato…</p>
        )}

        {preview && (
          <div className="border border-rule rounded p-3 space-y-2 text-[13px]">
            <p className="font-medium">Cosa verrà spostato</p>
            {preview.total_rows === 0 ? (
              <p className="text-ink-3">
                Nessun appuntamento o pagamento collegato: si uniscono solo i dati
                della scheda.
              </p>
            ) : (
              <ul className="space-y-1">
                {Object.entries(preview.moved)
                  .filter(([, n]) => n > 0)
                  .map(([tabella, n]) => (
                    <li key={tabella}>
                      {n} {ETICHETTE[tabella] ?? tabella}
                    </li>
                  ))}
              </ul>
            )}

            {preview.filled_fields.length > 0 && (
              <p className="text-ink-3">
                Verranno completati i campi vuoti:{' '}
                {preview.filled_fields.map((f) => CAMPI[f] ?? f).join(', ')}.
              </p>
            )}
            {preview.notes_merged && (
              <p className="text-ink-3">Le note delle due schede verranno unite.</p>
            )}
            {preview.account_moved && (
              <p className="text-ink-3">
                L’account del portale passerà a {nome(target)}.
              </p>
            )}
          </div>
        )}

        <div className="flex gap-2 text-[13px] text-ink-3 border-t border-rule pt-3">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-px text-warning" />
          <p>
            L’unione non si può annullare. La scheda di partenza viene svuotata e
            archiviata, non cancellata: resta consultabile fra quelle non attive.
          </p>
        </div>

        {error && <p className="text-[13px] text-danger">{error}</p>}
      </div>
    </Sheet>
  )
}
