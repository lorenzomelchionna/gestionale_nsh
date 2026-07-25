import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import clsx from 'clsx'

interface SheetProps {
  open?: boolean
  onClose: () => void
  title?: string
  description?: string
  children: React.ReactNode
  /** Sticky action bar pinned to the bottom (buttons stay reachable while scrolling). */
  footer?: React.ReactNode
  /** Max width of the desktop dialog. */
  size?: 'sm' | 'md' | 'lg'
}

const SIZES = {
  sm: 'sm:max-w-sm',
  md: 'sm:max-w-md',
  lg: 'sm:max-w-2xl',
}

/**
 * Responsive dialog: a bottom sheet on phones (thumb-reachable, slides up from
 * the edge the hand is already near) and a centered modal from `sm` up.
 *
 * Handles the things hand-rolled modals in this codebase kept missing: body
 * scroll lock, Escape to dismiss, focus containment on open, safe-area padding
 * so the action bar clears the iOS home indicator, and its own scroll container
 * so long forms never clip off-screen.
 */
export default function Sheet({
  open = true,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: SheetProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // Lock background scroll while the sheet is up.
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    // Move focus into the panel so keyboard and screen readers follow along.
    panelRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prev
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center sm:justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-[2px] animate-fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={clsx(
          'relative w-full flex flex-col outline-none',
          'bg-elevated shadow-sheet',
          // Mobile: full-width sheet anchored to the bottom edge.
          'rounded-t-2xl max-h-[92dvh] animate-slide-up',
          // Desktop: centered card.
          'sm:rounded-2xl sm:max-h-[85vh] sm:shadow-raised sm:animate-scale-in sm:m-4',
          SIZES[size]
        )}
      >
        {/* Grab handle — signals "drag/dismiss" affordance on touch. */}
        <div className="sm:hidden pt-3 pb-1 flex justify-center shrink-0">
          <span className="h-1 w-9 rounded-full bg-border" />
        </div>

        {(title || description) && (
          <header className="flex items-start justify-between gap-3 px-5 pt-3 pb-4 sm:pt-5 shrink-0">
            <div className="min-w-0">
              {title && <h2 className="text-lg font-semibold text-foreground truncate">{title}</h2>}
              {description && (
                <p className="text-[13px] text-muted-foreground mt-0.5">{description}</p>
              )}
            </div>
            <button onClick={onClose} className="btn-icon -mr-2 -mt-1" aria-label="Chiudi">
              <X className="w-5 h-5" />
            </button>
          </header>
        )}

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto overscroll-contain px-5 pb-5">{children}</div>

        {footer && (
          <footer className="shrink-0 border-t border-border px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] bg-elevated flex items-center justify-end gap-2 rounded-b-2xl">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body
  )
}
