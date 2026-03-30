import client from './client'
import { MaintenanceSchedule } from '../types'

export async function listMaintenance(filters: { status?: string; skip?: number; limit?: number } = {}): Promise<MaintenanceSchedule[]> {
  const { data } = await client.get<MaintenanceSchedule[]>('/maintenance', { params: { limit: 200, ...filters } })
  return data
}

export async function createMaintenance(payload: {
  elevator_id: string
  technician_id?: string
  scheduled_date: string
  maintenance_type: string
}): Promise<MaintenanceSchedule> {
  const { data } = await client.post<MaintenanceSchedule>('/maintenance', payload)
  return data
}

export async function updateMaintenance(id: string, payload: {
  status?: string
  completion_notes?: string
}): Promise<MaintenanceSchedule> {
  const { data } = await client.patch<MaintenanceSchedule>(`/maintenance/${id}`, payload)
  return data
}
