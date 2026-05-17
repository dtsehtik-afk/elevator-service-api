import { useState } from 'react'
import {
  Stack, Title, Text, Button, Paper, Badge, Group, TextInput,
  Modal, Textarea, ActionIcon, Loader, Center, Collapse,
  Table, Divider,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'
import type { Consultant } from '../types'

const STATUS_COLOR: Record<string, string> = { ACTIVE: 'green', INACTIVE: 'gray', UNDER_REPAIR: 'orange' }
const STATUS_LABEL: Record<string, string> = { ACTIVE: 'פעילה', INACTIVE: 'לא פעילה', UNDER_REPAIR: 'בתיקון' }

interface ConsultantDetail extends Consultant {
  elevators: { id: string; address: string; city: string; building_name: string | null; status: string }[]
}

export default function ConsultantsPage() {
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [editConsultant, setEditConsultant] = useState<Consultant | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [detail, setDetail] = useState<ConsultantDetail | null>(null)

  const emptyForm = { name: '', phone: '', email: '', address: '', notes: '', contacts_raw: '' }
  const [form, setForm] = useState(emptyForm)

  const { data: consultants = [], isLoading } = useQuery<Consultant[]>({
    queryKey: ['consultants'],
    queryFn: async () => (await client.get('/consultants')).data,
  })

  async function loadDetail(id: string) {
    const { data } = await client.get(`/consultants/${id}`)
    setDetail(data)
  }

  const createMutation = useMutation({
    mutationFn: (d: any) => client.post('/consultants', d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['consultants'] })
      setCreateOpen(false)
      setForm(emptyForm)
      notifications.show({ message: 'יועץ נוצר', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, d }: { id: string; d: any }) => client.patch(`/consultants/${id}`, d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['consultants'] })
      if (detail) loadDetail(detail.id)
      setEditConsultant(null)
      notifications.show({ message: 'יועץ עודכן', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => client.delete(`/consultants/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['consultants'] })
      setDetail(null)
      notifications.show({ message: 'יועץ נמחק', color: 'orange' })
    },
  })

  function parseContacts(raw: string) {
    return raw.split('\n').map(l => l.trim()).filter(Boolean).map(line => {
      const parts = line.split(',').map(p => p.trim())
      return { name: parts[0] || '', phone: parts[1] || undefined, email: parts[2] || undefined }
    })
  }

  function submitCreate() {
    createMutation.mutate({
      name: form.name.trim(),
      phone: form.phone || null,
      email: form.email || null,
      address: form.address || null,
      notes: form.notes || null,
      consultant_contacts: parseContacts(form.contacts_raw),
    })
  }

  function submitEdit() {
    if (!editConsultant) return
    updateMutation.mutate({
      id: editConsultant.id,
      d: {
        name: form.name.trim(),
        phone: form.phone || null,
        email: form.email || null,
        address: form.address || null,
        notes: form.notes || null,
        consultant_contacts: parseContacts(form.contacts_raw),
      },
    })
  }

  function openEdit(c: Consultant) {
    setForm({
      name: c.name,
      phone: c.phone ?? '',
      email: c.email ?? '',
      address: c.address ?? '',
      notes: c.notes ?? '',
      contacts_raw: (c.consultant_contacts ?? [])
        .map(cc => [cc.name, cc.phone, cc.email].filter(Boolean).join(', '))
        .join('\n'),
    })
    setEditConsultant(c)
  }

  const modalContent = (onSubmit: () => void, loading: boolean) => (
    <Stack gap="sm">
      <TextInput label="שם" required value={form.name} onChange={e => setForm(s => ({ ...s, name: e.target.value }))} />
      <TextInput label="טלפון" value={form.phone} onChange={e => setForm(s => ({ ...s, phone: e.target.value }))} />
      <TextInput label="מייל" value={form.email} onChange={e => setForm(s => ({ ...s, email: e.target.value }))} />
      <TextInput label="כתובת" value={form.address} onChange={e => setForm(s => ({ ...s, address: e.target.value }))} />
      <Textarea
        label="אנשי קשר (שורה לכל איש קשר: שם, טלפון, מייל)"
        placeholder={"ישראל ישראלי, 050-1234567, israel@example.com"}
        minRows={3}
        value={form.contacts_raw}
        onChange={e => setForm(s => ({ ...s, contacts_raw: e.target.value }))}
      />
      <Textarea label="הערות" minRows={2} value={form.notes} onChange={e => setForm(s => ({ ...s, notes: e.target.value }))} />
      <Button disabled={!form.name.trim()} loading={loading} onClick={onSubmit}>שמור</Button>
    </Stack>
  )

  return (
    <Stack gap="lg" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>🧑‍💼 יועצים</Title>
        <Button onClick={() => { setForm(emptyForm); setCreateOpen(true) }}>+ יועץ חדש</Button>
      </Group>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="יועץ חדש" dir="rtl">
        {modalContent(submitCreate, createMutation.isPending)}
      </Modal>

      <Modal opened={!!editConsultant} onClose={() => setEditConsultant(null)} title="עריכת יועץ" dir="rtl">
        {modalContent(submitEdit, updateMutation.isPending)}
      </Modal>

      {isLoading ? (
        <Center py="xl"><Loader /></Center>
      ) : consultants.length === 0 ? (
        <Paper withBorder p="xl" radius="md">
          <Text c="dimmed" ta="center">אין יועצים רשומים. לחץ "+ יועץ חדש" להוספה.</Text>
        </Paper>
      ) : (
        <Stack gap="sm">
          {consultants.map(c => (
            <Paper key={c.id} withBorder p="md" radius="md">
              <Group justify="space-between" wrap="nowrap">
                <Stack gap={2} style={{ flex: 1, minWidth: 0 }}>
                  <Group gap="xs">
                    <Text fw={700} size="sm">{c.name}</Text>
                    {!c.is_active && <Badge color="gray" size="xs">לא פעיל</Badge>}
                    <Badge color="blue" size="xs" variant="light">{c.elevator_count} מעליות</Badge>
                  </Group>
                  <Group gap="md">
                    {c.phone && <Text size="xs" c="dimmed">📞 {c.phone}</Text>}
                    {c.email && <Text size="xs" c="dimmed">✉️ {c.email}</Text>}
                    {c.address && <Text size="xs" c="dimmed">📍 {c.address}</Text>}
                  </Group>
                  {(c.consultant_contacts ?? []).length > 0 && (
                    <Text size="xs" c="dimmed">
                      👥 {c.consultant_contacts.map(cc => cc.name).join(', ')}
                    </Text>
                  )}
                </Stack>
                <Group gap="xs" wrap="nowrap">
                  <Button
                    size="xs" variant="light"
                    onClick={() => {
                      if (expanded === c.id) { setExpanded(null); setDetail(null) }
                      else { setExpanded(c.id); loadDetail(c.id) }
                    }}
                  >
                    {expanded === c.id ? '▲ סגור' : '▼ פרטים'}
                  </Button>
                  <ActionIcon size="sm" variant="subtle" onClick={() => openEdit(c)}>✏️</ActionIcon>
                  <ActionIcon
                    size="sm" variant="subtle" color="red"
                    onClick={() => { if (window.confirm('למחוק יועץ זה?')) deleteMutation.mutate(c.id) }}
                  >🗑️</ActionIcon>
                </Group>
              </Group>

              <Collapse in={expanded === c.id}>
                <Divider my="sm" />
                {!detail ? (
                  <Center py="sm"><Loader size="sm" /></Center>
                ) : (
                  <Stack gap="sm">
                    {(detail.consultant_contacts ?? []).length > 0 && (
                      <Stack gap="xs">
                        <Text size="sm" fw={600}>אנשי קשר</Text>
                        {detail.consultant_contacts.map((cc, i) => (
                          <Group key={i} gap="md">
                            <Text size="sm">{cc.name}</Text>
                            {cc.phone && <Text size="xs" c="dimmed">{cc.phone}</Text>}
                            {cc.email && <Text size="xs" c="dimmed">{cc.email}</Text>}
                          </Group>
                        ))}
                      </Stack>
                    )}
                    {detail.notes && <Text size="sm" c="dimmed">{detail.notes}</Text>}
                    {(detail.elevators ?? []).length > 0 && (
                      <Stack gap="xs">
                        <Text size="sm" fw={600}>מעליות ({detail.elevators.length})</Text>
                        <Table size="xs">
                          <Table.Tbody>
                            {detail.elevators.map(e => (
                              <Table.Tr key={e.id}>
                                <Table.Td>{e.address}, {e.city}</Table.Td>
                                <Table.Td>{e.building_name ?? ''}</Table.Td>
                                <Table.Td>
                                  <Badge size="xs" color={STATUS_COLOR[e.status] ?? 'gray'}>
                                    {STATUS_LABEL[e.status] ?? e.status}
                                  </Badge>
                                </Table.Td>
                              </Table.Tr>
                            ))}
                          </Table.Tbody>
                        </Table>
                      </Stack>
                    )}
                  </Stack>
                )}
              </Collapse>
            </Paper>
          ))}
        </Stack>
      )}
    </Stack>
  )
}
