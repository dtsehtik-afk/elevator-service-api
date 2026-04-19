import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Grid, TextInput,
  NumberInput, Select, Tabs, Table, Loader, Center, ActionIcon, Alert,
  Checkbox, Textarea, Anchor, Modal, Divider,
} from '@mantine/core'
import { useAuthStore } from '../stores/authStore'
import { DateInput } from '@mantine/dates'
import { FileInput } from '@mantine/core'
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
  const [selectedBuildingId, setSelectedBuildingId] = useState<string | null>(null)
  const [selectedCompanyId, setSelectedCompanyId] = useState<string | null>(null)
  const [addToGroupOpen, setAddToGroupOpen] = useState(false)
  const [elevatorSearch, setElevatorSearch] = useState('')

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
      <Modal opened={assignCompanyOpen} onClose={() => { setAssignCompanyOpen(false); setSelectedCompanyId(null) }} title="שיוך לחברת ניהול" dir="rtl">
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
          <Tabs.Tab value="inspection">ביקורת</Tabs.Tab>
          <Tabs.Tab value="calls">קריאות ({(calls as any[]).length})</Tabs.Tab>
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
                </Group>
                {elevator.building_id && (
                  <Text size="xs" c="dimmed" mt={4}>
                    {siblings.length > 0 ? `${siblings.length} מעליות נוספות בקבוצה זו` : 'מעלית זו היחידה בקבוצה'}
                    {elevator.management_company_id && ` · ${elevator.management_company_name ?? 'חברת ניהול'}`}
                  </Text>
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
    </Stack>
  )
}
