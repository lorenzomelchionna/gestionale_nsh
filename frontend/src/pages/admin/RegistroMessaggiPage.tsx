import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, parseISO } from 'date-fns'
import { it } from 'date-fns/locale'
import { Mail, MessageCircle, ScrollText } from 'lucide-react'
import clsx from 'clsx'
import {
  PageHeader, SearchInput, Segmented, EmptyState, SkeletonList, Pagination,
} from '@/components/ui'
import Sheet from '@/components/ui/Sheet'
import { getRegistroMessaggi, getTipiMessaggio } from '@/services/api'
import type { VoceRegistro } from '@/types'

const CANALI = [
  { value: '', label: 'Tutti' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
] as const

/** Come si legge ogni stato, e che colore ha: verde quello che è arrivato,
 *  rosso quello che non è arrivato, neutro quello di cui non si sa ancora. */
const STATI: Record<string, { label: string; tono: 'ok' | 'ko' | 'neutro' }> = {
  inviato: { label: 'Inviato', tono: 'neutro' },
  consegnato: { label: 'Consegnato', tono: 'ok' },
  letto: { label: 'Letto', tono: 'ok' },
  non_consegnato: { label: 'Non consegnato', tono: 'ko' },
  errore: { label: 'Non partito', tono: 'ko' },
}

function Stato({ stato }: { stato: string }) {
  const s = STATI[stato] ?? { label: stato, tono: 'neutro' as const }
  return (
    <span className={clsx(
      'inline-block px-2 py-0.5 text-[12px] whitespace-nowrap border',
      s.tono === 'ok' && 'border-primary/40 bg-primary/10 text-primary-dark',
      s.tono === 'ko' && 'border-danger/40 bg-danger/10 text-danger',
      s.tono === 'neutro' && 'border-border text-ink-2',
    )}>
      {s.label}
    </span>
  )
}

function Canale({ canale, soloIcona = false }: { canale: string; soloIcona?: boolean }) {
  const Icona = canale === 'email' ? Mail : MessageCircle
  const nome = canale === 'email' ? 'Email' : 'WhatsApp'
  return (
    <span className="inline-flex items-center gap-1.5 text-ink-2" title={nome}>
      <Icona className="w-4 h-4" aria-hidden="true" />
      <span className={soloIcona ? 'sr-only' : undefined}>{nome}</span>
    </span>
  )
}

const quando = (iso: string) => format(parseISO(iso), 'dd/MM/yyyy · HH:mm')
const chi = (v: VoceRegistro) => v.cliente_nome || v.destinatario

/**
 * Ogni messaggio partito dal gestionale, email e WhatsApp, di qualunque tipo:
 * conferme, promemoria, codici, risposte in chat, avvisi allo staff.
 *
 * Esiste per rispondere a «mi avete mandato la conferma?» e «perché non mi è
 * arrivato niente?» senza aprire Twilio e Brevo. Per WhatsApp lo stato si
 * aggiorna da solo quando Twilio lo comunica (consegnato, letto, non
 * consegnato col motivo); per le email si sa solo se Brevo l'ha accettata.
 *
 * Solo admin: numeri, indirizzi e testi di tutte le clienti in un posto solo.
 * Le righe si cancellano da sole dopo sei mesi.
 */
export default function RegistroMessaggiPage() {
  const [search, setSearch] = useState('')
  const [termine, setTermine] = useState('')
  const [dal, setDal] = useState('')
  const [al, setAl] = useState('')
  const [canale, setCanale] = useState<'' | 'whatsapp' | 'email'>('')
  const [tipo, setTipo] = useState('')
  const [stato, setStato] = useState('')
  const [page, setPage] = useState(1)
  const [aperta, setAperta] = useState<VoceRegistro | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      setTermine(search.trim().length >= 2 ? search.trim() : '')
      setPage(1)
    }, 350)
    return () => clearTimeout(t)
  }, [search])

  const { data: tipi } = useQuery({ queryKey: ['registro-tipi'], queryFn: getTipiMessaggio })

  const filtri = {
    cerca: termine || undefined,
    dal: dal || undefined,
    al: al || undefined,
    canale: canale || undefined,
    tipo: tipo || undefined,
    stato: stato || undefined,
  }
  const { data, isLoading } = useQuery({
    queryKey: ['registro-messaggi', page, filtri],
    queryFn: () => getRegistroMessaggi({ ...filtri, page, page_size: 50 }),
  })
  const voci = data?.items ?? []
  const filtrato = Boolean(termine || dal || al || canale || tipo || stato)

  const azzera = () => {
    setSearch(''); setDal(''); setAl(''); setCanale(''); setTipo(''); setStato(''); setPage(1)
  }
  /** Un giorno solo: «Dal» e «Al» uguali, che è la ricerca più comune. */
  const soloOggi = () => {
    const oggi = format(new Date(), 'yyyy-MM-dd')
    setDal(oggi); setAl(oggi); setPage(1)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Registro messaggi"
        subtitle={data ? `${data.total} messaggi · ultimi sei mesi` : undefined}
      />

      <div className="space-y-3">
        <SearchInput
          value={search}
          onChange={setSearch}
          placeholder="Cerca per cliente, numero, email o oggetto…"
        />
        <Segmented options={[...CANALI]} value={canale} onChange={v => { setCanale(v); setPage(1) }} />

        <div className="grid gap-3 grid-cols-2 sm:grid-cols-4">
          <div>
            <label className="label">Dal</label>
            <input type="date" className="input tabular-nums" value={dal}
              onChange={e => { setDal(e.target.value); if (!al || al < e.target.value) setAl(e.target.value); setPage(1) }} />
          </div>
          <div>
            <label className="label">Al</label>
            <input type="date" className="input tabular-nums" value={al} min={dal || undefined}
              onChange={e => { setAl(e.target.value); setPage(1) }} />
          </div>
          <div>
            <label className="label">Tipo</label>
            <select className="input" value={tipo} onChange={e => { setTipo(e.target.value); setPage(1) }}>
              <option value="">Tutti</option>
              {Object.entries(tipi ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="label">Stato</label>
            <select className="input" value={stato} onChange={e => { setStato(e.target.value); setPage(1) }}>
              <option value="">Tutti</option>
              {Object.entries(STATI).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <button onClick={soloOggi} className="btn-secondary btn-sm">Solo oggi</button>
          {filtrato && <button onClick={azzera} className="btn-secondary btn-sm">Azzera filtri</button>}
        </div>
      </div>

      {isLoading ? (
        <SkeletonList rows={6} />
      ) : voci.length === 0 ? (
        <div className="panel">
          <EmptyState
            icon={ScrollText}
            title={filtrato ? 'Nessun messaggio trovato' : 'Ancora nessun messaggio'}
            description={
              filtrato
                ? 'Prova con un altro nome, periodo o tipo.'
                : 'Ogni email e WhatsApp che parte dal gestionale compare qui.'
            }
          />
        </div>
      ) : (
        <>
          {/* Telefono: una riga per messaggio. */}
          <div className="panel sm:hidden divide-y divide-rule-soft">
            {voci.map(v => (
              <button
                key={v.id}
                onClick={() => setAperta(v)}
                className="w-full text-left px-4 py-3.5 flex items-start justify-between gap-3 hover:bg-foreground/[0.05] transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-[13px] text-ink-3 tabular-nums flex items-center gap-2">
                    <Canale canale={v.canale} soloIcona /> {quando(v.creato_il)}
                  </p>
                  <p className="text-sm text-foreground truncate mt-0.5">{chi(v)}</p>
                  <p className="text-[13px] text-muted-foreground truncate">{v.tipo_etichetta}</p>
                </div>
                <Stato stato={v.stato} />
              </button>
            ))}
            {data && <Pagination page={page} pages={data.pages} total={data.total} unit="messaggi" onChange={setPage} />}
          </div>

          <div className="panel hidden sm:block">
            <div className="table-scroll">
              <table className="ledger">
                <thead>
                  <tr>
                    <th>Quando</th>
                    <th>A chi</th>
                    <th>Tipo</th>
                    <th className="text-right">Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {voci.map(v => (
                    <tr key={v.id} onClick={() => setAperta(v)}
                      className="cursor-pointer hover:bg-foreground/[0.05] transition-colors">
                      <td className="tabular-nums whitespace-nowrap">
                        <span className="inline-flex items-center gap-2">
                          <Canale canale={v.canale} soloIcona />
                          {quando(v.creato_il)}
                        </span>
                      </td>
                      <td>
                        <span className="text-foreground">{chi(v)}</span>
                        {v.cliente_nome && (
                          <span className="block text-[13px] text-ink-3 tabular-nums">{v.destinatario}</span>
                        )}
                      </td>
                      <td className="text-muted-foreground">
                        {v.tipo_etichetta}
                        {v.oggetto && <span className="block text-[13px] text-ink-3 truncate max-w-[22rem]">{v.oggetto}</span>}
                      </td>
                      <td className="text-right"><Stato stato={v.stato} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {data && <Pagination page={page} pages={data.pages} total={data.total} unit="messaggi" onChange={setPage} />}
          </div>
        </>
      )}

      {aperta && <Dettaglio voce={aperta} onClose={() => setAperta(null)} />}
    </div>
  )
}

function Riga({ etichetta, children }: { etichetta: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 py-2 border-b border-rule-soft last:border-b-0 text-[14px]">
      <span className="text-ink-3">{etichetta}</span>
      <span className="text-foreground min-w-0 break-words">{children}</span>
    </div>
  )
}

function Dettaglio({ voce, onClose }: { voce: VoceRegistro; onClose: () => void }) {
  return (
    <Sheet
      onClose={onClose}
      title={voce.tipo_etichetta}
      description={format(parseISO(voce.creato_il), "EEEE d MMMM yyyy 'alle' HH:mm", { locale: it })}
      size="md"
    >
      <div className="flex flex-col gap-4">
        <div>
          <Riga etichetta="Canale"><Canale canale={voce.canale} /></Riga>
          <Riga etichetta="A chi">
            {voce.cliente_nome ? <>{voce.cliente_nome} <span className="text-ink-3">· {voce.destinatario}</span></> : voce.destinatario}
          </Riga>
          <Riga etichetta="Stato"><Stato stato={voce.stato} /></Riga>
          {voce.stato_aggiornato_il && (
            <Riga etichetta="Aggiornato">{format(parseISO(voce.stato_aggiornato_il), 'dd/MM/yyyy · HH:mm')}</Riga>
          )}
          {voce.errore && <Riga etichetta="Motivo"><span className="text-danger">{voce.errore}</span></Riga>}
          {voce.formato && (
            <Riga etichetta="Formato">{voce.formato === 'template' ? 'Template approvato' : 'Testo libero'}</Riga>
          )}
          {voce.oggetto && <Riga etichetta="Oggetto">{voce.oggetto}</Riga>}
        </div>

        <div>
          <p className="kicker mb-2">Testo</p>
          {voce.testo ? (
            <p className="whitespace-pre-wrap text-[14px] leading-relaxed border border-border bg-surface px-4 py-3">
              {voce.testo}
            </p>
          ) : (
            <p className="text-[13px] text-ink-3">
              Non conservato: codici di verifica, link di reset e codici dei buoni
              sono chiavi d'accesso e non restano nel registro.
            </p>
          )}
        </div>
      </div>
    </Sheet>
  )
}
