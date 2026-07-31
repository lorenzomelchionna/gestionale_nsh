import clsx from 'clsx'

/** Drawn proportions of the mark: 586 × 247. */
const RATIO = 586 / 247

/**
 * The New Style Hair wordmark.
 *
 * Painted as a CSS mask over `currentColor` rather than inlined: the traced
 * artwork is ~70 KB of path data, so it stays a separately cached file
 * instead of riding along in every JS bundle — and the mask still lets it
 * take the colour of whatever it sits on. Ink on paper, cream on the dark bar,
 * no second asset and no theme switch.
 */
export default function Logo({
  height = 28,
  className,
}: {
  /** Height in pixels; the width follows the drawn ratio. */
  height?: number
  className?: string
}) {
  return (
    <span
      role="img"
      aria-label="New Style Hair"
      className={clsx('block bg-current shrink-0', className)}
      style={{
        height,
        width: Math.round(height * RATIO),
        maskImage: 'url(/nsh-logo.svg)',
        WebkitMaskImage: 'url(/nsh-logo.svg)',
        maskSize: 'contain',
        WebkitMaskSize: 'contain',
        maskRepeat: 'no-repeat',
        WebkitMaskRepeat: 'no-repeat',
        maskPosition: 'center',
        WebkitMaskPosition: 'center',
      }}
    />
  )
}
