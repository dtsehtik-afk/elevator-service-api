import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  userName: string | null
  userRole: string | null
  setAuth: (token: string, name: string, role: string) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      userName: null,
      userRole: null,
      setAuth: (token, userName, userRole) => set({ token, userName, userRole }),
      clear: () => set({ token: null, userName: null, userRole: null }),
    }),
    { name: 'elevator-auth' }
  )
)
