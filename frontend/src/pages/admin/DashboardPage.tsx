import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, DollarSign, Calendar, Clock, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getDashboardStats, getRevenueChart, getYearlyChart } from '@/services/api'
import { useUIStore } from '@/store/uiStore'
import { PageHeader, Segmented, SkeletonCards } from '@/components/ui'

type Period = 'today' | 'week' | 'month' | 'year'

const PERIOD_OPTIONS: { value: Period; label: string }[] = [
  { value: 'today', label: 'Oggi' },
  { value: 'week', label: 'Settimana' },
  { value: 'month', label: 'Mese' },
  { value: 'year', label: 'Anno' },
]

const CHART_COLORS = {
  revenue: '#C8A96E',
  expenses: '#F87171',
  margin: '#34D399',
  appointments: '#818CF8',
}

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>('today')
  const [year, setYear] = useState(new Date().getFullYear())
  const isDark = useUIStore(s => s.isDark)

  // Charts are drawn on canvas, so they cannot inherit CSS variables the way
  // the rest of the UI does — resolve the few colours they need per theme.
  const axisColor = isDark ? '#8a8178' : '#8b8378'
  const gridColor = isDark ? '#3a3733' : '#E5E0D8'
  const tooltipStyle = {
    backgroundColor: isDark ? '#2b2825' : '#ffffff',
    border: `1px solid ${gridColor}`,
    borderRadius: 12,
    fontSize: 12,
    color: isDark ? '#f0eae1' : '#1f1c19',
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
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={<DollarSign className="w-[18px] h-[18px]" />}
            label="Incassi totali"
            value={fmt(stats?.total_revenue ?? 0)}
            sub={period === 'year' ? `Spese: ${fmt(stats?.total_expenses ?? 0)}` : `Contanti: ${fmt(stats?.cash_revenue ?? 0)}`}
            tone="success"
          />
          <StatCard
            icon={<TrendingUp className="w-[18px] h-[18px]" />}
            label="Margine netto"
            value={fmt(stats?.net_margin ?? 0)}
            sub={`Spese: ${fmt(stats?.total_expenses ?? 0)}`}
            tone="info"
          />
          <StatCard
            icon={<Calendar className="w-[18px] h-[18px]" />}
            label="Appuntamenti"
            value={String(stats?.appointment_count ?? 0)}
            sub="confermati / completati"
            tone="primary"
          />
          <StatCard
            icon={<Clock className="w-[18px] h-[18px]" />}
            label="In attesa"
            value={String(stats?.pending_appointments ?? 0)}
            sub="da confermare"
            tone="warning"
          />
        </div>
      )}

      {period !== 'year' && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Incassi per tipo</h3>
              <div className="space-y-3">
                <Bar label="Servizi" value={stats?.service_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary" />
                <Bar label="Prodotti" value={stats?.product_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary-dark" />
              </div>
            </div>
            <div className="card p-4">
              <h3 className="text-sm font-semibold text-foreground mb-3">Metodo di pagamento</h3>
              <div className="space-y-3">
                <Bar label="Contanti" value={stats?.cash_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-emerald-500" />
                <Bar label="Carta" value={stats?.card_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-blue-500" />
              </div>
            </div>
          </div>

          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4">Incassi ultimi 30 giorni</h3>
            <ResponsiveContainer width="100%" height={180} className="sm:!h-[220px]">
              <AreaChart data={chartData ?? []} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <defs>
                  <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={CHART_COLORS.revenue} stopOpacity={0.35} />
                    <stop offset="95%" stopColor={CHART_COLORS.revenue} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: axisColor }}
                  tickLine={false}
                  axisLine={false}
                  minTickGap={24}
                  tickFormatter={d => `${d.slice(8)}/${d.slice(5, 7)}`}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: axisColor }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={fmtCompact}
                />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [fmt(v), 'Incasso']} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke={CHART_COLORS.revenue}
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
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4">
              Ricavi e spese mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={220} className="sm:!h-[260px]">
              <BarChart data={yearlyData ?? []} barCategoryGap="25%" margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} width={52} tickFormatter={fmtCompact} />
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
                  iconType="circle"
                  iconSize={8}
                  wrapperStyle={{ fontSize: 11 }}
                />
                <RBar dataKey="revenue" fill={CHART_COLORS.revenue} radius={[3, 3, 0, 0]} />
                <RBar dataKey="expenses" fill={CHART_COLORS.expenses} radius={[3, 3, 0, 0]} />
                <RBar dataKey="net_margin" fill={CHART_COLORS.margin} radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4">
              Appuntamenti mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={170} className="sm:!h-[190px]">
              <BarChart data={yearlyData ?? []} barCategoryGap="30%" margin={{ top: 4, right: 4, bottom: 0, left: -24 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fontSize: 10, fill: axisColor }} tickLine={false} axisLine={false} width={40} allowDecimals={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => [v, 'Appuntamenti']} />
                <RBar dataKey="appointments" fill={CHART_COLORS.appointments} radius={[3, 3, 0, 0]} />
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
    <div className="card overflow-hidden">
      <div className="px-4 pt-4 pb-2">
        <h3 className="text-sm font-semibold text-foreground">Riepilogo mensile {year}</h3>
      </div>

      {/* Phones */}
      <div className="sm:hidden divide-y divide-border">
        {rows.map(row => (
          <div key={row.month_num} className="px-4 py-3">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-medium text-foreground">{row.month}</span>
              <span className="text-xs text-muted-foreground">{row.appointments} appunt.</span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-[13px]">
              <div>
                <p className="text-[11px] text-muted-foreground">Ricavi</p>
                <p className="font-medium text-emerald-600 dark:text-emerald-400">{fmt(row.revenue)}</p>
              </div>
              <div>
                <p className="text-[11px] text-muted-foreground">Spese</p>
                <p className="font-medium text-red-500">{fmt(row.expenses)}</p>
              </div>
              <div>
                <p className="text-[11px] text-muted-foreground">Margine</p>
                <p className={`font-semibold ${row.net_margin >= 0 ? 'text-blue-600 dark:text-blue-400' : 'text-red-600'}`}>
                  {fmt(row.net_margin)}
                </p>
              </div>
            </div>
          </div>
        ))}
        <div className="px-4 py-3 bg-muted/50">
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-semibold text-foreground">Totale</span>
            <span className="text-xs text-muted-foreground">{totals.appointments} appunt.</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-[13px]">
            <div>
              <p className="text-[11px] text-muted-foreground">Ricavi</p>
              <p className="font-semibold text-emerald-600 dark:text-emerald-400">{fmt(totals.revenue)}</p>
            </div>
            <div>
              <p className="text-[11px] text-muted-foreground">Spese</p>
              <p className="font-semibold text-red-500">{fmt(totals.expenses)}</p>
            </div>
            <div>
              <p className="text-[11px] text-muted-foreground">Margine</p>
              <p className="font-bold text-blue-600 dark:text-blue-400">{fmt(totals.net_margin)}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tablet and up */}
      <div className="hidden sm:block table-scroll">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">Mese</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Ricavi</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Spese</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Margine</th>
              <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground">Appuntamenti</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr key={row.month_num} className="border-b border-border last:border-0 hover:bg-muted/40 transition-colors">
                <td className="px-4 py-2.5 font-medium text-foreground">{row.month}</td>
                <td className="px-4 py-2.5 text-right text-emerald-600 dark:text-emerald-400 font-medium tabular-nums">{fmt(row.revenue)}</td>
                <td className="px-4 py-2.5 text-right text-red-500 tabular-nums">{fmt(row.expenses)}</td>
                <td className={`px-4 py-2.5 text-right font-semibold tabular-nums ${row.net_margin >= 0 ? 'text-blue-600 dark:text-blue-400' : 'text-red-600'}`}>
                  {fmt(row.net_margin)}
                </td>
                <td className="px-4 py-2.5 text-right text-muted-foreground tabular-nums">{row.appointments}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-muted/50">
              <td className="px-4 py-2.5 font-semibold text-foreground">Totale</td>
              <td className="px-4 py-2.5 text-right text-emerald-600 dark:text-emerald-400 font-semibold tabular-nums">{fmt(totals.revenue)}</td>
              <td className="px-4 py-2.5 text-right text-red-500 font-semibold tabular-nums">{fmt(totals.expenses)}</td>
              <td className="px-4 py-2.5 text-right text-blue-600 dark:text-blue-400 font-bold tabular-nums">{fmt(totals.net_margin)}</td>
              <td className="px-4 py-2.5 text-right text-muted-foreground font-semibold tabular-nums">{totals.appointments}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  )
}

const TONES = {
  success: 'bg-emerald-500/12 text-emerald-600 dark:text-emerald-400',
  info: 'bg-blue-500/12 text-blue-600 dark:text-blue-400',
  primary: 'bg-primary/12 text-primary',
  warning: 'bg-amber-500/12 text-amber-600 dark:text-amber-400',
}

function StatCard({ icon, label, value, sub, tone }: {
  icon: React.ReactNode
  label: string
  value: string
  sub: string
  tone: keyof typeof TONES
}) {
  return (
    <div className="card p-3.5 sm:p-4">
      <div className={`w-9 h-9 ${TONES[tone]} rounded-lg flex items-center justify-center mb-3`}>
        {icon}
      </div>
      <p className="text-xs text-muted-foreground truncate">{label}</p>
      <p className="text-lg sm:text-xl font-bold text-foreground mt-0.5 tabular-nums">{value}</p>
      <p className="text-[11px] text-muted-foreground mt-0.5 truncate">{sub}</p>
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
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
