import client from './client'

export interface FilterItem {
  field: string
  op: string
  value?: any
}

export interface ReportQuery {
  entity_type: string
  columns?: string[]
  filters?: FilterItem[]
  sort_by?: string
  sort_dir?: string
  skip?: number
  limit?: number
  include_custom_fields?: boolean
}

export interface ColumnMeta {
  key: string
  label_he: string
  type: string
  filterable: boolean
}

export interface EntitySchema {
  entity_type: string
  label_he: string
  default_columns: string[]
  columns: ColumnMeta[]
}

export interface ReportResult {
  total: number
  rows: Record<string, any>[]
  columns_meta: ColumnMeta[]
}

export interface SavedView {
  id: string
  entity_type: string
  name: string
  columns: string[]
  filters: FilterItem[]
  sort_by?: string
  sort_dir: string
  is_default: boolean
  created_at?: string
  updated_at?: string
}

export const reportsApi = {
  getAllSchemas: () =>
    client.get<EntitySchema[]>('/reports/schema').then(r => r.data),

  getEntitySchema: (entityType: string) =>
    client.get<EntitySchema>(`/reports/schema/${entityType}`).then(r => r.data),

  query: (body: ReportQuery) =>
    client.post<ReportResult>('/reports/query', body).then(r => r.data),

  exportUrl: (params: {
    entity_type: string
    columns?: string
    filters?: string
    sort_by?: string
    sort_dir?: string
  }) => {
    const base = client.defaults.baseURL || ''
    const token = localStorage.getItem('token') || ''
    const qs = new URLSearchParams({ ...params } as any).toString()
    return `${base}/reports/export?${qs}`
  },

  listViews: (entityType?: string) =>
    client.get<SavedView[]>('/reports/views', { params: entityType ? { entity_type: entityType } : {} }).then(r => r.data),

  createView: (body: Partial<SavedView>) =>
    client.post<{ id: string; name: string }>('/reports/views', body).then(r => r.data),

  updateView: (id: string, body: Partial<SavedView>) =>
    client.put(`/reports/views/${id}`, body).then(r => r.data),

  deleteView: (id: string) =>
    client.delete(`/reports/views/${id}`),

  setDefaultView: (id: string) =>
    client.post(`/reports/views/${id}/set-default`).then(r => r.data),
}
