/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#C8A96E',
          dark: '#A07840',
          light: '#E8D5B0',
          foreground: '#FFFFFF',
        },
        background: '#FAFAF8',
        surface: '#FFFFFF',
        border: '#E5E0D8',
        muted: '#F5F2EE',
        'muted-foreground': '#8A7968',
        foreground: '#1A1A1A',
        // Appointment status colors
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
