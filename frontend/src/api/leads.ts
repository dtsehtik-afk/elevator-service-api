import client from './client'
import type { Lead } from '../types'

export const leadsApi = {
  list: (params?: { status?: string; owner?: string; source?: string; skip?: number; limit?: number }) =>
    client.get<Lead[]>('/leads', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Lead>(`/leads/${id}`).then(r => r.data),

  create: (data: Partial<Lead>) =>
    client.post<Lead>('/leads', data).then(r => r.data),

  update: (id: string, data: Partial<Lead>) =>
    client.patch<Lead>(`/leads/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/leads/${id}`),

  convert: (id: string) =>
    client.post<{ customer_id: string; customer_name: string }>(`/leads/${id}/convert`).then(r => r.data),

  kanban: () =>
    client.get<Record<string, { id: string; name: string; company: string | null; phone: string | null; estimated_value: number | null; owner: string | null; stage: string | null }[]>>('/leads/board/kanban').then(r => r.data),
}
