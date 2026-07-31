import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getDashboardStats, getRevenueChart, getYearlyChart } from '@/services/api'
import { useUIStore } from '@/store/uiStore'
import { PageHeader, Segmented, SkeletonCards } from '@/components/ui'
import clsx from 'clsx'

type Period = 'today' | 'week' | 'month' | 'year'

const PERIOD_OPTIONS: { value: Period; label: string }[] = [
  { value: 'today', label: 'Oggi' },
  { value: 'week', label: 'Settimana' },
  { value: 'month', label: 'Mese' },
  { value: 'year', label: 'Anno' },
]

/* Recharts writes colours into SVG attributes, so a chart cannot inherit the
   CSS variables the rest of the page reads — the ledger tokens are repeated
   here as literals, one set per theme, copied from index.css. The charts keep
   the register's rule: money is gold, everything counted is ink. */
const LEDGER_LIGHT = {
  gold:  'hsl(34, 49%, 46%)',   /* --primary */
  ink:   'hsl(25, 28%, 14%)',   /* --foreground */
  ink2:  'hsl(27, 24%, 24%)',   /* --ink-2 */
  ink3:  'hsl(31, 13%, 54%)',   /* --ink-3 */
  rule:  'hsl(35, 32%, 84%)',   /* --rule */
  panel: 'hsl(36, 71%, 97%)',   /* --surface */
  edge:  'hsl(34, 28%, 78%)',   /* --border */
}
const LEDGER_DARK = {
  gold:  'hsl(36, 55%, 60%)',
  ink:   'hsl(38, 42%, 90%)',
  ink2:  'hsl(34, 24%, 80%)',
  ink3:  'hsl(31, 14%, 55%)',
  rule:  'hsl(28, 17%, 21%)',
  panel: 'hsl(26, 18%, 12%)',
  edge:  'hsl(28, 18%, 26%)',
}

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>('today')
  const [year, setYear] = useState(new Date().getFullYear())
  const isDark = useUIStore(s => s.isDark)

  const ink = isDark ? LEDGER_DARK : LEDGER_LIGHT
  const axisTick = { fontSize: 10, fill: ink.ink3 }
  const tooltipStyle = {
    backgroundColor: ink.panel,
    border: `1px solid ${ink.edge}`,
    borderRadius: 0,
    fontSize: 12,
    color: ink.ink,
  }

  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboard-stats', period],
    queryFn: () => getDashboardStats(period),
  })

  const { data: chartData } = useQuery({
    queryKey: ['revenue-chart'],
    queryFn: () => getRevenueChart(30),
    enabled: period !== 'year',
  })

  const { data: yearlyData } = useQuery({
    queryKey: ['yearly-chart', year],
    queryFn: () => getYearlyChart(year),
    enabled: period === 'year',
  })

  const fmt = (n: number) => `€${n.toFixed(2)}`
  const fmtCompact = (n: number) =>
    n >= 1000 ? `€${(n / 1000).toFixed(1)}k` : `€${Math.round(n)}`

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        action={
          period === 'year' ? (
            <div className="flex items-center gap-1 justify-center">
              <button onClick={() => setYear(y => y - 1)} className="btn-icon" aria-label="Anno precedente">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm font-semibold text-foreground w-12 text-center tabular-nums">
                {year}
              </span>
              <button
                onClick={() => setYear(y => Math.min(y + 1, new Date().getFullYear()))}
                disabled={year >= new Date().getFullYear()}
                className="btn-icon disabled:opacity-30"
                aria-label="Anno successivo"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          ) : undefined
        }
      />

      {/* Period picker scrolls sideways on narrow phones instead of wrapping. */}
      <Segmented options={PERIOD_OPTIONS} value={period} onChange={setPeriod} />

      {/* KPI cards */}
      {isLoading ? (
        <SkeletonCards count={4} />
      ) : (
        /* One sheet ruled into four cells, not four floating cards: the
           figures are meant to be read across, like a summary line. */
        <div className="panel grid grid-cols-2 lg:grid-cols-4">
          <Figure
            label="Incassi totali"
            value={fmt(stats?.total_revenue ?? 0)}
            sub={period === 'year' ? `Spese: ${fmt(stats?.total_expenses ?? 0)}` : `Contanti: ${fmt(stats?.cash_revenue ?? 0)}`}
            gold
          />
          <Figure
            label="Margine netto"
            value={fmt(stats?.net_margin ?? 0)}
            sub={`Spese: ${fmt(stats?.total_expenses ?? 0)}`}
          />
          <Figure
            label="Appuntamenti"
            value={String(stats?.appointment_count ?? 0)}
            sub="confermati / completati"
          />
          <Figure
            label="In attesa"
            value={String(stats?.pending_appointments ?? 0)}
            sub="da confermare"
          />
        </div>
      )}

      {period !== 'year' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="panel p-5">
              <h3 className="font-heading text-lg text-foreground border-b border-rule pb-2.5 mb-4">Incassi per tipo</h3>
              <div className="space-y-3">
                <Bar label="Servizi" value={stats?.service_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary" />
                <Bar label="Prodotti" value={stats?.product_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary-dark" />
              </div>
            </div>
            <div className="panel p-5">
              <h3 className="font-heading text-lg text-foreground border-b border-rule pb-2.5 mb-4">Metodo di pagamento</h3>
              <div className="space-y-3">
                <Bar label="Contanti" value={stats?.cash_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary" />
                <Bar label="Carta" value={stats?.card_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-ink-3" />
              </div>
            </div>
          </div>

          <div className="panel p-5">
            <h3 className="font-heading text-lg text-foreground border-b border-rule pb-2.5 mb-4">Incassi ultimi 30 giorni</h3>
            <ResponsiveContainer width="100%" height={180} className="sm:!h-[220px]">
              <AreaChart data={chartData ?? []} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={ink.gold} stopOpacity={0.35} />
                    <stop offset="95%" stopColor={ink.gold} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={ink.rule} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                  tickFormatter={d => `${d.slice(8)}/${d.slice(5, 7)}`}
                />
                <YAxis
                  tick={axisTick}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={fmtCompact}
                />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), 'Incasso']} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke={ink.gold}
                  strokeWidth={2}
                  fill="url(#colorRevenue)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </>
      )}

      {period === 'year' && (
        <>
          <div className="panel p-5">
            <h3 className="font-heading text-lg text-foreground border-b border-rule pb-2.5 mb-4">
              Ricavi e spese mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={220} className="sm:!h-[260px]">
              <BarChart data={yearlyData ?? []} barCategoryGap="25%" margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={ink.rule} vertical={false} />
                <XAxis dataKey="month" tick={axisTick} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={52} tickFormatter={fmtCompact} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v: number, name: string) => [
                    fmt(v),
                    name === 'revenue' ? 'Ricavi' : name === 'expenses' ? 'Spese' : 'Margine',
                  ]}
                />
                <Legend
                  formatter={name =>
                    name === 'revenue' ? 'Ricavi' : name === 'expenses' ? 'Spese' : 'Margine netto'
                  }
                  iconType="square"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 11 }}
                />
                <RBar dataKey="revenue" fill={ink.gold} radius={0} />
                <RBar dataKey="expenses" fill={ink.ink3} radius={0} />
                <RBar dataKey="net_margin" fill={ink.ink2} radius={0} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="panel p-5">
            <h3 className="font-heading text-lg text-foreground border-b border-rule pb-2.5 mb-4">
              Appuntamenti mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={170} className="sm:!h-[190px]">
              <BarChart data={yearlyData ?? []} barCategoryGap="30%" margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={ink.rule} vertical={false} />
                <XAxis dataKey="month" tick={axisTick} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={axisTick} tickLine={false} axisLine={false} width={40} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v, 'Appuntamenti']} />
                <RBar dataKey="appointments" fill={ink.ink2} radius={0} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <YearlySummary year={year} rows={yearlyData ?? []} fmt={fmt} />
        </>
      )}
    </div>
  )
}

/* Monthly summary: stacked cards on phones, table from `sm` up — five numeric
   columns are unreadable at 375px. */
function YearlySummary({
  year, rows, fmt,
}: {
  year: number
  rows: { month: string; month_num: number; revenue: number; expenses: number; net_margin: number; appointments: number }[]
  fmt: (n: number) => string
}) {
  const totals = rows.reduce(
    (acc, r) => ({
      revenue: acc.revenue + r.revenue,
      expenses: acc.expenses + r.expenses,
      net_margin: acc.net_margin + r.net_margin,
      appointments: acc.appointments + r.appointments,
    }),
    { revenue: 0, expenses: 0, net_margin: 0, appointments: 0 }
  )

  return (
    <div className="panel overflow-hidden">
      <div className="px-4 pt-4 pb-2">
        <h3 className="font-heading text-lg text-foreground">Riepilogo mensile {year}</h3>
      </div>

      {/* Phones */}
      <div className="sm:hidden divide-y divide-rule-soft">
        {rows.map(row => (
          <div key={row.month_num} className="px-4 py-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-medium text-foreground">{row.month}</span>
              <span className="text-xs text-muted-foreground">{row.appointments} appunt.</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-[13px]">
              <div>
                <p className="kicker">Ricavi</p>
                <p className="font-medium text-primary-dark">{fmt(row.revenue)}</p>
              </div>
              <div>
                <p className="kicker">Spese</p>
                <p className="font-medium text-danger">{fmt(row.expenses)}</p>
              </div>
              <div>
                <p className="kicker">Margine</p>
                <p className={`font-semibold ${row.net_margin >= 0 ?'text-foreground' : 'text-danger'}`}>
                  {fmt(row.net_margin)}
                </p>
              </div>
            </div>
          </div>
        ))}
        <div className="px-4 py-3 bg-band">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-semibold text-foreground">Totale</span>
            <span className="text-xs text-muted-foreground">{totals.appointments} appunt.</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-[13px]">
            <div>
              <p className="kicker">Ricavi</p>
              <p className="font-semibold text-primary-dark">{fmt(totals.revenue)}</p>
            </div>
            <div>
              <p className="kicker">Spese</p>
              <p className="font-semibold text-danger">{fmt(totals.expenses)}</p>
            </div>
            <div>
              <p className="kicker">Margine</p>
              <p className="font-bold text-foreground">{fmt(totals.net_margin)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tablet and up */}
      <div className="hidden sm:block table-scroll">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-rule">
              <th className="px-4 py-2 text-left kicker">Mese</th>
              <th className="px-4 py-2 text-right kicker">Ricavi</th>
              <th className="px-4 py-2 text-right kicker">Spese</th>
              <th className="px-4 py-2 text-right kicker">Margine</th>
              <th className="px-4 py-2 text-right kicker">Appuntamenti</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.month_num} className="border-b border-rule-soft last:border-0 hover:bg-foreground/[0.05] transition-colors">
                <td className="px-4 py-2.5 font-medium text-foreground">{row.month}</td>
                <td className="px-4 py-2.5 text-right text-primary-dark font-medium tabular-nums">{fmt(row.revenue)}</td>
                <td className="px-4 py-2.5 text-right text-danger tabular-nums">{fmt(row.expenses)}</td>
                <td className={`px-4 py-2.5 text-right font-semibold tabular-nums ${row.net_margin >= 0 ?'text-foreground' : 'text-danger'}`}>
                  {fmt(row.net_margin)}
                </td>
                <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">{row.appointments}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-band">
              <td className="px-4 py-2.5 font-semibold text-foreground">Totale</td>
              <td className="px-4 py-2.5 text-right text-primary-dark font-semibold tabular-nums">{fmt(totals.revenue)}</td>
              <td className="px-4 py-2.5 text-right text-danger font-semibold tabular-nums">{fmt(totals.expenses)}</td>
              <td className="px-4 py-2.5 text-right text-foreground font-bold tabular-nums">{fmt(totals.net_margin)}</td>
              <td className="px-4 py-2.5 text-right text-muted-foreground font-semibold tabular-nums">{totals.appointments}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

/* A cell of the summary sheet: what it counts, the figure, and the note that
   qualifies it. Money leads in gold; everything counted stays ink. */
function Figure({ label, value, sub, gold = false }: {
  label: string
  value: string
  sub: string
  gold?: boolean
}) {
  return (
    <div className="p-5 border-r border-b border-rule-soft last:border-r-0 lg:border-b-0 [&:nth-child(2)]:border-r-0 lg:[&:nth-child(2)]:border-r">
      <span className="kicker truncate">{label}</span>
      <p
        className={clsx(
          'font-heading text-[32px] leading-none mt-2 tabular-nums',
          gold ? 'text-primary-dark' : 'text-foreground'
        )}
      >
        {value}
      </p>
      <p className="text-xs text-muted-foreground mt-2 truncate">{sub}</p>
    </div>
  )
}

function Bar({ label, value, total, color }: {
  label: string; value: number; total: number; color: string
}) {
  const pct = total > 0 ? (value / total) * 100 : 0
  return (
    <div>
      <div className="flex justify-between text-[13px] mb-1.5">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">€{value.toFixed(2)}</span>
      </div>
      <div className="h-2 bg-muted overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
