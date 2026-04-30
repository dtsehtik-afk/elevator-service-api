import client from './client'
import type { Invoice, Receipt } from '../types'

export const invoicesApi = {
  list: (params?: { customer_id?: string; status?: string; skip?: number; limit?: number }) =>
    client.get<Invoice[]>('/invoices', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<Invoice>(`/invoices/${id}`).then(r => r.data),

  create: (data: Partial<Invoice>) =>
    client.post<Invoice>('/invoices', data).then(r => r.data),

  update: (id: string, data: Partial<Invoice>) =>
    client.patch<Invoice>(`/invoices/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/invoices/${id}`),

  addReceipt: (invoiceId: string, data: Partial<Receipt>) =>
    client.post<Receipt>(`/invoices/${invoiceId}/receipts`, data).then(r => r.data),

  receipts: (invoiceId: string) =>
    client.get<Receipt[]>(`/invoices/${invoiceId}/receipts`).then(r => r.data),

  debtors: () =>
    client.get<{ customer_id: string; customer_name: string; total_billed: number; total_paid: number; balance: number }[]>('/invoices/summary/debtors').then(r => r.data),
}
