import client from './client'
import type { Part } from '../types'

export const inventoryApi = {
  list: (params?: { search?: string; category?: string; low_stock?: boolean; is_active?: boolean; skip?: number; limit?: number }) =>
    client.get<Part[]>('/inventory', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Part>(`/inventory/${id}`).then(r => r.data),

  create: (data: Partial<Part>) =>
    client.post<Part>('/inventory', data).then(r => r.data),

  update: (id: string, data: Partial<Part>) =>
    client.patch<Part>(`/inventory/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/inventory/${id}`),

  adjustStock: (id: string, delta: number) =>
    client.patch<{ part_id: string; new_quantity: number; is_low_stock: boolean }>(`/inventory/${id}/adjust-stock`, null, { params: { delta } }).then(r => r.data),

  categories: () =>
    client.get<string[]>('/inventory/categories').then(r => r.data),

  recordUsage: (data: { part_id: string; service_call_id?: string; quantity: number; notes?: string }) =>
    client.post('/inventory/usage', data).then(r => r.data),

  usageByCall: (serviceCallId: string) =>
    client.get(`/inventory/usage/by-call/${serviceCallId}`).then(r => r.data),
}
