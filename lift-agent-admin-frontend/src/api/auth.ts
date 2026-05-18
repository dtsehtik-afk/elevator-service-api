import api from './client'

export type LoginResult =
  | { mfa_required: false; access_token: string }
  | { mfa_required: true; pending_token: string }

export const login = async (email: string, password: string): Promise<LoginResult> => {
  const { data } = await api.post<{ mfa_required?: true; pending_token?: string; access_token?: string }>(
    '/auth/login',
    new URLSearchParams({ username: email, password }),
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
  )
  if (data.mfa_required) return { mfa_required: true, pending_token: data.pending_token! }
  return { mfa_required: false, access_token: data.access_token! }
}

export const verifyTotp = async (pendingToken: string, code: string): Promise<string> => {
  const { data } = await api.post<{ access_token: string }>('/auth/totp/verify', { pending_token: pendingToken, code })
  return data.access_token
}

export const getMe = () => api.get<{ id: string; name: string; email: string; totp_enabled: boolean }>('/auth/me').then((r) => r.data)

export const totpSetup = () => api.post<{ secret: string; otpauth_uri: string }>('/auth/totp/setup').then(r => r.data)
export const totpConfirm = (code: string) => api.post('/auth/totp/confirm', { code })
export const totpDisable = (code: string) => api.post('/auth/totp/disable', { code })
export const totpStatus = () => api.get<{ totp_enabled: boolean }>('/auth/totp/status').then(r => r.data)
export const loginHistory = () => api.get<{ ip_address: string; user_agent: string; success: boolean; created_at: string }[]>('/auth/login-history').then(r => r.data)
