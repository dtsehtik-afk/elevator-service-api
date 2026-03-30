import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Grid, TextInput,
  NumberInput, Select, Tabs, Table, Loader, Center, ActionIcon, Tooltip,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { getElevator, updateElevator, getElevatorCalls } from '../api/elevators'
import { Elevator } from '../types'
import {
  ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS,
  PRIORITY_LABELS, PRIORITY_COLORS, CALL_STATUS_LABELS, CALL_STATUS_COLORS, FAULT_TYPE_LABELS,
} from '../utils/constants'
import { formatDate, formatDateTime } from '../utils/dates'

export default function ElevatorDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<Elevator>>({})

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

  const updateMutation = useMutation({
    mutationFn: (payload: any) => updateElevator(id!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator', id] })
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: 'פרטי המעלית עודכנו', color: 'green' })
      setEditing(false)
    },
    onError: () => notifications.show({ message: 'שגיאה בעדכון', color: 'red' }),
  })

  if (isLoading) return <Center h={400}><Loader /></Center>
  if (!elevator) return <Center h={400}><Text>מעלית לא נמצאה</Text></Center>

  const data: Elevator = editing ? { ...elevator, ...form } as Elevator : elevator

  return (
    <Stack gap="lg">
      <Group>
        <ActionIcon variant="subtle" onClick={() => navigate('/elevators')}>←</ActionIcon>
        <Title order={2}>מעלית #{elevator.serial_number ?? elevator.id.slice(0, 8)}</Title>
        <Badge color={ELEVATOR_STATUS_COLORS[elevator.status]} size="lg">
          {ELEVATOR_STATUS_LABELS[elevator.status]}
        </Badge>
        {!editing && (
          <Button variant="light" size="xs" onClick={() => { setForm(elevator); setEditing(true) }}>
            ✏️ ערוך
          </Button>
        )}
      </Group>

      <Tabs defaultValue="details">
        <Tabs.List>
          <Tabs.Tab value="details">פרטים</Tabs.Tab>
          <Tabs.Tab value="calls">היסטוריית קריאות ({(calls as any[]).length})</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="details" pt="md">
          <Paper withBorder p="lg" radius="md">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="כתובת" value={form.address ?? ''} onChange={e => setForm((s: any) => ({ ...s, address: e.target.value }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">כתובת</Text><Text fw={500}>{elevator.address}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="עיר" value={form.city ?? ''} onChange={e => setForm((s: any) => ({ ...s, city: e.target.value }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">עיר</Text><Text fw={500}>{elevator.city}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="שם בניין" value={form.building_name ?? ''} onChange={e => setForm((s: any) => ({ ...s, building_name: e.target.value }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">שם בניין</Text><Text fw={500}>{elevator.building_name ?? '—'}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <NumberInput label="מספר קומות" min={1} max={200} value={form.floor_count ?? 1} onChange={v => setForm((s: any) => ({ ...s, floor_count: Number(v) }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">מספר קומות</Text><Text fw={500}>{elevator.floor_count}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="יצרן" value={form.manufacturer ?? ''} onChange={e => setForm((s: any) => ({ ...s, manufacturer: e.target.value }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">יצרן</Text><Text fw={500}>{elevator.manufacturer ?? '—'}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                {editing ? (
                  <TextInput label="דגם" value={form.model ?? ''} onChange={e => setForm((s: any) => ({ ...s, model: e.target.value }))} />
                ) : (
                  <Stack gap={2}><Text size="xs" c="dimmed">דגם</Text><Text fw={500}>{elevator.model ?? '—'}</Text></Stack>
                )}
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Stack gap={2}><Text size="xs" c="dimmed">שירות אחרון</Text><Text fw={500}>{formatDate(elevator.last_service_date)}</Text></Stack>
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Stack gap={2}><Text size="xs" c="dimmed">שירות הבא</Text><Text fw={500}>{formatDate(elevator.next_service_date)}</Text></Stack>
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Stack gap={2}><Text size="xs" c="dimmed">תאריך התקנה</Text><Text fw={500}>{formatDate(elevator.installation_date)}</Text></Stack>
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Stack gap={2}>
                  <Text size="xs" c="dimmed">ציון סיכון</Text>
                  <Badge color={elevator.risk_score > 70 ? 'red' : elevator.risk_score > 40 ? 'orange' : 'green'} size="lg" variant="light">
                    {elevator.risk_score.toFixed(1)}
                  </Badge>
                </Stack>
              </Grid.Col>
              {editing && (
                <Grid.Col span={12}>
                  <Select
                    label="סטטוס"
                    data={[
                      { value: 'ACTIVE', label: 'פעילה' },
                      { value: 'INACTIVE', label: 'לא פעילה' },
                      { value: 'UNDER_REPAIR', label: 'בתיקון' },
                    ]}
                    value={form.status}
                    onChange={v => setForm((s: any) => ({ ...s, status: v }))}
                  />
                </Grid.Col>
              )}
            </Grid>

            {editing && (
              <Group justify="flex-end" mt="lg">
                <Button variant="default" onClick={() => setEditing(false)}>ביטול</Button>
                <Button loading={updateMutation.isPending} onClick={() => updateMutation.mutate(form)}>
                  שמור שינויים
                </Button>
              </Group>
            )}
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="calls" pt="md">
          <Paper withBorder radius="md">
            {(calls as any[]).length === 0 ? (
              <Center h={200}><Text c="dimmed">אין קריאות שירות לעמלית זו</Text></Center>
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
                    <Table.Tr key={call.id}>
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
      </Tabs>
    </Stack>
  )
}
