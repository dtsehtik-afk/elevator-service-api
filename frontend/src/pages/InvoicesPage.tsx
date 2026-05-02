import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Table, Badge, Button, Group, Select, Modal, Stack, Text,
  Paper, NumberInput, Textarea, Tabs,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { invoicesApi } from '../api/invoices'
import { customersApi } from '../api/customers'
import type { Invoice, Customer } from '../types'
import { EditViewDrawer } from '../components/EditViewDrawer'

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'gray', SENT: 'blue', PAID: 'green', PARTIAL: 'orange', OVERDUE: 'red', CANCELLED: 'dark',
}
const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'טיוטה', SENT: 'נשלחה', PAID: 'שולמה', PARTIAL: 'חלקית', OVERDUE: 'באיחור', CANCELLED: 'בוטלה',
}

export default function InvoicesPage() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState<Invoice[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [debtors, setDebtors] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({
    customer_id: '', issue_date: new Date().toISOString().slice(0, 10), due_date: '',
    items: [{ description: '', quantity: 1, unit_price: 0, total: 0 }],
    vat_rate: 18, notes: '',
  })

  const load = () => {
    setLoading(true)
    invoicesApi.list({ status: statusFilter || undefined }).then(setInvoices).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [statusFilter])
  useEffect(() => {
    customersApi.list({ limit: 500 }).then(setCustomers)
    invoicesApi.debtors().then(setDebtors)
  }, [])

  const calcTotals = (items: typeof form.items, vatRate: number) => {
    const subtotal = items.reduce((s, i) => s + i.quantity * i.unit_price, 0)
    const vat = subtotal * (vatRate / 100)
    return { subtotal, vat_amount: vat, total: subtotal + vat }
  }

  const handleCreate = async () => {
    const items = form.items.map(i => ({ ...i, total: i.quantity * i.unit_price }))
    const { subtotal, vat_amount, total } = calcTotals(items, form.vat_rate)
    try {
      const inv = await invoicesApi.create({
        customer_id: form.customer_id,
        items, subtotal, vat_rate: form.vat_rate, vat_amount, total,
        issue_date: form.issue_date,
        due_date: form.due_date || undefined,
        notes: form.notes || undefined,
      } as any)
      notifications.show({ message: `חשבונית ${inv.number} נוצרה`, color: 'green' })
      setCreateOpen(false)
      navigate(`/invoices/${inv.id}`)
    } catch {
      notifications.show({ message: 'שגיאה ביצירת חשבונית', color: 'red' })
    }
  }

  const rows = invoices.map(inv => (
    <Table.Tr key={inv.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/invoices/${inv.id}`)}>
      <Table.Td>{inv.number}</Table.Td>
      <Table.Td>{inv.customer_name || '—'}</Table.Td>
      <Table.Td>₪{Number(inv.total).toLocaleString()}</Table.Td>
      <Table.Td c={Number(inv.balance) > 0 ? 'red' : 'green'}>₪{Number(inv.balance).toLocaleString()}</Table.Td>
      <Table.Td><Badge color={STATUS_COLORS[inv.status]} size="sm">{STATUS_LABELS[inv.status] || inv.status}</Badge></Table.Td>
      <Table.Td>{inv.issue_date}</Table.Td>
      <Table.Td>{inv.due_date || '—'}</Table.Td>
    </Table.Tr>
  ))

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>💰 חשבוניות</Title>
        <Group>
          <EditViewDrawer entityType="invoices" entityLabel="חשבוניות" />
          <Button onClick={() => setCreateOpen(true)}>+ חשבונית חדשה</Button>
        </Group>
      </Group>

      <Tabs defaultValue="invoices">
        <Tabs.List mb="md">
          <Tabs.Tab value="invoices">כל החשבוניות ({invoices.length})</Tabs.Tab>
          <Tabs.Tab value="debtors">חייבים ({debtors.length})</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="invoices">
          <Group mb="md">
            <Select placeholder="סטטוס" clearable value={statusFilter} onChange={setStatusFilter}
              data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Group>
          <Paper withBorder>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr><Table.Th>מספר</Table.Th><Table.Th>לקוח</Table.Th><Table.Th>סכום</Table.Th>
                  <Table.Th>יתרה</Table.Th><Table.Th>סטטוס</Table.Th><Table.Th>הנפקה</Table.Th><Table.Th>לתשלום</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {loading ? (
                  <Table.Tr><Table.Td colSpan={7}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
                ) : rows.length === 0 ? (
                  <Table.Tr><Table.Td colSpan={7}><Text ta="center" py="xl" c="dimmed">אין חשבוניות</Text></Table.Td></Table.Tr>
                ) : rows}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="debtors">
          <Paper withBorder>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr><Table.Th>לקוח</Table.Th><Table.Th>חויב</Table.Th><Table.Th>שולם</Table.Th><Table.Th>חוב פתוח</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {debtors.map(d => (
                  <Table.Tr key={d.customer_id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/customers/${d.customer_id}`)}>
                    <Table.Td>{d.customer_name}</Table.Td>
                    <Table.Td>₪{Number(d.total_billed).toLocaleString()}</Table.Td>
                    <Table.Td>₪{Number(d.total_paid).toLocaleString()}</Table.Td>
                    <Table.Td c="red" fw={600}>₪{Number(d.balance).toLocaleString()}</Table.Td>
                  </Table.Tr>
                ))}
                {debtors.length === 0 && <Table.Tr><Table.Td colSpan={4}><Text ta="center" py="xl" c="green">אין חייבים 🎉</Text></Table.Td></Table.Tr>}
              </Table.Tbody>
            </Table>
          </Paper>
        </Tabs.Panel>
      </Tabs>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="חשבונית חדשה" size="xl" dir="rtl">
        <Stack>
          <Select label="לקוח" required searchable value={form.customer_id}
            onChange={v => setForm(f => ({ ...f, customer_id: v || '' }))}
            data={customers.map(c => ({ value: c.id, label: c.name }))} />
          <Group grow>
            <input type="date" value={form.issue_date} onChange={e => setForm(f => ({ ...f, issue_date: e.target.value }))} style={{ padding: 8, border: '1px solid #ccc', borderRadius: 6 }} />
            <input type="date" value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} style={{ padding: 8, border: '1px solid #ccc', borderRadius: 6 }} placeholder="לתשלום עד" />
          </Group>
          <Text size="sm" fw={600}>פריטים</Text>
          {form.items.map((item, idx) => (
            <Group key={idx} grow>
              <input placeholder="תיאור" value={item.description}
                onChange={e => setForm(f => { const items = [...f.items]; items[idx] = { ...items[idx], description: e.target.value }; return { ...f, items } })}
                style={{ padding: 8, border: '1px solid #ccc', borderRadius: 6, flex: 2 }} />
              <NumberInput placeholder="כמות" value={item.quantity} min={0}
                onChange={v => setForm(f => { const items = [...f.items]; items[idx] = { ...items[idx], quantity: Number(v) || 0 }; return { ...f, items } })} />
              <NumberInput placeholder="מחיר" value={item.unit_price} min={0}
                onChange={v => setForm(f => { const items = [...f.items]; items[idx] = { ...items[idx], unit_price: Number(v) || 0 }; return { ...f, items } })} />
            </Group>
          ))}
          <Button variant="light" size="xs"
            onClick={() => setForm(f => ({ ...f, items: [...f.items, { description: '', quantity: 1, unit_price: 0, total: 0 }] }))}>
            + פריט
          </Button>
          <NumberInput label="מע״מ %" value={form.vat_rate} min={0} max={100}
            onChange={v => setForm(f => ({ ...f, vat_rate: Number(v) || 18 }))} />
          {(() => {
            const items = form.items.map(i => ({ ...i, total: i.quantity * i.unit_price }))
            const { subtotal, vat_amount, total } = calcTotals(items, form.vat_rate)
            return <Text fw={700} size="lg">סה״כ: ₪{total.toLocaleString()}</Text>
          })()}
          <Textarea label="הערות" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <Button onClick={handleCreate} disabled={!form.customer_id || !form.issue_date}>צור חשבונית</Button>
        </Stack>
      </Modal>
    </>
  )
}
