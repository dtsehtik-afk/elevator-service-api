import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Table, Badge, Button, Group, Select, Modal, Stack, Text,
  Paper, TextInput, NumberInput, Textarea, ActionIcon,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { quotesApi } from '../api/quotes'
import { customersApi } from '../api/customers'
import type { Quote, Customer } from '../types'

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'gray', SENT: 'blue', ACCEPTED: 'green', REJECTED: 'red', EXPIRED: 'orange',
}
const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'טיוטה', SENT: 'נשלחה', ACCEPTED: 'אושרה', REJECTED: 'נדחתה', EXPIRED: 'פגה',
}

export default function QuotesPage() {
  const navigate = useNavigate()
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({
    customer_id: '', notes: '', valid_until: '',
    items: [{ description: '', quantity: 1, unit_price: 0, total: 0 }],
    vat_rate: 18,
  })

  const load = () => {
    setLoading(true)
    quotesApi.list({ status: statusFilter || undefined })
      .then(setQuotes)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [statusFilter])
  useEffect(() => { customersApi.list({ limit: 500 }).then(setCustomers) }, [])

  const calcTotals = (items: typeof form.items, vatRate: number) => {
    const subtotal = items.reduce((s, i) => s + i.quantity * i.unit_price, 0)
    const vat = subtotal * (vatRate / 100)
    return { subtotal, vat_amount: vat, total: subtotal + vat }
  }

  const handleCreate = async () => {
    const items = form.items.map(i => ({ ...i, total: i.quantity * i.unit_price }))
    const { subtotal, vat_amount, total } = calcTotals(items, form.vat_rate)
    try {
      const q = await quotesApi.create({
        customer_id: form.customer_id,
        items,
        subtotal,
        vat_rate: form.vat_rate,
        vat_amount,
        total,
        valid_until: form.valid_until || undefined,
        notes: form.notes || undefined,
      } as any)
      notifications.show({ message: `הצעת מחיר ${q.number} נוצרה`, color: 'green' })
      setCreateOpen(false)
      navigate(`/quotes/${q.id}`)
    } catch {
      notifications.show({ message: 'שגיאה ביצירת הצעת מחיר', color: 'red' })
    }
  }

  const rows = quotes.map(q => (
    <Table.Tr key={q.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/quotes/${q.id}`)}>
      <Table.Td>{q.number}</Table.Td>
      <Table.Td>{q.customer_name || '—'}</Table.Td>
      <Table.Td>₪{Number(q.total).toLocaleString()}</Table.Td>
      <Table.Td><Badge color={STATUS_COLORS[q.status]} size="sm">{STATUS_LABELS[q.status] || q.status}</Badge></Table.Td>
      <Table.Td>{q.valid_until || '—'}</Table.Td>
      <Table.Td>{new Date(q.created_at).toLocaleDateString('he-IL')}</Table.Td>
    </Table.Tr>
  ))

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>📄 הצעות מחיר</Title>
        <Button onClick={() => setCreateOpen(true)}>+ הצעה חדשה</Button>
      </Group>

      <Group mb="md">
        <Select
          placeholder="סטטוס"
          clearable
          value={statusFilter}
          onChange={setStatusFilter}
          data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))}
        />
      </Group>

      <Paper withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>מספר</Table.Th><Table.Th>לקוח</Table.Th><Table.Th>סכום</Table.Th>
              <Table.Th>סטטוס</Table.Th><Table.Th>תוקף עד</Table.Th><Table.Th>תאריך</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {loading ? (
              <Table.Tr><Table.Td colSpan={6}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
            ) : rows.length === 0 ? (
              <Table.Tr><Table.Td colSpan={6}><Text ta="center" py="xl" c="dimmed">אין הצעות מחיר</Text></Table.Td></Table.Tr>
            ) : rows}
          </Table.Tbody>
        </Table>
      </Paper>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="הצעת מחיר חדשה" size="xl" dir="rtl">
        <Stack>
          <Select
            label="לקוח"
            required
            searchable
            value={form.customer_id}
            onChange={v => setForm(f => ({ ...f, customer_id: v || '' }))}
            data={customers.map(c => ({ value: c.id, label: c.name }))}
          />
          <Text size="sm" fw={600}>פריטים</Text>
          {form.items.map((item, idx) => (
            <Group key={idx} grow>
              <TextInput
                placeholder="תיאור"
                value={item.description}
                onChange={e => setForm(f => {
                  const items = [...f.items]
                  items[idx] = { ...items[idx], description: e.target.value }
                  return { ...f, items }
                })}
              />
              <NumberInput
                placeholder="כמות"
                value={item.quantity}
                min={0}
                onChange={v => setForm(f => {
                  const items = [...f.items]
                  items[idx] = { ...items[idx], quantity: Number(v) || 0 }
                  return { ...f, items }
                })}
              />
              <NumberInput
                placeholder="מחיר יחידה"
                value={item.unit_price}
                min={0}
                onChange={v => setForm(f => {
                  const items = [...f.items]
                  items[idx] = { ...items[idx], unit_price: Number(v) || 0 }
                  return { ...f, items }
                })}
              />
              {form.items.length > 1 && (
                <ActionIcon color="red" onClick={() => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }))}>✕</ActionIcon>
              )}
            </Group>
          ))}
          <Button variant="light" size="xs" onClick={() => setForm(f => ({ ...f, items: [...f.items, { description: '', quantity: 1, unit_price: 0, total: 0 }] }))}>
            + הוסף פריט
          </Button>
          <Group>
            <NumberInput label="מע״מ %" value={form.vat_rate} onChange={v => setForm(f => ({ ...f, vat_rate: Number(v) || 18 }))} min={0} max={100} />
            <TextInput label="תוקף עד" type="date" value={form.valid_until} onChange={e => setForm(f => ({ ...f, valid_until: e.target.value }))} />
          </Group>
          <Textarea label="הערות" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <Group>
            {(() => {
              const items = form.items.map(i => ({ ...i, total: i.quantity * i.unit_price }))
              const { subtotal, vat_amount, total } = calcTotals(items, form.vat_rate)
              return (
                <Stack gap={2}>
                  <Text size="sm">סכום לפני מע״מ: <b>₪{subtotal.toLocaleString()}</b></Text>
                  <Text size="sm">מע״מ: <b>₪{vat_amount.toFixed(2)}</b></Text>
                  <Text size="lg" fw={700}>סה״כ: ₪{total.toLocaleString()}</Text>
                </Stack>
              )
            })()}
          </Group>
          <Button onClick={handleCreate} disabled={!form.customer_id}>צור הצעת מחיר</Button>
        </Stack>
      </Modal>
    </>
  )
}
