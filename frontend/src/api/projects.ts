import client from './client'

export interface Project {
  id: string
  name: string
  site: string | null
  status: 'PLANNING' | 'ACTIVE' | 'ON_HOLD' | 'COMPLETED' | 'CANCELLED'
  start_date: string | null
  end_date: string | null
  notes: string | null
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

  createTask: (projectId: string, data: Partial<ProjectTask>) =>
    client.post<ProjectTask>(`/projects/${projectId}/tasks`, data).then(r => r.data),

  updateTask: (projectId: string, taskId: string, data: Partial<ProjectTask>) =>
    client.patch<ProjectTask>(`/projects/${projectId}/tasks/${taskId}`, data).then(r => r.data),

  deleteTask: (projectId: string, taskId: string) =>
    client.delete(`/projects/${projectId}/tasks/${taskId}`),
}
