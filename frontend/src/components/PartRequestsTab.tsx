import { useState } from 'react'
import {
  Stack, Text, Badge, Button, Group, Select, NumberInput, Textarea,
  Table, Alert, Modal, Loader, Center, Paper,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPartRequests, createPartRequest, approvePartRequest,
  rejectPartRequest, issuePartRequest, returnFaultyPart,
} from '../api/partRequests'
import { useAuthStore } from '../stores/authStore'
import type { PartRequest } from '../types'

const STATUS_COLORS: Record<string, string> = {
  PENDING_APPROVAL: 'yellow', APPROVED: 'green', REJECTED: 'red',
  ISSUED: 'blue', CANCELLED: 'gray',
}
const STATUS_LABELS: Record<string, string> = {
  PENDING_APPROVAL: 'ממתין לאישור', APPROVED: 'אושר', REJECTED: 'נדחה',
  ISSUED: 'הוצא', CANCELLED: 'בוטל',
}

interface Props {
  serviceCallId: string
  parts: { value: string; label: string; category?: string }[]
  warehouses: { value: string; label: string }[]
  elevatorManufacturer?: string | null
}

export function PartRequestsTab({ serviceCallId, parts, warehouses, elevatorManufacturer }: Props) {
  const filteredParts = elevatorManufacturer
    ? parts.filter(p => !p.category || p.category.toLowerCase().includes(elevatorManufacturer.toLowerCase()) || elevatorManufacturer.toLowerCase().includes((p.category || '').toLowerCase()))
    : parts
  const qc = useQueryClient()
  const role = useAuthStore(s => s.role)
  const isManager = role === 'ADMIN' || role === 'MANAGER' || role === 'DISPATCHER'

  const [addOpen, setAddOpen] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [selectedPr, setSelectedPr] = useState<PartRequest | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [form, setForm] = useState({
    part_id: '', quantity: 1, source_warehouse_id: '', notes: '',
  })

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['part-requests', serviceCallId],
    queryFn: () => listPartRequests({ service_call_id: serviceCallId }),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['part-requests', serviceCallId] })

  const createMut = useMutation({
    mutationFn: () => createPartRequest({
      service_call_id: serviceCallId,
      part_id: form.part_id,
      quantity: form.quantity,
      source_warehouse_id: form.source_warehouse_id || null,
      notes: form.notes || null,
    }),
    onSuccess: () => {
      notifications.show({ message: 'בקשת חלק נשלחה לאישור', color: 'yellow' })
      setAddOpen(false)
      setForm({ part_id: '', quantity: 1, source_warehouse_id: '', notes: '' })
      invalidate()
    },
    onError: () => notifications.show({ message: 'שגיאה בשליחת בקשה', color: 'red' }),
  })

  const approveMut = useMutation({
    mutationFn: (id: string) => approvePartRequest(id),
    onSuccess: () => { notifications.show({ message: 'בקשה אושרה', color: 'green' }); invalidate() },
    onError: () => notifications.show({ message: 'שגיאה באישור', color: 'red' }),
  })

  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => rejectPartRequest(id, reason),
    onSuccess: () => {
      notifications.show({ message: 'בקשה נדחתה', color: 'red' })
      setRejectOpen(false)
      setRejectReason('')
      invalidate()
    },
    onError: () => notifications.show({ message: 'שגיאה בדחייה', color: 'red' }),
  })

  const issueMut = useMutation({
    mutationFn: (id: string) => issuePartRequest(id),
    onSuccess: () => { notifications.show({ message: 'חלק הוצא מהמחסן ✅', color: 'blue' }); invalidate() },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail || 'שגיאה בהוצאת חלק', color: 'red' }),
  })

  const returnMut = useMutation({
    mutationFn: (id: string) => returnFaultyPart(id),
    onSuccess: () => { notifications.show({ message: 'החזרת חלק תקול אושרה', color: 'teal' }); invalidate() },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  const pendingReturns = requests.filter(r => r.status === 'ISSUED' && !r.faulty_part_returned)

  return (
    <Stack gap="sm">
      {pendingReturns.length > 0 && (
        <Alert color="orange" title="⚠️ נדרשת החזרת חלק תקול">
          יש {pendingReturns.length} חלק/ים שהוחלפו. הקריאה יכולה לדווח כ"טופלה" ללקוח, אך לא ניתן לסגור אותה סופית עד להחזרת החלק/ים התקולים למחסן הראשי.
        </Alert>
      )}

      <Group justify="space-between">
        <Text fw={600} size="sm">חלקים שהוחלפו / נדרשים</Text>
        <Button size="xs" onClick={() => setAddOpen(true)}>+ בקש חלק</Button>
      </Group>

      {isLoading ? (
        <Center py="md"><Loader size="sm" /></Center>
      ) : requests.length === 0 ? (
        <Text c="dimmed" size="sm" ta="center" py="md">אין בקשות חלקים לקריאה זו</Text>
      ) : (
        <Paper withBorder>
          <Table size="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>חלק</Table.Th>
                <Table.Th>כמות</Table.Th>
                <Table.Th>סוג שירות</Table.Th>
                <Table.Th>סטטוס</Table.Th>
                <Table.Th>החזרה</Table.Th>
                <Table.Th>פעולות</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {requests.map(pr => (
                <Table.Tr key={pr.id}>
                  <Table.Td>
                    <Text size="sm">{pr.part_name || '—'}</Text>
                    {pr.part_sku && <Text size="xs" c="dimmed">{pr.part_sku}</Text>}
                  </Table.Td>
                  <Table.Td>{pr.quantity}</Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={pr.service_type_snapshot === 'COMPREHENSIVE' ? 'green' : 'orange'}>
                      {pr.service_type_snapshot === 'COMPREHENSIVE' ? 'מקיף' : 'רגיל'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={STATUS_COLORS[pr.status]}>{STATUS_LABELS[pr.status] || pr.status}</Badge>
                  </Table.Td>
                  <Table.Td>
                    {pr.status === 'ISSUED' && (
                      <Badge size="xs" color={pr.faulty_part_returned ? 'teal' : 'red'}>
                        {pr.faulty_part_returned ? 'הוחזר ✓' : 'טרם הוחזר'}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {isManager && pr.status === 'PENDING_APPROVAL' && (
                        <>
                          <Button size="xs" color="green" onClick={() => approveMut.mutate(pr.id)}>אשר</Button>
                          <Button size="xs" color="red" variant="light" onClick={() => { setSelectedPr(pr); setRejectOpen(true) }}>דחה</Button>
                        </>
                      )}
                      {pr.status === 'APPROVED' && (
                        <Button size="xs" color="blue" onClick={() => issueMut.mutate(pr.id)}>הוצא מהמחסן</Button>
                      )}
                      {pr.status === 'ISSUED' && !pr.faulty_part_returned && (
                        <Button size="xs" color="teal" variant="light" onClick={() => returnMut.mutate(pr.id)}>
                          סמן החזרת חלק תקול
                        </Button>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      {/* Add part request modal */}
      <Modal opened={addOpen} onClose={() => setAddOpen(false)} title="בקשת חלק להחלפה" dir="rtl" size="md">
        <Stack>
          <Alert color="blue" size="sm">
            המערכת תבדוק את סוג השירות של הלקוח ותשלח בקשת אישור מתאימה למנהל.
          </Alert>
          {elevatorManufacturer && filteredParts.length < parts.length && (
            <Text size="xs" c="dimmed">מסונן לפי יצרן: {elevatorManufacturer} ({filteredParts.length} מתוך {parts.length})</Text>
          )}
          <Select
            label="חלק" required searchable
            data={filteredParts}
            value={form.part_id}
            onChange={v => setForm(f => ({ ...f, part_id: v || '' }))}
          />
          <NumberInput
            label="כמות" min={1} value={form.quantity}
            onChange={v => setForm(f => ({ ...f, quantity: Number(v) || 1 }))}
          />
          <Select
            label="מחסן מקור (ברירת מחדל: מחסן ראשי)"
            clearable
            data={warehouses}
            value={form.source_warehouse_id}
            onChange={v => setForm(f => ({ ...f, source_warehouse_id: v || '' }))}
          />
          <Textarea
            label="הערות"
            value={form.notes}
            onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
          />
          <Button onClick={() => createMut.mutate()} disabled={!form.part_id} loading={createMut.isPending}>
            שלח לאישור
          </Button>
        </Stack>
      </Modal>

      {/* Reject modal */}
      <Modal opened={rejectOpen} onClose={() => setRejectOpen(false)} title="דחיית בקשת חלק" dir="rtl">
        <Stack>
          <Textarea
            label="סיבת דחייה" required
            value={rejectReason}
            onChange={e => setRejectReason(e.target.value)}
          />
          <Button
            color="red"
            disabled={!rejectReason}
            loading={rejectMut.isPending}
            onClick={() => selectedPr && rejectMut.mutate({ id: selectedPr.id, reason: rejectReason })}
          >
            דחה בקשה
          </Button>
        </Stack>
      </Modal>
    </Stack>
  )
}
