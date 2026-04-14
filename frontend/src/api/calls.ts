import client from './client'
import { ServiceCall, CallDetail, AuditLogEntry, CallFilters } from '../types'

export async function listCalls(filters: CallFilters = {}): Promise<ServiceCall[]> {
  const { data } = await client.get<ServiceCall[]>('/calls', { params: { limit: 200, ...filters } })
  return data
}

export async function getCall(id: string): Promise<ServiceCall> {
  const { data } = await client.get<ServiceCall>(`/calls/${id}`)
  return data
}

export async function createCall(payload: {
  elevator_id: string
  reported_by: string
  description: string
  priority: string
  fault_type: string
}): Promise<ServiceCall> {
  const { data } = await client.post<ServiceCall>('/calls', payload)
  return data
}

export async function updateCall(id: string, payload: {
  status?: string
  priority?: string
  fault_type?: string
  resolution_notes?: string
  quote_needed?: boolean
}): Promise<ServiceCall> {
  const { data } = await client.patch<ServiceCall>(`/calls/${id}`, payload)
  return data
}

export async function getCallDetails(id: string): Promise<CallDetail> {
  const { data } = await client.get<CallDetail>(`/calls/${id}/details`)
  return data
}

export async function getCallAudit(id: string): Promise<AuditLogEntry[]> {
  const { data } = await client.get<AuditLogEntry[]>(`/calls/${id}/audit`)
  return data
}

export async function autoAssignCall(id: string): Promise<void> {
  await client.post(`/calls/${id}/auto-assign`)
}

export async function setCallMonitoring(id: string, notes: string): Promise<ServiceCall> {
  const { data } = await client.post<ServiceCall>(`/calls/${id}/monitor`, null, { params: { notes } })
  return data
}

export async function manualAssignCall(id: string, technicianId: string, notes?: string): Promise<void> {
  await client.post(`/calls/${id}/assign`, { technician_id: technicianId, notes })
}

export async function resetAndReassignCall(id: string): Promise<void> {
  await client.post(`/calls/${id}/reset-and-reassign`)
}
