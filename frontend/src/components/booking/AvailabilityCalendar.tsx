import { useMemo, useState } from 'react'
import {
  addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format,
  isSameMonth, startOfMonth, startOfToday, startOfWeek, subMonths,
} from 'date-fns'
import { it } from 'date-fns/locale'
import { Loader2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { publicGetAvailabilityCalendar } from '@/services/publicApi'

const WEEKDAYS = ['L', 'M', 'M', 'G', 'V', 'S', 'D']

interface Props {
  serviceId: number
  collaboratorId: number
  /** yyyy-MM-dd, or '' when nothing is chosen yet. */
  value: string
  onChange: (date: string) => void
}

/**
 * Month grid showing which days the chosen stylist still has room on.
 *
 * A date input tells you nothing until you pick a day and wait, so finding the
 * next free slot meant guessing one day at a time. The whole visible month is
 * fetched in one request instead, and days that cannot be booked are disabled
 * rather than merely unhelpful when tapped.
 */
export default function AvailabilityCalendar({
  serviceId, collaboratorId, value, onChange,
}: Props) {
  const today = startOfToday()
  const [month, setMonth] = useState(() => (value ? new Date(value) : today))

  // Weeks are padded to whole rows, so the request covers the leading and
  // trailing days of adjacent months that the grid actually displays.
  const gridStart = startOfWeek(startOfMonth(month), { weekStartsOn: 1 })
  const gridEnd = endOfWeek(endOfMonth(month), { weekStartsOn: 1 })

  const { data, isLoading } = useQuery({
    queryKey: [
      'availability-calendar', serviceId, collaboratorId,
      format(gridStart, 'yyyy-MM-dd'), format(gridEnd, 'yyyy-MM-dd'),
    ],
    queryFn: () => publicGetAvailabilityCalendar({
      service_id: serviceId,
      collaborator_id: collaboratorId,
      start_date: format(gridStart, 'yyyy-MM-dd'),
      end_date: format(gridEnd, 'yyyy-MM-dd'),
    }),
  })

  const slotsByDay = useMemo(() => {
    const map = new Map<string, number>()
    for (const d of data ?? []) map.set(d.date, d.slots)
    return map
  }, [data])

  const days = useMemo(
    () => eachDayOfInterval({ start: gridStart, end: gridEnd }),
    [gridStart, gridEnd]
  )

  const atFirstMonth = isSameMonth(month, today)

  return (
    <div className="panel">
      {/* The month named on its band, with the steppers squared into it. */}
      <div className="band flex items-center gap-3 px-4 py-2.5">
        <div className="flex border border-border">
          <button
            type="button"
            onClick={() => setMonth(m => subMonths(m, 1))}
            disabled={atFirstMonth}
            className="px-3 py-1.5 text-muted-foreground hover:bg-foreground/[0.05]
                       disabled:opacity-30 disabled:pointer-events-none transition-colors"
            aria-label="Mese precedente"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={() => setMonth(m => addMonths(m, 1))}
            className="px-3 py-1.5 text-muted-foreground border-l border-border
                       hover:bg-foreground/[0.05] transition-colors"
            aria-label="Mese successivo"
          >
            ›
          </button>
        </div>
        <p
          className="font-heading text-[17px] tracking-[0.03em] text-foreground first-letter:uppercase"
          aria-live="polite"
        >
          {format(month, 'MMMM yyyy', { locale: it })}
        </p>
      </div>

      <div className="grid grid-cols-7 border-b border-rule">
        {WEEKDAYS.map((d, i) => (
          <div key={i} aria-hidden="true" className="kicker text-center py-2">
            {d}
          </div>
        ))}
      </div>

      {/* Hairlines between the cells rather than gaps: the month reads as a
          ruled sheet, the way a wall calendar is printed. */}
      <div className="grid grid-cols-7 gap-px bg-rule-soft">
        {days.map(day => {
          const key = format(day, 'yyyy-MM-dd')
          const slots = slotsByDay.get(key) ?? 0
          const outsideMonth = !isSameMonth(day, month)
          const selected = value === key
          // While the month loads, days are not yet knowably free — leaving
          // them enabled would let someone tap into an empty slot list.
          const selectable = !isLoading && slots > 0

          return (
            <button
              key={key}
              type="button"
              disabled={!selectable}
              onClick={() => onChange(key)}
              aria-label={`${format(day, 'd MMMM', { locale: it })} — ${
                slots > 0 ? `${slots} orari liberi` : 'non disponibile'
              }`}
              aria-pressed={selected}
              className={clsx(
                'relative min-h-touch py-2 text-[15px] tabular-nums transition-colors',
                'flex flex-col items-center justify-center gap-0.5',
                outsideMonth && 'opacity-45',
                selected
                  ? 'bg-action text-action-foreground'
                  : selectable
                    ? 'bg-surface text-foreground hover:bg-primary/10 hover:text-primary-dark'
                    : 'bg-surface text-ink-3'
              )}
            >
              {format(day, 'd')}
              {/* How much room, not merely that there is some: the count is the
                  one thing that makes a day worth choosing over another. */}
              <span
                aria-hidden="true"
                className={clsx(
                  'text-[10px] leading-none',
                  selected ? 'text-action-foreground/80' : 'text-ink-3'
                )}
              >
                {selectable ? slots : ' '}
              </span>
            </button>
          )
        })}
      </div>

      {isLoading && (
        <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground py-3">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Controllo le disponibilità…
        </p>
      )}
      {!isLoading && data && !data.some(d => d.slots > 0) && (
        <p className="ledger-foot text-center">
          Nessuna disponibilità in {format(month, 'MMMM', { locale: it })}. Prova
          il mese successivo.
        </p>
      )}
    </div>
  )
}
