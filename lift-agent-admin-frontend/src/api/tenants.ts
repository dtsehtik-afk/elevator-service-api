import api from './client'

export interface Module { module: string; enabled: boolean }

export interface Tenant {
  id: string
  name: string
  slug: string
  domain: string | null
  api_url: string | null
  api_key: string | null
  plan: string
  is_active: boolean
  is_demo: boolean
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
  monthly_price: number | null
  billing_notes: string | null
  stats: Record<string, unknown> | null
  stats_refreshed_at: string | null
  last_seen_at: string | null
  created_at: string | null
  modules: Module[]
}

export const listTenants = () => api.get<Tenant[]>('/tenants').then((r) => r.data)
export const getTenant = (id: string) => api.get<Tenant>(`/tenants/${id}`).then((r) => r.data)
export const createTenant = (body: Partial<Tenant> & { slug: string; name: string }) =>
  api.post<Tenant>('/tenants', body).then((r) => r.data)
export const updateTenant = (id: string, body: Partial<Tenant>) =>
  api.patch<Tenant>(`/tenants/${id}`, body).then((r) => r.data)
export const deleteTenant = (id: string) => api.delete(`/tenants/${id}`).then((r) => r.data)
export const setModules = (id: string, modules: Module[]) =>
  api.put(`/tenants/${id}/modules`, modules).then((r) => r.data)
export const getTenantStats = (id: string) => api.get(`/stats/${id}`).then((r) => r.data)
export const pingTenant = (id: string) => api.post(`/stats/${id}/ping`).then((r) => r.data)
