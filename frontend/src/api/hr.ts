import client from './client'

export interface HRProfile {
  technician_id: string
  name: string
  email: string
  phone?: string
  role: string
  is_available: boolean
  is_active: boolean
  hr_id?: string
  employment_start?: string
  employment_end?: string
  employment_type?: string
  salary_type?: string
  base_salary?: number
  hourly_rate?: number
  id_number?: string
  bank_account?: string
  emergency_contact?: string
  emergency_phone?: string
  notes?: string
}

export interface HRStats {
  total_staff: number
  available: number
  by_employment_type: Record<string, number>
  by_role: Record<string, number>
  avg_salary?: number
}

export const hrApi = {
  stats: () =>
    client.get<HRStats>('/hr/stats').then(r => r.data),

  list: () =>
    client.get<HRProfile[]>('/hr').then(r => r.data),

  get: (technicianId: string) =>
    client.get<HRProfile>(`/hr/${technicianId}`).then(r => r.data),

  upsert: (technicianId: string, data: Partial<HRProfile>) =>
    client.put<HRProfile>(`/hr/${technicianId}`, data).then(r => r.data),
}
