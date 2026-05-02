import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Table, Badge, Button, Group, TextInput, Select, Modal,
  Stack, Text, ActionIcon, Tooltip, Paper, SimpleGrid, Card, NumberInput, Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { customersApi } from '../api/customers'
import type { Customer } from '../types'
import { EditViewDrawer } from '../components/EditViewDrawer'

const TYPE_LABELS: Record<string, string> = {
  OWNER: 'בעל נכס',
  MANAGEMENT_COMPANY: 'חברת ניהול',
  COMMITTEE: 'ועד בית',
  PRIVATE: 'פרטי',
  CORPORATE: 'תאגיד',
}

const TYPE_COLORS: Record<string, string> = {
  OWNER: 'blue',
  MANAGEMENT_COMPANY: 'teal',
  COMMITTEE: 'violet',
  PRIVATE: 'gray',
  CORPORATE: 'orange',
}

export default function CustomersPage() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({
    name: '', customer_type: 'PRIVATE', phone: '', email: '',
    address: '', city: '', contact_person: '', vat_number: '',
    payment_terms: 30, notes: '', parent_id: '',
  })
  const [allCustomers, setAllCustomers] = useState<Customer[]>([])

  const load = () => {
    setLoading(true)
    customersApi.list({ search: search || undefined, customer_type: typeFilter || undefined })
      .then(setCustomers)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [search, typeFilter])
  useEffect(() => {
    customersApi.list({ limit: 500 }).then(setAllCustomers)
  }, [])

  const handleCreate = async () => {
    try {
      await customersApi.create({
        ...form,
        parent_id: form.parent_id || undefined,
        payment_terms: Number(form.payment_terms),
      } as any)
      notifications.show({ message: 'לקוח נוצר בהצלחה', color: 'green' })
      setCreateOpen(false)
      setForm({ name: '', customer_type: 'PRIVATE', phone: '', email: '', address: '', city: '', contact_person: '', vat_number: '', payment_terms: 30, notes: '', parent_id: '' })
      load()
    } catch {
      notifications.show({ message: 'שגיאה ביצירת לקוח', color: 'red' })
    }
  }

  const rows = customers.map(c => (
    <Table.Tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/customers/${c.id}`)}>
      <Table.Td>
        <Group gap={4}>
          <Text size="sm" fw={500}>{c.name}</Text>
          {c.parent_name && <Text size="xs" c="dimmed">↳ {c.parent_name}</Text>}
        </Group>
      </Table.Td>
      <Table.Td>
        <Badge color={TYPE_COLORS[c.customer_type] || 'gray'} size="sm">
          {TYPE_LABELS[c.customer_type] || c.customer_type}
        </Badge>
      </Table.Td>
      <Table.Td>{c.phone || '—'}</Table.Td>
      <Table.Td>{c.city || '—'}</Table.Td>
      <Table.Td>
        <Badge color={c.elevator_count > 0 ? 'blue' : 'gray'} size="sm">{c.elevator_count}</Badge>
      </Table.Td>
      <Table.Td>
        <Badge color={c.active_contracts > 0 ? 'green' : 'gray'} size="sm">{c.active_contracts}</Badge>
      </Table.Td>
      <Table.Td>
        <Badge color={c.open_invoices > 0 ? 'orange' : 'gray'} size="sm">{c.open_invoices}</Badge>
      </Table.Td>
      <Table.Td>
        <Badge color={c.is_active ? 'green' : 'red'} size="xs">{c.is_active ? 'פעיל' : 'לא פעיל'}</Badge>
      </Table.Td>
    </Table.Tr>
  ))

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>👤 לקוחות</Title>
        <Group>
          <EditViewDrawer entityType="customers" entityLabel="לקוחות" />
          <Button onClick={() => setCreateOpen(true)}>+ לקוח חדש</Button>
        </Group>
      </Group>

      <Group mb="md" grow>
        <TextInput
          placeholder="חיפוש לפי שם..."
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <Select
          placeholder="סוג לקוח"
          clearable
          value={typeFilter}
          onChange={setTypeFilter}
          data={Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
        />
      </Group>

      <Paper withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>שם</Table.Th>
              <Table.Th>סוג</Table.Th>
              <Table.Th>טלפון</Table.Th>
              <Table.Th>עיר</Table.Th>
              <Table.Th>מעליות</Table.Th>
              <Table.Th>חוזים פעילים</Table.Th>
              <Table.Th>חשבוניות פתוחות</Table.Th>
              <Table.Th>סטטוס</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {loading ? (
              <Table.Tr><Table.Td colSpan={8}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
            ) : rows.length === 0 ? (
              <Table.Tr><Table.Td colSpan={8}><Text ta="center" py="xl" c="dimmed">אין לקוחות</Text></Table.Td></Table.Tr>
            ) : rows}
          </Table.Tbody>
        </Table>
      </Paper>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="לקוח חדש" size="lg" dir="rtl">
        <Stack>
          <TextInput label="שם" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <Select
            label="סוג לקוח"
            value={form.customer_type}
            onChange={v => setForm(f => ({ ...f, customer_type: v || 'PRIVATE' }))}
            data={Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          />
          <Select
            label="לקוח אב (אופציונלי)"
            placeholder="ללא לקוח אב"
            clearable
            searchable
            value={form.parent_id || null}
            onChange={v => setForm(f => ({ ...f, parent_id: v || '' }))}
            data={allCustomers.map(c => ({ value: c.id, label: c.name }))}
          />
          <Group grow>
            <TextInput label="טלפון" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
            <TextInput label="אימייל" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="כתובת" value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
            <TextInput label="עיר" value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="איש קשר" value={form.contact_person} onChange={e => setForm(f => ({ ...f, contact_person: e.target.value }))} />
            <TextInput label="ח.פ / עוסק מורשה" value={form.vat_number} onChange={e => setForm(f => ({ ...f, vat_number: e.target.value }))} />
          </Group>
          <NumberInput label="ימי תשלום" value={form.payment_terms} onChange={v => setForm(f => ({ ...f, payment_terms: Number(v) || 30 }))} min={0} />
          <Textarea label="הערות" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <Button onClick={handleCreate} disabled={!form.name}>צור לקוח</Button>
        </Stack>
      </Modal>
    </>
  )
}
