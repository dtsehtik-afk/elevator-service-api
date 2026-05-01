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
  customer_id: string | null
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
  fault_type: 'MECHANICAL' | 'ELECTRICAL' | 'SOFTWARE' | 'STUCK' | 'DOOR' | 'RESCUE' | 'MAINTENANCE' | 'OTHER'
  is_recurring: boolean
  resolution_notes: string | null
  quote_needed: boolean
  technician_id: string | null
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
  technician_id?: string
  skip?: number
  limit?: number
}

// ── ERP Types ──────────────────────────────────────────────────────────────

export interface Customer {
  id: string
  name: string
  customer_type: 'OWNER' | 'MANAGEMENT_COMPANY' | 'COMMITTEE' | 'PRIVATE' | 'CORPORATE'
  parent_id: string | null
  parent_name: string | null
  phone: string | null
  email: string | null
  address: string | null
  city: string | null
  contact_person: string | null
  vat_number: string | null
  payment_terms: number
  credit_limit: number | null
  notes: string | null
  is_active: boolean
  children_count: number
  elevator_count: number
  active_contracts: number
  open_invoices: number
  created_at: string
  updated_at: string
}

export interface CustomerDetail extends Customer {
  children: { id: string; name: string; customer_type: string }[]
}

export interface QuoteItem {
  description: string
  quantity: number
  unit_price: number
  total: number
}

export interface Quote {
  id: string
  number: string
  customer_id: string
  customer_name: string | null
  elevator_id: string | null
  elevator_address: string | null
  items: QuoteItem[]
  subtotal: number
  vat_rate: number
  vat_amount: number
  total: number
  status: 'DRAFT' | 'SENT' | 'ACCEPTED' | 'REJECTED' | 'EXPIRED'
  valid_until: string | null
  notes: string | null
  contract_id: string | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface Contract {
  id: string
  number: string
  customer_id: string
  customer_name: string | null
  contract_type: 'SERVICE' | 'MAINTENANCE' | 'INSPECTION' | 'RENOVATION' | 'OTHER'
  status: 'PENDING' | 'ACTIVE' | 'EXPIRED' | 'CANCELLED'
  start_date: string | null
  end_date: string | null
  monthly_price: number | null
  total_value: number | null
  payment_terms: number
  auto_invoice: boolean
  invoice_frequency: string | null
  last_invoiced_at: string | null
  notes: string | null
  elevator_count: number
  created_at: string
  updated_at: string
}

export interface Invoice {
  id: string
  number: string
  customer_id: string
  customer_name: string | null
  contract_id: string | null
  items: QuoteItem[]
  subtotal: number
  vat_rate: number
  vat_amount: number
  total: number
  amount_paid: number
  balance: number
  status: 'DRAFT' | 'SENT' | 'PAID' | 'PARTIAL' | 'OVERDUE' | 'CANCELLED'
  issue_date: string
  due_date: string | null
  paid_at: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface Receipt {
  id: string
  invoice_id: string
  amount: number
  payment_method: 'CASH' | 'BANK_TRANSFER' | 'CHECK' | 'CREDIT_CARD' | 'OTHER'
  reference: string | null
  payment_date: string
  notes: string | null
  created_at: string
}

export interface Part {
  id: string
  sku: string | null
  name: string
  description: string | null
  category: string | null
  unit: string
  quantity: number
  min_quantity: number
  cost_price: number | null
  sell_price: number | null
  supplier_name: string | null
  supplier_phone: string | null
  supplier_email: string | null
  is_active: boolean
  is_low_stock: boolean
  notes: string | null
  created_at: string
  updated_at: string
}

export interface Lead {
  id: string
  name: string
  company: string | null
  phone: string | null
  email: string | null
  source: 'WEBSITE' | 'PHONE' | 'REFERRAL' | 'EMAIL' | 'SOCIAL' | 'OTHER'
  status: 'NEW' | 'CONTACTED' | 'QUALIFIED' | 'PROPOSAL' | 'WON' | 'LOST'
  stage: string | null
  owner: string | null
  estimated_value: number | null
  customer_id: string | null
  customer_name: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface ERPDashboard {
  service: {
    open_calls: number
    critical_calls: number
    overdue_maintenance: number
    upcoming_maintenance: number
  }
  crm: {
    total_customers: number
    active_contracts: number
    expiring_contracts: number
    new_leads: number
  }
  financial: {
    month_revenue: number
    open_receivables: number
    overdue_invoices: number
  }
  inventory: {
    low_stock_parts: number
  }
  elevators: {
    total_active: number
    high_risk: number
    with_debt: number
  }
  alerts: { level: 'error' | 'warning' | 'info'; message: string }[]
}
