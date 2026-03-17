import { create } from 'zustand'

interface UIState {
  sidebarOpen: boolean
  pendingCount: number
  setSidebarOpen: (open: boolean) => void
  setPendingCount: (count: number) => void
}

export const useUIStore = create<UIState>((set) => ({
  sidebarOpen: true,
  pendingCount: 0,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  setPendingCount: (count) => set({ pendingCount: count }),
}))
