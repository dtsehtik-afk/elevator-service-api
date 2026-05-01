import client from './client'
import type { Contract } from '../types'

export const contractsApi = {
  list: (params?: { customer_id?: string; status?: string; contract_type?: string; skip?: number; limit?: number }) =>
    client.get<Contract[]>('/contracts', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Contract>(`/contracts/${id}`).then(r => r.data),

  create: (data: Partial<Contract> & { elevator_ids?: string[] }) =>
    client.post<Contract>('/contracts', data).then(r => r.data),

  update: (id: string, data: Partial<Contract> & { elevator_ids?: string[] }) =>
    client.patch<Contract>(`/contracts/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/contracts/${id}`),

  elevators: (id: string) =>
    client.get<{ id: string; address: string; city: string; status: string }[]>(`/contracts/${id}/elevators`).then(r => r.data),
}
