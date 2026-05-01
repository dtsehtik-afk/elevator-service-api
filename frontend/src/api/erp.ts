import client from './client'
import type { ERPDashboard } from '../types'

export const erpApi = {
  dashboard: () =>
    client.get<ERPDashboard>('/erp/dashboard').then(r => r.data),

  related: (entityType: string, entityId: string) =>
    client.get(`/erp/related/${entityType}/${entityId}`).then(r => r.data),
}
