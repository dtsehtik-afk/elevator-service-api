import client from './client'
import { Technician } from '../types'

export async function login(email: string, password: string): Promise<string> {
  const params = new URLSearchParams()
  params.append('username', email)
  params.append('password', password)
  const { data } = await client.post<{ access_token: string }>('/auth/login', params, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
  return data.access_token
}

export async function getMe(): Promise<Technician> {
  const { data } = await client.get<Technician>('/auth/me')
  return data
}
