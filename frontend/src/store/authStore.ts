import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '@/types'
import { setTokens, clearTokens } from '@/services/api'
import type { TokenResponse } from '@/types'

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  login: (tokens: TokenResponse, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      login: (tokens, user) => {
        setTokens(tokens)
        set({ user, isAuthenticated: true })
      },
      logout: () => {
        clearTokens()
        set({ user: null, isAuthenticated: false })
      },
      setUser: (user) => set({ user }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ user: state.user, isAuthenticated: state.isAuthenticated }),
    }
  )
)
