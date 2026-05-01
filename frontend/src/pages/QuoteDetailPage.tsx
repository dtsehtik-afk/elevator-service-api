import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Title, Group, Badge, Stack, Text, Button, Select, Paper, Table, Divider, Modal, Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { quotesApi } from '../api/quotes'
import type { Quote } from '../types'

const STATUS_COLORS: Record<string, string> = {
  DRAFT: 'gray', SENT: 'blue', ACCEPTED: 'green', REJECTED: 'red', EXPIRED: 'orange',
}
const STATUS_LABELS: Record<string, string> = {
  DRAFT: 'טיוטה', SENT: 'נשלחה', ACCEPTED: 'אושרה', REJECTED: 'נדחתה', EXPIRED: 'פגה',
}

export default function QuoteDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [quote, setQuote] = useState<Quote | null>(null)
  const [converting, setConverting] = useState(false)

  const load = () => {
    if (!id) return
    quotesApi.get(id).then(setQuote)
  }

  useEffect(() => { load() }, [id])

  const handleStatusChange = async (status: Quote['status']) => {
    if (!id) return
    try {
      await quotesApi.update(id, { status })
      notifications.show({ message: 'סטטוס עודכן', color: 'green' })
      load()
    } catch {
      notifications.show({ message: 'שגיאה', color: 'red' })
    }
  }

  const handleConvert = async () => {
    if (!id) return
    setConverting(true)
    try {
      const res = await quotesApi.convertToContract(id)
      notifications.show({ message: `חוזה ${res.contract_number} נוצר`, color: 'green' })
      navigate(`/contracts/${res.contract_id}`)
    } catch {
      notifications.show({ message: 'שגיאה בהמרה לחוזה', color: 'red' })
    } finally {
      setConverting(false)
    }
  }

  if (!quote) return <Text>טוען...</Text>

  return (
    <>
      <Group justify="space-between" mb="md">
        <Group>
          <Button variant="subtle" onClick={() => navigate('/quotes')}>← חזרה</Button>
          <Title order={2}>{quote.number}</Title>
          <Badge color={STATUS_COLORS[quote.status]}>{STATUS_LABELS[quote.status] || quote.status}</Badge>
        </Group>
        <Group>
          <Select
            size="sm"
            value={quote.status}
            onChange={v => v && handleStatusChange(v as Quote['status'])}
            data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          />
          {['SENT', 'ACCEPTED'].includes(quote.status) && !quote.contract_id && (
            <Button size="sm" color="green" loading={converting} onClick={handleConvert}>
              המר לחוזה
            </Button>
          )}
          {quote.contract_id && (
            <Button size="sm" variant="outline" onClick={() => navigate(`/contracts/${quote.contract_id}`)}>
              לחוזה →
            </Button>
          )}
        </Group>
      </Group>

      <Paper withBorder p="md" mb="md">
        <Group>
          <Stack gap={0}>
            <Text size="xs" c="dimmed">לקוח</Text>
            <Text size="sm" style={{ cursor: 'pointer', color: 'var(--mantine-color-blue-6)' }}
              onClick={() => navigate(`/customers/${quote.customer_id}`)}>
              {quote.customer_name}
            </Text>
          </Stack>
          {quote.elevator_address && (
            <Stack gap={0}>
              <Text size="xs" c="dimmed">מעלית</Text>
              <Text size="sm" style={{ cursor: 'pointer', color: 'var(--mantine-color-blue-6)' }}
                onClick={() => navigate(`/elevators/${quote.elevator_id}`)}>
                {quote.elevator_address}
              </Text>
            </Stack>
          )}
          {quote.valid_until && <Stack gap={0}><Text size="xs" c="dimmed">תוקף עד</Text><Text size="sm">{quote.valid_until}</Text></Stack>}
          {quote.created_by && <Stack gap={0}><Text size="xs" c="dimmed">נוצר על ידי</Text><Text size="sm">{quote.created_by}</Text></Stack>}
        </Group>
      </Paper>

      <Paper withBorder mb="md">
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>תיאור</Table.Th><Table.Th ta="center">כמות</Table.Th>
              <Table.Th ta="right">מחיר יחידה</Table.Th><Table.Th ta="right">סה״כ</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(quote.items || []).map((item, i) => (
              <Table.Tr key={i}>
                <Table.Td>{item.description}</Table.Td>
                <Table.Td ta="center">{item.quantity}</Table.Td>
                <Table.Td ta="right">₪{Number(item.unit_price).toLocaleString()}</Table.Td>
                <Table.Td ta="right">₪{Number(item.total || item.quantity * item.unit_price).toLocaleString()}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Divider />
        <Group justify="flex-end" p="md">
          <Stack gap={2} align="flex-end">
            <Text size="sm">סכום לפני מע״מ: ₪{Number(quote.subtotal).toLocaleString()}</Text>
            <Text size="sm">מע״מ ({quote.vat_rate}%): ₪{Number(quote.vat_amount).toFixed(2)}</Text>
            <Text size="xl" fw={700}>סה״כ: ₪{Number(quote.total).toLocaleString()}</Text>
          </Stack>
        </Group>
      </Paper>

      {quote.notes && (
        <Paper withBorder p="md">
          <Text size="xs" c="dimmed" mb={4}>הערות</Text>
          <Text size="sm">{quote.notes}</Text>
        </Paper>
      )}
    </>
  )
}
