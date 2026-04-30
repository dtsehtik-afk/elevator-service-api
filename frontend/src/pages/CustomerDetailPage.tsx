import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Title, Group, Badge, Stack, Text, Button, TextInput, Select, Modal,
  Paper, SimpleGrid, Card, NumberInput, Textarea, Tabs, Table, ActionIcon, Divider,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { customersApi } from '../api/customers'
import { quotesApi } from '../api/quotes'
import { contractsApi } from '../api/contracts'
import { invoicesApi } from '../api/invoices'
import RelatedPanel from '../components/RelatedPanel'
import type { CustomerDetail, Quote, Contract, Invoice } from '../types'

const TYPE_LABELS: Record<string, string> = {
  OWNER: 'בעל נכס', MANAGEMENT_COMPANY: 'חברת ניהול', COMMITTEE: 'ועד בית', PRIVATE: 'פרטי', CORPORATE: 'תאגיד',
}

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [customer, setCustomer] = useState<CustomerDetail | null>(null)
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [contracts, setContracts] = useState<Contract[]>([])
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [editOpen, setEditOpen] = useState(false)
  const [editForm, setEditForm] = useState<any>({})

  const load = () => {
    if (!id) return
    customersApi.get(id).then(c => {
      setCustomer(c)
      setEditForm({ name: c.name, customer_type: c.customer_type, phone: c.phone || '', email: c.email || '', address: c.address || '', city: c.city || '', contact_person: c.contact_person || '', vat_number: c.vat_number || '', payment_terms: c.payment_terms, notes: c.notes || '', is_active: c.is_active })
    })
    quotesApi.list({ customer_id: id }).then(setQuotes)
    contractsApi.list({ customer_id: id }).then(setContracts)
    invoicesApi.list({ customer_id: id }).then(setInvoices)
  }

  useEffect(() => { load() }, [id])

  const handleSave = async () => {
    if (!id) return
    try {
      await customersApi.update(id, editForm)
      notifications.show({ message: 'הלקוח עודכן', color: 'green' })
      setEditOpen(false)
      load()
    } catch {
      notifications.show({ message: 'שגיאה בעדכון', color: 'red' })
    }
  }

  if (!customer) return <Text>טוען...</Text>

  const totalDebt = invoices
    .filter(inv => ['SENT', 'PARTIAL', 'OVERDUE'].includes(inv.status))
    .reduce((s, inv) => s + inv.balance, 0)

  return (
    <>
      <Group justify="space-between" mb="md">
        <Group>
          <Button variant="subtle" onClick={() => navigate('/customers')}>← חזרה</Button>
          <Title order={2}>{customer.name}</Title>
          <Badge color={customer.is_active ? 'green' : 'red'}>{customer.is_active ? 'פעיל' : 'לא פעיל'}</Badge>
          <Badge color="blue">{TYPE_LABELS[customer.customer_type] || customer.customer_type}</Badge>
        </Group>
        <Button variant="outline" onClick={() => setEditOpen(true)}>עריכה</Button>
      </Group>

      {/* Related panel */}
      <RelatedPanel entityType="customer" entityId={customer.id} />

      <SimpleGrid cols={{ base: 2, md: 4 }} mt="md" mb="md">
        <Card withBorder><Text size="xs" c="dimmed">מעליות</Text><Text fw={700} size="xl">{customer.elevator_count}</Text></Card>
        <Card withBorder><Text size="xs" c="dimmed">חוזים פעילים</Text><Text fw={700} size="xl">{customer.active_contracts}</Text></Card>
        <Card withBorder><Text size="xs" c="dimmed">חשבוניות פתוחות</Text><Text fw={700} size="xl">{customer.open_invoices}</Text></Card>
        <Card withBorder><Text size="xs" c="dimmed">חוב פתוח</Text><Text fw={700} size="xl" c={totalDebt > 0 ? 'red' : 'green'}>₪{totalDebt.toLocaleString()}</Text></Card>
      </SimpleGrid>

      {/* Info */}
      <Paper withBorder p="md" mb="md">
        <SimpleGrid cols={{ base: 2, md: 4 }}>
          {customer.parent_name && <Stack gap={0}><Text size="xs" c="dimmed">לקוח אב</Text><Text size="sm" style={{ cursor: 'pointer', color: 'var(--mantine-color-blue-6)' }} onClick={() => navigate(`/customers/${customer.parent_id}`)}>{customer.parent_name}</Text></Stack>}
          {customer.phone && <Stack gap={0}><Text size="xs" c="dimmed">טלפון</Text><Text size="sm">{customer.phone}</Text></Stack>}
          {customer.email && <Stack gap={0}><Text size="xs" c="dimmed">אימייל</Text><Text size="sm">{customer.email}</Text></Stack>}
          {customer.city && <Stack gap={0}><Text size="xs" c="dimmed">עיר</Text><Text size="sm">{customer.city}</Text></Stack>}
          {customer.address && <Stack gap={0}><Text size="xs" c="dimmed">כתובת</Text><Text size="sm">{customer.address}</Text></Stack>}
          {customer.contact_person && <Stack gap={0}><Text size="xs" c="dimmed">איש קשר</Text><Text size="sm">{customer.contact_person}</Text></Stack>}
          {customer.vat_number && <Stack gap={0}><Text size="xs" c="dimmed">ח.פ / עוסק</Text><Text size="sm">{customer.vat_number}</Text></Stack>}
          <Stack gap={0}><Text size="xs" c="dimmed">ימי תשלום</Text><Text size="sm">{customer.payment_terms} ימים</Text></Stack>
        </SimpleGrid>
        {customer.notes && <><Divider my="sm" /><Text size="sm" c="dimmed">{customer.notes}</Text></>}
      </Paper>

      {/* Tabs */}
      <Tabs defaultValue="quotes">
        <Tabs.List>
          <Tabs.Tab value="quotes">הצעות מחיר ({quotes.length})</Tabs.Tab>
          <Tabs.Tab value="contracts">חוזים ({contracts.length})</Tabs.Tab>
          <Tabs.Tab value="invoices">חשבוניות ({invoices.length})</Tabs.Tab>
          {customer.children.length > 0 && <Tabs.Tab value="children">לקוחות משנה ({customer.children.length})</Tabs.Tab>}
        </Tabs.List>

        <Tabs.Panel value="quotes" pt="sm">
          <Group justify="flex-end" mb="xs">
            <Button size="xs" onClick={() => navigate('/quotes')}>+ הצעת מחיר חדשה</Button>
          </Group>
          <Table highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>מספר</Table.Th><Table.Th>סכום</Table.Th><Table.Th>סטטוס</Table.Th><Table.Th>תוקף</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {quotes.map(q => (
                <Table.Tr key={q.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/quotes/${q.id}`)}>
                  <Table.Td>{q.number}</Table.Td>
                  <Table.Td>₪{Number(q.total).toLocaleString()}</Table.Td>
                  <Table.Td><Badge size="sm">{q.status}</Badge></Table.Td>
                  <Table.Td>{q.valid_until || '—'}</Table.Td>
                </Table.Tr>
              ))}
              {quotes.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text c="dimmed" ta="center" py="md">אין הצעות מחיר</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="contracts" pt="sm">
          <Group justify="flex-end" mb="xs">
            <Button size="xs" onClick={() => navigate('/contracts')}>+ חוזה חדש</Button>
          </Group>
          <Table highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>מספר</Table.Th><Table.Th>סוג</Table.Th><Table.Th>סטטוס</Table.Th><Table.Th>עד</Table.Th><Table.Th>מחיר חודשי</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {contracts.map(c => (
                <Table.Tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/contracts/${c.id}`)}>
                  <Table.Td>{c.number}</Table.Td>
                  <Table.Td>{c.contract_type}</Table.Td>
                  <Table.Td><Badge color={c.status === 'ACTIVE' ? 'green' : 'gray'} size="sm">{c.status}</Badge></Table.Td>
                  <Table.Td>{c.end_date || '—'}</Table.Td>
                  <Table.Td>{c.monthly_price ? `₪${Number(c.monthly_price).toLocaleString()}` : '—'}</Table.Td>
                </Table.Tr>
              ))}
              {contracts.length === 0 && <Table.Tr><Table.Td colSpan={5}><Text c="dimmed" ta="center" py="md">אין חוזים</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="invoices" pt="sm">
          <Group justify="flex-end" mb="xs">
            <Button size="xs" onClick={() => navigate('/invoices')}>+ חשבונית חדשה</Button>
          </Group>
          <Table highlightOnHover>
            <Table.Thead><Table.Tr><Table.Th>מספר</Table.Th><Table.Th>סכום</Table.Th><Table.Th>שולם</Table.Th><Table.Th>יתרה</Table.Th><Table.Th>סטטוס</Table.Th><Table.Th>לתשלום</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>
              {invoices.map(inv => (
                <Table.Tr key={inv.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/invoices/${inv.id}`)}>
                  <Table.Td>{inv.number}</Table.Td>
                  <Table.Td>₪{Number(inv.total).toLocaleString()}</Table.Td>
                  <Table.Td>₪{Number(inv.amount_paid).toLocaleString()}</Table.Td>
                  <Table.Td c={inv.balance > 0 ? 'red' : 'green'}>₪{Number(inv.balance).toLocaleString()}</Table.Td>
                  <Table.Td><Badge size="sm" color={inv.status === 'PAID' ? 'green' : inv.status === 'OVERDUE' ? 'red' : 'orange'}>{inv.status}</Badge></Table.Td>
                  <Table.Td>{inv.due_date || '—'}</Table.Td>
                </Table.Tr>
              ))}
              {invoices.length === 0 && <Table.Tr><Table.Td colSpan={6}><Text c="dimmed" ta="center" py="md">אין חשבוניות</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        {customer.children.length > 0 && (
          <Tabs.Panel value="children" pt="sm">
            <Table highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>שם</Table.Th><Table.Th>סוג</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {customer.children.map(ch => (
                  <Table.Tr key={ch.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/customers/${ch.id}`)}>
                    <Table.Td>{ch.name}</Table.Td>
                    <Table.Td><Badge size="sm">{TYPE_LABELS[ch.customer_type] || ch.customer_type}</Badge></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Tabs.Panel>
        )}
      </Tabs>

      {/* Edit modal */}
      <Modal opened={editOpen} onClose={() => setEditOpen(false)} title="עריכת לקוח" size="lg" dir="rtl">
        <Stack>
          <TextInput label="שם" required value={editForm.name} onChange={e => setEditForm((f: any) => ({ ...f, name: e.target.value }))} />
          <Select label="סוג" value={editForm.customer_type} onChange={v => setEditForm((f: any) => ({ ...f, customer_type: v }))} data={Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          <Group grow>
            <TextInput label="טלפון" value={editForm.phone} onChange={e => setEditForm((f: any) => ({ ...f, phone: e.target.value }))} />
            <TextInput label="אימייל" value={editForm.email} onChange={e => setEditForm((f: any) => ({ ...f, email: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="כתובת" value={editForm.address} onChange={e => setEditForm((f: any) => ({ ...f, address: e.target.value }))} />
            <TextInput label="עיר" value={editForm.city} onChange={e => setEditForm((f: any) => ({ ...f, city: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="איש קשר" value={editForm.contact_person} onChange={e => setEditForm((f: any) => ({ ...f, contact_person: e.target.value }))} />
            <TextInput label="ח.פ / עוסק" value={editForm.vat_number} onChange={e => setEditForm((f: any) => ({ ...f, vat_number: e.target.value }))} />
          </Group>
          <NumberInput label="ימי תשלום" value={editForm.payment_terms} onChange={v => setEditForm((f: any) => ({ ...f, payment_terms: Number(v) }))} min={0} />
          <Textarea label="הערות" value={editForm.notes} onChange={e => setEditForm((f: any) => ({ ...f, notes: e.target.value }))} />
          <Select label="סטטוס" value={editForm.is_active ? 'true' : 'false'} onChange={v => setEditForm((f: any) => ({ ...f, is_active: v === 'true' }))} data={[{ value: 'true', label: 'פעיל' }, { value: 'false', label: 'לא פעיל' }]} />
          <Button onClick={handleSave}>שמור</Button>
        </Stack>
      </Modal>
    </>
  )
}
