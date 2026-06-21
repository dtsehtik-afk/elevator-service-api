import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Table, Badge, Button, Group, TextInput, Select, Modal,
  Stack, Text, ActionIcon, Tooltip, Paper, SimpleGrid, Card, NumberInput, Textarea,
  Collapse, Divider, Tabs, Grid,
} from '@mantine/core'
import { AIRefineButton } from '../components/AIRefineButton'
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

function SortTh({ col, label, sortBy, sortDir, onSort }: { col: string; label: string; sortBy: string; sortDir: 'asc' | 'desc'; onSort: (c: string) => void }) {
  return (
    <Table.Th style={{ cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none' }} onClick={() => onSort(col)}>
      {label}{sortBy === col ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
    </Table.Th>
  )
}

export default function CustomersPage() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState('name')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [createOpen, setCreateOpen] = useState(false)
  const [erpOpen, setErpOpen] = useState(false)
  const [form, setForm] = useState({
    name: '', customer_type: 'PRIVATE', phone: '', email: '',
    address: '', city: '', contact_person: '', vat_number: '',
    payment_terms: 30, notes: '', parent_id: '',
    fax: '', industry_type: '', territory: '', delivery_route: '',
    website: '', sales_target: 0, employee_count: 0,
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
      setForm({ name: '', customer_type: 'PRIVATE', phone: '', email: '', address: '', city: '', contact_person: '', vat_number: '', payment_terms: 30, notes: '', parent_id: '', fax: '', industry_type: '', territory: '', delivery_route: '', website: '', sales_target: 0, employee_count: 0 })
      load()
    } catch {
      notifications.show({ message: 'שגיאה ביצירת לקוח', color: 'red' })
    }
  }

  function handleSort(col: string) {
    if (sortBy === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortBy(col); setSortDir('asc') }
  }

  const sortedCustomers = [...customers].sort((a, b) => {
    const aVal = (a as any)[sortBy] ?? ''
    const bVal = (b as any)[sortBy] ?? ''
    const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal), 'he')
    return sortDir === 'asc' ? cmp : -cmp
  })

  const rows = sortedCustomers.map(c => (
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
              <SortTh col="name" label="שם" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortTh col="customer_type" label="סוג" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <Table.Th>טלפון</Table.Th>
              <SortTh col="city" label="עיר" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortTh col="elevator_count" label="מעליות" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortTh col="active_contracts" label="חוזים פעילים" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortTh col="open_invoices" label="חשבוניות פתוחות" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
              <SortTh col="is_active" label="סטטוס" sortBy={sortBy} sortDir={sortDir} onSort={handleSort} />
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

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="לקוח חדש" size="xl" dir="rtl">
        <Tabs defaultValue="general" keepMounted={false}>
          <Tabs.List mb="md">
            <Tabs.Tab value="general">פרטים כלליים</Tabs.Tab>
            <Tabs.Tab value="address">כתובת ואינטרנט</Tabs.Tab>
            <Tabs.Tab value="notes">הערות</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="general">
            <Grid gutter="md">
              <Grid.Col span={12}>
                <TextInput label="שם" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Select
                  label="סוג לקוח"
                  value={form.customer_type}
                  onChange={v => setForm(f => ({ ...f, customer_type: v || 'PRIVATE' }))}
                  data={Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <Select
                  label="לקוח אב"
                  placeholder="ללא לקוח אב"
                  clearable searchable
                  value={form.parent_id || null}
                  onChange={v => setForm(f => ({ ...f, parent_id: v || '' }))}
                  data={allCustomers.map(c => ({ value: c.id, label: c.name }))}
                />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="ח.פ / עוסק מורשה" value={form.vat_number} onChange={e => setForm(f => ({ ...f, vat_number: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="איש קשר" value={form.contact_person} onChange={e => setForm(f => ({ ...f, contact_person: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="טלפון" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="אימייל" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <NumberInput label="תנאי תשלום (ימים)" value={form.payment_terms} onChange={v => setForm(f => ({ ...f, payment_terms: Number(v) || 30 }))} min={0} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="תחום עיסוק" value={form.industry_type} onChange={e => setForm(f => ({ ...f, industry_type: e.target.value }))} />
              </Grid.Col>
            </Grid>
          </Tabs.Panel>

          <Tabs.Panel value="address">
            <Grid gutter="md">
              <Grid.Col span={12}>
                <TextInput label="כתובת" value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="עיר" value={form.city} onChange={e => setForm(f => ({ ...f, city: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="אתר אינטרנט" value={form.website} onChange={e => setForm(f => ({ ...f, website: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="פקס" value={form.fax} onChange={e => setForm(f => ({ ...f, fax: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="אזור / טריטוריה" value={form.territory} onChange={e => setForm(f => ({ ...f, territory: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <TextInput label="קו חלוקה" value={form.delivery_route} onChange={e => setForm(f => ({ ...f, delivery_route: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 6 }}>
                <NumberInput label="מס' עובדים" value={form.employee_count} min={0} onChange={v => setForm(f => ({ ...f, employee_count: Number(v) || 0 }))} />
              </Grid.Col>
            </Grid>
          </Tabs.Panel>

          <Tabs.Panel value="notes">
            <Stack gap="md">
              <Textarea
                label="הערות"
                minRows={5}
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                rightSection={<AIRefineButton value={form.notes} onChange={v => setForm(f => ({ ...f, notes: v }))} />}
                rightSectionPointerEvents="all"
              />
              <NumberInput label="יעד מכירות (₪)" value={form.sales_target} min={0} onChange={v => setForm(f => ({ ...f, sales_target: Number(v) || 0 }))} />
            </Stack>
          </Tabs.Panel>
        </Tabs>

        <Divider my="md" />
        <Group justify="flex-end">
          <Button variant="default" onClick={() => setCreateOpen(false)}>ביטול</Button>
          <Button onClick={handleCreate} disabled={!form.name}>➕ צור לקוח</Button>
        </Group>
      </Modal>
    </>
  )
}
