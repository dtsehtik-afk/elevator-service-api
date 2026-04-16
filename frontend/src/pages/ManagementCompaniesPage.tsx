import { useState } from 'react'
import {
  Stack, Title, Text, Button, Paper, Badge, Group, TextInput,
  Modal, Textarea, ActionIcon, Card, Loader, Center, Collapse,
  Table, Tooltip,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface Company {
  id: string
  name: string
  contact_name: string | null
  phone: string | null
  email: string | null
  caller_phones: string[]
  notes: string | null
  elevator_count: number
  created_at: string | null
}

interface CompanyDetail extends Company {
  elevators: { id: string; address: string; city: string; building_name: string | null; status: string }[]
}

const STATUS_COLOR: Record<string, string> = { ACTIVE: 'green', INACTIVE: 'gray', UNDER_REPAIR: 'orange' }
const STATUS_LABEL: Record<string, string> = { ACTIVE: 'פעילה', INACTIVE: 'לא פעילה', UNDER_REPAIR: 'בתיקון' }

export default function ManagementCompaniesPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editCompany, setEditCompany] = useState<Company | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<CompanyDetail | null>(null)
  const [searchElev, setSearchElev] = useState('')
  const [assignElevId, setAssignElevId] = useState('')

  const emptyForm = { name: '', contact_name: '', phone: '', email: '', notes: '', caller_phones_raw: '' }
  const [form, setForm] = useState(emptyForm)

  const { data: companies = [], isLoading } = useQuery<Company[]>({
    queryKey: ['management-companies'],
    queryFn: async () => (await client.get('/management-companies')).data,
  })

  const createMutation = useMutation({
    mutationFn: (d: any) => client.post('/management-companies', d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['management-companies'] })
      setCreateOpen(false)
      setForm(emptyForm)
      notifications.show({ message: 'חברת ניהול נוצרה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, d }: { id: string; d: any }) => client.patch(`/management-companies/${id}`, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['management-companies'] })
      if (detail) loadDetail(detail.id)
      setEditCompany(null)
      notifications.show({ message: 'חברה עודכנה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/management-companies/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['management-companies'] })
      setDetail(null)
      notifications.show({ message: 'חברה נמחקה', color: 'orange' })
    },
  })

  const assignMutation = useMutation({
    mutationFn: ({ companyId, elevId }: { companyId: string; elevId: string }) =>
      client.post(`/management-companies/${companyId}/assign-elevator?elevator_id=${elevId}`),
    onSuccess: () => {
      if (detail) loadDetail(detail.id)
      qc.invalidateQueries({ queryKey: ['management-companies'] })
      setAssignElevId('')
      notifications.show({ message: 'מעלית שויכה לחברה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const removeMutation = useMutation({
    mutationFn: ({ companyId, elevId }: { companyId: string; elevId: string }) =>
      client.post(`/management-companies/${companyId}/remove-elevator?elevator_id=${elevId}`),
    onSuccess: () => {
      if (detail) loadDetail(detail.id)
      qc.invalidateQueries({ queryKey: ['management-companies'] })
      notifications.show({ message: 'מעלית הוסרה מהחברה', color: 'orange' })
    },
  })

  async function loadDetail(id: string) {
    const { data } = await client.get(`/management-companies/${id}`)
    setDetail(data)
  }

  function parseForm(f: typeof form) {
    return {
      name: f.name.trim(),
      contact_name: f.contact_name.trim() || null,
      phone: f.phone.trim() || null,
      email: f.email.trim() || null,
      notes: f.notes.trim() || null,
      caller_phones: f.caller_phones_raw.split('\n').map(s => s.trim()).filter(Boolean),
    }
  }

  function openEdit(c: Company) {
    setForm({
      name: c.name,
      contact_name: c.contact_name ?? '',
      phone: c.phone ?? '',
      email: c.email ?? '',
      notes: c.notes ?? '',
      caller_phones_raw: (c.caller_phones || []).join('\n'),
    })
    setEditCompany(c)
  }

  const filteredElevators = detail?.elevators.filter(e =>
    `${e.address} ${e.city} ${e.building_name ?? ''}`.includes(searchElev)
  ) ?? []

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>🏗️ חברות ניהול</Title>
        <Button onClick={() => { setForm(emptyForm); setCreateOpen(true) }}>+ חברה חדשה</Button>
      </Group>

      {isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : companies.length === 0 ? (
        <Text c="dimmed" ta="center" mt="xl">אין חברות ניהול עדיין</Text>
      ) : (
        <Stack gap="sm">
          {companies.map(c => (
            <Card key={c.id} withBorder radius="md" p="md">
              <Group justify="space-between">
                <Group gap="sm">
                  <Text fw={700}>{c.name}</Text>
                  <Badge variant="light" color="blue">{c.elevator_count} מעליות</Badge>
                </Group>
                <Group gap="xs">
                  <Button size="xs" variant="light" onClick={() => { loadDetail(c.id); setExpanded(c.id) }}>
                    {expanded === c.id ? 'סגור ▲' : 'פרטים ▼'}
                  </Button>
                  <Button size="xs" variant="subtle" onClick={() => openEdit(c)}>✏️</Button>
                  <Button size="xs" variant="subtle" color="red"
                    onClick={() => { if (confirm(`למחוק את "${c.name}"?`)) deleteMutation.mutate(c.id) }}>
                    🗑️
                  </Button>
                </Group>
              </Group>

              {(c.contact_name || c.phone || c.email) && (
                <Group gap="md" mt={4}>
                  {c.contact_name && <Text size="sm" c="dimmed">👤 {c.contact_name}</Text>}
                  {c.phone && <Text size="sm" c="dimmed">📞 {c.phone}</Text>}
                  {c.email && <Text size="sm" c="dimmed">✉️ {c.email}</Text>}
                </Group>
              )}

              <Collapse in={expanded === c.id && !!detail && detail.id === c.id}>
                {detail && detail.id === c.id && (
                  <Stack gap="sm" mt="md">
                    <Group gap="sm">
                      <TextInput
                        placeholder="חפש מעלית (כתובת / עיר)..."
                        value={searchElev}
                        onChange={e => setSearchElev(e.target.value)}
                        style={{ flex: 1 }}
                        size="xs"
                      />
                      <TextInput
                        placeholder="UUID מעלית לשיוך..."
                        value={assignElevId}
                        onChange={e => setAssignElevId(e.target.value)}
                        style={{ flex: 1 }}
                        size="xs"
                      />
                      <Button size="xs" disabled={!assignElevId.trim()}
                        loading={assignMutation.isPending}
                        onClick={() => assignMutation.mutate({ companyId: c.id, elevId: assignElevId.trim() })}>
                        שייך
                      </Button>
                    </Group>

                    {filteredElevators.length === 0 ? (
                      <Text size="sm" c="dimmed" ta="center">אין מעליות משויכות</Text>
                    ) : (
                      <Table striped withTableBorder withColumnBorders fz="sm">
                        <Table.Thead>
                          <Table.Tr>
                            <Table.Th>כתובת</Table.Th>
                            <Table.Th>עיר</Table.Th>
                            <Table.Th>שם בניין</Table.Th>
                            <Table.Th>סטטוס</Table.Th>
                            <Table.Th></Table.Th>
                          </Table.Tr>
                        </Table.Thead>
                        <Table.Tbody>
                          {filteredElevators.map(e => (
                            <Table.Tr key={e.id}>
                              <Table.Td>{e.address}</Table.Td>
                              <Table.Td>{e.city}</Table.Td>
                              <Table.Td>{e.building_name ?? '—'}</Table.Td>
                              <Table.Td>
                                <Badge color={STATUS_COLOR[e.status]} size="xs">{STATUS_LABEL[e.status]}</Badge>
                              </Table.Td>
                              <Table.Td>
                                <Tooltip label="הסר מהחברה">
                                  <ActionIcon size="xs" color="red" variant="subtle"
                                    onClick={() => removeMutation.mutate({ companyId: c.id, elevId: e.id })}>
                                    ✕
                                  </ActionIcon>
                                </Tooltip>
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    )}
                  </Stack>
                )}
              </Collapse>
            </Card>
          ))}
        </Stack>
      )}

      {/* Create / Edit modal */}
      <Modal
        opened={createOpen || !!editCompany}
        onClose={() => { setCreateOpen(false); setEditCompany(null) }}
        title={editCompany ? 'עריכת חברת ניהול' : 'חברת ניהול חדשה'}
        dir="rtl"
      >
        <Stack gap="sm">
          <TextInput label="שם החברה *" required value={form.name} onChange={e => setForm(s => ({ ...s, name: e.target.value }))} />
          <TextInput label="איש קשר" value={form.contact_name} onChange={e => setForm(s => ({ ...s, contact_name: e.target.value }))} />
          <TextInput label="טלפון" value={form.phone} onChange={e => setForm(s => ({ ...s, phone: e.target.value }))} />
          <TextInput label="אימייל" value={form.email} onChange={e => setForm(s => ({ ...s, email: e.target.value }))} />
          <Textarea
            label="מספרי טלפון מזוהים (שורה לכל מספר)"
            description="מספרים שמהם מתקשרים לדווח על מעליות בחברה זו"
            placeholder="050-1234567&#10;052-9876543"
            minRows={2}
            value={form.caller_phones_raw}
            onChange={e => setForm(s => ({ ...s, caller_phones_raw: e.target.value }))}
          />
          <Textarea label="הערות" value={form.notes} onChange={e => setForm(s => ({ ...s, notes: e.target.value }))} minRows={2} />
          <Button
            mt="sm"
            disabled={!form.name.trim()}
            loading={createMutation.isPending || updateMutation.isPending}
            onClick={() => {
              const d = parseForm(form)
              if (editCompany) updateMutation.mutate({ id: editCompany.id, d })
              else createMutation.mutate(d)
            }}
          >
            {editCompany ? 'שמור שינויים' : 'צור חברה'}
          </Button>
        </Stack>
      </Modal>
    </Stack>
  )
}
