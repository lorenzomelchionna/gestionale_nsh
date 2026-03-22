import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, DollarSign, Calendar, Clock, ChevronLeft, ChevronRight } from 'lucide-react'
import {
  AreaChart, Area, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { getDashboardStats, getRevenueChart, getYearlyChart } from '@/services/api'

type Period = 'today' | 'week' | 'month' | 'year'

const PERIOD_LABELS: Record<Period, string> = {
  today: 'Oggi',
  week: 'Settimana',
  month: 'Mese',
  year: 'Anno',
}

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>('today')
  const [year, setYear] = useState(new Date().getFullYear())

  const { data: stats } = useQuery({
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
          {period === 'year' && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setYear(y => y - 1)}
                className="p-1 rounded-md hover:bg-muted transition-colors"
              >
                <ChevronLeft className="w-4 h-4 text-muted-foreground" />
              </button>
              <span className="text-sm font-semibold text-foreground w-12 text-center">{year}</span>
              <button
                onClick={() => setYear(y => Math.min(y + 1, new Date().getFullYear()))}
                disabled={year >= new Date().getFullYear()}
                className="p-1 rounded-md hover:bg-muted transition-colors disabled:opacity-30"
              >
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          )}
        </div>
        <div className="flex gap-2">
          {(['today', 'week', 'month', 'year'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors ${
                period === p ? 'bg-primary text-white' : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<DollarSign className="w-5 h-5" />}
          label="Incassi totali"
          value={fmt(stats?.total_revenue ?? 0)}
          sub={period === 'year' ? `Spese: ${fmt(stats?.total_expenses ?? 0)}` : `Contanti: ${fmt(stats?.cash_revenue ?? 0)}`}
          color="text-emerald-600"
          bg="bg-emerald-50"
        />
        <StatCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Margine netto"
          value={fmt(stats?.net_margin ?? 0)}
          sub={`Spese: ${fmt(stats?.total_expenses ?? 0)}`}
          color="text-blue-600"
          bg="bg-blue-50"
        />
        <StatCard
          icon={<Calendar className="w-5 h-5" />}
          label="Appuntamenti"
          value={String(stats?.appointment_count ?? 0)}
          sub="confermati / completati"
          color="text-primary"
          bg="bg-primary/10"
        />
        <StatCard
          icon={<Clock className="w-5 h-5" />}
          label="In attesa"
          value={String(stats?.pending_appointments ?? 0)}
          sub="da confermare"
          color="text-amber-600"
          bg="bg-amber-50"
        />
      </div>

      {/* Revenue breakdown — solo periodi non-anno */}
      {period !== 'year' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">Incassi per tipo</h3>
            <div className="space-y-2">
              <Bar label="Servizi" value={stats?.service_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary" />
              <Bar label="Prodotti" value={stats?.product_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-primary-dark" />
            </div>
          </div>
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">Metodo di pagamento</h3>
            <div className="space-y-2">
              <Bar label="Contanti" value={stats?.cash_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-emerald-500" />
              <Bar label="Carta" value={stats?.card_revenue ?? 0} total={stats?.total_revenue ?? 1} color="bg-blue-500" />
            </div>
          </div>
        </div>
      )}

      {/* Chart 30 giorni — periodi non-anno */}
      {period !== 'year' && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-foreground mb-4">Incassi ultimi 30 giorni</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData ?? []}>
              <defs>
                <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#C8A96E" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#C8A96E" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E0D8" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => `${d.slice(8)}/${d.slice(5, 7)}`} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `€${v}`} />
              <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, 'Incasso']} />
              <Area type="monotone" dataKey="total" stroke="#C8A96E" strokeWidth={2} fill="url(#colorRevenue)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Vista annuale */}
      {period === 'year' && (
        <>
          {/* Grafico ricavi vs spese mensili */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4">
              Ricavi e spese mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={yearlyData ?? []} barCategoryGap="25%">
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E0D8" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `€${v}`} />
                <Tooltip
                  formatter={(v: number, name: string) => [
                    `€${v.toFixed(2)}`,
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
                <RBar dataKey="revenue" fill="#C8A96E" radius={[3, 3, 0, 0]} />
                <RBar dataKey="expenses" fill="#F87171" radius={[3, 3, 0, 0]} />
                <RBar dataKey="net_margin" fill="#34D399" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Grafico appuntamenti mensili */}
          <div className="card p-4">
            <h3 className="text-sm font-semibold text-foreground mb-4">
              Appuntamenti mensili — {year}
            </h3>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={yearlyData ?? []} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E0D8" vertical={false} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip formatter={(v: number) => [v, 'Appuntamenti']} />
                <RBar dataKey="appointments" fill="#818CF8" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Tabella riepilogo mensile */}
          <div className="card overflow-hidden">
            <div className="px-4 pt-4 pb-2">
              <h3 className="text-sm font-semibold text-foreground">Riepilogo mensile {year}</h3>
            </div>
            <div className="overflow-x-auto">
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
                  {(yearlyData ?? []).map(row => (
                    <tr key={row.month_num} className="border-b border-border last:border-0 hover:bg-muted/40 transition-colors">
                      <td className="px-4 py-2.5 font-medium text-foreground">{row.month}</td>
                      <td className="px-4 py-2.5 text-right text-emerald-600 font-medium">{fmt(row.revenue)}</td>
                      <td className="px-4 py-2.5 text-right text-red-500">{fmt(row.expenses)}</td>
                      <td className={`px-4 py-2.5 text-right font-semibold ${row.net_margin >= 0 ? 'text-blue-600' : 'text-red-600'}`}>
                        {fmt(row.net_margin)}
                      </td>
                      <td className="px-4 py-2.5 text-right text-muted-foreground">{row.appointments}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-muted/50">
                    <td className="px-4 py-2.5 font-semibold text-foreground">Totale</td>
                    <td className="px-4 py-2.5 text-right text-emerald-600 font-semibold">
                      {fmt((yearlyData ?? []).reduce((s, r) => s + r.revenue, 0))}
                    </td>
                    <td className="px-4 py-2.5 text-right text-red-500 font-semibold">
                      {fmt((yearlyData ?? []).reduce((s, r) => s + r.expenses, 0))}
                    </td>
                    <td className="px-4 py-2.5 text-right text-blue-600 font-bold">
                      {fmt((yearlyData ?? []).reduce((s, r) => s + r.net_margin, 0))}
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground font-semibold">
                      {(yearlyData ?? []).reduce((s, r) => s + r.appointments, 0)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, sub, color, bg }: {
  icon: React.ReactNode; label: string; value: string; sub: string; color: string; bg: string
}) {
  return (
    <div className="card p-4">
      <div className={`w-9 h-9 ${bg} ${color} rounded-lg flex items-center justify-center mb-3`}>
        {icon}
      </div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-bold text-foreground mt-0.5">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>
    </div>
  )
}

function Bar({ label, value, total, color }: {
  label: string; value: number; total: number; color: string
}) {
  const pct = total > 0 ? (value / total) * 100 : 0
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">€{value.toFixed(2)}</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
