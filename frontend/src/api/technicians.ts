import client from './client'
import { Technician } from '../types'

export async function listTechnicians(): Promise<Technician[]> {
  const { data } = await client.get<Technician[]>('/technicians')
  return data
}

export async function getTechnician(id: string): Promise<Technician> {
  const { data } = await client.get<Technician>(`/technicians/${id}`)
  return data
}

export async function updateTechnician(id: string, payload: Partial<Technician>): Promise<Technician> {
  const { data } = await client.put<Technician>(`/technicians/${id}`, payload)
  return data
}

export async function createTechnician(payload: {
  name: string
  email: string
  phone?: string
  password: string
  role: string
  specializations: string[]
  area_codes: string[]
  max_daily_calls: number
}): Promise<Technician> {
  const { data } = await client.post<Technician>('/technicians', payload)
  return data
}
