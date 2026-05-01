import axios from 'axios'

export const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const raw = localStorage.getItem('cp-auth')
  if (raw) {
    const { state } = JSON.parse(raw)
    if (state?.token) config.headers.Authorization = `Bearer ${state.token}`
  }
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('cp-auth')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Tenant {
  id: string
  name: string
  slug: string
  contact_email: string
  contact_phone: string | null
  api_url: string | null
  api_key: string
  status: 'PENDING' | 'DEPLOYING' | 'ACTIVE' | 'SUSPENDED' | 'ERROR' | 'CANCELLED'
  plan: 'TRIAL' | 'BASIC' | 'PRO' | 'ENTERPRISE'
  billing_active: boolean
  stripe_customer_id: string | null
  hetzner_server_id: number | null
  hetzner_server_ip: string | null
  modules: Record<string, boolean>
  is_healthy: boolean
  last_seen_at: string | null
  last_stats: Record<string, unknown> | null
  created_at: string
  notes: string | null
}

export interface TenantSnapshot {
  id: string
  tenant_id: string
  captured_at: string
  is_healthy: boolean
  stats: Record<string, unknown> | null
  error: string | null
}

export interface HealthOverviewItem {
  tenant_id: string
  tenant_name: string
  status: string
  is_healthy: boolean
  last_seen_at: string | null
  last_stats: Record<string, unknown> | null
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const login = (email: string, password: string) =>
  api.post<{ access_token: string }>('/auth/login', new URLSearchParams({ username: email, password }))

// ── Tenants ───────────────────────────────────────────────────────────────────

export const fetchTenants = () => api.get<Tenant[]>('/tenants').then((r) => r.data)
export const fetchTenant = (id: string) => api.get<Tenant>(`/tenants/${id}`).then((r) => r.data)
export const createTenant = (body: Partial<Tenant>) => api.post<Tenant>('/tenants', body).then((r) => r.data)
export const updateTenant = (id: string, body: Partial<Tenant>) => api.patch<Tenant>(`/tenants/${id}`, body).then((r) => r.data)
export const deleteTenant = (id: string) => api.delete(`/tenants/${id}`)
export const rotateKey = (id: string) => api.post<Tenant>(`/tenants/${id}/rotate-key`).then((r) => r.data)

// ── Modules ───────────────────────────────────────────────────────────────────

export const fetchModules = (id: string) => api.get<{ tenant_id: string; modules: Record<string, boolean> }>(`/tenants/${id}/modules`).then((r) => r.data)
export const updateModules = (id: string, modules: Record<string, boolean>) =>
  api.post<{ tenant_id: string; modules: Record<string, boolean> }>(`/tenants/${id}/modules`, { modules }).then((r) => r.data)
export const syncModules = (id: string) => api.post(`/tenants/${id}/modules/sync`).then((r) => r.data)

// ── Deploy ────────────────────────────────────────────────────────────────────

export const deployTenant = (id: string, body: Record<string, string>) =>
  api.post(`/tenants/${id}/deploy`, body).then((r) => r.data)
export const destroyServer = (id: string) => api.delete(`/tenants/${id}/deploy`).then((r) => r.data)
export const fetchDeployStatus = (id: string) => api.get(`/tenants/${id}/deploy/status`).then((r) => r.data)
export const provisionSSL = (id: string) => api.post(`/tenants/${id}/deploy/ssl`).then((r) => r.data)

// ── Billing ───────────────────────────────────────────────────────────────────

export const createSubscription = (tenantId: string, plan: string, paymentMethodId: string) =>
  api.post('/billing/subscribe', { tenant_id: tenantId, plan, payment_method_id: paymentMethodId }).then((r) => r.data)

export const cancelSubscription = (tenantId: string) =>
  api.delete(`/billing/${tenantId}/cancel`).then((r) => r.data)

// ── Monitoring ────────────────────────────────────────────────────────────────

export const fetchSnapshots = (id: string, limit = 48) =>
  api.get<TenantSnapshot[]>(`/tenants/${id}/monitoring`, { params: { limit } }).then((r) => r.data)
export const pollNow = (id: string) => api.post<TenantSnapshot>(`/tenants/${id}/monitoring/poll`).then((r) => r.data)
export const fetchHealthOverview = () => api.get<HealthOverviewItem[]>('/monitoring/overview').then((r) => r.data)
