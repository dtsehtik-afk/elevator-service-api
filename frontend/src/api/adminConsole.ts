import client from './client'

export interface AdminLog {
  id: string
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'
  source: string | null
  message: string
  stack_trace: string | null
  created_at: string
}

export interface HealthResponse {
  status: string
  uptime_seconds: number
  db_ok: boolean
  python_version: string
  server_time: string
  log_counts: Record<string, number>
}

export const adminConsoleApi = {
  getHealth: () => client.get<HealthResponse>('/admin-console/health').then(r => r.data),

  getLogs: (params?: { level?: string; source?: string; search?: string; skip?: number; limit?: number }) =>
    client.get<AdminLog[]>('/admin-console/logs', { params }).then(r => r.data),

  writeLog: (data: { level: string; source: string; message: string }) =>
    client.post<AdminLog>('/admin-console/logs', data).then(r => r.data),

  clearLogs: (level?: string) =>
    client.delete<{ deleted: number }>('/admin-console/logs', { params: level ? { level } : {} }).then(r => r.data),

  getModules: () => client.get<Record<string, boolean>>('/admin-console/modules').then(r => r.data),

  updateModules: (data: Record<string, boolean>) =>
    client.put<Record<string, boolean>>('/admin-console/modules', data).then(r => r.data),
}
