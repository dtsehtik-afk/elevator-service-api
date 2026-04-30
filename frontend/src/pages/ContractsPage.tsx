import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, Table, Badge, Button, Group, Select, Modal, Stack, Text,
  Paper, TextInput, NumberInput, Textarea, Switch, Checkbox,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { contractsApi } from '../api/contracts'
import { customersApi } from '../api/customers'
import type { Contract, Customer } from '../types'

const STATUS_COLORS: Record<string, string> = {
  PENDING: 'gray', ACTIVE: 'green', EXPIRED: 'orange', CANCELLED: 'red',
}
const STATUS_LABELS: Record<string, string> = {
  PENDING: 'ממתין', ACTIVE: 'פעיל', EXPIRED: 'פג', CANCELLED: 'בוטל',
}
const TYPE_LABELS: Record<string, string> = {
  SERVICE: 'שירות', MAINTENANCE: 'תחזוקה', INSPECTION: 'ביקורת', RENOVATION: 'שיפוץ', OTHER: 'אחר',
}

export default function ContractsPage() {
  const navigate = useNavigate()
  const [contracts, setContracts] = useState<Contract[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [form, setForm] = useState({
    customer_id: '', contract_type: 'SERVICE', status: 'PENDING',
    start_date: '', end_date: '', monthly_price: 0, total_value: 0,
    payment_terms: 30, auto_invoice: false, invoice_frequency: '',
    notes: '',
  })

  const load = () => {
    setLoading(true)
    contractsApi.list({ status: statusFilter || undefined })
      .then(setContracts)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [statusFilter])
  useEffect(() => { customersApi.list({ limit: 500 }).then(setCustomers) }, [])

  const handleCreate = async () => {
    try {
      const c = await contractsApi.create({
        ...form,
        start_date: form.start_date || undefined,
        end_date: form.end_date || undefined,
        monthly_price: form.monthly_price || undefined,
        total_value: form.total_value || undefined,
        invoice_frequency: form.invoice_frequency || undefined,
      } as any)
      notifications.show({ message: `חוזה ${c.number} נוצר`, color: 'green' })
      setCreateOpen(false)
      navigate(`/contracts/${c.id}`)
    } catch {
      notifications.show({ message: 'שגיאה ביצירת חוזה', color: 'red' })
    }
  }

  const rows = contracts.map(c => (
    <Table.Tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/contracts/${c.id}`)}>
      <Table.Td>{c.number}</Table.Td>
      <Table.Td>{c.customer_name || '—'}</Table.Td>
      <Table.Td>{TYPE_LABELS[c.contract_type] || c.contract_type}</Table.Td>
      <Table.Td><Badge color={STATUS_COLORS[c.status]} size="sm">{STATUS_LABELS[c.status] || c.status}</Badge></Table.Td>
      <Table.Td>{c.start_date || '—'}</Table.Td>
      <Table.Td>{c.end_date || '—'}</Table.Td>
      <Table.Td>{c.monthly_price ? `₪${Number(c.monthly_price).toLocaleString()}` : '—'}</Table.Td>
      <Table.Td><Badge size="xs" color="blue">{c.elevator_count}</Badge></Table.Td>
    </Table.Tr>
  ))

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>📋 חוזים</Title>
        <Button onClick={() => setCreateOpen(true)}>+ חוזה חדש</Button>
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
              <Table.Th>מספר</Table.Th><Table.Th>לקוח</Table.Th><Table.Th>סוג</Table.Th>
              <Table.Th>סטטוס</Table.Th><Table.Th>התחלה</Table.Th><Table.Th>סיום</Table.Th>
              <Table.Th>מחיר חודשי</Table.Th><Table.Th>מעליות</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {loading ? (
              <Table.Tr><Table.Td colSpan={8}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
            ) : rows.length === 0 ? (
              <Table.Tr><Table.Td colSpan={8}><Text ta="center" py="xl" c="dimmed">אין חוזים</Text></Table.Td></Table.Tr>
            ) : rows}
          </Table.Tbody>
        </Table>
      </Paper>

      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="חוזה חדש" size="lg" dir="rtl">
        <Stack>
          <Select label="לקוח" required searchable value={form.customer_id}
            onChange={v => setForm(f => ({ ...f, customer_id: v || '' }))}
            data={customers.map(c => ({ value: c.id, label: c.name }))} />
          <Group grow>
            <Select label="סוג חוזה" value={form.contract_type}
              onChange={v => setForm(f => ({ ...f, contract_type: v || 'SERVICE' }))}
              data={Object.entries(TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
            <Select label="סטטוס" value={form.status}
              onChange={v => setForm(f => ({ ...f, status: v || 'PENDING' }))}
              data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Group>
          <Group grow>
            <TextInput label="תאריך התחלה" type="date" value={form.start_date}
              onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} />
            <TextInput label="תאריך סיום" type="date" value={form.end_date}
              onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} />
          </Group>
          <Group grow>
            <NumberInput label="מחיר חודשי (₪)" value={form.monthly_price} min={0}
              onChange={v => setForm(f => ({ ...f, monthly_price: Number(v) || 0 }))} />
            <NumberInput label="ערך כולל (₪)" value={form.total_value} min={0}
              onChange={v => setForm(f => ({ ...f, total_value: Number(v) || 0 }))} />
          </Group>
          <NumberInput label="ימי תשלום" value={form.payment_terms} min={0}
            onChange={v => setForm(f => ({ ...f, payment_terms: Number(v) || 30 }))} />
          <Switch
            label="חיוב אוטומטי"
            checked={form.auto_invoice}
            onChange={e => setForm(f => ({ ...f, auto_invoice: e.target.checked }))} />
          {form.auto_invoice && (
            <Select label="תדירות חיוב" value={form.invoice_frequency}
              onChange={v => setForm(f => ({ ...f, invoice_frequency: v || '' }))}
              data={[{ value: 'MONTHLY', label: 'חודשי' }, { value: 'QUARTERLY', label: 'רבעוני' }, { value: 'ANNUAL', label: 'שנתי' }]} />
          )}
          <Textarea label="הערות" value={form.notes}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <Button onClick={handleCreate} disabled={!form.customer_id}>צור חוזה</Button>
        </Stack>
      </Modal>
    </>
  )
}
