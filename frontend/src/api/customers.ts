import client from './client'
import type { Customer, CustomerDetail } from '../types'

export const customersApi = {
  list: (params?: { search?: string; customer_type?: string; city?: string; is_active?: boolean; parent_only?: boolean; skip?: number; limit?: number }) =>
    client.get<Customer[]>('/customers', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<CustomerDetail>(`/customers/${id}`).then(r => r.data),

  create: (data: Partial<Customer>) =>
    client.post<Customer>('/customers', data).then(r => r.data),

  update: (id: string, data: Partial<Customer>) =>
    client.patch<Customer>(`/customers/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/customers/${id}`),

  related: (id: string) =>
    client.get(`/customers/${id}/related`).then(r => r.data),
}
