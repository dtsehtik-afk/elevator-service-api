import api from './client'

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>('/auth/login', new URLSearchParams({ username: email, password }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  ).then((r) => r.data)

export const getMe = () => api.get<{ id: string; name: string; email: string }>('/auth/me').then((r) => r.data)
