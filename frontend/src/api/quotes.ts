import client from './client'
import type { Quote } from '../types'

export const quotesApi = {
  list: (params?: { customer_id?: string; status?: string; skip?: number; limit?: number }) =>
    client.get<Quote[]>('/quotes', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Quote>(`/quotes/${id}`).then(r => r.data),

  create: (data: Partial<Quote>) =>
    client.post<Quote>('/quotes', data).then(r => r.data),

  update: (id: string, data: Partial<Quote>) =>
    client.patch<Quote>(`/quotes/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/quotes/${id}`),

  convertToContract: (id: string) =>
    client.post<{ contract_id: string; contract_number: string }>(`/quotes/${id}/convert-to-contract`).then(r => r.data),
}
