import React, { useState, useMemo } from 'react'
import {
  Stack, Title, Group, Select, Badge, Text, Button, Paper, TextInput,
  Modal, Textarea, Pagination, Table, ScrollArea, Loader, Center,
  Divider, Timeline, ThemeIcon, Box, Checkbox, Alert, ActionIcon, NumberInput,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { listCalls, createCall, updateCall, getCallDetails, autoAssignCall, setCallMonitoring, manualAssignCall, resetAndReassignCall } from '../api/calls'
import { listElevators, updateElevator } from '../api/elevators'
import client from '../api/client'
import LocationPickerModal from '../components/LocationPickerModal'
import { listTechnicians } from '../api/technicians'
import { useAuthStore } from '../stores/authStore'
import {
  PRIORITY_LABELS, PRIORITY_COLORS, CALL_STATUS_LABELS, CALL_STATUS_COLORS, FAULT_TYPE_LABELS,
} from '../utils/constants'
import { formatDateTime } from '../utils/dates'
import { ServiceCall, CallDetail } from '../types'

const PAGE_SIZE = 20

const rescueStyle: React.CSSProperties = {
  animation: 'rescue-blink 1.2s ease-in-out infinite',
  backgroundColor: 'rgba(255,50,50,0.08)',
}

// inject keyframes once
if (typeof document !== 'undefined' && !document.getElementById('rescue-blink-style')) {
  const s = document.createElement('style')
  s.id = 'rescue-blink-style'
  s.textContent = `@keyframes rescue-blink { 0%,100%{background-color:rgba(255,50,50,0.08)} 50%{background-color:rgba(255,50,50,0.24)} }`
  document.head.appendChild(s)
}

const ASSIGNMENT_STATUS_LABELS: Record<string, string> = {
  PENDING_CONFIRMATION: 'ממתין לאישור',
  CONFIRMED: 'אושר',
  REJECTED: 'נדחה',
  CANCELLED: 'בוטל',
  AUTO_ASSIGNED: 'הושלם',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge color={CALL_STATUS_COLORS[status] ?? 'gray'} variant="light" size="sm">
      {CALL_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

export default function CallsPage() {
  const qc = useQueryClient()
  const userName = useAuthStore(s => s.userName)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [priorityFilter, setPriorityFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [newOpened, { open: openNew, close: closeNew }] = useDisclosure()
  const [updateOpened, { open: openUpdate, close: closeUpdate }] = useDisclosure()
  const [detailOpened, { open: openDetail, close: closeDetail }] = useDisclosure()
  const [selectedCall, setSelectedCall] = useState<ServiceCall | null>(null)
  const [detailCall, setDetailCall] = useState<CallDetail | null>(null)
  const [monitorNotes, setMonitorNotes] = useState('')
  const [monitorOpened, { open: openMonitor, close: closeMonitor }] = useDisclosure()
  const [assignOpened, { open: openAssign, close: closeAssign }] = useDisclosure()
  const [assignTechId, setAssignTechId] = useState<string | null>(null)
  const [assignNotes, setAssignNotes] = useState('')
  const [changeElevOpened, { open: openChangeElev, close: closeChangeElev }] = useDisclosure()
  const [changeElevId, setChangeElevId] = useState<string | null>(null)
  const [locationPickerElevId, setLocationPickerElevId] = useState<string | null>(null)
  const [locationPickerOpen, setLocationPickerOpen] = useState(false)
  const [addElevOpened, { open: openAddElev, close: closeAddElev }] = useDisclosure()
  const [addElevForm, setAddElevForm] = useState({
    address: '', city: '', contact_phone: '', building_name: '', floor_count: 1, notes: '',
  })

  const [newForm, setNewForm] = useState({
    elevator_id: '',
    description: '',
    priority: 'MEDIUM',
    fault_type: 'OTHER',
  })
  const [updateForm, setUpdateForm] = useState({
    status: '',
    priority: '',
    fault_type: '',
    description: '',
    resolution_notes: '',
    quote_needed: false,
  })

  const { data: calls = [], isLoading } = useQuery({
    queryKey: ['calls'],
    queryFn: () => listCalls(),
    refetchInterval: 30_000,
  })

  const { data: elevators = [] } = useQuery({
    queryKey: ['elevators'],
    queryFn: () => listElevators(),
  })

  const { data: technicians = [] } = useQuery({
    queryKey: ['technicians'],
    queryFn: () => listTechnicians(),
  })

  const { data: callDetail, isLoading: detailLoading } = useQuery({
    queryKey: ['call-detail', detailCall?.id],
    queryFn: () => getCallDetails(detailCall!.id),
    enabled: !!detailCall,
  })

  const elevatorOptions = elevators.map(e => ({
    value: e.id,
    label: `${e.internal_number ? `#${e.internal_number} — ` : ''}${e.address}, ${e.city}`,
  }))

  const filtered = useMemo(() => {
    return calls.filter(c => {
      if (c.fault_type === 'MAINTENANCE') return false
      const matchStatus = !statusFilter || c.status === statusFilter
      const matchPriority = !priorityFilter || c.priority === priorityFilter
      return matchStatus && matchPriority
    })
  }, [calls, statusFilter, priorityFilter])

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const createMutation = useMutation({
    mutationFn: createCall,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      notifications.show({ message: 'קריאת שירות נפתחה', color: 'green' })
      closeNew()
      setNewForm({ elevator_id: '', description: '', priority: 'MEDIUM', fault_type: 'OTHER' })
    },
    onError: () => notifications.show({ message: 'שגיאה בפתיחת קריאה', color: 'red' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => updateCall(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: 'קריאה עודכנה', color: 'green' })
      closeUpdate()
    },
    onError: () => notifications.show({ message: 'שגיאה בעדכון', color: 'red' }),
  })

  const reassignMutation = useMutation({
    mutationFn: (id: string) => autoAssignCall(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: 'הקריאה הועברה לטכנאי הבא', color: 'blue' })
      closeDetail()
    },
    onError: () => notifications.show({ message: 'לא נמצא טכנאי פנוי', color: 'red' }),
  })

  const resetReassignMutation = useMutation({
    mutationFn: (id: string) => resetAndReassignCall(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: '🔄 הדחיות אופסו — הקריאה נשלחה מחדש', color: 'blue' })
      closeDetail()
    },
    onError: () => notifications.show({ message: 'לא נמצא טכנאי פנוי', color: 'red' }),
  })

  const manualAssignMutation = useMutation({
    mutationFn: ({ id, techId, notes }: { id: string; techId: string; notes: string }) =>
      manualAssignCall(id, techId, notes || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: '✅ הקריאה שובצה לטכנאי', color: 'green' })
      closeAssign()
      closeDetail()
      setAssignTechId(null)
      setAssignNotes('')
    },
    onError: () => notifications.show({ message: 'שגיאה בשיבוץ', color: 'red' }),
  })

  const monitorMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => setCallMonitoring(id, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: 'הקריאה הועברה למעקב', color: 'teal' })
      closeMonitor()
      closeDetail()
      setMonitorNotes('')
    },
    onError: () => notifications.show({ message: 'שגיאה בהעברה למעקב', color: 'red' }),
  })

  const addElevMutation = useMutation({
    mutationFn: async ({ callId, form }: { callId: string; form: typeof addElevForm }) => {
      const { data: elev } = await client.post('/elevators/', {
        address: form.address, city: form.city,
        contact_phone: form.contact_phone || null,
        building_name: form.building_name || null,
        floor_count: form.floor_count || 1,
        notes: form.notes || null,
      })
      await client.patch(`/calls/${callId}/elevator`, null, { params: { elevator_id: elev.id } })
      return elev
    },
    onSuccess: (elev) => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: `🏗️ מעלית חדשה נוספה: ${elev.address}, ${elev.city}`, color: 'teal' })
      closeAddElev()
      closeDetail()
      setAddElevForm({ address: '', city: '', contact_phone: '', building_name: '', floor_count: 1, notes: '' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בהוספת מעלית', color: 'red' }),
  })

  const changeElevMutation = useMutation({
    mutationFn: ({ callId, elevId }: { callId: string; elevId: string }) =>
      client.patch(`/calls/${callId}/elevator`, null, { params: { elevator_id: elevId } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      qc.invalidateQueries({ queryKey: ['call-detail'] })
      notifications.show({ message: '🏢 הכתובת עודכנה בהצלחה', color: 'teal' })
      closeChangeElev()
      closeDetail()
      setChangeElevId(null)
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בעדכון כתובת', color: 'red' }),
  })

  const userRole = useAuthStore(s => s.userRole)
  const isAdmin = userRole === 'ADMIN'

  const deleteCallMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/calls/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calls'] })
      notifications.show({ message: 'הקריאה נמחקה', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה במחיקה', color: 'red' }),
  })

  const saveLocationMutation = useMutation({
    mutationFn: ({ elevId, lat, lng }: { elevId: string; lat: number; lng: number }) =>
      updateElevator(elevId, { latitude: lat, longitude: lng } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevators'] })
      setLocationPickerOpen(false)
      setLocationPickerElevId(null)
      notifications.show({ message: '📍 מיקום עודכן', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירת מיקום', color: 'red' }),
  })

  function openDetailModal(call: ServiceCall) {
    setDetailCall(call as CallDetail)
    openDetail()
  }

  function openUpdateModal(call: ServiceCall) {
    setSelectedCall(call)
    setUpdateForm({
      status: call.status,
      priority: call.priority,
      fault_type: call.fault_type,
      description: call.description,
      resolution_notes: call.resolution_notes ?? '',
      quote_needed: call.quote_needed ?? false,
    })
    openUpdate()
  }

  const detail = callDetail ?? detailCall

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>קריאות שירות ({filtered.length})</Title>
        <Button onClick={openNew}>+ קריאה חדשה</Button>
      </Group>

      <Group>
        <Select
          placeholder="סטטוס"
          data={[
            { value: 'OPEN', label: 'פתוחה' },
            { value: 'ASSIGNED', label: 'שובצה' },
            { value: 'IN_PROGRESS', label: 'בטיפול' },
            { value: 'RESOLVED', label: 'נפתרה' },
            { value: 'CLOSED', label: 'סגורה' },
          ]}
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
          clearable w={160}
        />
        <Select
          placeholder="עדיפות"
          data={[
            { value: 'CRITICAL', label: 'קריטי' },
            { value: 'HIGH', label: 'גבוה' },
            { value: 'MEDIUM', label: 'בינוני' },
            { value: 'LOW', label: 'נמוך' },
          ]}
          value={priorityFilter}
          onChange={v => { setPriorityFilter(v); setPage(1) }}
          clearable w={140}
        />
      </Group>

      <Paper withBorder radius="md">
        {isLoading ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <ScrollArea>
            <Table highlightOnHover style={{ cursor: 'pointer' }}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>עדיפות</Table.Th>
                  <Table.Th>תיאור</Table.Th>
                  <Table.Th>סוג תקלה</Table.Th>
                  <Table.Th>סטטוס</Table.Th>
                  <Table.Th>דווח ע"י</Table.Th>
                  <Table.Th>תאריך</Table.Th>
                  <Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paginated.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={7}><Center h={100}><Text c="dimmed">לא נמצאו קריאות</Text></Center></Table.Td>
                  </Table.Tr>
                ) : paginated.map(c => {
                  const isRescue = c.fault_type === 'RESCUE'
                  return (
                    <Table.Tr
                      key={c.id}
                      onClick={() => openDetailModal(c)}
                      style={isRescue && !['RESOLVED','CLOSED'].includes(c.status) ? rescueStyle : undefined}
                    >
                      <Table.Td>
                        <Group gap={4}>
                          {isRescue && <Text size="sm">🚨</Text>}
                          <Badge color={PRIORITY_COLORS[c.priority]} size="sm">{PRIORITY_LABELS[c.priority]}</Badge>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Stack gap={0}>
                          <Text size="sm" lineClamp={1} fw={isRescue ? 700 : undefined}>{c.description}</Text>
                          <Group gap={4}>
                            {isRescue && <Text size="xs" c="red" fw={700}>🚨 חילוץ</Text>}
                            {c.is_recurring && <Text size="xs" c="orange">🔁 חוזרת</Text>}
                            {c.quote_needed && <Text size="xs" c="yellow">💰 הצעת מחיר</Text>}
                          </Group>
                        </Stack>
                      </Table.Td>
                      <Table.Td><Text size="sm">{FAULT_TYPE_LABELS[c.fault_type]}</Text></Table.Td>
                      <Table.Td><StatusBadge status={c.status} /></Table.Td>
                      <Table.Td><Text size="sm">{c.reported_by}</Text></Table.Td>
                      <Table.Td><Text size="xs" c="dimmed">{formatDateTime(c.created_at)}</Text></Table.Td>
                      <Table.Td onClick={e => e.stopPropagation()}>
                        <Group gap="xs">
                          <Button size="xs" variant="light" onClick={() => openUpdateModal(c)}>עדכן</Button>
                          {isAdmin && (
                            <ActionIcon
                              size="sm" color="red" variant="subtle"
                              onClick={() => { if (window.confirm('למחוק קריאה זו?')) deleteCallMutation.mutate(c.id) }}
                            >🗑️</ActionIcon>
                          )}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Paper>

      {filtered.length > PAGE_SIZE && (
        <Group justify="center">
          <Pagination total={Math.ceil(filtered.length / PAGE_SIZE)} value={page} onChange={setPage} />
        </Group>
      )}

      {/* ── Detail modal ── */}
      <Modal
        opened={detailOpened}
        onClose={closeDetail}
        title={<Text fw={700} size="lg">פרטי קריאת שירות</Text>}
        size="lg"
      >
        {detailLoading || !detail ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <Stack gap="md">
            {/* Header badges */}
            <Group>
              <Badge color={PRIORITY_COLORS[detail.priority]}>{PRIORITY_LABELS[detail.priority]}</Badge>
              <StatusBadge status={detail.status} />
              {detail.is_recurring && <Badge color="orange" variant="light">🔁 תקלה חוזרת</Badge>}
              {detail.quote_needed && <Badge color="yellow" variant="filled">💰 נדרשת הצעת מחיר</Badge>}
            </Group>

            {/* Elevator + call info */}
            <Paper withBorder p="md" radius="md">
              <Stack gap="xs">
                {'elevator_address' in detail && (
                  <Group gap="xs">
                    <Text size="sm" c="dimmed" w={100}>📍 כתובת</Text>
                    <Text size="sm" fw={600}>{detail.elevator_address}, {detail.elevator_city}</Text>
                    {detail.elevator_serial && <Text size="xs" c="dimmed">#{detail.elevator_serial}</Text>}
                    <Button
                      size="xs" variant="subtle" color="teal" px={6}
                      onClick={() => { setLocationPickerElevId(detail.elevator_id); setLocationPickerOpen(true) }}
                    >📍 עדכן מיקום</Button>
                  </Group>
                )}
                <Group gap="xs">
                  <Text size="sm" c="dimmed" w={100}>⚡ סוג תקלה</Text>
                  <Text size="sm">{FAULT_TYPE_LABELS[detail.fault_type]}</Text>
                </Group>
                <Group gap="xs">
                  <Text size="sm" c="dimmed" w={100}>👤 דווח ע"י</Text>
                  <Text size="sm">{detail.reported_by}</Text>
                </Group>
                <Group gap="xs">
                  <Text size="sm" c="dimmed" w={100}>📅 נפתחה</Text>
                  <Text size="sm">{formatDateTime(detail.created_at)}</Text>
                </Group>
                {detail.resolved_at && (
                  <Group gap="xs">
                    <Text size="sm" c="dimmed" w={100}>✅ נסגרה</Text>
                    <Text size="sm">{formatDateTime(detail.resolved_at)}</Text>
                  </Group>
                )}
              </Stack>
            </Paper>

            {/* Description */}
            <Box>
              <Text size="sm" c="dimmed" mb={4}>תיאור התקלה</Text>
              <Text size="sm">{detail.description}</Text>
            </Box>

            {/* Technician report — shown when resolved */}
            {(detail.status === 'RESOLVED' || detail.status === 'CLOSED') && (
              <>
                <Divider label="דו״ח טכנאי" labelPosition="center" />
                {detail.resolution_notes ? (
                  <Paper withBorder p="md" radius="md" bg="green.0">
                    <Text size="sm" c="dimmed" mb={6}>פרטי הטיפול</Text>
                    <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>{detail.resolution_notes}</Text>
                  </Paper>
                ) : (
                  <Text size="sm" c="dimmed" fs="italic">לא הוזן דו"ח טכנאי</Text>
                )}
                {detail.quote_needed && (
                  <Alert color="yellow" title="💰 נדרשת הצעת מחיר ללקוח" radius="md">
                    הטכנאי ציין כי יש להכין הצעת מחיר ולשלוח ללקוח.
                  </Alert>
                )}
              </>
            )}

            {/* Assignments */}
            {'assignments' in detail && detail.assignments.length > 0 && (
              <>
                <Divider label="שיבוץ טכנאים" labelPosition="center" />
                <Stack gap="xs">
                  {detail.assignments.map(a => (
                    <Paper key={a.id} withBorder p="sm" radius="md">
                      <Group justify="space-between">
                        <Group gap="xs">
                          <Text size="sm" fw={600}>👨‍🔧 {a.technician_name}</Text>
                          <Badge size="xs" color="gray" variant="light">
                            {ASSIGNMENT_STATUS_LABELS[a.status] ?? a.status}
                          </Badge>
                        </Group>
                        <Group gap="xs">
                          {a.travel_minutes && (
                            <Text size="xs" c="dimmed">🚗 ~{a.travel_minutes} דק׳</Text>
                          )}
                          <Text size="xs" c="dimmed">{formatDateTime(a.assigned_at)}</Text>
                        </Group>
                      </Group>
                    </Paper>
                  ))}
                </Stack>
              </>
            )}

            {/* Audit trail */}
            {'audit_logs' in detail && detail.audit_logs.length > 0 && (
              <>
                <Divider label="היסטוריית סטטוסים" labelPosition="center" />
                <Timeline active={detail.audit_logs.length - 1} bulletSize={20} lineWidth={2}>
                  {detail.audit_logs.map(log => (
                    <Timeline.Item
                      key={log.id}
                      bullet={<Text size="xs">•</Text>}
                      title={
                        <Group gap="xs">
                          {log.old_status && (
                            <StatusBadge status={log.old_status} />
                          )}
                          {log.old_status && <Text size="xs" c="dimmed">→</Text>}
                          <StatusBadge status={log.new_status} />
                        </Group>
                      }
                    >
                      <Text size="xs" c="dimmed">{log.changed_by} · {formatDateTime(log.changed_at)}</Text>
                      {log.notes && <Text size="xs" mt={2}>{log.notes}</Text>}
                    </Timeline.Item>
                  ))}
                </Timeline>
              </>
            )}

            <Group justify="flex-end" mt="md">
              <Button variant="default" onClick={closeDetail}>סגור</Button>
              {detail && ['OPEN', 'ASSIGNED', 'IN_PROGRESS'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="grape"
                  onClick={() => { setSelectedCall(detail); setChangeElevId(null); openChangeElev() }}
                >
                  🔗 שייך למעלית קיימת
                </Button>
              )}
              {detail && ['OPEN', 'ASSIGNED', 'IN_PROGRESS'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="teal"
                  onClick={() => {
                    setSelectedCall(detail)
                    const phone = /^\+?[\d\s\-]{7,}$/.test(detail.reported_by ?? '') ? detail.reported_by : ''
                    setAddElevForm({
                      address: detail.elevator_address?.split(',')[0]?.trim() || '',
                      city: detail.elevator_city || '',
                      contact_phone: phone,
                      building_name: '',
                      floor_count: 1,
                      notes: '',
                    })
                    openAddElev()
                  }}
                >
                  🏗️ הוסף מעלית חדשה
                </Button>
              )}
              {detail && ['OPEN', 'ASSIGNED', 'IN_PROGRESS'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="teal"
                  onClick={() => { setSelectedCall(detail); openMonitor() }}
                >
                  🔍 העבר למעקב
                </Button>
              )}
              {detail && ['OPEN', 'ASSIGNED'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="blue"
                  onClick={() => { setSelectedCall(detail); openAssign() }}
                >
                  👨‍🔧 שבץ טכנאי
                </Button>
              )}
              {detail && ['OPEN', 'ASSIGNED'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="orange"
                  loading={reassignMutation.isPending}
                  onClick={() => detail && reassignMutation.mutate(detail.id)}
                >
                  🔄 העבר לטכנאי הבא
                </Button>
              )}
              {detail && ['OPEN', 'ASSIGNED'].includes(detail.status) && (
                <Button
                  variant="light"
                  color="red"
                  loading={resetReassignMutation.isPending}
                  onClick={() => detail && resetReassignMutation.mutate(detail.id)}
                >
                  ♻️ שלח שוב לכולם
                </Button>
              )}
              <Button onClick={() => {
                closeDetail()
                openUpdateModal(detail)
              }}>
                ✏️ עריכה
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>

      {/* ── New call modal ── */}
      <Modal opened={newOpened} onClose={closeNew} title="פתח קריאת שירות חדשה" size="lg">
        <Stack gap="sm">
          <Select
            label="מעלית" placeholder="בחר מעלית..." required
            data={elevatorOptions}
            value={newForm.elevator_id}
            onChange={v => setNewForm(s => ({ ...s, elevator_id: v ?? '' }))}
            searchable
          />
          <Textarea
            label="תיאור התקלה" required minRows={3}
            value={newForm.description}
            onChange={e => setNewForm(s => ({ ...s, description: e.target.value }))}
          />
          <Group grow>
            <Select
              label="עדיפות"
              data={[
                { value: 'CRITICAL', label: 'קריטי' }, { value: 'HIGH', label: 'גבוה' },
                { value: 'MEDIUM', label: 'בינוני' }, { value: 'LOW', label: 'נמוך' },
              ]}
              value={newForm.priority}
              onChange={v => setNewForm(s => ({ ...s, priority: v ?? 'MEDIUM' }))}
            />
            <Select
              label="סוג תקלה"
              data={[
                { value: 'MECHANICAL', label: 'מכאני' }, { value: 'ELECTRICAL', label: 'חשמלי' },
                { value: 'SOFTWARE', label: 'תוכנה' }, { value: 'STUCK', label: 'תקועה' },
                { value: 'DOOR', label: 'דלת' }, { value: 'RESCUE', label: '🚨 חילוץ' },
                { value: 'OTHER', label: 'אחר' },
              ]}
              value={newForm.fault_type}
              onChange={v => setNewForm(s => ({ ...s, fault_type: v ?? 'OTHER' }))}
            />
          </Group>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeNew}>ביטול</Button>
            <Button
              loading={createMutation.isPending}
              disabled={!newForm.elevator_id || !newForm.description}
              onClick={() => createMutation.mutate({
                elevator_id: newForm.elevator_id,
                reported_by: userName || 'מזכירה',
                description: newForm.description,
                priority: newForm.priority,
                fault_type: newForm.fault_type,
              })}
            >
              פתח קריאה
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* ── Monitor modal ── */}
      <Modal opened={monitorOpened} onClose={closeMonitor} title="🔍 העבר למעקב">
        <Stack gap="sm">
          <Text size="sm">המעלית חזרה לפעול? העבר את הקריאה למעקב — העדיפות תרד ל-LOW והקריאה תיסגר אוטומטית אחרי 7 ימים ללא תקלה חוזרת.</Text>
          <Textarea
            label="הערות מעקב"
            placeholder="לדוגמה: דיברתי עם הלקוח, המעלית חזרה לפעול"
            value={monitorNotes}
            onChange={e => setMonitorNotes(e.target.value)}
            rows={3}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={closeMonitor}>ביטול</Button>
            <Button
              color="teal"
              loading={monitorMutation.isPending}
              onClick={() => selectedCall && monitorMutation.mutate({ id: selectedCall.id, notes: monitorNotes })}
            >
              אשר מעקב
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* ── Manual assign modal ── */}
      <Modal opened={assignOpened} onClose={closeAssign} title="👨‍🔧 שיבוץ ידני לטכנאי">
        <Stack gap="sm">
          <Select
            label="בחר טכנאי"
            placeholder="בחר..."
            data={technicians
              .filter(t => t.is_active)
              .map(t => ({ value: t.id, label: `${t.name}${t.is_available ? '' : ' (לא זמין)'}` }))}
            value={assignTechId}
            onChange={setAssignTechId}
            searchable
          />
          <Textarea
            label="הערות (אופציונלי)"
            placeholder="הערות לשיבוץ..."
            value={assignNotes}
            onChange={e => setAssignNotes(e.target.value)}
            rows={2}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={closeAssign}>ביטול</Button>
            <Button
              color="blue"
              disabled={!assignTechId}
              loading={manualAssignMutation.isPending}
              onClick={() => selectedCall && assignTechId && manualAssignMutation.mutate({
                id: selectedCall.id,
                techId: assignTechId,
                notes: assignNotes,
              })}
            >
              שבץ
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* ── Update modal ── */}
      <Modal opened={updateOpened} onClose={closeUpdate} title="✏️ עריכת קריאת שירות" size="lg">
        <Stack gap="sm">
          <Textarea
            label="תיאור התקלה" required minRows={3}
            value={updateForm.description}
            onChange={e => setUpdateForm(s => ({ ...s, description: e.target.value }))}
          />
          <Group grow>
            <Select
              label="עדיפות"
              data={[
                { value: 'CRITICAL', label: 'קריטי' }, { value: 'HIGH', label: 'גבוה' },
                { value: 'MEDIUM', label: 'בינוני' }, { value: 'LOW', label: 'נמוך' },
              ]}
              value={updateForm.priority}
              onChange={v => setUpdateForm(s => ({ ...s, priority: v ?? 'MEDIUM' }))}
            />
            <Select
              label="סוג תקלה"
              data={[
                { value: 'MECHANICAL', label: 'מכאני' }, { value: 'ELECTRICAL', label: 'חשמלי' },
                { value: 'SOFTWARE', label: 'תוכנה' }, { value: 'STUCK', label: 'תקועה' },
                { value: 'DOOR', label: 'דלת' }, { value: 'RESCUE', label: '🚨 חילוץ' },
                { value: 'OTHER', label: 'אחר' },
              ]}
              value={updateForm.fault_type}
              onChange={v => setUpdateForm(s => ({ ...s, fault_type: v ?? 'OTHER' }))}
            />
          </Group>
          <Select
            label="סטטוס"
            data={[
              { value: 'OPEN', label: 'פתוחה' }, { value: 'ASSIGNED', label: 'שובצה' },
              { value: 'IN_PROGRESS', label: 'בטיפול' }, { value: 'RESOLVED', label: 'נפתרה' },
              { value: 'CLOSED', label: 'סגורה' }, { value: 'MONITORING', label: 'במעקב' },
            ]}
            value={updateForm.status}
            onChange={v => setUpdateForm(s => ({ ...s, status: v ?? '' }))}
          />
          <Textarea
            label='הערות / דו"ח טיפול' minRows={3}
            value={updateForm.resolution_notes}
            onChange={e => setUpdateForm(s => ({ ...s, resolution_notes: e.target.value }))}
          />
          <Checkbox
            label="💰 נדרשת הצעת מחיר ללקוח"
            checked={updateForm.quote_needed}
            onChange={e => setUpdateForm(s => ({ ...s, quote_needed: e.currentTarget.checked }))}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeUpdate}>ביטול</Button>
            <Button
              loading={updateMutation.isPending}
              disabled={!updateForm.description}
              onClick={() => selectedCall && updateMutation.mutate({
                id: selectedCall.id,
                payload: {
                  status: updateForm.status || undefined,
                  priority: updateForm.priority || undefined,
                  fault_type: updateForm.fault_type || undefined,
                  description: updateForm.description || undefined,
                  resolution_notes: updateForm.resolution_notes || undefined,
                  quote_needed: updateForm.quote_needed,
                },
              })}
            >
              שמור
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* ── Change elevator modal ── */}
      <Modal opened={changeElevOpened} onClose={closeChangeElev} title="🏢 שנה מעלית לקריאה" size="md" dir="rtl">
        <Stack gap="sm">
          {selectedCall && (
            <Text size="sm" c="dimmed">
              קריאה #{selectedCall.id.slice(0, 8)} — בחר מעלית חדשה מהרשימה
            </Text>
          )}
          <Select
            label="מעלית"
            placeholder="חפש לפי כתובת..."
            data={elevatorOptions}
            value={changeElevId}
            onChange={setChangeElevId}
            searchable
            clearable
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={closeChangeElev}>ביטול</Button>
            <Button
              color="grape"
              disabled={!changeElevId}
              loading={changeElevMutation.isPending}
              onClick={() => {
                if (selectedCall && changeElevId)
                  changeElevMutation.mutate({ callId: selectedCall.id, elevId: changeElevId })
              }}
            >
              עדכן מעלית
            </Button>
          </Group>
        </Stack>
      </Modal>
      {/* ── Add new elevator modal ── */}
      <Modal opened={addElevOpened} onClose={closeAddElev} title="🏗️ הוסף מעלית חדשה לקריאה" size="md" dir="rtl">
        <Stack gap="sm">
          <Text size="sm" c="dimmed">הפרטים נמשכו מהקריאה — השלם ועדכן לפני שמירה</Text>
          <Group grow>
            <TextInput label="רחוב ומספר בית" required
              value={addElevForm.address}
              onChange={e => setAddElevForm(s => ({ ...s, address: e.target.value }))} />
            <TextInput label="עיר" required
              value={addElevForm.city}
              onChange={e => setAddElevForm(s => ({ ...s, city: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="שם בניין"
              value={addElevForm.building_name}
              onChange={e => setAddElevForm(s => ({ ...s, building_name: e.target.value }))} />
            <TextInput label="טלפון איש קשר" dir="ltr"
              value={addElevForm.contact_phone}
              onChange={e => setAddElevForm(s => ({ ...s, contact_phone: e.target.value }))} />
          </Group>
          <NumberInput label="מספר קומות" min={1} max={100}
            value={addElevForm.floor_count}
            onChange={v => setAddElevForm(s => ({ ...s, floor_count: Number(v) || 1 }))} />
          <Group justify="flex-end" mt="sm">
            <Button variant="default" onClick={closeAddElev}>ביטול</Button>
            <Button
              color="teal"
              disabled={!addElevForm.address || !addElevForm.city}
              loading={addElevMutation.isPending}
              onClick={() => { if (selectedCall) addElevMutation.mutate({ callId: selectedCall.id, form: addElevForm }) }}
            >
              צור מעלית ושייך
            </Button>
          </Group>
        </Stack>
      </Modal>

      <LocationPickerModal
        opened={locationPickerOpen}
        onClose={() => { setLocationPickerOpen(false); setLocationPickerElevId(null) }}
        onSave={(lat, lng) => locationPickerElevId && saveLocationMutation.mutate({ elevId: locationPickerElevId, lat, lng })}
        loading={saveLocationMutation.isPending}
      />
    </Stack>
  )
}
