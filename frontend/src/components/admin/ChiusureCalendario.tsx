import { useMemo, useState } from 'react'
import {
  addDays, addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format,
  isSameMonth, parseISO, startOfMonth, startOfWeek, subMonths,
} from 'date-fns'
import { it } from 'date-fns/locale'
import { CalendarDays, X } from 'lucide-react'
import clsx from 'clsx'
import type { ChiusuraSalone } from '@/types'

const WEEKDAYS = ['L', 'M', 'M', 'G', 'V', 'S', 'D']
const iso = (d: Date) => format(d, 'yyyy-MM-dd')
const leggibile = (s: string) => format(parseISO(s), 'd MMM yyyy', { locale: it })

/** Ogni giorno chiuso con la sua nota: le chiusure salvate sono periodi, ma
 *  qui si ragiona giorno per giorno. */
function giorni(chiusure: ChiusuraSalone[]): Map<string, string> {
  const m = new Map<string, string>()
  for (const c of chiusure) {
    for (const d of eachDayOfInterval({ start: parseISO(c.dal), end: parseISO(c.al) })) {
      m.set(iso(d), c.nota)
    }
  }
  return m
}

/** Di nuovo in periodi: i giorni consecutivi diventano uno solo, con la prima
 *  nota non vuota che c'era fra i loro giorni. */
function periodi(m: Map<string, string>): ChiusuraSalone[] {
  const ordinati = [...m.keys()].sort()
  const out: ChiusuraSalone[] = []
  for (const g of ordinati) {
    const ultimo = out[out.length - 1]
    if (ultimo && iso(addDays(parseISO(ultimo.al), 1)) === g) {
      ultimo.al = g
      if (!ultimo.nota) ultimo.nota = m.get(g) ?? ''
    } else {
      out.push({ dal: g, al: g, nota: m.get(g) ?? '' })
    }
  }
  return out
}

/**
 * Ferie, ponti, festività in cui il salone non apre — scelti su un calendario.
 *
 * Prima erano due campi «Dal / Al» (2026-11-20): Lorenzo ha preferito vedere
 * il mese e toccare i giorni. Un tocco chiude il giorno, un secondo lo
 * riapre; i giorni di fila diventano un periodo solo nell'elenco sotto, dove
 * si scrive la nota. Si salvano col resto della pagina.
 *
 * I giorni chiusi ogni settimana sono già chiusi: compaiono barrati e non si
 * toccano, così non sembrano un'altra cosa da decidere. I giorni passati non
 * si toccano nemmeno — chiuderli non cambierebbe niente.
 */
export default function ChiusureCalendario({ value, onChange, closedWeekdays }: {
  value: ChiusuraSalone[]
  onChange: (v: ChiusuraSalone[]) => void
  /** Convenzione JS: 0 = domenica … 6 = sabato. */
  closedWeekdays: number[]
}) {
  const [aperto, setAperto] = useState(false)
  const [mese, setMese] = useState(() => startOfMonth(new Date()))
  const oggi = iso(new Date())
  const chiusi = useMemo(() => giorni(value), [value])

  const griglia = useMemo(() => eachDayOfInterval({
    start: startOfWeek(startOfMonth(mese), { weekStartsOn: 1 }),
    end: endOfWeek(endOfMonth(mese), { weekStartsOn: 1 }),
  }), [mese])

  const alterna = (g: string) => {
    const m = new Map(chiusi)
    if (m.has(g)) m.delete(g)
    else m.set(g, '')
    onChange(periodi(m))
  }

  const cambiaNota = (i: number, nota: string) =>
    onChange(value.map((c, j) => (j === i ? { ...c, nota } : c)))

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={() => setAperto(a => !a)}
        aria-expanded={aperto}
        className="btn-secondary self-start"
      >
        <CalendarDays className="w-4 h-4" />
        {aperto ? 'Chiudi il calendario' : 'Scegli i giorni'}
      </button>

      {aperto && (
        <div className="panel">
          <div className="band flex items-center gap-3 px-4 py-2.5">
            <div className="flex border border-border">
              <button
                type="button"
                onClick={() => setMese(m => subMonths(m, 1))}
                disabled={isSameMonth(mese, new Date())}
                className="px-3 py-1.5 text-muted-foreground hover:bg-foreground/[0.05]
                           disabled:opacity-30 disabled:pointer-events-none transition-colors"
                aria-label="Mese precedente"
              >
                ‹
              </button>
              <button
                type="button"
                onClick={() => setMese(m => addMonths(m, 1))}
                className="px-3 py-1.5 text-muted-foreground border-l border-border
                           hover:bg-foreground/[0.05] transition-colors"
                aria-label="Mese successivo"
              >
                ›
              </button>
            </div>
            <p className="font-heading text-[17px] tracking-[0.03em] text-foreground first-letter:uppercase">
              {format(mese, 'MMMM yyyy', { locale: it })}
            </p>
          </div>

          <div className="grid grid-cols-7 border-b border-rule">
            {WEEKDAYS.map((d, i) => (
              <div key={i} aria-hidden="true" className="kicker text-center py-2">{d}</div>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-px bg-rule-soft">
            {griglia.map(giorno => {
              const g = iso(giorno)
              const fuoriMese = !isSameMonth(giorno, mese)
              const passato = g < oggi
              const settimanale = closedWeekdays.includes(giorno.getDay())
              const chiuso = chiusi.has(g)
              const toccabile = !passato && !settimanale && !fuoriMese
              return (
                <button
                  key={g}
                  type="button"
                  disabled={!toccabile}
                  onClick={() => alterna(g)}
                  aria-pressed={chiuso}
                  aria-label={`${format(giorno, 'EEEE d MMMM', { locale: it })} — ${
                    settimanale ? 'chiuso ogni settimana' : chiuso ? 'chiuso, tocca per riaprire' : 'aperto, tocca per chiudere'
                  }`}
                  className={clsx(
                    'min-h-touch py-2 text-[15px] tabular-nums transition-colors',
                    fuoriMese && 'opacity-0 pointer-events-none',
                    chiuso
                      ? 'bg-danger/[0.15] text-danger line-through font-medium'
                      : settimanale
                        ? 'bg-surface text-ink-3 line-through'
                        : passato
                          ? 'bg-surface text-ink-3 opacity-50'
                          : 'bg-surface text-foreground hover:bg-danger/[0.08]'
                  )}
                >
                  {format(giorno, 'd')}
                </button>
              )
            })}
          </div>
          <p className="ledger-foot">
            Tocca un giorno per chiuderlo, toccalo di nuovo per riaprirlo.
          </p>
        </div>
      )}

      {value.length === 0 ? (
        <p className="text-[13px] text-ink-3">Nessuna chiusura per data.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-rule-soft border border-border">
          {value.map((c, i) => {
            const passata = c.al < oggi
            return (
              <li
                key={`${c.dal}-${c.al}`}
                className={clsx('flex flex-wrap items-center gap-x-3 gap-y-2 px-3 py-2.5 text-[14px]', passata && 'opacity-50')}
              >
                <span className="tabular-nums text-foreground whitespace-nowrap">
                  {c.dal === c.al ? leggibile(c.dal) : `${leggibile(c.dal)} – ${leggibile(c.al)}`}
                </span>
                <input
                  className="input !py-1.5 flex-1 min-w-[10rem]"
                  maxLength={80}
                  placeholder="Nota (es. Natale, ferie)"
                  value={c.nota}
                  onChange={e => cambiaNota(i, e.target.value)}
                  aria-label={`Nota per la chiusura del ${leggibile(c.dal)}`}
                />
                {passata && <span className="text-xs text-ink-3">passata</span>}
                <button
                  type="button"
                  onClick={() => onChange(value.filter((_, j) => j !== i))}
                  className="btn-icon hover:text-danger"
                  aria-label={`Togli la chiusura del ${leggibile(c.dal)}`}
                >
                  <X className="w-4 h-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
      <p className="text-xs text-ink-3">
        In questi giorni il portale non mostra orari a nessun collaboratore. Le
        modifiche valgono dopo «Salva impostazioni».
      </p>
    </div>
  )
}
