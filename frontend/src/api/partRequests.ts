import client from './client'
import type { PartRequest } from '../types'

export async function listPartRequests(params: { service_call_id?: string; status?: string } = {}): Promise<PartRequest[]> {
  const { data } = await client.get<PartRequest[]>('/part-requests', { params })
  return data
}

export async function createPartRequest(payload: {
  service_call_id: string
  part_id: string
  quantity: number
  source_warehouse_id?: string | null
  notes?: string | null
}): Promise<PartRequest> {
  const { data } = await client.post<PartRequest>('/part-requests', payload)
  return data
}

export async function approvePartRequest(id: string, approval_notes?: string): Promise<PartRequest> {
  const { data } = await client.post<PartRequest>(`/part-requests/${id}/approve`, { approval_notes })
  return data
}

export async function rejectPartRequest(id: string, rejection_reason: string): Promise<PartRequest> {
  const { data } = await client.post<PartRequest>(`/part-requests/${id}/reject`, { rejection_reason })
  return data
}

export async function issuePartRequest(id: string): Promise<PartRequest> {
  const { data } = await client.post<PartRequest>(`/part-requests/${id}/issue`)
  return data
}

export async function returnFaultyPart(id: string): Promise<PartRequest> {
  const { data } = await client.post<PartRequest>(`/part-requests/${id}/return-faulty`)
  return data
}

export async function getPendingPartRequestsCount(): Promise<number> {
  const { data } = await client.get<{ count: number }>('/part-requests/pending-count')
  return data.count
}
