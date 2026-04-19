export interface Elevator {
  id: string
  // Identity
  internal_number: string | null
  labor_file_number: string | null
  // Location
  building_id: string | null
  address: string
  city: string
  latitude: number | null
  longitude: number | null
  // Description
  building_name: string | null
  notes: string | null
  // Technical
  floor_count: number
  model: string | null
  manufacturer: string | null
  installation_date: string | null
  serial_number: string | null
  warranty_end: string | null
  is_coded: boolean
  entry_code: string | null
  // Contact
  contact_phone: string | null
  intercom_phone: string | null
  caller_phones: string[]
  // Service
  service_type: 'REGULAR' | 'COMPREHENSIVE' | null
  service_contract: 'ANNUAL_6' | 'ANNUAL_12' | null
  maintenance_interval_days: number | null
  contract_start: string | null
  contract_renewal: string | null
  contract_end: string | null
  drive_link: string | null
  // Debt
  has_debt: boolean
  debt_freeze_date: string | null
  // Maintenance
  last_service_date: string | null
  next_service_date: string | null
  // Inspection
  last_inspection_date: string | null
  next_inspection_date: string | null
  inspector_name: string | null
  inspector_phone: string | null
  inspector_mobile: string | null
  inspector_email: string | null
  last_inspection_report_url: string | null
  // Status
  status: 'ACTIVE' | 'INACTIVE' | 'UNDER_REPAIR'
  risk_score: number
  // Grouping
  management_company_id: string | null
  management_company_name: string | null
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
  fault_type: 'MECHANICAL' | 'ELECTRICAL' | 'SOFTWARE' | 'STUCK' | 'DOOR' | 'RESCUE' | 'OTHER'
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
  last_location_at: string | null
  base_latitude: number | null
  base_longitude: number | null
  is_available: boolean
  is_active: boolean
  is_on_call: boolean
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
