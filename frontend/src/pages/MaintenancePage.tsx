import { useState, useMemo } from 'react'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Select, Modal,
  Pagination, Table, ScrollArea, Loader, Center, SimpleGrid, ThemeIcon, Tooltip,
} from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { listMaintenance, createMaintenance, updateMaintenance } from '../api/maintenance'
import { listCalls } from '../api/calls'
import { listElevators } from '../api/elevators'
import { listTechnicians } from '../api/technicians'
import { MAINTENANCE_TYPE_LABELS, MAINTENANCE_STATUS_LABELS, MAINTENANCE_STATUS_COLORS } from '../utils/constants'
import { formatDate, isOverdue } from '../utils/dates'
import { MaintenanceSchedule } from '../types'
import dayjs from 'dayjs'

const PAGE_SIZE = 20

export default function MaintenancePage() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [addOpened, { open: openAdd, close: closeAdd }] = useDisclosure()
  const [updateOpened, { open: openUpdate, close: closeUpdate }] = useDisclosure()
  const [selected, setSelected] = useState<MaintenanceSchedule | null>(null)

  const [newForm, setNewForm] = useState({
    elevator_id: '', technician_id: '',
    scheduled_date: null as Date | null, maintenance_type: 'ROUTINE',
  })
  const [updateForm, setUpdateForm] = useState({ status: '', completion_notes: '' })

  const { data: maintenance = [], isLoading } = useQuery({ queryKey: ['maintenance'], queryFn: () => listMaintenance() })
  const { data: elevators = [] } = useQuery({ queryKey: ['elevators'], queryFn: () => listElevators() })
  const { data: technicians = [] } = useQuery({ queryKey: ['technicians'], queryFn: listTechnicians })
  const { data: maintCalls = [] } = useQuery({
    queryKey: ['maint-calls'],
    queryFn: () => listCalls({ fault_type: 'MAINTENANCE', status: 'OPEN', limit: 100 }),
  })

  // Inject blink animation once
  if (typeof document !== 'undefined' && !document.getElementById('maint-blink-style')) {
    const s = document.createElement('style')
    s.id = 'maint-blink-style'
    s.textContent = `@keyframes maint-blink { 0%,100%{background-color:rgba(255,50,50,0.08)} 50%{background-color:rgba(255,50,50,0.28)} }`
    document.head.appendChild(s)
  }

  const elevatorOptions = elevators.map(e => ({ value: e.id, label: `#${e.serial_number} — ${e.address}, ${e.city}` }))
  const techOptions = [
    { value: '', label: 'ללא שיבוץ' },
    ...technicians.filter(t => t.is_active).map(t => ({ value: t.id, label: t.name })),
  ]

  const filtered = useMemo(() =>
    maintenance
      .filter(m => !statusFilter || m.status === statusFilter)
      .sort((a, b) => a.scheduled_date.localeCompare(b.scheduled_date)),
    [maintenance, statusFilter]
  )

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)
  const overdue = maintenance.filter(m => m.status === 'SCHEDULED' && isOverdue(m.scheduled_date)).length

  // Traffic-light buckets from elevator next_service_date
  const today = new Date(); today.setHours(0,0,0,0)
  const elevatorServiceStatus = useMemo(() => {
    const red: typeof elevators = [], yellow: typeof elevators = [], green: typeof elevators = []
    for (const e of elevators) {
      if (!e.next_service_date || e.status !== 'ACTIVE') continue
      const d = new Date(e.next_service_date); d.setHours(0,0,0,0)
      const days = Math.round((d.getTime() - today.getTime()) / 86400000)
      if (days <= 5) red.push(e)
      else if (days <= 15) yellow.push(e)
      else green.push(e)
    }
    return { red, yellow, green }
  }, [elevators])

  const createMutation = useMutation({
    mutationFn: createMaintenance,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['maintenance'] })
      notifications.show({ message: 'תחזוקה נוספה בהצלחה', color: 'green' })
      closeAdd()
      setNewForm({ elevator_id: '', technician_id: '', scheduled_date: null, maintenance_type: 'ROUTINE' })
    },
    onError: () => notifications.show({ message: 'שגיאה בהוספת תחזוקה', color: 'red' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => updateMaintenance(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['maintenance'] })
      notifications.show({ message: 'תחזוקה עודכנה', color: 'green' })
      closeUpdate()
    },
    onError: () => notifications.show({ message: 'שגיאה בעדכון', color: 'red' }),
  })

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Stack gap={0}>
          <Title order={2}>תחזוקה מתוזמנת</Title>
          {overdue > 0 && <Text size="sm" c="red">⚠️ {overdue} תחזוקות באיחור</Text>}
        </Stack>
        <Button onClick={openAdd}>+ הוסף תחזוקה</Button>
      </Group>

      {/* Traffic-light service status */}
      {(elevatorServiceStatus.red.length > 0 || elevatorServiceStatus.yellow.length > 0) && (
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
          {elevatorServiceStatus.red.length > 0 && (
            <Paper withBorder p="sm" radius="md" style={{ borderColor: '#fa5252' }}>
              <Group gap="xs" mb={6}>
                <ThemeIcon color="red" variant="light" size="md">🔴</ThemeIcon>
                <Text fw={700} c="red">דחוף / באיחור ({elevatorServiceStatus.red.length})</Text>
              </Group>
              <Stack gap={2}>
                {elevatorServiceStatus.red.map(e => {
                  const d = new Date(e.next_service_date!)
                  const days = Math.round((d.getTime() - today.getTime()) / 86400000)
                  return (
                    <Tooltip key={e.id} label={`${e.address}, ${e.city}`} position="top">
                      <Text size="xs" truncate>
                        #{e.serial_number} {e.city} —{' '}
                        <Text span c="red" fw={600}>
                          {days < 0 ? `איחור ${-days} ימים` : `${days} ימים`}
                        </Text>
                      </Text>
                    </Tooltip>
                  )
                })}
              </Stack>
            </Paper>
          )}
          {elevatorServiceStatus.yellow.length > 0 && (
            <Paper withBorder p="sm" radius="md" style={{ borderColor: '#fab005' }}>
              <Group gap="xs" mb={6}>
                <ThemeIcon color="yellow" variant="light" size="md">🟡</ThemeIcon>
                <Text fw={700} c="yellow.8">מתקרב ({elevatorServiceStatus.yellow.length})</Text>
              </Group>
              <Stack gap={2}>
                {elevatorServiceStatus.yellow.map(e => {
                  const d = new Date(e.next_service_date!)
                  const days = Math.round((d.getTime() - today.getTime()) / 86400000)
                  return (
                    <Tooltip key={e.id} label={`${e.address}, ${e.city}`} position="top">
                      <Text size="xs" truncate>
                        #{e.serial_number} {e.city} — <Text span c="yellow.8" fw={600}>{days} ימים</Text>
                      </Text>
                    </Tooltip>
                  )
                })}
              </Stack>
            </Paper>
          )}
          {elevatorServiceStatus.green.length > 0 && (
            <Paper withBorder p="sm" radius="md" style={{ borderColor: '#40c057' }}>
              <Group gap="xs" mb={6}>
                <ThemeIcon color="green" variant="light" size="md">🟢</ThemeIcon>
                <Text fw={700} c="green">תקין ({elevatorServiceStatus.green.length})</Text>
              </Group>
              <Text size="xs" c="dimmed">טיפול בעוד יותר מ-15 יום</Text>
            </Paper>
          )}
        </SimpleGrid>
      )}

      <Group>
        <Select
          placeholder="סטטוס"
          data={[
            { value: 'SCHEDULED', label: 'מתוזמן' }, { value: 'IN_PROGRESS', label: 'בביצוע' },
            { value: 'COMPLETED', label: 'הושלם' }, { value: 'CANCELLED', label: 'בוטל' },
          ]}
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
          clearable w={160}
        />
        <Text size="sm" c="dimmed">{filtered.length} רשומות</Text>
      </Group>

      {maintCalls.length > 0 && (
        <Paper withBorder radius="md" p="sm">
          <Text fw={600} mb="xs">📋 קריאות טיפול מונע פתוחות ({maintCalls.length})</Text>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>מעלית</Table.Th>
                <Table.Th>תיאור</Table.Th>
                <Table.Th>דחיפות</Table.Th>
                <Table.Th>נפתח</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {maintCalls.map(c => {
                const elev = elevators.find(e => e.id === c.elevator_id)
                const isUrgent = c.priority === 'HIGH' || c.priority === 'CRITICAL'
                const priorityColor = c.priority === 'LOW' ? 'green' : c.priority === 'MEDIUM' ? 'orange' : 'red'
                const rowStyle: React.CSSProperties = isUrgent
                  ? { animation: 'maint-blink 1.2s ease-in-out infinite' }
                  : {}
                return (
                  <Table.Tr key={c.id} style={rowStyle}>
                    <Table.Td>
                      <Text size="sm">{elev ? `#${elev.serial_number} — ${elev.address}, ${elev.city}` : c.elevator_id.slice(0, 8)}</Text>
                    </Table.Td>
                    <Table.Td><Text size="sm">{c.description}</Text></Table.Td>
                    <Table.Td>
                      <Badge color={priorityColor} variant="light" size="sm">
                        {c.priority === 'LOW' ? 'נמוך' : c.priority === 'MEDIUM' ? 'בינוני' : c.priority === 'HIGH' ? 'גבוה' : 'קריטי'}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">{new Date(c.created_at).toLocaleDateString('he-IL')}</Text>
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      <Paper withBorder radius="md">
        {isLoading ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <ScrollArea>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>תאריך</Table.Th>
                  <Table.Th>מעלית</Table.Th>
                  <Table.Th>סוג</Table.Th>
                  <Table.Th>טכנאי</Table.Th>
                  <Table.Th>סטטוס</Table.Th>
                  <Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paginated.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={6}><Center h={100}><Text c="dimmed">לא נמצאה תחזוקה</Text></Center></Table.Td>
                  </Table.Tr>
                ) : paginated.map(m => {
                  const elev = elevators.find(e => e.id === m.elevator_id)
                  const tech = technicians.find(t => t.id === m.technician_id)
                  const late = isOverdue(m.scheduled_date) && m.status === 'SCHEDULED'
                  return (
                    <Table.Tr key={m.id}>
                      <Table.Td>
                        <Text size="sm" c={late ? 'red' : undefined} fw={late ? 600 : undefined}>
                          {formatDate(m.scheduled_date)}{late && ' ⚠️'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{elev ? `#${elev.serial_number} ${elev.city}` : m.elevator_id.slice(0, 8)}</Text>
                      </Table.Td>
                      <Table.Td><Text size="sm">{MAINTENANCE_TYPE_LABELS[m.maintenance_type] ?? m.maintenance_type}</Text></Table.Td>
                      <Table.Td><Text size="sm">{tech?.name ?? '—'}</Text></Table.Td>
                      <Table.Td>
                        <Badge color={MAINTENANCE_STATUS_COLORS[m.status]} variant="light" size="sm">
                          {MAINTENANCE_STATUS_LABELS[m.status]}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Button size="xs" variant="light" onClick={() => {
                          setSelected(m)
                          setUpdateForm({ status: m.status, completion_notes: m.completion_notes ?? '' })
                          openUpdate()
                        }}>עדכן</Button>
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

      <Modal opened={addOpened} onClose={closeAdd} title="הוסף תחזוקה מתוזמנת">
        <Stack gap="sm">
          <Select label="מעלית" required data={elevatorOptions} value={newForm.elevator_id}
            onChange={v => setNewForm(s => ({ ...s, elevator_id: v ?? '' }))} searchable />
          <Select label="טכנאי" data={techOptions} value={newForm.technician_id}
            onChange={v => setNewForm(s => ({ ...s, technician_id: v ?? '' }))} clearable />
          <DateInput label="תאריך" required value={newForm.scheduled_date}
            onChange={v => setNewForm(s => ({ ...s, scheduled_date: v }))}
            minDate={new Date()} valueFormat="DD/MM/YYYY" />
          <Select
            label="סוג תחזוקה"
            data={[
              { value: 'ROUTINE', label: 'שגרתי' }, { value: 'INSPECTION', label: 'בדיקה' },
              { value: 'EMERGENCY', label: 'חירום' }, { value: 'ANNUAL', label: 'שנתי' },
            ]}
            value={newForm.maintenance_type}
            onChange={v => setNewForm(s => ({ ...s, maintenance_type: v ?? 'ROUTINE' }))}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeAdd}>ביטול</Button>
            <Button
              loading={createMutation.isPending}
              disabled={!newForm.elevator_id || !newForm.scheduled_date}
              onClick={() => createMutation.mutate({
                elevator_id: newForm.elevator_id,
                technician_id: newForm.technician_id || undefined,
                scheduled_date: dayjs(newForm.scheduled_date!).format('YYYY-MM-DD'),
                maintenance_type: newForm.maintenance_type,
              })}
            >הוסף</Button>
          </Group>
        </Stack>
      </Modal>

      <Modal opened={updateOpened} onClose={closeUpdate} title="עדכן תחזוקה">
        <Stack gap="sm">
          <Select
            label="סטטוס"
            data={[
              { value: 'SCHEDULED', label: 'מתוזמן' }, { value: 'IN_PROGRESS', label: 'בביצוע' },
              { value: 'COMPLETED', label: 'הושלם' }, { value: 'CANCELLED', label: 'בוטל' },
            ]}
            value={updateForm.status}
            onChange={v => setUpdateForm(s => ({ ...s, status: v ?? '' }))}
          />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeUpdate}>ביטול</Button>
            <Button
              loading={updateMutation.isPending}
              onClick={() => selected && updateMutation.mutate({ id: selected.id, payload: updateForm })}
            >שמור</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
