import { create } from 'zustand'

// Initialize dark mode from localStorage or system preference
const storedTheme = localStorage.getItem('theme')
const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
const initialDark = storedTheme ? storedTheme === 'dark' : prefersDark

if (initialDark) {
  document.documentElement.classList.add('dark')
} else {
  document.documentElement.classList.remove('dark')
}

interface UIState {
  sidebarOpen: boolean
  pendingCount: number
  isDark: boolean
  setSidebarOpen: (open: boolean) => void
  setPendingCount: (count: number) => void
  toggleDark: () => void
}

export const useUIStore = create<UIState>((set, get) => ({
  sidebarOpen: true,
  pendingCount: 0,
  isDark: initialDark,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setPendingCount: (count) => set({ pendingCount: count }),
  toggleDark: () => {
    const next = !get().isDark
    if (next) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
    set({ isDark: next })
  },
}))
