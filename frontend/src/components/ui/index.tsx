import { Search, X } from 'lucide-react'
import clsx from 'clsx'

/* ── PageHeader ────────────────────────────────────────────────────
   Title + optional action. On phones the action drops to a full-width
   button under the title instead of being squeezed beside it. */

export function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string
  subtitle?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-title-lg font-bold text-foreground truncate">{title}</h1>
        {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
      {action && <div className="flex items-center gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">{action}</div>}
    </div>
  )
}

/* ── SearchInput ──────────────────────────────────────────────── */

export function SearchInput({
  value,
  onChange,
  placeholder = 'Cerca...',
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div className="relative">
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
      <input
        type="search"
        className="input pl-10 pr-10"
        placeholder={placeholder}
        value={value}
        onChange={e => onChange(e.target.value)}
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-muted-foreground hover:text-foreground"
          aria-label="Cancella ricerca"
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}

/* ── Segmented control ────────────────────────────────────────────
   Replaces rows of pill buttons. Scrolls horizontally when the options
   do not fit, instead of wrapping into a ragged block. */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  className?: string
}) {
  return (
    <div className={clsx('segmented max-w-full overflow-x-auto scroll-x !mx-0 !px-1', className)}>
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx('segmented-item', value === o.value && 'segmented-item-active')}
          aria-pressed={value === o.value}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ── EmptyState ───────────────────────────────────────────────── */

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>
  title: string
  description?: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
          <Icon className="w-6 h-6 text-muted-foreground" />
        </div>
      )}
      <p className="font-semibold text-foreground">{title}</p>
      {description && (
        <p className="text-sm text-muted-foreground mt-1 max-w-xs">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/* ── Loading skeletons ────────────────────────────────────────────
   Placeholders that match the shape of the content being loaded, so the
   layout does not jump when data lands. */

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Caricamento">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="card p-4 flex items-center gap-3">
          <div className="skeleton w-10 h-10 rounded-full shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-3.5 w-1/3" />
            <div className="skeleton h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="card p-4 space-y-3">
          <div className="skeleton w-9 h-9 rounded-lg" />
          <div className="skeleton h-3 w-2/3" />
          <div className="skeleton h-5 w-1/2" />
        </div>
      ))}
    </div>
  )
}

/* ── Pagination ───────────────────────────────────────────────────
   Prev/next with a page counter. The old build rendered one button per
   page, which overflowed as soon as there were more than a handful. */

export function Pagination({
  page,
  pages,
  total,
  unit = 'elementi',
  onChange,
}: {
  page: number
  pages: number
  total: number
  unit?: string
  onChange: (p: number) => void
}) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3 border-t border-border">
      <p className="text-[13px] text-muted-foreground">
        {total} {unit}
      </p>
      <div className="flex items-center gap-1">
        <button
          className="btn-outline btn-sm"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Prec
        </button>
        <span className="text-[13px] text-muted-foreground tabular-nums px-2">
          {page} / {pages}
        </span>
        <button
          className="btn-outline btn-sm"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Succ
        </button>
      </div>
    </div>
  )
}
