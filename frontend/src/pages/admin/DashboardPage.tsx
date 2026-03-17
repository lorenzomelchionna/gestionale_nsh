import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TrendingUp, DollarSign, Calendar, Clock } from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'
import { getDashboardStats, getRevenueChart } from '@/services/api'

type Period = 'today' | 'week' | 'month'

export default function DashboardPage() {
  const [period, setPeriod] = useState<Period>('today')

  const { data: stats } = useQuery({
    queryKey: ['dashboard-stats', period],
    queryFn: () => getDashboardStats(period),
  })

  const { data: chartData } = useQuery({
    queryKey: ['revenue-chart'],
    queryFn: () => getRevenueChart(30),
  })

  const fmt = (n: number) => `€${n.toFixed(2)}`

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <div className="flex gap-2">
          {(['today', 'week', 'month'] as Period[]).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-sm rounded-md font-medium transition-colors ${
                period === p ? 'bg-primary text-white' : 'bg-muted text-muted-foreground hover:text-foreground'
              }`}
            >
              {p === 'today' ? 'Oggi' : p === 'week' ? 'Settimana' : 'Mese'}
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
          sub={`Contanti: ${fmt(stats?.cash_revenue ?? 0)}`}
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

      {/* Revenue breakdown */}
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

      {/* Chart */}
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
            <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={d => d.slice(5)} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={v => `€${v}`} />
            <Tooltip formatter={(v: number) => [`€${v.toFixed(2)}`, 'Incasso']} />
            <Area
              type="monotone"
              dataKey="total"
              stroke="#C8A96E"
              strokeWidth={2}
              fill="url(#colorRevenue)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
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
