import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Grid, TextInput,
  NumberInput, Select, Tabs, Table, Loader, Center, ActionIcon, Alert,
  Checkbox, Textarea, Anchor, Modal, Divider, Timeline, ScrollArea, Box,
} from '@mantine/core'
import { AIRefineButton } from '../components/AIRefineButton'
import { useAuthStore } from '../stores/authStore'
import { DateInput } from '@mantine/dates'
import { FileInput } from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { getElevator, updateElevator, getElevatorCalls } from '../api/elevators'
import client from '../api/client'
import { Elevator } from '../types'
import LocationPickerModal from '../components/LocationPickerModal'
import RelatedPanel from '../components/RelatedPanel'
import {
  ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS,
  PRIORITY_LABELS, PRIORITY_COLORS, CALL_STATUS_LABELS, CALL_STATUS_COLORS, FAULT_TYPE_LABELS,
} from '../utils/constants'
import { formatDate, formatDateTime } from '../utils/dates'

// Fields that require a confirmation dialog before editing
const SENSITIVE_FIELDS = new Set(['internal_number', 'labor_file_number'])

interface Contact {
  id: string
  name: string
  phone: string | null
  email: string | null
  role: string
  auto_added: boolean
}

const ROLE_LABELS: Record<string, string> = {
  VAAD: 'ועד בית', RESIDENT: 'דייר', MANAGEMENT: 'ניהול', DIALER: 'חייגן', OTHER: 'אחר',
}
const ROLE_COLORS: Record<string, string> = {
  VAAD: 'blue', RESIDENT: 'teal', MANAGEMENT: 'violet', DIALER: 'gray', OTHER: 'gray',
}

function Field({ label, value, children }: { label: string; value?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <Stack gap={2}>
      <Text size="xs" c="dimmed">{label}</Text>
      {children ?? <Text fw={500}>{value ?? '—'}</Text>}
    </Stack>
  )
}

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

function toISODate(d: Date | null): string | null {
  if (!d) return null
  return d.toISOString().slice(0, 10)
}

const REPORT_STATUS_COLOR: Record<string, string> = { NA: 'gray', OPEN: 'red', PARTIAL: 'orange', CLOSED: 'green' }
const REPORT_STATUS_LABEL: Record<string, string> = { NA: 'תקין', OPEN: 'פתוח', PARTIAL: 'בטיפול', CLOSED: 'טופל' }

async function openReportFile(fileUrl: string) {
  if (fileUrl.startsWith('https://drive.google.com')) {
    window.open(fileUrl, '_blank')
    return
  }
  const { data } = await client.get(fileUrl, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(data)
  window.open(blobUrl, '_blank')
}

function InspectionHistory({ elevatorId }: { elevatorId: string }) {
  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['inspections', elevatorId],
    queryFn: async () => {
      const { data } = await client.get(`/inspections?elevator_id=${elevatorId}&limit=50`)
      return data
    },
  })

  if (isLoading) return null
  if (!reports.length) return (
    <Paper withBorder p="md" radius="md" mt="md">
      <Text size="sm" c="dimmed" ta="center">אין תסקירי ביקורת שמורים למעלית זו</Text>
    </Paper>
  )

  return (
    <Paper withBorder p="md" radius="md" mt="md">
      <Text fw={600} mb="sm">היסטוריית תסקירים ({reports.length})</Text>
      <Stack gap="xs">
        {reports.map((r: any) => (
          <Paper key={r.id} withBorder p="sm" radius="sm">
            <Group justify="space-between">
              <Group gap="xs">
                <Badge size="xs" color={r.result === 'PASS' ? 'green' : r.result === 'FAIL' ? 'red' : 'gray'}>
                  {r.result === 'PASS' ? 'תקין' : r.result === 'FAIL' ? 'ליקויים' : 'לא ידוע'}
                </Badge>
                {r.report_status !== 'NA' && (
                  <Badge size="xs" color={REPORT_STATUS_COLOR[r.report_status]} variant="dot">
                    {REPORT_STATUS_LABEL[r.report_status]}
                  </Badge>
                )}
                <Text size="sm">
                  {r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('he-IL') : '—'}
                </Text>
                {r.inspector_name && <Text size="sm" c="dimmed">{r.inspector_name}</Text>}
              </Group>
              <Group gap="xs">
                {r.deficiency_count > 0 && (
                  <Badge size="xs" color="red" variant="light">{r.deficiency_count} ליקויים</Badge>
                )}
                {r.file_url && (
                  <Anchor size="xs" style={{ cursor: 'pointer' }}
                    onClick={() => openReportFile(r.file_url)}>
                    📄 פתח
                  </Anchor>
                )}
              </Group>
            </Group>
          </Paper>
        ))}
      </Stack>
    </Paper>
  )
}

const FAULT_LABELS: Record<string, string> = {
  STUCK: 'תקועה', DOOR: 'דלת', ELECTRICAL: 'חשמלי', MECHANICAL: 'מכאני',
  SOFTWARE: 'תוכנה', RESCUE: 'חילוץ', MAINTENANCE: 'תחזוקה', OTHER: 'אחר',
}
const MAINT_STATUS_LABEL: Record<string, string> = {
  SCHEDULED: 'מתוכנן', COMPLETED: 'בוצע', OVERDUE: 'בפיגור', CANCELLED: 'בוטל',
}
const MAINT_STATUS_COLOR: Record<string, string> = {
  SCHEDULED: 'blue', COMPLETED: 'green', OVERDUE: 'red', CANCELLED: 'gray',
}

type LogEntry = {
  date: string
  type: 'call' | 'maintenance' | 'inspection'
  raw: any
}

function ElevatorLog({
  calls, maintenance, inspections, elevatorId,
}: {
  calls: any[]; maintenance: any[]; inspections: any[]; elevatorId: string
}) {
  const [dateFrom, setDateFrom] = useState<Date | null>(null)
  const [dateTo, setDateTo] = useState<Date | null>(null)

  const allEntries: LogEntry[] = [
    ...calls.map(c => ({ date: c.created_at, type: 'call' as const, raw: c })),
    ...maintenance.map(m => ({ date: m.scheduled_date || m.created_at, type: 'maintenance' as const, raw: m })),
    ...inspections.map(i => ({ date: i.inspection_date || i.created_at, type: 'inspection' as const, raw: i })),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())

  const entries = allEntries.filter(e => {
    const d = new Date(e.date)
    if (dateFrom && d < dateFrom) return false
    if (dateTo) { const end = new Date(dateTo); end.setHours(23,59,59,999); if (d > end) return false }
    return true
  })

  function applyPreset(days: number) {
    const from = new Date(); from.setDate(from.getDate() - days)
    from.setHours(0, 0, 0, 0)
    setDateFrom(from); setDateTo(null)
  }

  function exportCsv() {
    const rows = [['סוג', 'תאריך', 'תיאור', 'סטטוס', 'עדיפות', 'פותח']]
    entries.forEach(e => {
      if (e.type === 'call') {
        const c = e.raw
        rows.push(['קריאת שירות', new Date(c.created_at).toLocaleDateString('he-IL'),
          c.description ?? '', c.status ?? '', c.priority ?? '', c.reported_by ?? ''])
      } else if (e.type === 'maintenance') {
        const m = e.raw
        rows.push(['תחזוקה', m.scheduled_date ? new Date(m.scheduled_date).toLocaleDateString('he-IL') : '',
          m.notes ?? '', m.status ?? '', '', m.technician_name ?? ''])
      } else {
        const r = e.raw
        rows.push(['דוח בודק', r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('he-IL') : '',
          `${r.deficiency_count ?? 0} ליקויים`, r.result ?? '', '', r.inspector_name ?? ''])
      }
    })
    const bom = '﻿'
    const csv = bom + rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    a.download = `יומן-מעלית-${elevatorId.slice(0,8)}.csv`
    a.click()
  }

  function printLog() {
    const TYPE_LABEL: Record<string, string> = { call: '🔧 קריאת שירות', maintenance: '📅 תחזוקה', inspection: '🔍 דוח בודק' }
    const rows = entries.map(e => {
      let date = '', desc = '', status = '', extra = ''
      if (e.type === 'call') {
        const c = e.raw
        date = new Date(c.created_at).toLocaleDateString('he-IL')
        desc = c.description ?? ''
        status = c.status ?? ''
        extra = c.priority ?? ''
      } else if (e.type === 'maintenance') {
        const m = e.raw
        date = m.scheduled_date ? new Date(m.scheduled_date).toLocaleDateString('he-IL') : ''
        desc = m.notes ?? ''
        status = m.status ?? ''
        extra = m.technician_name ?? ''
      } else {
        const r = e.raw
        date = r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('he-IL') : ''
        desc = `${r.deficiency_count ?? 0} ליקויים`
        status = r.result ?? ''
        extra = r.inspector_name ?? ''
      }
      return `<tr><td>${date}</td><td>${TYPE_LABEL[e.type]}</td><td>${desc}</td><td>${status}</td><td>${extra}</td></tr>`
    }).join('')

    const html = `<!DOCTYPE html><html dir="rtl"><head><meta charset="UTF-8"><title>יומן מעלית</title>
<style>body{font-family:Arial,sans-serif;direction:rtl;font-size:12px;padding:16px}
table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccc;padding:5px 8px;text-align:right}
th{background:#f0f0f0;font-weight:bold}h2{font-size:15px;margin-bottom:10px}</style></head>
<body><h2>יומן מעלית — ${entries.length} רשומות</h2>
<table><thead><tr><th>תאריך</th><th>סוג</th><th>תיאור</th><th>סטטוס</th><th>נוסף</th></tr></thead>
<tbody>${rows}</tbody></table></body></html>`

    const w = window.open('', '_blank', 'width=900,height=700')
    if (w) { w.document.write(html); w.document.close(); setTimeout(() => { w.print() }, 300) }
  }

  if (allEntries.length === 0) {
    return (
      <Paper withBorder p="xl" radius="md">
        <Center><Text c="dimmed">אין רשומות ביומן</Text></Center>
      </Paper>
    )
  }

  return (
    <Stack gap="md">
      {/* Date filters */}
      <Paper withBorder p="sm" radius="md">
        <Group gap="sm" align="flex-end" wrap="wrap">
          <DateInput
            label="מתאריך"
            value={dateFrom}
            onChange={setDateFrom}
            clearable
            valueFormat="DD/MM/YYYY"
            size="xs"
            w={130}
          />
          <DateInput
            label="עד תאריך"
            value={dateTo}
            onChange={setDateTo}
            clearable
            valueFormat="DD/MM/YYYY"
            size="xs"
            w={130}
          />
          <Group gap={4}>
            {[
              { label: 'שבוע', days: 7 },
              { label: 'חודש', days: 30 },
              { label: 'רבעון', days: 90 },
              { label: 'שנה', days: 365 },
            ].map(p => (
              <Button key={p.label} size="xs" variant="light" onClick={() => applyPreset(p.days)}>
                {p.label}
              </Button>
            ))}
            {(dateFrom || dateTo) && (
              <Button size="xs" variant="subtle" color="gray" onClick={() => { setDateFrom(null); setDateTo(null) }}>
                נקה
              </Button>
            )}
          </Group>
        </Group>
      </Paper>

      <Group justify="space-between">
        <Text fw={700} size="sm" c="dimmed">
          {entries.length} רשומות מוצגות · סה"כ {allEntries.length} · קריאות {calls.length} · תחזוקה {maintenance.length} · בודק {inspections.length}
        </Text>
        <Group gap="xs">
          <Button size="xs" variant="light" color="blue" onClick={exportCsv}>📊 ייצוא Excel</Button>
          <Button size="xs" variant="light" color="gray" onClick={printLog}>🖨️ PDF</Button>
        </Group>
      </Group>

      <ScrollArea h={600}>
        <Timeline bulletSize={28} lineWidth={2}>
          {entries.map((entry, idx) => {
            if (entry.type === 'call') {
              const c = entry.raw
              const color = c.priority === 'CRITICAL' ? 'red' : c.priority === 'HIGH' ? 'orange' : c.priority === 'MEDIUM' ? 'yellow' : 'gray'
              return (
                <Timeline.Item
                  key={`call-${c.id}`}
                  bullet={<Text size="xs">🔧</Text>}
                  title={
                    <Group gap="xs" wrap="nowrap">
                      <Text size="sm" fw={600} lineClamp={1}>{c.description}</Text>
                      <Badge size="xs" color={color}>{PRIORITY_LABELS[c.priority]}</Badge>
                      <Badge size="xs" color={CALL_STATUS_COLORS[c.status]} variant="light">{CALL_STATUS_LABELS[c.status]}</Badge>
                    </Group>
                  }
                >
                  <Stack gap={2}>
                    <Group gap="xs">
                      <Badge size="xs" variant="dot" color="gray">{FAULT_LABELS[c.fault_type] ?? c.fault_type}</Badge>
                      {c.call_number && <Text size="xs" c="dimmed">#{String(c.call_number).padStart(5, '0')}</Text>}
                    </Group>
                    {c.resolution_notes && (
                      <Text size="xs" c="dimmed" lineClamp={2}>✅ {c.resolution_notes}</Text>
                    )}
                    <Text size="xs" c="dimmed">{new Date(c.created_at).toLocaleString('he-IL')}</Text>
                  </Stack>
                </Timeline.Item>
              )
            }

            if (entry.type === 'maintenance') {
              const m = entry.raw
              return (
                <Timeline.Item
                  key={`maint-${m.id}`}
                  bullet={<Text size="xs">📅</Text>}
                  title={
                    <Group gap="xs">
                      <Text size="sm" fw={600}>תחזוקה מתוכננת</Text>
                      <Badge size="xs" color={MAINT_STATUS_COLOR[m.status] ?? 'gray'}>
                        {MAINT_STATUS_LABEL[m.status] ?? m.status}
                      </Badge>
                    </Group>
                  }
                >
                  <Stack gap={2}>
                    {m.technician_name && <Text size="xs" c="dimmed">טכנאי: {m.technician_name}</Text>}
                    {m.notes && <Text size="xs" c="dimmed" lineClamp={2}>{m.notes}</Text>}
                    <Text size="xs" c="dimmed">
                      {m.scheduled_date ? new Date(m.scheduled_date).toLocaleDateString('he-IL') : '—'}
                    </Text>
                  </Stack>
                </Timeline.Item>
              )
            }

            if (entry.type === 'inspection') {
              const r = entry.raw
              const result = r.result === 'PASS' ? 'תקין' : r.result === 'FAIL' ? 'ליקויים' : 'לא ידוע'
              const resultColor = r.result === 'PASS' ? 'green' : r.result === 'FAIL' ? 'red' : 'gray'
              return (
                <Timeline.Item
                  key={`insp-${r.id}`}
                  bullet={<Text size="xs">🔍</Text>}
                  title={
                    <Group gap="xs">
                      <Text size="sm" fw={600}>דוח בודק</Text>
                      <Badge size="xs" color={resultColor}>{result}</Badge>
                      {r.report_status && r.report_status !== 'NA' && (
                        <Badge size="xs" color={REPORT_STATUS_COLOR[r.report_status]} variant="light">
                          {REPORT_STATUS_LABEL[r.report_status]}
                        </Badge>
                      )}
                    </Group>
                  }
                >
                  <Stack gap={2}>
                    {r.inspector_name && <Text size="xs" c="dimmed">בודק: {r.inspector_name}</Text>}
                    {r.deficiency_count > 0 && (
                      <Text size="xs" c="red">{r.deficiency_count} ליקויים</Text>
                    )}
                    {r.file_url && (
                      <Anchor size="xs" onClick={() => openReportFile(r.file_url)} style={{ cursor: 'pointer' }}>
                        📄 פתח דוח
                      </Anchor>
                    )}
                    <Text size="xs" c="dimmed">
                      {r.inspection_date ? new Date(r.inspection_date).toLocaleDateString('he-IL') : '—'}
                    </Text>
                  </Stack>
                </Timeline.Item>
              )
            }

            return null
          })}
        </Timeline>
      </ScrollArea>
    </Stack>
  )
}

export default function ElevatorDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const userRole = useAuthStore(s => s.userRole)
  const isAdmin = userRole === 'ADMIN'
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<Elevator>>({})
  const [sensitiveField, setSensitiveField] = useState<string | null>(null)
  const [addContactOpen, setAddContactOpen] = useState(false)
  const [newContact, setNewContact] = useState({ name: '', phone: '', email: '', role: 'VAAD' })
  const [residentsExpanded, setResidentsExpanded] = useState(false)
  const [assignBuildingOpen, setAssignBuildingOpen] = useState(false)
  const [assignCompanyOpen, setAssignCompanyOpen] = useState(false)
  const [assignConsultantOpen, setAssignConsultantOpen] = useState(false)
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null)
  const [selectedConsultantId, setSelectedConsultantId] = useState<string | null>(null)
  const [inlineCreateCompany, setInlineCreateCompany] = useState(false)
  const [newCompanyName, setNewCompanyName] = useState('')
  const [inlineCreateConsultant, setInlineCreateConsultant] = useState(false)
  const [newConsultantName, setNewConsultantName] = useState('')
  const [addToGroupOpen, setAddToGroupOpen] = useState(false)
  const [elevatorSearch, setElevatorSearch] = useState('')
  const [locationPickerOpen, setLocationPickerOpen] = useState(false)

  const set = (key: string, value: any) => setForm(s => ({ ...s, [key]: value }))
  const dateSet = (key: string, d: Date | null) => set(key, toISODate(d))

  function openAddContact(defaultRole: string) {
    setNewContact({ name: '', phone: '', email: '', role: defaultRole })
    setAddContactOpen(true)
  }

  function sensitiveSet(key: string, value: any) {
    if (SENSITIVE_FIELDS.has(key)) {
      setSensitiveField(key)
    } else {
      set(key, value)
    }
  }

  const { data: elevator, isLoading } = useQuery<Elevator>({
    queryKey: ['elevator', id],
    queryFn: () => getElevator(id!),
    enabled: !!id,
  })

  const { data: calls = [] } = useQuery({
    queryKey: ['elevator-calls', id],
    queryFn: () => getElevatorCalls(id!),
    enabled: !!id,
  })

  const { data: maintenanceLogs = [] } = useQuery({
    queryKey: ['elevator-maintenance', id],
    queryFn: async () => (await client.get(`/maintenance?elevator_id=${id}&limit=200`)).data,
    enabled: !!id,
  })

  const { data: inspectionLogs = [] } = useQuery({
    queryKey: ['elevator-inspections', id],
    queryFn: async () => (await client.get(`/inspections?elevator_id=${id}&limit=200`)).data,
    enabled: !!id,
  })

  const { data: contacts = [] } = useQuery<Contact[]>({
    queryKey: ['elevator-contacts', elevator?.building_id],
    queryFn: async () => {
      if (!elevator?.building_id) return []
      return (await client.get(`/contacts?building_id=${elevator.building_id}`)).data
    },
    enabled: !!elevator?.building_id,
  })

  const { data: buildingDetail } = useQuery({
    queryKey: ['building-detail', elevator?.building_id],
    queryFn: async () => {
      if (!elevator?.building_id) return null
      return (await client.get(`/buildings/${elevator.building_id}`)).data
    },
    enabled: !!elevator?.building_id,
  })
  const siblings: any[] = (buildingDetail?.elevators ?? []).filter((e: any) => e.id !== id)

  const { data: buildingsList = [] } = useQuery({
    queryKey: ['buildings-list'],
    queryFn: async () => (await client.get('/buildings?limit=500')).data,
    enabled: assignBuildingOpen,
  })

  const { data: companiesList = [] } = useQuery({
    queryKey: ['companies-list'],
    queryFn: async () => (await client.get('/management-companies')).data,
    enabled: assignCompanyOpen,
  })

  const { data: techniciansList = [] } = useQuery({
    queryKey: ['technicians-list'],
    queryFn: async () => (await client.get('/technicians')).data,
    staleTime: 5 * 60 * 1000,
  })

  const { data: consultantsList = [] } = useQuery({
    queryKey: ['consultants-list'],
    queryFn: async () => (await client.get('/consultants')).data,
    enabled: assignConsultantOpen,
  })

  const { data: companyDetail } = useQuery({
    queryKey: ['company-detail', elevator?.management_company_id],
    queryFn: async () => (await client.get(`/management-companies/${elevator!.management_company_id}`)).data,
    enabled: !!elevator?.management_company_id,
  })

  const { data: potentialSiblings = [] } = useQuery<any[]>({
    queryKey: ['potential-siblings', id],
    queryFn: async () => {
      const res = await client.get(`/elevators?city=${encodeURIComponent(elevator!.city)}&limit=100`)
      return res.data.filter((e: any) =>
        e.id !== id &&
        e.address === elevator!.address &&
        (!e.building_id || e.building_id !== elevator!.building_id)
      )
    },
    enabled: !!elevator,
    staleTime: 60000,
  })

  const { data: allElevatorsForSearch = [] } = useQuery<any[]>({
    queryKey: ['elevators'],
    enabled: addToGroupOpen,
  })

  const updateMutation = useMutation({
    mutationFn: (payload: any) => updateElevator(id!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: 'פרטי המעלית עודכנו', color: 'green' })
      setEditing(false)
    },
    onError: (err: any) => notifications.show({
      message: err?.response?.data?.detail ?? 'שגיאה בעדכון',
      color: 'red',
    }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => client.delete(`/elevators/${id}`),
    onSuccess: () => {
      notifications.show({ message: 'המעלית נמחקה', color: 'green' })
      navigate('/elevators')
    },
    onError: () => notifications.show({ message: 'שגיאה במחיקה', color: 'red' }),
  })

  const addContactMutation = useMutation({
    mutationFn: async (contactData: any) => {
      let buildingId = elevator!.building_id
      if (!buildingId) {
        const bRes = await client.post('/buildings', { address: elevator!.address, city: elevator!.city })
        buildingId = bRes.data.id
        await updateElevator(id!, { building_id: buildingId } as any)
      }
      return client.post('/contacts', { ...contactData, building_id: buildingId })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['elevator-contacts'] })
      setAddContactOpen(false)
      setNewContact({ name: '', phone: '', email: '', role: 'VAAD' })
      notifications.show({ message: 'איש קשר נוסף', color: 'green' })
    },
  })

  async function uploadFile(field: 'drive_link' | 'last_inspection_report_url', file: File) {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await client.post(`/elevators/${id}/upload-file?field=${field}`, fd)
    set(field, data.url)
    await updateElevator(id!, { [field]: data.url } as any)
    qc.invalidateQueries({ queryKey: ['elevator', id] })
    notifications.show({ message: 'הקובץ הועלה', color: 'green' })
  }

  const deleteContactMutation = useMutation({
    mutationFn: (contactId: string) => client.delete(`/contacts/${contactId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['elevator-contacts', elevator?.building_id] }),
  })

  const assignBuildingMutation = useMutation({
    mutationFn: (buildingId: string | null) => updateElevator(id!, { building_id: buildingId } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['building-detail'] })
      qc.invalidateQueries({ queryKey: ['potential-siblings', id] })
      setAssignBuildingOpen(false)
      setSelectedBuildingId(null)
      notifications.show({ message: 'שיוך הבניין עודכן', color: 'green' })
    },
  })

  const assignCompanyMutation = useMutation({
    mutationFn: (companyId: string | null) => updateElevator(id!, { management_company_id: companyId } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['company-detail'] })
      setAssignCompanyOpen(false)
      setSelectedCompanyId(null)
      notifications.show({ message: 'שיוך חברת הניהול עודכן', color: 'green' })
    },
  })

  const assignConsultantMutation = useMutation({
    mutationFn: (consultantId: string | null) => updateElevator(id!, { consultant_id: consultantId } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      setAssignConsultantOpen(false)
      setSelectedConsultantId(null)
      notifications.show({ message: 'שיוך היועץ עודכן', color: 'green' })
    },
  })

  const createCompanyMutation = useMutation({
    mutationFn: (name: string) => client.post('/management-companies', { name }).then(r => r.data),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['companies-list'] })
      setSelectedCompanyId(data.id)
      setInlineCreateCompany(false)
      setNewCompanyName('')
      notifications.show({ message: 'חברת הניהול נוצרה', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה ביצירת חברה', color: 'red' }),
  })

  const createConsultantMutation = useMutation({
    mutationFn: (name: string) => client.post('/consultants', { name }).then(r => r.data),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['consultants-list'] })
      setSelectedConsultantId(data.id)
      setInlineCreateConsultant(false)
      setNewConsultantName('')
      notifications.show({ message: 'היועץ נוצר', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה ביצירת יועץ', color: 'red' }),
  })

  const locationMutation = useMutation({
    mutationFn: ({ lat, lng }: { lat: number; lng: number }) =>
      updateElevator(id!, { latitude: lat, longitude: lng } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      setLocationPickerOpen(false)
      notifications.show({ message: '📍 מיקום עודכן בהצלחה', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירת מיקום', color: 'red' }),
  })

  const addElevatorToGroupMutation = useMutation({
    mutationFn: (otherElevatorId: string) =>
      client.put(`/elevators/${otherElevatorId}`, { building_id: elevator!.building_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['building-detail', elevator!.building_id] })
      qc.invalidateQueries({ queryKey: ['elevators'] })
      setAddToGroupOpen(false)
      setElevatorSearch('')
      notifications.show({ message: 'מעלית נוספה לקבוצה', color: 'green' })
    },
  })

  const autoGroupMutation = useMutation({
    mutationFn: async () => {
      let buildingId = elevator!.building_id
      if (!buildingId) {
        const bRes = await client.post('/buildings', { address: elevator!.address, city: elevator!.city })
        buildingId = bRes.data.id
        await updateElevator(id!, { building_id: buildingId } as any)
      }
      await Promise.all(potentialSiblings.map((s: any) =>
        client.put(`/elevators/${s.id}`, { building_id: buildingId })
      ))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['building-detail'] })
      qc.invalidateQueries({ queryKey: ['potential-siblings', id] })
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: `${potentialSiblings.length + 1} מעליות קושרו לקבוצה`, color: 'green' })
    },
  })

  if (isLoading) return <Center h={400}><Loader /></Center>
  if (!elevator) return <Center h={400}><Text>מעלית לא נמצאה</Text></Center>

  const data: Elevator = editing ? { ...elevator, ...form } as Elevator : elevator

  // Maintenance urgency color
  const daysToService = elevator.next_service_date
    ? Math.ceil((new Date(elevator.next_service_date).getTime() - Date.now()) / 86400000)
    : null
  const serviceUrgency = daysToService === null ? null
    : daysToService < 0 ? 'red'
    : daysToService <= 2 ? 'red'
    : daysToService <= 5 ? 'orange'
    : daysToService <= 10 ? 'yellow'
    : 'green'

  return (
    <Stack gap="lg">
      {/* Sensitive field confirmation */}
      <Modal
        opened={!!sensitiveField}
        onClose={() => setSensitiveField(null)}
        title="⚠️ שינוי ערך רגיש"
        dir="rtl"
        size="sm"
      >
        <Text size="sm" mb="md">
          אתה משנה שדה רגיש: <strong>{sensitiveField}</strong>. פעולה זו עלולה להשפיע על התממשקות עם מערכות אחרות. האם אתה בטוח?
        </Text>
        <Group>
          <Button variant="default" onClick={() => setSensitiveField(null)}>ביטול</Button>
          <Button color="orange" onClick={() => setSensitiveField(null)}>אני מאשר, המשך</Button>
        </Group>
      </Modal>

      {/* Add contact modal */}
      <Modal opened={addContactOpen} onClose={() => setAddContactOpen(false)} title="הוסף איש קשר" dir="rtl">
        <Stack gap="sm">
          <TextInput label="שם" required value={newContact.name} onChange={e => setNewContact(s => ({ ...s, name: e.target.value }))} />
          <TextInput label="טלפון" value={newContact.phone} onChange={e => setNewContact(s => ({ ...s, phone: e.target.value }))} />
          <TextInput label="מייל" value={newContact.email} onChange={e => setNewContact(s => ({ ...s, email: e.target.value }))} />
          <Select label="תפקיד" value={newContact.role}
            data={Object.entries(ROLE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
            onChange={v => setNewContact(s => ({ ...s, role: v ?? 'OTHER' }))}
          />
          <Button
            loading={addContactMutation.isPending}
            disabled={!newContact.name.trim()}
            onClick={() => addContactMutation.mutate({
              ...newContact,
              building_id: elevator.building_id,
              phone: newContact.phone || null,
              email: newContact.email || null,
            })}
          >
            הוסף
          </Button>
        </Stack>
      </Modal>

      {/* Assign building modal */}
      <Modal opened={assignBuildingOpen} onClose={() => { setAssignBuildingOpen(false); setSelectedBuildingId(null) }} title="שיוך לקבוצה / בניין" dir="rtl">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">בחר בניין קיים כדי לשתף אנשי קשר עם מעליות אחרות, או צור קבוצה חדשה לכתובת זו.</Text>
          <Select
            label="בניין קיים"
            placeholder="חפש לפי כתובת..."
            searchable clearable
            data={(buildingsList as any[]).map((b: any) => ({
              value: b.id,
              label: `${b.address}, ${b.city}${b.elevator_count > 0 ? ` (${b.elevator_count} מעליות)` : ''}`,
            }))}
            value={selectedBuildingId}
            onChange={setSelectedBuildingId}
          />
          <Button
            disabled={!selectedBuildingId}
            loading={assignBuildingMutation.isPending}
            onClick={() => assignBuildingMutation.mutate(selectedBuildingId!)}
          >
            שייך לבניין הנבחר
          </Button>
          <Divider label="או" labelPosition="center" />
          <Button variant="outline" loading={assignBuildingMutation.isPending}
            onClick={async () => {
              const bRes = await client.post('/buildings', { address: elevator!.address, city: elevator!.city })
              assignBuildingMutation.mutate(bRes.data.id)
            }}
          >
            צור קבוצה חדשה לכתובת זו
          </Button>
        </Stack>
      </Modal>

      {/* Assign company modal */}
      <Modal opened={assignCompanyOpen} onClose={() => { setAssignCompanyOpen(false); setSelectedCompanyId(null); setInlineCreateCompany(false); setNewCompanyName('') }} title="שיוך לחברת ניהול" dir="rtl">
        <Stack gap="sm">
          <Select
            label="חברת ניהול"
            placeholder="חפש חברה..."
            searchable clearable
            data={(companiesList as any[]).map((c: any) => ({ value: c.id, label: c.name }))}
            value={selectedCompanyId}
            onChange={setSelectedCompanyId}
          />
          <Button
            disabled={!selectedCompanyId}
            loading={assignCompanyMutation.isPending}
            onClick={() => assignCompanyMutation.mutate(selectedCompanyId!)}
          >
            שייך
          </Button>
          <Divider label="או צור חברה חדשה" labelPosition="center" />
          {!inlineCreateCompany ? (
            <Button variant="outline" size="xs" onClick={() => setInlineCreateCompany(true)}>+ חברת ניהול חדשה</Button>
          ) : (
            <Stack gap="xs">
              <TextInput
                placeholder="שם חברת הניהול"
                value={newCompanyName}
                onChange={e => setNewCompanyName(e.target.value)}
                autoFocus
              />
              <Group gap="xs">
                <Button size="xs" loading={createCompanyMutation.isPending} disabled={!newCompanyName.trim()} onClick={() => createCompanyMutation.mutate(newCompanyName.trim())}>צור</Button>
                <Button size="xs" variant="subtle" onClick={() => { setInlineCreateCompany(false); setNewCompanyName('') }}>ביטול</Button>
              </Group>
            </Stack>
          )}
        </Stack>
      </Modal>

      {/* Assign consultant modal */}
      <Modal opened={assignConsultantOpen} onClose={() => { setAssignConsultantOpen(false); setSelectedConsultantId(null); setInlineCreateConsultant(false); setNewConsultantName('') }} title="שיוך יועץ" dir="rtl">
        <Stack gap="sm">
          <Select
            label="יועץ"
            placeholder="חפש יועץ..."
            searchable clearable
            data={(consultantsList as any[]).map((c: any) => ({ value: c.id, label: c.name }))}
            value={selectedConsultantId}
            onChange={setSelectedConsultantId}
          />
          <Button
            disabled={!selectedConsultantId}
            loading={assignConsultantMutation.isPending}
            onClick={() => assignConsultantMutation.mutate(selectedConsultantId!)}
          >
            שייך
          </Button>
          <Divider label="או צור יועץ חדש" labelPosition="center" />
          {!inlineCreateConsultant ? (
            <Button variant="outline" size="xs" onClick={() => setInlineCreateConsultant(true)}>+ יועץ חדש</Button>
          ) : (
            <Stack gap="xs">
              <TextInput
                placeholder="שם היועץ"
                value={newConsultantName}
                onChange={e => setNewConsultantName(e.target.value)}
                autoFocus
              />
              <Group gap="xs">
                <Button size="xs" loading={createConsultantMutation.isPending} disabled={!newConsultantName.trim()} onClick={() => createConsultantMutation.mutate(newConsultantName.trim())}>צור</Button>
                <Button size="xs" variant="subtle" onClick={() => { setInlineCreateConsultant(false); setNewConsultantName('') }}>ביטול</Button>
              </Group>
            </Stack>
          )}
        </Stack>
      </Modal>

      {/* Add elevator to group modal */}
      <Modal opened={addToGroupOpen} onClose={() => { setAddToGroupOpen(false); setElevatorSearch('') }} title="הוסף מעלית לקבוצה" dir="rtl">
        <Stack gap="sm">
          <TextInput
            label="חפש מעלית"
            placeholder="כתובת, מס׳ סידורי, עיר..."
            value={elevatorSearch}
            onChange={e => setElevatorSearch(e.target.value)}
          />
          <Stack gap="xs" style={{ maxHeight: 300, overflowY: 'auto' }}>
            {(allElevatorsForSearch as any[])
              .filter((e: any) =>
                e.id !== id &&
                elevatorSearch.length > 1 &&
                (e.address?.includes(elevatorSearch) || e.city?.includes(elevatorSearch) ||
                  (e.internal_number ?? '').includes(elevatorSearch) || (e.serial_number ?? '').includes(elevatorSearch))
              )
              .slice(0, 15)
              .map((e: any) => (
                <Paper key={e.id} withBorder p="xs" radius="sm"
                  style={{ cursor: 'pointer' }}
                  onClick={() => addElevatorToGroupMutation.mutate(e.id)}
                >
                  <Group justify="space-between">
                    <Stack gap={0}>
                      <Text size="sm" fw={500}>{e.address}, {e.city}</Text>
                      {e.internal_number && <Text size="xs" c="dimmed">#{e.internal_number}</Text>}
                    </Stack>
                    <Badge color={e.building_id ? 'orange' : 'gray'} size="xs" variant="light">
                      {e.building_id ? 'כבר בקבוצה' : 'ללא קבוצה'}
                    </Badge>
                  </Group>
                </Paper>
              ))}
            {elevatorSearch.length > 1 && (allElevatorsForSearch as any[]).filter((e: any) =>
              e.id !== id &&
              (e.address?.includes(elevatorSearch) || e.city?.includes(elevatorSearch) ||
                (e.internal_number ?? '').includes(elevatorSearch))
            ).length === 0 && (
              <Text size="sm" c="dimmed" ta="center">לא נמצאו תוצאות</Text>
            )}
          </Stack>
        </Stack>
      </Modal>

      {/* Related cross-reference panel */}
      <RelatedPanel entityType="elevator" entityId={elevator.id} />

      <Group>
        <ActionIcon variant="subtle" onClick={() => navigate('/elevators')}>←</ActionIcon>
        <Title order={2}>
          מעלית {elevator.internal_number ? `#${elevator.internal_number}` : elevator.id.slice(0, 8)}
        </Title>
        <Badge color={ELEVATOR_STATUS_COLORS[elevator.status]} size="lg">
          {ELEVATOR_STATUS_LABELS[elevator.status]}
        </Badge>
        {elevator.service_type && (
          <Badge color={elevator.service_type === 'COMPREHENSIVE' ? 'violet' : 'blue'} variant="light">
            {elevator.service_type === 'COMPREHENSIVE' ? 'מקיף' : 'רגיל'}
          </Badge>
        )}
        {elevator.has_debt && <Badge color="red" variant="filled">⚠️ חוב פעיל</Badge>}
        {!editing ? (
          <Button variant="light" size="xs" onClick={() => { setForm(elevator); setEditing(true) }}>✏️ ערוך</Button>
        ) : (
          <Group gap="xs">
            <Button variant="default" size="xs" onClick={() => setEditing(false)}>ביטול</Button>
            <Button size="xs" loading={updateMutation.isPending} onClick={() => updateMutation.mutate(form)}>שמור</Button>
          </Group>
        )}
        {isAdmin && (
          <Button
            size="xs" color="red" variant="subtle"
            loading={deleteMutation.isPending}
            onClick={() => { if (window.confirm('למחוק את המעלית לצמיתות?')) deleteMutation.mutate() }}
          >🗑️ מחק מעלית</Button>
        )}
      </Group>

      {/* Alerts */}
      {!elevator.labor_file_number && (
        <Alert color="orange" title="מספר משרד העבודה חסר" icon="⚠️">
          לא הוזן מספר תיק משרד העבודה — שיוך תסקירים אוטומטי לא יעבוד.
        </Alert>
      )}
      {serviceUrgency === 'red' && (
        <Alert color="red" title="דורש טיפול מיידי" icon="🔴">
          תאריך הטיפול {daysToService! < 0 ? `עבר לפני ${Math.abs(daysToService!)} ימים` : 'בעוד פחות מ-2 ימים'}.
        </Alert>
      )}
      {serviceUrgency === 'orange' && (
        <Alert color="orange" title="טיפול קרוב" icon="🟠">
          טיפול מתוכנן בעוד {daysToService} ימים.
        </Alert>
      )}

      {potentialSiblings.length > 0 && !elevator.building_id && (
        <Alert color="orange" title="מעליות שאינן בקבוצה" icon="🏢">
          נמצאו {potentialSiblings.length} מעליות נוספות בכתובת {elevator.address} שאינן משויכות לאותו בניין.{' '}
          <Button size="xs" variant="white" loading={autoGroupMutation.isPending} onClick={() => autoGroupMutation.mutate()}>
            קישור אוטומטי
          </Button>
        </Alert>
      )}

      <Tabs defaultValue="details">
        <Tabs.List>
          <Tabs.Tab value="details">פרטים</Tabs.Tab>
          <Tabs.Tab value="service">שירות</Tabs.Tab>
          <Tabs.Tab value="contacts">אנשי קשר {contacts.length > 0 && `(${contacts.length})`}</Tabs.Tab>
          <Tabs.Tab value="contract">חוזה</Tabs.Tab>
          <Tabs.Tab value="inspection">דוחות בודק</Tabs.Tab>
          <Tabs.Tab value="calls">קריאות ({(calls as any[]).length})</Tabs.Tab>
          <Tabs.Tab value="log">📋 יומן מעלית</Tabs.Tab>
          {elevator.building_id && (
            <Tabs.Tab value="group">קבוצה {siblings.length > 0 && `(${siblings.length + 1})`}</Tabs.Tab>
          )}
          {elevator.management_company_id && (
            <Tabs.Tab value="management">חברת ניהול</Tabs.Tab>
          )}
        </Tabs.List>

        {/* ── DETAILS ── */}
        <Tabs.Panel value="details" pt="md">
          <Paper withBorder p="lg" radius="md">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="מס״ד (מזהה ממערכת ישנה)" value={form.internal_number ?? ''} onChange={e => set('internal_number', e.target.value || null)} />
                ) : (
                  <Field label="מס״ד" value={elevator.internal_number} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="מספר תיק משרד העבודה" value={form.labor_file_number ?? ''} onChange={e => set('labor_file_number', e.target.value || null)} />
                ) : (
                  <Field label="מספר תיק משרד העבודה">
                    {elevator.labor_file_number
                      ? <Text fw={500}>{elevator.labor_file_number}</Text>
                      : <Badge color="orange" variant="light">⚠ חסר</Badge>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="כתובת" value={form.address ?? ''} onChange={e => set('address', e.target.value)} />
                ) : (
                  <Field label="כתובת" value={elevator.address} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="עיר" value={form.city ?? ''} onChange={e => set('city', e.target.value)} />
                ) : (
                  <Field label="עיר" value={elevator.city} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="שם/תיאור (כינוי)" value={form.building_name ?? ''} onChange={e => set('building_name', e.target.value || null)} />
                ) : (
                  <Field label="שם/תיאור" value={elevator.building_name} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="טלפון חייגן" value={form.intercom_phone ?? ''} onChange={e => set('intercom_phone', e.target.value || null)} />
                ) : (
                  <Field label="טלפון חייגן" value={elevator.intercom_phone} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Checkbox
                    label="קוד כניסה לבניין"
                    checked={form.is_coded ?? false}
                    onChange={e => set('is_coded', e.target.checked)}
                    mt="sm"
                  />
                ) : (
                  <Field label="קוד כניסה לבניין">
                    {elevator.is_coded ? <Badge color="grape">כן</Badge> : <Text fw={500}>לא</Text>}
                  </Field>
                )}
              </Grid.Col>
              {(editing ? form.is_coded : elevator.is_coded) && (
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  {editing ? (
                    <TextInput label="קוד כניסה" value={form.entry_code ?? ''} onChange={e => set('entry_code', e.target.value || null)} />
                  ) : (
                    <Field label="קוד כניסה" value={elevator.entry_code} />
                  )}
                </Grid.Col>
              )}
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <NumberInput label="מספר קומות" min={1} max={200} value={form.floor_count ?? 1} onChange={v => set('floor_count', Number(v))} />
                ) : (
                  <Field label="מספר קומות" value={elevator.floor_count} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="מספר סידורי" value={form.serial_number ?? ''} onChange={e => set('serial_number', e.target.value || null)} />
                ) : (
                  <Field label="מספר סידורי" value={elevator.serial_number} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="תאריך התקנה" value={parseDate(form.installation_date)} onChange={d => dateSet('installation_date', d)} clearable locale="he" />
                ) : (
                  <Field label="תאריך התקנה" value={elevator.installation_date ? new Date(elevator.installation_date).toLocaleDateString('he-IL') : null} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="יצרן" value={form.manufacturer ?? ''} onChange={e => set('manufacturer', e.target.value || null)} />
                ) : (
                  <Field label="יצרן" value={elevator.manufacturer} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="דגם" value={form.model ?? ''} onChange={e => set('model', e.target.value || null)} />
                ) : (
                  <Field label="דגם" value={elevator.model} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Field label="ציון סיכון">
                  <Badge color={elevator.risk_score > 70 ? 'red' : elevator.risk_score > 40 ? 'orange' : 'green'} size="lg" variant="light">
                    {elevator.risk_score.toFixed(1)}
                  </Badge>
                </Field>
              </Grid.Col>
              {editing && (
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  <Select label="סטטוס"
                    data={[{ value: 'ACTIVE', label: 'פעילה' }, { value: 'INACTIVE', label: 'לא פעילה' }, { value: 'UNDER_REPAIR', label: 'בתיקון' }]}
                    value={form.status}
                    onChange={v => set('status', v)}
                  />
                </Grid.Col>
              )}
              <Grid.Col span={12}>
                {editing ? (
                  <Textarea label="הערות" value={form.notes ?? ''} onChange={e => set('notes', e.target.value || null)} minRows={2} rightSection={<AIRefineButton value={form.notes ?? ''} onChange={v => set('notes', v || null)} />} rightSectionPointerEvents="all" />
                ) : elevator.notes ? (
                  <Field label="הערות" value={elevator.notes} />
                ) : null}
              </Grid.Col>

              {/* Extended tech specs */}
              <Grid.Col span={12}>
                <Divider label="מפרט טכני מורחב" labelPosition="right" mt="sm" mb="xs" />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="סוג מנוע" value={form.motor_type ?? ''} onChange={e => set('motor_type', e.target.value || null)} />
                ) : (
                  <Field label="סוג מנוע" value={elevator.motor_type} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="דגם בקר" value={form.controller_model ?? ''} onChange={e => set('controller_model', e.target.value || null)} />
                ) : (
                  <Field label="דגם בקר" value={elevator.controller_model} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="סוג דלת" value={form.door_type ?? ''} onChange={e => set('door_type', e.target.value || null)} />
                ) : (
                  <Field label="סוג דלת" value={elevator.door_type} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label="עומק בור (ס״מ)" value={form.pit_depth_cm ?? ''} onChange={v => set('pit_depth_cm', v || null)} min={0} />
                ) : (
                  <Field label="עומק בור (ס״מ)" value={elevator.pit_depth_cm ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label='גובה חדר מכונות (ס"מ)' value={form.headroom_cm ?? ''} onChange={v => set('headroom_cm', v || null)} min={0} />
                ) : (
                  <Field label='גובה חדר מכונות (ס"מ)' value={elevator.headroom_cm ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="תוקף תעודת בטיחות" value={parseDate(form.safety_certificate_expiry)} onChange={d => dateSet('safety_certificate_expiry', d)} clearable locale="he" />
                ) : (
                  <Field label="תוקף תעודת בטיחות">
                    {elevator.safety_certificate_expiry ? (() => {
                      const exp = new Date(elevator.safety_certificate_expiry)
                      const today = new Date()
                      today.setHours(0, 0, 0, 0)
                      const days = Math.ceil((exp.getTime() - today.getTime()) / 86400000)
                      const color = days < 0 ? 'red' : days <= 30 ? 'orange' : 'green'
                      const label = days < 0 ? `פג תוקף לפני ${Math.abs(days)} ימים` : days === 0 ? 'פג היום' : `בעוד ${days} ימים`
                      return (
                        <Group gap="xs">
                          <Text fw={500}>{exp.toLocaleDateString('he-IL')}</Text>
                          <Badge color={color} size="sm" variant="light">{label}</Badge>
                        </Group>
                      )
                    })() : <Text fw={500} c="dimmed">—</Text>}
                  </Field>
                )}
              </Grid.Col>

              {/* Deep tech specs */}
              <Grid.Col span={12}>
                <Divider label="מפרט תקני ועמידה בדרישות" labelPosition="right" mt="sm" mb="xs" />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label='משקל נשיאה (ק"ג)' value={form.load_capacity_kg ?? ''} onChange={v => set('load_capacity_kg', v || null)} min={0} />
                ) : (
                  <Field label='משקל נשיאה (ק"ג)' value={elevator.load_capacity_kg ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label="מספר נוסעים" value={form.max_persons ?? ''} onChange={v => set('max_persons', v || null)} min={0} />
                ) : (
                  <Field label="מספר נוסעים" value={elevator.max_persons ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label="מהירות (מ/ש)" value={form.speed_m_s ?? ''} onChange={v => set('speed_m_s', v || null)} min={0} step={0.1} />
                ) : (
                  <Field label="מהירות (מ/ש)" value={elevator.speed_m_s ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label="מספר תחנות" value={form.stops_count ?? ''} onChange={v => set('stops_count', v || null)} min={0} />
                ) : (
                  <Field label="מספר תחנות" value={elevator.stops_count ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label="מספר דלתות" value={form.doors_count ?? ''} onChange={v => set('doors_count', v || null)} min={0} />
                ) : (
                  <Field label="מספר דלתות" value={elevator.doors_count ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <NumberInput label='רוחב דלת (ס"מ)' value={form.door_width_cm ?? ''} onChange={v => set('door_width_cm', v || null)} min={0} />
                ) : (
                  <Field label='רוחב דלת (ס"מ)' value={elevator.door_width_cm ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="גימור תא" value={form.cabin_finish ?? ''} onChange={e => set('cabin_finish', e.target.value || null)} />
                ) : (
                  <Field label="גימור תא" value={elevator.cabin_finish} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="סוג רצפה" value={form.floor_type ?? ''} onChange={e => set('floor_type', e.target.value || null)} />
                ) : (
                  <Field label="סוג רצפה" value={elevator.floor_type} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <TextInput label="מס׳ סידורי מנוע" value={form.engine_serial ?? ''} onChange={e => set('engine_serial', e.target.value || null)} />
                ) : (
                  <Field label="מס׳ סידורי מנוע" value={elevator.engine_serial} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <TextInput label="מס׳ סידורי בקר" value={form.controller_serial ?? ''} onChange={e => set('controller_serial', e.target.value || null)} />
                ) : (
                  <Field label="מס׳ סידורי בקר" value={elevator.controller_serial} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <TextInput label="כתובת IP/IoT" value={form.iot_gateway_ip ?? ''} onChange={e => set('iot_gateway_ip', e.target.value || null)} />
                ) : (
                  <Field label="כתובת IP/IoT" value={elevator.iot_gateway_ip} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <Checkbox label="עומד בתקן נגישות" checked={form.accessibility_compliant ?? false} onChange={e => set('accessibility_compliant', e.target.checked)} mt="sm" />
                ) : (
                  <Field label="תקן נגישות">
                    {elevator.accessibility_compliant ? <Badge color="green">כן</Badge> : <Text fw={500}>לא</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <Checkbox label="מחובר לגלאי אש" checked={form.fire_system_connected ?? false} onChange={e => set('fire_system_connected', e.target.checked)} mt="sm" />
                ) : (
                  <Field label="גלאי אש">
                    {elevator.fire_system_connected ? <Badge color="green">מחובר</Badge> : <Text fw={500}>לא</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                {editing ? (
                  <Checkbox label="מחובר לגנרטור" checked={form.generator_connected ?? false} onChange={e => set('generator_connected', e.target.checked)} mt="sm" />
                ) : (
                  <Field label="גנרטור">
                    {elevator.generator_connected ? <Badge color="green">מחובר</Badge> : <Text fw={500}>לא</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Select label="סטטוס התקנה"
                    data={[{value:'פעיל',label:'פעיל'},{value:'בבניה',label:'בבניה'},{value:'מושבת',label:'מושבת'},{value:'שיפוץ',label:'שיפוץ'}]}
                    value={form.installation_status ?? null}
                    onChange={v => set('installation_status', v)}
                    clearable
                  />
                ) : (
                  <Field label="סטטוס התקנה" value={elevator.installation_status} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <DateInput label="תאריך מסירה ללקוח" value={parseDate(form.handover_date)} onChange={d => dateSet('handover_date', d)} clearable locale="he" />
                ) : (
                  <Field label="תאריך מסירה" value={elevator.handover_date ? new Date(elevator.handover_date).toLocaleDateString('he-IL') : null} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 3 }}>
                {editing ? (
                  <DateInput label="תאריך פירוק" value={parseDate(form.dismantle_date)} onChange={d => dateSet('dismantle_date', d)} clearable locale="he" />
                ) : (
                  <Field label="תאריך פירוק" value={elevator.dismantle_date ? new Date(elevator.dismantle_date).toLocaleDateString('he-IL') : null} />
                )}
              </Grid.Col>

              {/* Location */}
              <Grid.Col span={12}>
                <Divider label="מיקום גיאוגרפי" labelPosition="right" mt="sm" mb="xs" />
                <Group gap="sm" align="center">
                  {elevator.latitude && elevator.longitude ? (
                    <>
                      <Text size="sm" c="dimmed">📍 {elevator.latitude.toFixed(5)}, {elevator.longitude.toFixed(5)}</Text>
                      <Anchor size="xs" href={`https://waze.com/ul?ll=${elevator.latitude},${elevator.longitude}&navigate=yes`} target="_blank">🚘 Waze</Anchor>
                    </>
                  ) : (
                    <Text size="sm" c="dimmed">אין מיקום מוגדר</Text>
                  )}
                  <Button size="xs" variant="light" color="teal" onClick={() => setLocationPickerOpen(true)}>
                    📍 {elevator.latitude ? 'עדכן מיקום' : 'הוסף מיקום'}
                  </Button>
                </Group>
              </Grid.Col>

              {/* Group & management company checkboxes */}
              <Grid.Col span={12}>
                <Divider label="שיוכים" labelPosition="right" mt="sm" mb="sm" />
                <Group gap="xl">
                  <Checkbox
                    label="מעלית בקבוצה"
                    checked={!!elevator.building_id}
                    onChange={() => {
                      if (elevator.building_id) {
                        assignBuildingMutation.mutate(null)
                      } else {
                        setAssignBuildingOpen(true)
                      }
                    }}
                  />
                  <Checkbox
                    label="תחת חברת ניהול"
                    checked={!!elevator.management_company_id}
                    onChange={() => {
                      if (elevator.management_company_id) {
                        assignCompanyMutation.mutate(null)
                      } else {
                        setAssignCompanyOpen(true)
                      }
                    }}
                  />
                  <Checkbox
                    label="תחת יועץ"
                    checked={!!elevator.consultant_id}
                    onChange={() => {
                      if (elevator.consultant_id) {
                        assignConsultantMutation.mutate(null)
                      } else {
                        setAssignConsultantOpen(true)
                      }
                    }}
                  />
                </Group>
                {elevator.building_id && (
                  <Text size="xs" c="dimmed" mt={4}>
                    {siblings.length > 0 ? `${siblings.length} מעליות נוספות בקבוצה זו` : 'מעלית זו היחידה בקבוצה'}
                    {elevator.management_company_id && ` · ${elevator.management_company_name ?? 'חברת ניהול'}`}
                  </Text>
                )}
                {elevator.consultant_id && elevator.consultant_name && (
                  <Text size="xs" c="dimmed" mt={2}>🧑‍💼 יועץ: {elevator.consultant_name}</Text>
                )}
              </Grid.Col>

              {/* Responsible technician, lead source */}
              <Grid.Col span={12}>
                <Divider label="שיוך טכנאי ומקור" labelPosition="right" mt="sm" mb="xs" />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Select
                    label="טכנאי אחראי"
                    placeholder="בחר טכנאי..."
                    searchable clearable
                    data={(techniciansList as any[]).map((t: any) => ({ value: t.id, label: t.name }))}
                    value={form.responsible_technician_id ?? null}
                    onChange={v => set('responsible_technician_id', v || null)}
                  />
                ) : (
                  <Field label="טכנאי אחראי" value={elevator.responsible_technician_name ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Select
                    label="טכנאי אחראי תחזוקה"
                    placeholder="בחר טכנאי תחזוקה..."
                    searchable clearable
                    data={(techniciansList as any[])
                      .filter((t: any) => t.role === 'MAINTENANCE_TECHNICIAN')
                      .map((t: any) => ({ value: t.id, label: t.name }))}
                    value={form.maintenance_technician_id ?? null}
                    onChange={v => set('maintenance_technician_id', v || null)}
                  />
                ) : (
                  <Field label="טכנאי אחראי תחזוקה" value={(elevator as any).maintenance_technician_name ?? undefined} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput
                    label="נכנסה מ (מקור)"
                    placeholder="המלצה, טנדר, פנייה ישירה..."
                    value={form.lead_source ?? ''}
                    onChange={e => set('lead_source', e.target.value || null)}
                  />
                ) : (
                  <Field label="נכנסה מ (מקור)" value={elevator.lead_source ?? undefined} />
                )}
              </Grid.Col>
            </Grid>
          </Paper>
        </Tabs.Panel>

        {/* ── SERVICE ── */}
        <Tabs.Panel value="service" pt="md">
          <Paper withBorder p="lg" radius="md">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Select label="סוג שירות"
                    data={[{ value: 'REGULAR', label: 'רגיל' }, { value: 'COMPREHENSIVE', label: 'מקיף' }]}
                    value={form.service_type ?? null}
                    onChange={v => {
                      set('service_type', v)
                      if (v === 'COMPREHENSIVE') { set('service_contract', 'ANNUAL_12'); set('maintenance_times_per_year', 12) }
                      else if (v === 'REGULAR') { set('service_contract', 'ANNUAL_6'); set('maintenance_times_per_year', 6) }
                    }}
                    clearable
                  />
                ) : (
                  <Field label="סוג שירות">
                    {elevator.service_type
                      ? <Badge color={elevator.service_type === 'COMPREHENSIVE' ? 'violet' : 'blue'} variant="light">
                          {elevator.service_type === 'COMPREHENSIVE' ? 'מקיף' : 'רגיל'}
                        </Badge>
                      : <Badge color="orange" variant="light">לא הוגדר</Badge>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Select
                    label="תדירות טיפול מונע"
                    data={[
                      { value: '12', label: '12 פעמים בשנה (חודשי)' },
                      { value: '6', label: '6 פעמים בשנה (כל 2 חודשים)' },
                      { value: '4', label: '4 פעמים בשנה (רבעוני)' },
                      { value: '2', label: '2 פעמים בשנה (חצי שנתי)' },
                    ]}
                    value={String(form.maintenance_times_per_year ?? 6)}
                    onChange={v => set('maintenance_times_per_year', v ? Number(v) : 6)}
                  />
                ) : (
                  <Field label="תדירות טיפול מונע" value={
                    elevator.maintenance_times_per_year
                      ? `${elevator.maintenance_times_per_year}× בשנה`
                      : '6× בשנה'
                  } />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Field label="טיפול אחרון">
                  <Text fw={500}>{formatDate(elevator.last_service_date) ?? '—'}</Text>
                </Field>
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Field label="טיפול הבא">
                  {elevator.next_service_date ? (
                    <Group gap="xs">
                      <Text fw={500}>{formatDate(elevator.next_service_date)}</Text>
                      {serviceUrgency && <Badge color={serviceUrgency} size="xs" variant="light">
                        {daysToService! < 0 ? `${Math.abs(daysToService!)} ימים חריגה` : `${daysToService} ימים`}
                      </Badge>}
                    </Group>
                  ) : <Text fw={500}>—</Text>}
                </Field>
              </Grid.Col>

              {/* Debt */}
              <Grid.Col span={12}><Divider label="חוב / הקפאה" labelPosition="right" /></Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <Checkbox label="קיים חוב" checked={form.has_debt ?? false} onChange={e => set('has_debt', e.target.checked)} mt="sm" />
                ) : (
                  <Field label="חוב">
                    {elevator.has_debt ? <Badge color="red" variant="filled">כן</Badge> : <Text fw={500}>לא</Text>}
                  </Field>
                )}
              </Grid.Col>
              {(editing ? form.has_debt : elevator.has_debt) && (
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  {editing ? (
                    <DateInput label="תאריך הקפאת שירות שוטף" value={parseDate(form.debt_freeze_date)} onChange={d => dateSet('debt_freeze_date', d)} clearable />
                  ) : (
                    <Field label="הקפאת שירות שוטף מ-" value={formatDate(elevator.debt_freeze_date)} />
                  )}
                </Grid.Col>
              )}
            </Grid>
          </Paper>
        </Tabs.Panel>

        {/* ── CONTACTS ── */}
        <Tabs.Panel value="contacts" pt="md">
          <Stack gap="md">

            {/* ועד הבית */}
            <Paper withBorder p="md" radius="md">
              <Group justify="space-between" mb="sm">
                <Group gap="xs">
                  <Text fw={700}>ועד הבית</Text>
                  <Badge color="blue" size="xs" variant="light">{contacts.filter(c => c.role === 'VAAD').length}</Badge>
                </Group>
                <Button size="xs" variant="light" onClick={() => openAddContact('VAAD')}>+ הוסף ועד</Button>
              </Group>
              {contacts.filter(c => c.role === 'VAAD').length === 0 ? (
                <Text size="sm" c="dimmed">אין אנשי ועד רשומים</Text>
              ) : (
                <Stack gap="xs">
                  {contacts.filter(c => c.role === 'VAAD').map(c => (
                    <Group key={c.id} justify="space-between" p="xs" style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
                      <Stack gap={1}>
                        <Text size="sm" fw={600}>{c.name}</Text>
                        <Group gap="sm">
                          {c.phone && <Anchor href={`tel:${c.phone}`} size="xs">{c.phone}</Anchor>}
                          {c.email && <Anchor href={`mailto:${c.email}`} size="xs">{c.email}</Anchor>}
                        </Group>
                      </Stack>
                      <ActionIcon size="xs" color="red" variant="subtle" onClick={() => deleteContactMutation.mutate(c.id)}>✕</ActionIcon>
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>

            {/* דיירים */}
            <Paper withBorder p="md" radius="md">
              <Group justify="space-between" mb="sm">
                <Group gap="xs">
                  <Text fw={700}>דיירים</Text>
                  <Badge color="teal" size="xs" variant="light">{contacts.filter(c => c.role === 'RESIDENT').length}</Badge>
                </Group>
                <Group gap="xs">
                  {contacts.filter(c => c.role === 'RESIDENT').length > 3 && (
                    <Button size="xs" variant="subtle" onClick={() => setResidentsExpanded(e => !e)}>
                      {residentsExpanded ? '▲ צמצם' : '▼ הצג הכל'}
                    </Button>
                  )}
                  <Button size="xs" variant="light" color="teal" onClick={() => openAddContact('RESIDENT')}>+ הוסף דייר</Button>
                </Group>
              </Group>
              {contacts.filter(c => c.role === 'RESIDENT').length === 0 ? (
                <Text size="sm" c="dimmed">אין דיירים רשומים</Text>
              ) : (
                <Stack gap="xs">
                  {(residentsExpanded
                    ? contacts.filter(c => c.role === 'RESIDENT')
                    : contacts.filter(c => c.role === 'RESIDENT').slice(0, 3)
                  ).map(c => (
                    <Group key={c.id} justify="space-between" p="xs" style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
                      <Stack gap={1}>
                        <Group gap="xs">
                          <Text size="sm" fw={500}>{c.name}</Text>
                          {c.auto_added && <Badge size="xs" color="gray" variant="light">אוטו׳</Badge>}
                        </Group>
                        <Group gap="sm">
                          {c.phone && <Anchor href={`tel:${c.phone}`} size="xs">{c.phone}</Anchor>}
                          {c.email && <Anchor href={`mailto:${c.email}`} size="xs">{c.email}</Anchor>}
                        </Group>
                      </Stack>
                      <ActionIcon size="xs" color="red" variant="subtle" onClick={() => deleteContactMutation.mutate(c.id)}>✕</ActionIcon>
                    </Group>
                  ))}
                  {!residentsExpanded && contacts.filter(c => c.role === 'RESIDENT').length > 3 && (
                    <Text size="xs" c="dimmed" ta="center">+ {contacts.filter(c => c.role === 'RESIDENT').length - 3} נוספים</Text>
                  )}
                </Stack>
              )}
            </Paper>

            {/* אחרים — חייגן, ניהול, אחר */}
            <Paper withBorder p="md" radius="md">
              <Group justify="space-between" mb="sm">
                <Text fw={700}>אנשי קשר נוספים</Text>
                <Button size="xs" variant="subtle" onClick={() => openAddContact('OTHER')}>+ הוסף</Button>
              </Group>
              {contacts.filter(c => !['VAAD', 'RESIDENT'].includes(c.role)).length === 0 ? (
                <Text size="sm" c="dimmed">אין אנשי קשר נוספים</Text>
              ) : (
                <Stack gap="xs">
                  {contacts.filter(c => !['VAAD', 'RESIDENT'].includes(c.role)).map(c => (
                    <Group key={c.id} justify="space-between" p="xs" style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
                      <Stack gap={1}>
                        <Group gap="xs">
                          <Text size="sm" fw={500}>{c.name}</Text>
                          <Badge color={ROLE_COLORS[c.role]} size="xs">{ROLE_LABELS[c.role]}</Badge>
                        </Group>
                        <Group gap="sm">
                          {c.phone && <Anchor href={`tel:${c.phone}`} size="xs">{c.phone}</Anchor>}
                          {c.email && <Anchor href={`mailto:${c.email}`} size="xs">{c.email}</Anchor>}
                        </Group>
                      </Stack>
                      <ActionIcon size="xs" color="red" variant="subtle" onClick={() => deleteContactMutation.mutate(c.id)}>✕</ActionIcon>
                    </Group>
                  ))}
                </Stack>
              )}
            </Paper>
          </Stack>
        </Tabs.Panel>

        {/* ── CONTRACT ── */}
        <Tabs.Panel value="contract" pt="md">
          <Paper withBorder p="lg" radius="md">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="תחילת התקשרות" value={parseDate(form.contract_start)} onChange={d => dateSet('contract_start', d)} clearable />
                ) : (
                  <Field label="תחילת התקשרות" value={formatDate(elevator.contract_start)} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Field label="חידוש הבא" value={formatDate(elevator.contract_renewal)} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="סיום התקשרות" value={parseDate(form.contract_end)} onChange={d => dateSet('contract_end', d)} clearable />
                ) : (
                  <Field label="סיום התקשרות" value={formatDate(elevator.contract_end) ?? 'פעיל'} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="תום אחריות" value={parseDate(form.warranty_end)} onChange={d => dateSet('warranty_end', d)} clearable />
                ) : (
                  <Field label="תום אחריות" value={formatDate(elevator.warranty_end)} />
                )}
              </Grid.Col>
              <Grid.Col span={12}>
                <Field label="הסכם שירות">
                  <Group gap="xs" wrap="nowrap">
                    {editing
                      ? <TextInput placeholder="https://drive.google.com/..." value={form.drive_link ?? ''} onChange={e => set('drive_link', e.target.value || null)} style={{ flex: 1 }} />
                      : elevator.drive_link
                        ? <Anchor href={elevator.drive_link} target="_blank" size="sm">📄 פתח הסכם</Anchor>
                        : <Text fw={500} size="sm">—</Text>
                    }
                    <FileInput
                      placeholder="העלה PDF"
                      accept=".pdf,.jpg,.jpeg,.png"
                      size="xs"
                      onChange={f => f && uploadFile('drive_link', f)}
                    />
                  </Group>
                </Field>
              </Grid.Col>
            </Grid>
          </Paper>
        </Tabs.Panel>

        {/* ── INSPECTION ── */}
        <Tabs.Panel value="inspection" pt="md">
          <Paper withBorder p="lg" radius="md">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Field label="ביקורת אחרונה" value={formatDate(elevator.last_inspection_date)} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <DateInput label="ביקורת הבאה" value={parseDate(form.next_inspection_date)} onChange={d => dateSet('next_inspection_date', d)} clearable />
                ) : (
                  <Field label="ביקורת הבאה" value={formatDate(elevator.next_inspection_date)} />
                )}
              </Grid.Col>

              <Grid.Col span={12}><Divider label="בודק מוסמך" labelPosition="right" mt="xs" /></Grid.Col>

              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="שם הבודק" value={form.inspector_name ?? ''} onChange={e => set('inspector_name', e.target.value || null)} />
                ) : (
                  <Field label="שם הבודק" value={elevator.inspector_name} />
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="טלפון" value={form.inspector_phone ?? ''} onChange={e => set('inspector_phone', e.target.value || null)} />
                ) : (
                  <Field label="טלפון">
                    {elevator.inspector_phone
                      ? <Anchor href={`tel:${elevator.inspector_phone}`} size="sm">{elevator.inspector_phone}</Anchor>
                      : <Text fw={500}>—</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="נייד" value={form.inspector_mobile ?? ''} onChange={e => set('inspector_mobile', e.target.value || null)} />
                ) : (
                  <Field label="נייד">
                    {elevator.inspector_mobile
                      ? <Anchor href={`tel:${elevator.inspector_mobile}`} size="sm">{elevator.inspector_mobile}</Anchor>
                      : <Text fw={500}>—</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="מייל" value={form.inspector_email ?? ''} onChange={e => set('inspector_email', e.target.value || null)} />
                ) : (
                  <Field label="מייל">
                    {elevator.inspector_email
                      ? <Anchor href={`mailto:${elevator.inspector_email}`} size="sm">{elevator.inspector_email}</Anchor>
                      : <Text fw={500}>—</Text>}
                  </Field>
                )}
              </Grid.Col>
              <Grid.Col span={12}>
                <Field label="תסקיר אחרון">
                  <Group gap="xs" wrap="nowrap">
                    {editing
                      ? <TextInput placeholder="https://..." value={form.last_inspection_report_url ?? ''} onChange={e => set('last_inspection_report_url', e.target.value || null)} style={{ flex: 1 }} />
                      : elevator.last_inspection_report_url
                        ? <Anchor href={elevator.last_inspection_report_url} target="_blank" size="sm">📋 פתח תסקיר</Anchor>
                        : <Text fw={500} size="sm">—</Text>
                    }
                    <FileInput
                      placeholder="העלה PDF"
                      accept=".pdf,.jpg,.jpeg,.png"
                      size="xs"
                      onChange={f => f && uploadFile('last_inspection_report_url', f)}
                    />
                  </Group>
                </Field>
              </Grid.Col>
            </Grid>
          </Paper>

          {/* ── Inspection history ── */}
          <InspectionHistory elevatorId={id!} />
        </Tabs.Panel>

        {/* ── CALLS ── */}
        <Tabs.Panel value="calls" pt="md">
          <Paper withBorder radius="md">
            {(calls as any[]).length === 0 ? (
              <Center h={200}><Text c="dimmed">אין קריאות שירות למעלית זו</Text></Center>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>עדיפות</Table.Th>
                    <Table.Th>תיאור</Table.Th>
                    <Table.Th>סוג תקלה</Table.Th>
                    <Table.Th>סטטוס</Table.Th>
                    <Table.Th>תאריך</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {(calls as any[]).map((call: any) => (
                    <Table.Tr
                      key={call.id}
                      style={{ cursor: 'pointer' }}
                      onClick={() => navigate(`/calls?callId=${call.id}`)}
                    >
                      <Table.Td><Badge color={PRIORITY_COLORS[call.priority]} size="sm">{PRIORITY_LABELS[call.priority]}</Badge></Table.Td>
                      <Table.Td><Text size="sm" lineClamp={2}>{call.description}</Text></Table.Td>
                      <Table.Td><Text size="sm">{FAULT_TYPE_LABELS[call.fault_type]}</Text></Table.Td>
                      <Table.Td><Badge color={CALL_STATUS_COLORS[call.status]} variant="light" size="sm">{CALL_STATUS_LABELS[call.status]}</Badge></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{formatDateTime(call.created_at)}</Text></Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        </Tabs.Panel>

        {/* ── LOG ── */}
        <Tabs.Panel value="log" pt="md">
          <ElevatorLog
            calls={calls as any[]}
            maintenance={maintenanceLogs}
            inspections={inspectionLogs}
            elevatorId={id!}
          />
        </Tabs.Panel>

        {/* ── GROUP ── */}
        <Tabs.Panel value="group" pt="md">
          <Stack gap="md">
            <Group justify="space-between">
              <Text fw={700}>מעליות בקבוצה ({siblings.length + 1})</Text>
              <Button size="xs" onClick={() => setAddToGroupOpen(true)}>+ הוסף מעלית לקבוצה</Button>
            </Group>

            {/* Current elevator */}
            <Paper withBorder p="xs" radius="sm" style={{ background: 'var(--mantine-color-blue-0)' }}>
              <Group justify="space-between" wrap="nowrap">
                <Group gap="xs">
                  <Text size="sm" fw={600} c="blue">
                    {elevator.internal_number ? `#${elevator.internal_number}` : elevator.id.slice(0, 8)}
                  </Text>
                  <Text size="sm" c="dimmed">{elevator.building_name || elevator.address}</Text>
                  <Badge size="xs" color="blue" variant="dot">נוכחית</Badge>
                </Group>
                <Badge color={ELEVATOR_STATUS_COLORS[elevator.status]} size="xs" variant="light">
                  {ELEVATOR_STATUS_LABELS[elevator.status]}
                </Badge>
              </Group>
            </Paper>

            {siblings.map((s: any) => (
              <Paper key={s.id} withBorder p="xs" radius="sm" style={{ cursor: 'pointer' }} onClick={() => navigate(`/elevators/${s.id}`)}>
                <Group justify="space-between" wrap="nowrap">
                  <Group gap="xs">
                    <Text size="sm" fw={500}>{s.internal_number ? `#${s.internal_number}` : s.id.slice(0, 8)}</Text>
                    <Text size="sm" c="dimmed">{s.building_name || s.address}</Text>
                  </Group>
                  <Group gap="xs">
                    <Badge color={ELEVATOR_STATUS_COLORS[s.status]} size="xs" variant="light">
                      {ELEVATOR_STATUS_LABELS[s.status]}
                    </Badge>
                    <ActionIcon size="xs" color="red" variant="subtle"
                      onClick={e => {
                        e.stopPropagation()
                        client.put(`/elevators/${s.id}`, { building_id: null }).then(() => {
                          qc.invalidateQueries({ queryKey: ['building-detail', elevator.building_id] })
                        })
                      }}
                    >✕</ActionIcon>
                  </Group>
                </Group>
              </Paper>
            ))}

            {siblings.length === 0 && (
              <Text size="sm" c="dimmed">אין מעליות נוספות בקבוצה זו. לחץ "+ הוסף מעלית לקבוצה" כדי לשייך מעלית.</Text>
            )}

            <Divider />
            <Button variant="subtle" color="red" size="xs" onClick={() => assignBuildingMutation.mutate(null)}>
              הסר מעלית זו מהקבוצה
            </Button>
          </Stack>
        </Tabs.Panel>

        {/* ── MANAGEMENT COMPANY ── */}
        <Tabs.Panel value="management" pt="md">
          <Stack gap="md">
            {companyDetail ? (
              <Paper withBorder p="md" radius="md">
                <Group justify="space-between" mb="sm" align="flex-start">
                  <Stack gap={2}>
                    <Text fw={700} size="lg">{companyDetail.name}</Text>
                    {companyDetail.contact_name && <Text size="sm" c="dimmed">{companyDetail.contact_name}</Text>}
                  </Stack>
                  <Button size="xs" variant="light" onClick={() => navigate('/management-companies')}>
                    לדף חברות הניהול ←
                  </Button>
                </Group>
                <Grid>
                  {companyDetail.phone && (
                    <Grid.Col span={{ base: 12, sm: 6 }}>
                      <Field label="טלפון">
                        <Anchor href={`tel:${companyDetail.phone}`} size="sm">{companyDetail.phone}</Anchor>
                      </Field>
                    </Grid.Col>
                  )}
                  {companyDetail.email && (
                    <Grid.Col span={{ base: 12, sm: 6 }}>
                      <Field label="מייל">
                        <Anchor href={`mailto:${companyDetail.email}`} size="sm">{companyDetail.email}</Anchor>
                      </Field>
                    </Grid.Col>
                  )}
                  {companyDetail.notes && (
                    <Grid.Col span={12}>
                      <Field label="הערות" value={companyDetail.notes} />
                    </Grid.Col>
                  )}
                </Grid>
              </Paper>
            ) : (
              <Text size="sm" c="dimmed">טוען פרטי חברה...</Text>
            )}

            {/* Other elevators under same company */}
            {(companyDetail?.elevators ?? []).filter((e: any) => e.id !== id).length > 0 && (
              <Stack gap="xs">
                <Text fw={600}>
                  מעליות נוספות תחת חברה זו ({(companyDetail?.elevators ?? []).filter((e: any) => e.id !== id).length})
                </Text>
                {(companyDetail?.elevators ?? []).filter((e: any) => e.id !== id).map((e: any) => (
                  <Paper key={e.id} withBorder p="xs" radius="sm"
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/elevators/${e.id}`)}
                  >
                    <Group justify="space-between">
                      <Stack gap={0}>
                        <Text size="sm" fw={500}>{e.address}</Text>
                        <Text size="xs" c="dimmed">{e.city}</Text>
                      </Stack>
                      <Badge color={ELEVATOR_STATUS_COLORS[e.status ?? 'ACTIVE']} size="xs" variant="light">
                        {ELEVATOR_STATUS_LABELS[e.status ?? 'ACTIVE']}
                      </Badge>
                    </Group>
                  </Paper>
                ))}
              </Stack>
            )}

            <Divider />
            <Button variant="subtle" color="red" size="xs"
              loading={assignCompanyMutation.isPending}
              onClick={() => assignCompanyMutation.mutate(null)}
            >
              הסר מחברת הניהול
            </Button>
          </Stack>
        </Tabs.Panel>
      </Tabs>

      <LocationPickerModal
        opened={locationPickerOpen}
        onClose={() => setLocationPickerOpen(false)}
        onSave={(lat, lng) => locationMutation.mutate({ lat, lng })}
        initialLat={elevator.latitude}
        initialLng={elevator.longitude}
        loading={locationMutation.isPending}
      />
    </Stack>
  )
}
