import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
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
      {/* Backdrop — ink wash, not a neutral scrim. */}
      <div
        className="absolute inset-0 bg-chrome/50 animate-fade-in"
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
          'bg-surface border border-border shadow-dialog',
          // Mobile: full-width sheet anchored to the bottom edge.
          'max-h-[92dvh] animate-slide-up',
          // Desktop: centered card.
          'sm:max-h-[85vh] sm:animate-scale-in sm:m-4',
          SIZES[size]
        )}
      >
        {(title || description) && (
          <header className="band flex items-baseline gap-3 px-6 py-4 shrink-0">
            <div className="min-w-0">
              {title && (
                <h2 className="font-heading text-xl tracking-[0.04em] text-foreground truncate">
                  {title}
                </h2>
              )}
              {description && <p className="note mt-1">{description}</p>}
            </div>
            <div className="flex-1" />
            {/* Named rather than an X: the design labels its exits. */}
            <button
              onClick={onClose}
              className="text-[13px] text-ink-3 hover:text-foreground shrink-0"
              aria-label="Chiudi"
            >
              chiudi
            </button>
          </header>
        )}

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto overscroll-contain px-6 py-5">{children}</div>

        {footer && (
          <footer className="shrink-0 border-t border-rule px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] flex items-center justify-end gap-2.5">
            {footer}
          </footer>
        )}
      </div>
    </div>,
    document.body
  )
}
