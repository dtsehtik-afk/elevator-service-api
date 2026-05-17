import { useState } from 'react'
import {
  Stack, Title, Text, Badge, Button, Group, Textarea,
  Table, Paper, Center, Loader, Modal, Tabs, Alert,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listPartRequests, approvePartRequest, rejectPartRequest, issuePartRequest,
} from '../api/partRequests'
import { useAuthStore } from '../stores/authStore'
import type { PartRequest } from '../types'
import { useNavigate } from 'react-router-dom'
import { formatDate } from '../utils/dates'

const STATUS_COLORS: Record<string, string> = {
  PENDING_APPROVAL: 'yellow', APPROVED: 'green', REJECTED: 'red',
  ISSUED: 'blue', CANCELLED: 'gray',
}
const STATUS_LABELS: Record<string, string> = {
  PENDING_APPROVAL: 'ממתין לאישור', APPROVED: 'אושר', REJECTED: 'נדחה',
  ISSUED: 'הוצא', CANCELLED: 'בוטל',
}

export default function PartRequestsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const role = useAuthStore(s => s.role)
  const isManager = role === 'ADMIN' || role === 'MANAGER' || role === 'DISPATCHER'

  // '' = all statuses
  const [statusFilter, setStatusFilter] = useState<string>('PENDING_APPROVAL')
  const [rejectOpen, setRejectOpen] = useState(false)
  const [selectedPr, setSelectedPr] = useState<PartRequest | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [approvalNotes, setApprovalNotes] = useState('')
  const [approveOpen, setApproveOpen] = useState(false)

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['part-requests-all', statusFilter],
    queryFn: () => listPartRequests({ status: statusFilter === 'ALL' ? undefined : statusFilter }),
    refetchInterval: 30000,
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['part-requests-all'] })
    qc.invalidateQueries({ queryKey: ['part-requests-pending-count'] })
  }

  const approveMut = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) => approvePartRequest(id, notes),
    onSuccess: () => {
      notifications.show({ message: 'בקשה אושרה — נשלחה הודעה לטכנאי', color: 'green' })
      setApproveOpen(false)
      setApprovalNotes('')
      invalidate()
    },
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

  const pendingCount = statusFilter === 'ALL'
    ? requests.filter(r => r.status === 'PENDING_APPROVAL').length
    : (statusFilter === 'PENDING_APPROVAL' ? requests.length : 0)

  return (
    <Stack gap="md" p="md">
      <Group justify="space-between">
        <Title order={2}>בקשות חלפים</Title>
        {pendingCount > 0 && statusFilter !== 'PENDING_APPROVAL' && (
          <Badge color="orange" size="lg">{pendingCount} ממתינות לאישור</Badge>
        )}
      </Group>

      {pendingCount > 0 && statusFilter === 'PENDING_APPROVAL' && (
        <Alert color="orange" title="בקשות הממתינות לאישור שלך">
          {pendingCount} בקשות חלפים מטכנאים מחכות לאישורך.
        </Alert>
      )}

      <Tabs value={statusFilter} onChange={v => setStatusFilter(v ?? 'ALL')}>
        <Tabs.List>
          <Tabs.Tab value="PENDING_APPROVAL">ממתין לאישור</Tabs.Tab>
          <Tabs.Tab value="APPROVED">אושר</Tabs.Tab>
          <Tabs.Tab value="ISSUED">הוצא</Tabs.Tab>
          <Tabs.Tab value="REJECTED">נדחה</Tabs.Tab>
          <Tabs.Tab value="ALL">הכל</Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {isLoading ? (
        <Center py="xl"><Loader /></Center>
      ) : requests.length === 0 ? (
        <Center py="xl"><Text c="dimmed">אין בקשות</Text></Center>
      ) : (
        <Paper withBorder>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>קריאה</Table.Th>
                <Table.Th>חלק</Table.Th>
                <Table.Th>כמות</Table.Th>
                <Table.Th>טכנאי</Table.Th>
                <Table.Th>סוג שירות</Table.Th>
                <Table.Th>סטטוס</Table.Th>
                <Table.Th>תאריך</Table.Th>
                <Table.Th>פעולות</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {requests.map(pr => (
                <Table.Tr key={pr.id}>
                  <Table.Td>
                    <Button
                      size="xs" variant="subtle" p={0}
                      onClick={() => navigate(`/calls?callId=${pr.service_call_id}`)}
                    >
                      קריאה #{pr.service_call_id.slice(0, 8)}
                    </Button>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" fw={500}>{pr.part_name || '—'}</Text>
                    {pr.part_sku && <Text size="xs" c="dimmed">{pr.part_sku}</Text>}
                  </Table.Td>
                  <Table.Td>{pr.quantity}</Table.Td>
                  <Table.Td><Text size="sm">{pr.requester_name || '—'}</Text></Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={pr.service_type_snapshot === 'COMPREHENSIVE' ? 'green' : 'orange'}>
                      {pr.service_type_snapshot === 'COMPREHENSIVE' ? 'מקיף' : 'רגיל'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={STATUS_COLORS[pr.status]}>{STATUS_LABELS[pr.status] || pr.status}</Badge>
                  </Table.Td>
                  <Table.Td><Text size="xs" c="dimmed">{formatDate(pr.created_at)}</Text></Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      {isManager && pr.status === 'PENDING_APPROVAL' && (
                        <>
                          <Button size="xs" color="green" onClick={() => { setSelectedPr(pr); setApprovalNotes(''); setApproveOpen(true) }}>אשר</Button>
                          <Button size="xs" color="red" variant="light" onClick={() => { setSelectedPr(pr); setRejectOpen(true) }}>דחה</Button>
                        </>
                      )}
                      {pr.status === 'APPROVED' && (
                        <Button size="xs" color="blue" onClick={() => issueMut.mutate(pr.id)}>הוצא מהמחסן</Button>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      {/* Approve modal */}
      <Modal opened={approveOpen} onClose={() => setApproveOpen(false)} title="אישור בקשת חלק" dir="rtl">
        <Stack>
          <Text size="sm">
            אישור: <strong>{selectedPr?.part_name}</strong> × {selectedPr?.quantity}
          </Text>
          <Textarea
            label="הערות אישור (אופציונלי)"
            value={approvalNotes}
            onChange={e => setApprovalNotes(e.target.value)}
            placeholder="הוראות מיוחדות, מחסן מועדף וכד׳"
          />
          <Button
            color="green"
            loading={approveMut.isPending}
            onClick={() => selectedPr && approveMut.mutate({ id: selectedPr.id, notes: approvalNotes })}
          >
            אשר בקשה
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
