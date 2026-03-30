import client from './client'
import { Elevator, ElevatorFilters } from '../types'

export async function listElevators(filters: ElevatorFilters = {}): Promise<Elevator[]> {
  const { data } = await client.get<Elevator[]>('/elevators', { params: { limit: 200, ...filters } })
  return data
}

export async function getElevator(id: string): Promise<Elevator> {
  const { data } = await client.get<Elevator>(`/elevators/${id}`)
  return data
}

export async function updateElevator(id: string, payload: Partial<Elevator>): Promise<Elevator> {
  const { data } = await client.put<Elevator>(`/elevators/${id}`, payload)
  return data
}

export async function createElevator(payload: Omit<Elevator, 'id' | 'risk_score' | 'created_at' | 'updated_at'>): Promise<Elevator> {
  const { data } = await client.post<Elevator>('/elevators', payload)
  return data
}

export async function getElevatorCalls(id: string) {
  const { data } = await client.get(`/elevators/${id}/calls`)
  return data
}

export async function getElevatorAnalytics(id: string) {
  const { data } = await client.get(`/elevators/${id}/analytics`)
  return data
}
