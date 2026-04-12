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
        border: 'hsl(var(--border) / <alpha-value>)',
        muted: 'hsl(var(--muted) / <alpha-value>)',
        'muted-foreground': 'hsl(var(--muted-foreground) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        // Appointment status colors (fixed, no dark mode variant needed)
        'status-pending': '#F59E0B',
        'status-confirmed': '#10B981',
        'status-completed': '#6B7280',
        'status-cancelled': '#EF4444',
        'status-rejected': '#DC2626',
        'status-rescheduled': '#3B82F6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.625rem',
        md: '0.5rem',
        sm: '0.375rem',
      },
    },
  },
  plugins: [],
}
