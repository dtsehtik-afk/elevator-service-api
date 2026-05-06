import { useState } from 'react'
import {
  Stack, Title, Paper, Table, Badge, Button, Group, Text, Modal,
  TextInput, Select, NumberInput, Textarea, Grid, SimpleGrid,
  Loader, Center, Card, PasswordInput,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { hrApi, type HRProfile } from '../api/hr'
import client from '../api/client'

const EMPLOYMENT_TYPES = [
  { value: 'FULL_TIME', label: 'משרה מלאה' },
  { value: 'PART_TIME', label: 'משרה חלקית' },
  { value: 'CONTRACT', label: 'חוזה' },
  { value: 'FREELANCE', label: 'פרילנס' },
]

const SALARY_TYPES = [
  { value: 'MONTHLY', label: 'חודשי' },
  { value: 'HOURLY', label: 'שעתי' },
  { value: 'PROJECT', label: 'לפי פרויקט' },
]

const ROLE_OPTIONS = [
  { value: 'TECHNICIAN', label: 'טכנאי' },
  { value: 'DISPATCHER', label: 'מוקדן' },
  { value: 'SERVICE_MANAGER', label: 'מנהל שירות' },
  { value: 'ADMIN', label: 'מנהל מערכת' },
  { value: 'CEO', label: 'מנכ"ל' },
  { value: 'VP', label: 'סמנכ"ל' },
  { value: 'ACCOUNTANT', label: 'רואה חשבון' },
  { value: 'SECRETARY', label: 'מזכירה' },
  { value: 'SALES', label: 'מכירות' },
  { value: 'SALES_MANAGER', label: 'מנהל מכירות' },
  { value: 'INVENTORY_MANAGER', label: 'מנהל מלאי' },
]

const ROLE_LABELS: Record<string, string> = Object.fromEntries(ROLE_OPTIONS.map(r => [r.value, r.label]))

interface NewEmpForm {
  name: string; email: string; phone: string; password: string; role: string
  employment_type: string; employment_start: string; base_salary: string; notes: string
}

const NEW_EMP_DEFAULTS: NewEmpForm = {
  name: '', email: '', phone: '', password: '', role: 'TECHNICIAN',
  employment_type: 'FULL_TIME', employment_start: '', base_salary: '', notes: '',
}

export default function HRPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<HRProfile | null>(null)
  const [modalOpen, { open, close }] = useDisclosure(false)
  const [form, setForm] = useState<Partial<HRProfile>>({})
  const [addOpen, { open: openAdd, close: closeAdd }] = useDisclosure(false)
  const [newEmp, setNewEmp] = useState<NewEmpForm>(NEW_EMP_DEFAULTS)

  const { data: stats } = useQuery({ queryKey: ['hr-stats'], queryFn: hrApi.stats })
  const { data: employees, isLoading } = useQuery({ queryKey: ['hr-list'], queryFn: hrApi.list })

  const saveMutation = useMutation({
    mutationFn: () => hrApi.upsert(selected!.technician_id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hr-list'] })
      qc.invalidateQueries({ queryKey: ['hr-stats'] })
      close()
      notifications.show({ message: 'פרטי HR עודכנו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  const addMutation = useMutation({
    mutationFn: async () => {
      const { data: tech } = await client.post('/technicians', {
        name: newEmp.name,
        email: newEmp.email,
        phone: newEmp.phone || undefined,
        password: newEmp.password,
        role: newEmp.role,
      })
      if (newEmp.employment_type || newEmp.employment_start || newEmp.base_salary) {
        await hrApi.upsert(tech.id, {
          employment_type: newEmp.employment_type || undefined,
          employment_start: newEmp.employment_start || undefined,
          base_salary: newEmp.base_salary ? Number(newEmp.base_salary) : undefined,
          notes: newEmp.notes || undefined,
        })
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hr-list'] })
      qc.invalidateQueries({ queryKey: ['hr-stats'] })
      closeAdd()
      setNewEmp(NEW_EMP_DEFAULTS)
      notifications.show({ message: '✅ עובד חדש נוסף בהצלחה', color: 'green' })
    },
    onError: (e: any) => notifications.show({
      message: e?.response?.data?.detail ?? 'שגיאה בהוספת עובד', color: 'red',
    }),
  })

  function openEdit(emp: HRProfile) {
    setSelected(emp)
    setForm({
      employment_start: emp.employment_start,
      employment_end: emp.employment_end,
      employment_type: emp.employment_type || 'FULL_TIME',
      salary_type: emp.salary_type || 'MONTHLY',
      base_salary: emp.base_salary,
      hourly_rate: emp.hourly_rate,
      id_number: emp.id_number,
      bank_account: emp.bank_account,
      emergency_contact: emp.emergency_contact,
      emergency_phone: emp.emergency_phone,
      notes: emp.notes,
    })
    open()
  }

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>👥 משאבי אנוש (HR)</Title>
        <Button onClick={openAdd}>+ הוסף עובד חדש</Button>
      </Group>

      {/* Stats */}
      {stats && (
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Card withBorder radius="md" p="md">
            <Text size="xs" c="dimmed">סה"כ עובדים</Text>
            <Text size="xl" fw={700}>{stats.total_staff}</Text>
          </Card>
          <Card withBorder radius="md" p="md">
            <Text size="xs" c="dimmed">זמינים כעת</Text>
            <Text size="xl" fw={700} c="green">{stats.available}</Text>
          </Card>
          <Card withBorder radius="md" p="md">
            <Text size="xs" c="dimmed">שכר ממוצע</Text>
            <Text size="xl" fw={700}>
              {stats.avg_salary ? `₪${stats.avg_salary.toLocaleString()}` : '—'}
            </Text>
          </Card>
          <Card withBorder radius="md" p="md">
            <Text size="xs" c="dimmed">לפי תפקיד</Text>
            {Object.entries(stats.by_role).map(([role, count]) => (
              <Group key={role} gap={4}>
                <Text size="xs">{ROLE_LABELS[role] ?? role}:</Text>
                <Badge size="xs">{count}</Badge>
              </Group>
            ))}
          </Card>
        </SimpleGrid>
      )}

      {/* Employee table */}
      <Paper withBorder radius="md">
        {isLoading && <Center p="xl"><Loader /></Center>}
        {!isLoading && (
          <Table striped highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>שם</Table.Th>
                <Table.Th>תפקיד</Table.Th>
                <Table.Th>טלפון</Table.Th>
                <Table.Th>סוג העסקה</Table.Th>
                <Table.Th>שכר בסיס</Table.Th>
                <Table.Th>תחילת העסקה</Table.Th>
                <Table.Th>סטטוס</Table.Th>
                <Table.Th></Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(employees ?? []).map(emp => (
                <Table.Tr key={emp.technician_id}>
                  <Table.Td fw={500}>{emp.name}</Table.Td>
                  <Table.Td>
                    <Badge size="sm" variant="light">
                      {ROLE_LABELS[emp.role] ?? emp.role}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{emp.phone ?? '—'}</Table.Td>
                  <Table.Td>
                    {emp.employment_type
                      ? EMPLOYMENT_TYPES.find(e => e.value === emp.employment_type)?.label
                      : <Text c="dimmed" size="xs">לא הוגדר</Text>}
                  </Table.Td>
                  <Table.Td>
                    {emp.base_salary
                      ? `₪${emp.base_salary.toLocaleString()}`
                      : emp.hourly_rate
                        ? `₪${emp.hourly_rate}/ש׳`
                        : <Text c="dimmed" size="xs">—</Text>}
                  </Table.Td>
                  <Table.Td>
                    {emp.employment_start
                      ? new Date(emp.employment_start).toLocaleDateString('he-IL')
                      : <Text c="dimmed" size="xs">—</Text>}
                  </Table.Td>
                  <Table.Td>
                    <Badge color={emp.is_active ? 'green' : 'gray'} size="sm">
                      {emp.is_active ? 'פעיל' : 'לא פעיל'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Button size="xs" variant="light" onClick={() => openEdit(emp)}>
                      עריכה
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>

      {/* Add employee modal */}
      <Modal opened={addOpen} onClose={closeAdd} title="➕ הוסף עובד חדש" size="md" centered dir="rtl">
        <Stack gap="sm">
          <Grid>
            <Grid.Col span={6}>
              <TextInput label="שם מלא *" value={newEmp.name}
                onChange={e => setNewEmp(p => ({ ...p, name: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <Select label="תפקיד *" data={ROLE_OPTIONS} value={newEmp.role}
                onChange={v => setNewEmp(p => ({ ...p, role: v ?? 'TECHNICIAN' }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput label="אימייל *" type="email" value={newEmp.email}
                onChange={e => setNewEmp(p => ({ ...p, email: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput label="טלפון" value={newEmp.phone}
                onChange={e => setNewEmp(p => ({ ...p, phone: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={12}>
              <PasswordInput label="סיסמה ראשונית *" value={newEmp.password}
                onChange={e => setNewEmp(p => ({ ...p, password: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <Select label="סוג העסקה" data={EMPLOYMENT_TYPES} value={newEmp.employment_type}
                onChange={v => setNewEmp(p => ({ ...p, employment_type: v ?? 'FULL_TIME' }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput label="תאריך תחילת העסקה" type="date" value={newEmp.employment_start}
                onChange={e => setNewEmp(p => ({ ...p, employment_start: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput label="שכר בסיס (₪)" value={newEmp.base_salary}
                onChange={e => setNewEmp(p => ({ ...p, base_salary: e.target.value }))} />
            </Grid.Col>
            <Grid.Col span={12}>
              <Textarea label="הערות" rows={2} value={newEmp.notes}
                onChange={e => setNewEmp(p => ({ ...p, notes: e.target.value }))} />
            </Grid.Col>
          </Grid>
          <Button
            onClick={() => addMutation.mutate()}
            loading={addMutation.isPending}
            disabled={!newEmp.name || !newEmp.email || newEmp.password.length < 8}
          >
            הוסף עובד
          </Button>
        </Stack>
      </Modal>

      {/* Edit modal */}
      <Modal
        opened={modalOpen}
        onClose={close}
        title={`עריכת HR — ${selected?.name}`}
        size="lg"
        centered
        dir="rtl"
      >
        <Stack gap="sm">
          <Grid>
            <Grid.Col span={6}>
              <Select
                label="סוג העסקה"
                data={EMPLOYMENT_TYPES}
                value={form.employment_type ?? 'FULL_TIME'}
                onChange={v => setForm(p => ({ ...p, employment_type: v ?? 'FULL_TIME' }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <Select
                label="סוג שכר"
                data={SALARY_TYPES}
                value={form.salary_type ?? 'MONTHLY'}
                onChange={v => setForm(p => ({ ...p, salary_type: v ?? 'MONTHLY' }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <NumberInput
                label="שכר בסיס (₪)"
                value={form.base_salary ?? ''}
                onChange={v => setForm(p => ({ ...p, base_salary: Number(v) || undefined }))}
                min={0}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <NumberInput
                label="תעריף שעתי (₪)"
                value={form.hourly_rate ?? ''}
                onChange={v => setForm(p => ({ ...p, hourly_rate: Number(v) || undefined }))}
                min={0}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="תאריך תחילת העסקה"
                type="date"
                value={form.employment_start ?? ''}
                onChange={e => setForm(p => ({ ...p, employment_start: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="תאריך סיום העסקה"
                type="date"
                value={form.employment_end ?? ''}
                onChange={e => setForm(p => ({ ...p, employment_end: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="מספר זהות"
                value={form.id_number ?? ''}
                onChange={e => setForm(p => ({ ...p, id_number: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="חשבון בנק"
                value={form.bank_account ?? ''}
                onChange={e => setForm(p => ({ ...p, bank_account: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="איש קשר לחירום"
                value={form.emergency_contact ?? ''}
                onChange={e => setForm(p => ({ ...p, emergency_contact: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={6}>
              <TextInput
                label="טלפון חירום"
                value={form.emergency_phone ?? ''}
                onChange={e => setForm(p => ({ ...p, emergency_phone: e.target.value }))}
              />
            </Grid.Col>
            <Grid.Col span={12}>
              <Textarea
                label="הערות"
                value={form.notes ?? ''}
                onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                rows={3}
              />
            </Grid.Col>
          </Grid>
          <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
            שמור
          </Button>
        </Stack>
      </Modal>
    </Stack>
  )
}
