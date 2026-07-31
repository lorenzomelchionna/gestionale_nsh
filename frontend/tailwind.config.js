/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
          dark: 'hsl(var(--primary-dark) / <alpha-value>)',
          light: 'hsl(var(--primary-light) / <alpha-value>)',
          foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
        },
        background: 'hsl(var(--background) / <alpha-value>)',
        surface: 'hsl(var(--surface) / <alpha-value>)',
        // Raised panels (sheets, popovers) that must read above `surface`.
        elevated: 'hsl(var(--elevated) / <alpha-value>)',
        // Tinted strip behind table headers and toolbars.
        band: 'hsl(var(--band) / <alpha-value>)',
        // Recessed ground inside form fields.
        field: 'hsl(var(--field) / <alpha-value>)',
        border: 'hsl(var(--border) / <alpha-value>)',
        // Two lighter rules under `border`: section divider, then row divider.
        rule: 'hsl(var(--rule) / <alpha-value>)',
        'rule-soft': 'hsl(var(--rule-soft) / <alpha-value>)',
        muted: 'hsl(var(--muted) / <alpha-value>)',
        'muted-foreground': 'hsl(var(--muted-foreground) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        // Ink ramp between `foreground` and the page: body copy, then captions.
        'ink-2': 'hsl(var(--ink-2) / <alpha-value>)',
        'ink-3': 'hsl(var(--ink-3) / <alpha-value>)',
        // The dark bar, and everything that sits on it.
        chrome: 'hsl(var(--chrome) / <alpha-value>)',
        'chrome-ink': 'hsl(var(--chrome-ink) / <alpha-value>)',
        'chrome-dim': 'hsl(var(--chrome-dim) / <alpha-value>)',
        'on-chrome': 'hsl(var(--on-chrome) / <alpha-value>)',
        // The single filled action on a screen: ink by day, gold by night.
        action: {
          DEFAULT: 'hsl(var(--action) / <alpha-value>)',
          foreground: 'hsl(var(--action-foreground) / <alpha-value>)',
        },
        // Semantic feedback colours
        success: 'hsl(var(--success) / <alpha-value>)',
        warning: 'hsl(var(--warning) / <alpha-value>)',
        danger: 'hsl(var(--danger) / <alpha-value>)',
        info: 'hsl(var(--info) / <alpha-value>)',
      },
      fontFamily: {
        // Lora sets the body; Cormorant Garamond is the display face for
        // headings, buttons and figures.
        sans: ['Lora', 'Georgia', 'serif'],
        heading: ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      fontSize: {
        // Fluid titles — small phones to desktop without breakpoint juggling.
        // Larger than the old sans scale: Cormorant is drawn small on the body.
        'title-lg': ['clamp(1.625rem, 1.3rem + 1.5vw, 2.25rem)', { lineHeight: '1.1' }],
        title: ['clamp(1.3rem, 1.1rem + 0.8vw, 1.7rem)', { lineHeight: '1.15' }],
      },
      borderRadius: {
        // The ledger is square. What is left only takes the die-cut off a badge.
        '2xl': '4px',
        xl: '3px',
        lg: '2px',
        md: '2px',
        sm: '2px',
      },
      spacing: {
        // iOS notch / home-indicator insets.
        'safe-t': 'env(safe-area-inset-top, 0px)',
        'safe-b': 'env(safe-area-inset-bottom, 0px)',
        // Mobile bottom tab bar height, so pages can pad clear of it.
        tabbar: 'calc(3.75rem + env(safe-area-inset-bottom, 0px))',
        // Minimum comfortable touch target (WCAG 2.5.8 / iOS HIG).
        touch: '2.75rem',
      },
      boxShadow: {
        // Ink-tinted and shallow: paper lying on paper, not glass floating.
        card: '0 1px 2px rgb(60 45 32 / 0.08)',
        raised: '0 3px 10px rgb(60 45 32 / 0.13)',
        sheet: '0 -8px 32px -8px rgb(33 26 21 / 0.28)',
        dialog: '0 12px 40px rgb(33 26 21 / 0.28)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-up': { from: { transform: 'translateY(100%)' }, to: { transform: 'translateY(0)' } },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.96)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'slide-up': 'slide-up 240ms cubic-bezier(0.32, 0.72, 0, 1)',
        'scale-in': 'scale-in 150ms cubic-bezier(0.32, 0.72, 0, 1)',
      },
    },
  },
  plugins: [],
}
