import client from './client'
import { Technician } from '../types'

export type LoginResult =
  | { mfa_required: false; access_token: string }
  | { mfa_required: true; pending_token: string }

export async function login(email: string, password: string): Promise<LoginResult> {
  const params = new URLSearchParams()
  params.append('username', email)
  params.append('password', password)
  const { data } = await client.post<
    { mfa_required: true; pending_token: string } | { access_token: string }
  >('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  if ('mfa_required' in data && data.mfa_required) {
    return { mfa_required: true, pending_token: data.pending_token }
  }
  return { mfa_required: false, access_token: (data as { access_token: string }).access_token }
}

export async function verifyTotp(pendingToken: string, code: string): Promise<string> {
  const { data } = await client.post<{ access_token: string }>('/auth/totp/verify', {
    pending_token: pendingToken,
    code,
  })
  return data.access_token
}

export async function getMe(): Promise<Technician> {
  const { data } = await client.get<Technician>('/auth/me')
  return data
}

export async function forgotPassword(phone: string): Promise<void> {
  await client.post('/auth/forgot-password', { phone })
}

export async function resetPassword(phone: string, otp: string, newPassword: string): Promise<void> {
  await client.post('/auth/reset-password', { phone, otp, new_password: newPassword })
}

export async function totpSetup(): Promise<{ secret: string; otpauth_uri: string }> {
  const { data } = await client.post('/auth/totp/setup')
  return data
}

export async function totpConfirm(code: string): Promise<void> {
  await client.post('/auth/totp/confirm', { code })
}

export async function totpDisable(code: string): Promise<void> {
  await client.post('/auth/totp/disable', { code })
}

export async function totpStatus(): Promise<{ totp_enabled: boolean }> {
  const { data } = await client.get('/auth/totp/status')
  return data
}

export async function loginHistory(): Promise<
  { ip_address: string; user_agent: string; success: boolean; created_at: string }[]
> {
  const { data } = await client.get('/auth/login-history')
  return data
}
