import { Search, X } from 'lucide-react'
import clsx from 'clsx'

/* ── PageHeader ────────────────────────────────────────────────────
   The head of a page in the register: the name set large in the display
   face, the count or date beside it in italics, actions to the right, and
   a rule underneath closing the block. On phones the action drops to a
   full-width button under the title instead of being squeezed beside it. */

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
    <div className="flex flex-col gap-3 border-b border-rule pb-3.5 sm:flex-row sm:items-baseline sm:gap-4">
      <h1 className="text-title-lg text-foreground truncate">{title}</h1>
      {subtitle && <p className="note truncate">{subtitle}</p>}
      <div className="sm:flex-1" />
      {action && (
        <div className="flex items-center gap-2 [&>*]:flex-1 sm:[&>*]:flex-none">{action}</div>
      )}
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
      <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-ink-3 pointer-events-none" />
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
          className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-ink-3 hover:text-foreground"
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
    <div className={clsx('segmented max-w-full overflow-x-auto', className)}>
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
        <div className="w-12 h-12 border border-border flex items-center justify-center mb-4">
          <Icon className="w-5 h-5 text-ink-3" />
        </div>
      )}
      <p className="font-heading text-xl text-foreground">{title}</p>
      {description && <p className="note mt-1.5 max-w-xs">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

/* ── Loading skeletons ────────────────────────────────────────────
   Ruled blanks in the shape of the rows that are coming, so the page does
   not jump when the data lands — the register drawn before it is filled. */

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="panel" aria-busy="true" aria-label="Caricamento">
      <div className="band flex items-center gap-3.5 px-4 py-3">
        <span className="skeleton h-2.5 w-40" />
        <span className="skeleton h-2.5 w-24" />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3.5 px-4 py-4 border-b border-rule-soft last:border-b-0">
          <span className="skeleton w-9 h-9 shrink-0" />
          <div className="flex-1 space-y-2">
            <span className="skeleton block h-3 w-1/3" />
            <span className="skeleton block h-2.5 w-1/2" />
          </div>
          <span className="skeleton h-3 w-16 shrink-0" />
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="panel grid grid-cols-2 lg:grid-cols-4" aria-busy="true">
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="p-5 space-y-3 border-r border-b border-rule-soft last:border-r-0 lg:border-b-0"
        >
          <span className="skeleton block h-2.5 w-2/3" />
          <span className="skeleton block h-7 w-1/2" />
          <span className="skeleton block h-2.5 w-3/4" />
        </div>
      ))}
    </div>
  )
}

/* ── Pagination ───────────────────────────────────────────────────
   Prev/next with a page counter, set on the foot band of the table it
   belongs to. */

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
    <div className="flex items-center justify-between gap-3 px-4 py-3 bg-band border-t border-rule">
      <p className="text-[13px] text-muted-foreground tabular-nums">
        {total} {unit}
      </p>
      <div className="flex items-center gap-2">
        <button
          className="btn-secondary btn-sm"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Prec
        </button>
        <span className="text-[13px] text-muted-foreground tabular-nums px-1">
          {page} / {pages}
        </span>
        <button
          className="btn-secondary btn-sm"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Succ
        </button>
      </div>
    </div>
  )
}
