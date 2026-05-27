import client from './client'

export interface Project {
  id: string
  name: string
  site: string | null
  address: string | null
  city: string | null
  status: 'PLANNING' | 'ACTIVE' | 'ON_HOLD' | 'COMPLETED' | 'CANCELLED'
  project_type: string | null
  start_date: string | null
  end_date: string | null
  elevator_count: number | null
  manufacturer: string | null
  contract_value: number | null
  customer_id: string | null
  customer_name: string | null
  contact_person: string | null
  contact_phone: string | null
  consultant_id: string | null
  consultant_name: string | null
  consultant_phone: string | null
  consultant_email: string | null
  consultant_contacts: Array<{ name?: string; phone?: string; email?: string }>
  responsible_technician_id: string | null
  responsible_technician_name: string | null
  notes: string | null
  // Installation milestones
  milestone_elevator_arrived: boolean
  milestone_installation_started: boolean
  milestone_phase_a: boolean
  milestone_phase_b: boolean
  milestone_phase_c: boolean
  milestone_initial_inspection: boolean
  milestone_consultant_approved: boolean
  has_service_contract: boolean
  task_count: number
  created_at: string
  updated_at: string
}

export interface ProjectTask {
  id: string
  project_id: string
  name: string
  assignee: string | null
  start_date: string | null
  end_date: string | null
  status: 'PENDING' | 'IN_PROGRESS' | 'DONE' | 'BLOCKED'
  progress: number
  notes: string | null
  created_at: string
}

export interface ProjectDetail extends Project {
  tasks: ProjectTask[]
}

export const projectsApi = {
  list: (params?: { status?: string }) =>
    client.get<Project[]>('/projects', { params }).then(r => r.data),

  get: (id: string) =>
    client.get<ProjectDetail>(`/projects/${id}`).then(r => r.data),

  create: (data: Partial<Project>) =>
    client.post<Project>('/projects', data).then(r => r.data),

  update: (id: string, data: Partial<Project>) =>
    client.patch<Project>(`/projects/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    client.delete(`/projects/${id}`),

  updateMilestone: (id: string, field: string, value: boolean) =>
    client.patch<Project>(`/projects/${id}`, { [field]: value }).then(r => r.data),

  createTask: (projectId: string, data: Partial<ProjectTask>) =>
    client.post<ProjectTask>(`/projects/${projectId}/tasks`, data).then(r => r.data),

  updateTask: (projectId: string, taskId: string, data: Partial<ProjectTask>) =>
    client.patch<ProjectTask>(`/projects/${projectId}/tasks/${taskId}`, data).then(r => r.data),

  deleteTask: (projectId: string, taskId: string) =>
    client.delete(`/projects/${projectId}/tasks/${taskId}`),
}
