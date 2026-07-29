import { useMemo, useState } from 'react'
import {
  addMonths, eachDayOfInterval, endOfMonth, endOfWeek, format, isSameDay,
  isSameMonth, startOfMonth, startOfToday, startOfWeek, subMonths,
} from 'date-fns'
import { it } from 'date-fns/locale'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
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
    <div className="card p-3 sm:p-4">
      <div className="flex items-center justify-between mb-3">
        <button
          type="button"
          onClick={() => setMonth(m => subMonths(m, 1))}
          disabled={atFirstMonth}
          className="btn-icon disabled:opacity-30 disabled:pointer-events-none"
          aria-label="Mese precedente"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <p className="font-semibold capitalize" aria-live="polite">
          {format(month, 'MMMM yyyy', { locale: it })}
        </p>
        <button
          type="button"
          onClick={() => setMonth(m => addMonths(m, 1))}
          className="btn-icon"
          aria-label="Mese successivo"
        >
          <ChevronRight className="w-5 h-5" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 mb-1">
        {WEEKDAYS.map((d, i) => (
          <div
            key={i}
            aria-hidden="true"
            className="text-center text-[11px] font-semibold text-muted-foreground py-1"
          >
            {d}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
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
                'relative min-h-touch rounded-lg text-sm tabular-nums transition-colors',
                'flex flex-col items-center justify-center gap-0.5',
                outsideMonth && 'opacity-40',
                selected && 'bg-primary text-primary-foreground font-bold',
                !selected && selectable &&
                  'font-semibold text-foreground hover:bg-primary/10 hover:text-primary',
                !selected && !selectable && 'text-muted-foreground/50'
              )}
            >
              {format(day, 'd')}
              {/* Presence of room, not the exact count — the number itself is
                  noise at this size and reads as a price or a time. */}
              <span
                aria-hidden="true"
                className={clsx(
                  'w-1 h-1 rounded-full',
                  selected ? 'bg-primary-foreground' : selectable ? 'bg-primary' : 'bg-transparent'
                )}
              />
            </button>
          )
        })}
      </div>

      {isLoading && (
        <p className="flex items-center justify-center gap-2 text-xs text-muted-foreground pt-3">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Controllo le disponibilità...
        </p>
      )}
      {!isLoading && data && !data.some(d => d.slots > 0) && (
        <p className="text-center text-[13px] text-muted-foreground pt-3">
          Nessuna disponibilità in {format(month, 'MMMM', { locale: it })}.
          Prova il mese successivo.
        </p>
      )}
    </div>
  )
}
