import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Grid, TextInput,
  NumberInput, Select, Tabs, Table, Loader, Center, ActionIcon, Alert,
  Checkbox, Textarea, Anchor, Modal, Divider,
} from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { getElevator, updateElevator, getElevatorCalls } from '../api/elevators'
import client from '../api/client'
import { Elevator } from '../types'
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

export default function ElevatorDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState<Partial<Elevator>>({})
  const [sensitiveField, setSensitiveField] = useState<string | null>(null)
  const [addContactOpen, setAddContactOpen] = useState(false)
  const [newContact, setNewContact] = useState({ name: '', phone: '', email: '', role: 'VAAD' })

  const set = (key: string, value: any) => setForm(s => ({ ...s, [key]: value }))
  const dateSet = (key: string, d: Date | null) => set(key, toISODate(d))

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

  const { data: contacts = [] } = useQuery<Contact[]>({
    queryKey: ['elevator-contacts', elevator?.building_id],
    queryFn: async () => {
      if (!elevator?.building_id) return []
      return (await client.get(`/contacts?building_id=${elevator.building_id}`)).data
    },
    enabled: !!elevator?.building_id,
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

  const addContactMutation = useMutation({
    mutationFn: (d: any) => client.post('/contacts', d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevator-contacts', elevator?.building_id] })
      setAddContactOpen(false)
      setNewContact({ name: '', phone: '', email: '', role: 'VAAD' })
      notifications.show({ message: 'איש קשר נוסף', color: 'green' })
    },
  })

  const deleteContactMutation = useMutation({
    mutationFn: (contactId: string) => client.delete(`/contacts/${contactId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['elevator-contacts', elevator?.building_id] }),
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

      <Tabs defaultValue="details">
        <Tabs.List>
          <Tabs.Tab value="details">פרטים</Tabs.Tab>
          <Tabs.Tab value="service">שירות</Tabs.Tab>
          <Tabs.Tab value="contacts">אנשי קשר {contacts.length > 0 && `(${contacts.length})`}</Tabs.Tab>
          <Tabs.Tab value="contract">חוזה</Tabs.Tab>
          <Tabs.Tab value="inspection">ביקורת</Tabs.Tab>
          <Tabs.Tab value="calls">קריאות ({(calls as any[]).length})</Tabs.Tab>
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
                    label="קודן — מעלית עם קוד כניסה"
                    checked={form.is_coded ?? false}
                    onChange={e => set('is_coded', e.target.checked)}
                    mt="sm"
                  />
                ) : (
                  <Field label="קודן">
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
                  <Textarea label="הערות" value={form.notes ?? ''} onChange={e => set('notes', e.target.value || null)} minRows={2} />
                ) : elevator.notes ? (
                  <Field label="הערות" value={elevator.notes} />
                ) : null}
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
                      if (v === 'COMPREHENSIVE') { set('service_contract', 'ANNUAL_12'); set('maintenance_interval_days', 30) }
                      else if (v === 'REGULAR') { set('service_contract', 'ANNUAL_6'); set('maintenance_interval_days', 60) }
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
                  <NumberInput label="אינטרוול טיפול (ימים)" min={1} value={form.maintenance_interval_days ?? ''} onChange={v => set('maintenance_interval_days', v || null)} />
                ) : (
                  <Field label="אינטרוול טיפול" value={elevator.maintenance_interval_days ? `${elevator.maintenance_interval_days} יום` : null} />
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
          <Paper withBorder p="lg" radius="md">
            <Group justify="space-between" mb="md">
              <Text fw={600}>אנשי קשר</Text>
              {elevator.building_id && (
                <Button size="xs" onClick={() => setAddContactOpen(true)}>+ הוסף</Button>
              )}
            </Group>
            {!elevator.building_id && (
              <Alert color="yellow">מעלית זו לא משויכת לבניין — לא ניתן להוסיף אנשי קשר</Alert>
            )}
            {contacts.length === 0 && elevator.building_id && (
              <Text c="dimmed" ta="center" mt="md">אין אנשי קשר לבניין זה</Text>
            )}
            {contacts.length > 0 && (
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>שם</Table.Th>
                    <Table.Th>תפקיד</Table.Th>
                    <Table.Th>טלפון</Table.Th>
                    <Table.Th>מייל</Table.Th>
                    <Table.Th></Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {contacts.map(c => (
                    <Table.Tr key={c.id}>
                      <Table.Td>
                        {c.name}
                        {c.auto_added && <Badge size="xs" color="gray" variant="light" ml={4}>אוטו׳</Badge>}
                      </Table.Td>
                      <Table.Td><Badge color={ROLE_COLORS[c.role]} size="xs">{ROLE_LABELS[c.role]}</Badge></Table.Td>
                      <Table.Td>{c.phone ? <Anchor href={`tel:${c.phone}`} size="sm">{c.phone}</Anchor> : '—'}</Table.Td>
                      <Table.Td>{c.email ? <Anchor href={`mailto:${c.email}`} size="sm">{c.email}</Anchor> : '—'}</Table.Td>
                      <Table.Td>
                        <ActionIcon size="xs" color="red" variant="subtle"
                          onClick={() => deleteContactMutation.mutate(c.id)}>✕</ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
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
                {editing ? (
                  <TextInput label="קישור להסכם (Google Drive)" placeholder="https://drive.google.com/..." value={form.drive_link ?? ''} onChange={e => set('drive_link', e.target.value || null)} />
                ) : (
                  <Field label="הסכם שירות">
                    {elevator.drive_link
                      ? <Anchor href={elevator.drive_link} target="_blank" size="sm">📄 פתח הסכם</Anchor>
                      : <Text fw={500}>—</Text>}
                  </Field>
                )}
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
            </Grid>
          </Paper>
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
