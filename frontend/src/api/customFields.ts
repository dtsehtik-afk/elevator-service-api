import client from './client'

export interface CustomField {
  id: string
  entity_type: string
  field_name: string
  field_label: string
  field_type: string
  options?: string[] | null
  required: boolean
  is_active: boolean
  display_order: number
  created_at?: string
}

export interface CustomFieldValue {
  field_id: string
  field_name: string
  field_label: string
  field_type: string
  options?: string[] | null
  required: boolean
  value?: string | null
}

export const customFieldsApi = {
  list: (entityType: string, includeInactive = false) =>
    client.get<CustomField[]>(`/custom-fields/${entityType}`, {
      params: { include_inactive: includeInactive },
    }).then(r => r.data),

  create: (data: {
    entity_type: string
    field_label: string
    field_name?: string
    field_type?: string
    options?: string[]
    required?: boolean
    display_order?: number
  }) =>
    client.post<CustomField>('/custom-fields', data).then(r => r.data),

  update: (id: string, data: Partial<CustomField>) =>
    client.put<CustomField>(`/custom-fields/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/custom-fields/${id}`),

  reorder: (items: { id: string; display_order: number }[]) =>
    client.post('/custom-fields/reorder', items).then(r => r.data),

  getValues: (entityType: string, entityId: string) =>
    client.get<CustomFieldValue[]>(`/custom-fields/values/${entityType}/${entityId}`).then(r => r.data),

  setValues: (entityType: string, entityId: string, values: Record<string, any>) =>
    client.put(`/custom-fields/values/${entityType}/${entityId}`, values).then(r => r.data),
}
