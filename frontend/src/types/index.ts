export interface Elevator {
  id: string
  address: string
  city: string
  building_name: string | null
  floor_count: number
  model: string | null
  manufacturer: string | null
  installation_date: string | null
  serial_number: string | null
  last_service_date: string | null
  next_service_date: string | null
  status: 'ACTIVE' | 'INACTIVE' | 'UNDER_REPAIR'
  risk_score: number
  created_at: string
  updated_at: string
}

export interface ServiceCall {
  id: string
  elevator_id: string
  reported_by: string
  description: string
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  status: 'OPEN' | 'ASSIGNED' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED'
  fault_type: 'MECHANICAL' | 'ELECTRICAL' | 'SOFTWARE' | 'STUCK' | 'DOOR' | 'OTHER'
  is_recurring: boolean
  resolution_notes: string | null
  quote_needed: boolean
  created_at: string
  assigned_at: string | null
  resolved_at: string | null
}

export interface AssignmentDetail {
  id: string
  technician_id: string
  technician_name: string
  assignment_type: string
  status: string
  travel_minutes: number | null
  assigned_at: string
}

export interface AuditLogEntry {
  id: string
  service_call_id: string
  changed_by: string
  old_status: string | null
  new_status: string
  notes: string | null
  changed_at: string
}

export interface CallDetail extends ServiceCall {
  elevator_address: string
  elevator_city: string
  elevator_serial: string | null
  assignments: AssignmentDetail[]
  audit_logs: AuditLogEntry[]
}

export interface Technician {
  id: string
  name: string
  email: string
  phone: string | null
  whatsapp_number: string | null
  role: 'ADMIN' | 'TECHNICIAN' | 'DISPATCHER'
  specializations: string[]
  current_latitude: number | null
  current_longitude: number | null
  is_available: boolean
  is_active: boolean
  max_daily_calls: number
  area_codes: string[]
  created_at: string
}

export interface MaintenanceSchedule {
  id: string
  elevator_id: string
  technician_id: string | null
  scheduled_date: string
  maintenance_type: 'ROUTINE' | 'INSPECTION' | 'EMERGENCY' | 'ANNUAL'
  status: 'SCHEDULED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
  checklist: Record<string, boolean> | null
  completion_notes: string | null
  completed_at: string | null
  reminder_sent: string
  created_at: string
  updated_at: string
}

export interface ElevatorFilters {
  city?: string
  status?: string
  skip?: number
  limit?: number
}

export interface CallFilters {
  status?: string
  priority?: string
  fault_type?: string
  skip?: number
  limit?: number
}
