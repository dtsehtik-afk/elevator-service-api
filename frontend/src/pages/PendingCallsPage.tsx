/**
 * PendingCallsPage — Two sections:
 * 1. Unmatched incoming calls awaiting manual elevator assignment
 * 2. Open service calls with no technician assigned
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Stack, Title, Text, Card, Badge, Group, Button, Divider,
  Loader, Center, Modal, TextInput, Alert, Select, Tabs, Anchor,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '../api/client'

const FAULT_LABEL: Record<string, string> = {
  STUCK: 'מעלית תקועה', DOOR: 'תקלת דלת', ELECTRICAL: 'חשמלית',
  MECHANICAL: 'מכנית', SOFTWARE: 'תוכנה', OTHER: 'כללית',
}
const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'yellow', LOW: 'green',
}
const PRIORITY_LABEL: Record<string, string> = {
  CRITICAL: 'קריטי', HIGH: 'גבוה', MEDIUM: 'בינוני', LOW: 'נמוך',
}

interface PendingCall {
  id: string
  call_street: string | null
  call_city: string | null
  fault_type: string | null
  priority: string | null
  caller_name: string | null
  caller_phone: string | null
  match_status: string
  match_score: number | null
  match_notes: string | null
  closest_elevator: string | null
  closest_elevator_id: string | null
  created_at: string | null
}

interface UnassignedCall {
  id: string
  call_number: number | null
  elevator_id: string
  fault_type: string
  priority: string
  status: string
  description: string | null
  reported_by: string | null
  created_at: string
  address?: string
  city?: string
}

interface ElevatorOption {
  id: string
  address: string
  city: string
  building_name: string | null
}

interface TechOption {
  id: string
  name: string
  is_available: boolean
  role: string
}

async function fetchPending(): Promise<PendingCall[]> {
  const { data } = await client.get('/webhooks/pending-unmatched')
  return data
}

async function fetchUnassigned(): Promise<UnassignedCall[]> {
  const { data } = await client.get('/calls/unassigned')
  return data
}

async function fetchTechnicians(): Promise<TechOption[]> {
  const { data } = await client.get('/technicians')
  return data
}

async function addElevator(logId: string) {
  const { data } = await client.post(`/webhooks/pending-unmatched/${logId}/add-elevator`)
  return data
}

async function matchElevator(logId: string, elevatorId: string) {
  const { data } = await client.post(`/webhooks/pending-unmatched/${logId}/match-elevator`, null, {
    params: { elevator_id: elevatorId },
  })
  return data
}

async function dismissPending(logId: string) {
  await client.delete(`/webhooks/pending-unmatched/${logId}`)
}

async function searchElevators(q: string): Promise<ElevatorOption[]> {
  const { data } = await client.get('/elevators/', { params: { search: q, limit: 10 } })
  return data
}

async function assignTechnician(callId: string, technicianId: string) {
  const { data } = await client.post(`/calls/${callId}/assign`, { technician_id: technicianId })
  return data
}

async function autoAssign(callId: string) {
  const { data } = await client.post(`/calls/${callId}/auto-assign`)
  return data
}

function formatDate(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ── Section 2: Unassigned service calls ───────────────────────────────────
function UnassignedCallsSection() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [assignModal, setAssignModal] = useState<UnassignedCall | null>(null)
  const [selectedTech, setSelectedTech] = useState<string | null>(null)

  const { data: calls = [], isLoading } = useQuery({
    queryKey: ['unassigned-calls'],
    queryFn: fetchUnassigned,
    refetchInterval: 30000,
  })

  const { data: technicians = [] } = useQuery({
    queryKey: ['technicians'],
    queryFn: fetchTechnicians,
  })

  const manualAssignMut = useMutation({
    mutationFn: ({ callId, techId }: { callId: string; techId: string }) =>
      assignTechnician(callId, techId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['unassigned-calls'] })
      setAssignModal(null)
      setSelectedTech(null)
      notifications.show({ message: '✅ טכנאי שובץ בהצלחה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בשיבוץ', color: 'red' }),
  })

  const autoAssignMut = useMutation({
    mutationFn: (callId: string) => autoAssign(callId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['unassigned-calls'] })
      notifications.show({ message: '🤖 שיבוץ אוטומטי נשלח לטכנאי', color: 'teal' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בשיבוץ אוטו', color: 'red' }),
  })

  const techOptions = technicians
    .filter(t => t.is_available)
    .map(t => ({ value: t.id, label: t.name }))

  if (isLoading) return <Center h={100}><Loader /></Center>

  if (!calls.length) return (
    <Alert color="green" title="הכל תקין">אין קריאות פתוחות ללא שיבוץ טכנאי.</Alert>
  )

  return (
    <>
      {calls.map(call => (
        <Card key={call.id} withBorder radius="md" shadow="sm" p="md"
          style={{ borderRight: '4px solid #228be6' }}>
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <Badge color={PRIORITY_COLOR[call.priority] ?? 'gray'} size="sm">
                {PRIORITY_LABEL[call.priority] ?? call.priority}
              </Badge>
              <Badge color="blue" size="sm" variant="light">
                {FAULT_LABEL[call.fault_type] ?? call.fault_type}
              </Badge>
            </Group>
            <Text size="xs" c="dimmed">{formatDate(call.created_at)}</Text>
          </Group>

          <Group justify="space-between" align="flex-start">
            <Text fw={700} size="md">📍 {call.address || 'כתובת לא ידועה'}{call.city ? `, ${call.city}` : ''}</Text>
            <Anchor size="xs" onClick={() => navigate(`/calls?id=${call.id}`)} style={{ cursor: 'pointer' }}>
              {call.call_number ? `#${call.call_number}` : 'פתח קריאה →'}
            </Anchor>
          </Group>
          {call.description && <Text size="sm" c="dimmed" mt={2}>{call.description}</Text>}
          {call.reported_by && <Text size="sm" c="dimmed">📞 {call.reported_by}</Text>}

          <Divider my="sm" />

          <Group gap="sm">
            <Button
              size="sm" color="blue" variant="light" flex={1}
              onClick={() => { setAssignModal(call); setSelectedTech(null) }}
            >
              👤 שבץ טכנאי
            </Button>
            <Button
              size="sm" color="teal" variant="light" flex={1}
              loading={autoAssignMut.isPending}
              onClick={() => autoAssignMut.mutate(call.id)}
            >
              🤖 שיבוץ אוטומטי
            </Button>
          </Group>
        </Card>
      ))}

      <Modal
        opened={!!assignModal}
        onClose={() => { setAssignModal(null); setSelectedTech(null) }}
        title="👤 שיבוץ טכנאי ידני"
        size="sm"
        dir="rtl"
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            קריאה: {assignModal?.address}, {assignModal?.city}
          </Text>
          <Select
            label="בחר טכנאי זמין"
            placeholder="בחר..."
            data={techOptions}
            value={selectedTech}
            onChange={setSelectedTech}
            searchable
          />
          <Button
            disabled={!selectedTech}
            loading={manualAssignMut.isPending}
            onClick={() => assignModal && selectedTech &&
              manualAssignMut.mutate({ callId: assignModal.id, techId: selectedTech })}
          >
            שבץ
          </Button>
        </Stack>
      </Modal>
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────
export default function PendingCallsPage() {
  const qc = useQueryClient()
  const [matchModalLog, setMatchModalLog] = useState<PendingCall | null>(null)
  const [elevSearch, setElevSearch] = useState('')
  const [elevResults, setElevResults] = useState<ElevatorOption[]>([])

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['pending-unmatched'],
    queryFn: fetchPending,
    refetchInterval: 30000,
  })

  const { data: unassigned = [] } = useQuery({
    queryKey: ['unassigned-calls'],
    queryFn: fetchUnassigned,
    refetchInterval: 30000,
  })

  const addMutation = useMutation({
    mutationFn: (logId: string) => addElevator(logId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-unmatched'] })
      notifications.show({ message: '🏗️ מעלית חדשה נוספה וקריאה נפתחה', color: 'teal' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const matchMutation = useMutation({
    mutationFn: ({ logId, elevId }: { logId: string; elevId: string }) => matchElevator(logId, elevId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-unmatched'] })
      setMatchModalLog(null)
      setElevSearch('')
      setElevResults([])
      notifications.show({ message: '🔗 שויך למעלית קיימת וקריאה נפתחה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const dismissMutation = useMutation({
    mutationFn: (logId: string) => dismissPending(logId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-unmatched'] })
      notifications.show({ message: '🗑️ קריאה הוסרה מהתור', color: 'gray' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה במחיקה', color: 'red' }),
  })

  const handleElevSearch = async (q: string) => {
    setElevSearch(q)
    if (q.length < 2) { setElevResults([]); return }
    try {
      const results = await searchElevators(q)
      setElevResults(results)
    } catch {
      setElevResults([])
    }
  }

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>⚠️ קריאות ממתינות</Title>
        <Group gap="xs">
          <Badge color="orange" size="lg">{pending.length} ללא מעלית</Badge>
          <Badge color="blue" size="lg">{unassigned.length} ללא שיבוץ</Badge>
        </Group>
      </Group>

      <Tabs defaultValue="unassigned">
        <Tabs.List mb="md">
          <Tabs.Tab value="unassigned">
            🔵 ללא שיבוץ טכנאי ({unassigned.length})
          </Tabs.Tab>
          <Tabs.Tab value="unmatched">
            🟠 ללא שיוך מעלית ({pending.length})
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="unassigned">
          <Stack gap="sm">
            <Text c="dimmed" size="sm">
              קריאות פתוחות שהמעלית זוהתה אך לא שובץ טכנאי. ניתן לשבץ ידנית או להפעיל שיבוץ אוטומטי.
            </Text>
            <UnassignedCallsSection />
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="unmatched">
          <Stack gap="sm">
            <Text c="dimmed" size="sm">
              קריאות שהגיעו ממוקד הטלפוניה אך המערכת לא זיהתה את המעלית.
              ניתן להוסיף מעלית חדשה או לשייך לכתובת קיימת.
            </Text>

            {isLoading ? (
              <Center h={200}><Loader /></Center>
            ) : pending.length === 0 ? (
              <Alert color="green" title="הכל תקין">אין קריאות ממתינות לשיוך מעלית.</Alert>
            ) : (
              pending.map((call) => (
                <Card key={call.id} withBorder radius="md" shadow="sm" p="md"
                  style={{ borderRight: '4px solid #fd7e14' }}>
                  <Group justify="space-between" mb="xs">
                    <Group gap="xs">
                      <Badge color={PRIORITY_COLOR[call.priority ?? ''] ?? 'gray'} size="sm">
                        {PRIORITY_LABEL[call.priority ?? ''] ?? call.priority}
                      </Badge>
                      <Badge color={call.match_status === 'PARTIAL' ? 'orange' : 'red'} size="sm" variant="light">
                        {call.match_status === 'PARTIAL' ? 'התאמה חלקית' : 'לא זוהה'}
                      </Badge>
                    </Group>
                    <Text size="xs" c="dimmed">{formatDate(call.created_at)}</Text>
                  </Group>

                  <Text fw={700} size="md">📍 {call.call_street || 'רחוב לא ידוע'}, {call.call_city || 'עיר לא ידועה'}</Text>
                  <Text size="sm" c="dimmed" mt={2}>🔧 {FAULT_LABEL[call.fault_type ?? ''] ?? call.fault_type}</Text>

                  {(call.caller_name || call.caller_phone) && (
                    <Text size="sm" c="dimmed">
                      📞 {[call.caller_name, call.caller_phone].filter(Boolean).join(' | ')}
                    </Text>
                  )}

                  {call.closest_elevator && (
                    <Text size="sm" c="orange" mt={4}>
                      🏢 הכי קרוב במערכת: {call.closest_elevator}
                      {call.match_score ? ` (${Math.round(call.match_score * 100)}%)` : ''}
                    </Text>
                  )}

                  <Divider my="sm" />

                  <Group gap="sm">
                    <Button
                      size="sm" color="teal" variant="light" flex={1}
                      loading={addMutation.isPending && addMutation.variables === call.id}
                      onClick={() => {
                        if (confirm(`להוסיף מעלית חדשה בכתובת: ${call.call_street}, ${call.call_city}?`))
                          addMutation.mutate(call.id)
                      }}
                    >
                      🏗️ הוסף מעלית חדשה
                    </Button>
                    <Button
                      size="sm" color="blue" variant="light" flex={1}
                      onClick={() => { setMatchModalLog(call); setElevSearch(''); setElevResults([]) }}
                    >
                      🔗 שייך למעלית קיימת
                    </Button>
                    {call.closest_elevator_id && (
                      <Button
                        size="sm" color="grape" variant="light" flex={1}
                        loading={matchMutation.isPending}
                        onClick={() => {
                          if (confirm(`לשייך לכתובת הקרובה: ${call.closest_elevator}?`))
                            matchMutation.mutate({ logId: call.id, elevId: call.closest_elevator_id! })
                        }}
                      >
                        ✅ שייך לקרובה
                      </Button>
                    )}
                    <Button
                      size="sm" color="red" variant="subtle"
                      loading={dismissMutation.isPending && dismissMutation.variables === call.id}
                      onClick={() => {
                        if (confirm('למחוק קריאה זו מהתור? לא תיפתח קריאת שירות.'))
                          dismissMutation.mutate(call.id)
                      }}
                    >
                      🗑️ מחק
                    </Button>
                  </Group>
                </Card>
              ))
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>

      {/* Elevator search modal */}
      <Modal
        opened={!!matchModalLog}
        onClose={() => { setMatchModalLog(null); setElevSearch(''); setElevResults([]) }}
        title="🔗 שיוך למעלית קיימת"
        size="md"
        dir="rtl"
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            קריאה מ: {matchModalLog?.call_street}, {matchModalLog?.call_city}
          </Text>
          <TextInput
            placeholder="חפש לפי כתובת / עיר / שם בניין"
            value={elevSearch}
            onChange={e => handleElevSearch(e.target.value)}
            autoFocus
          />
          {elevResults.map(e => (
            <Card key={e.id} withBorder p="sm" style={{ cursor: 'pointer' }}
              onClick={() => {
                if (matchModalLog && confirm(`לשייך ל: ${e.address}, ${e.city}?`))
                  matchMutation.mutate({ logId: matchModalLog.id, elevId: e.id })
              }}>
              <Text fw={600}>{e.address}</Text>
              <Text size="sm" c="dimmed">{e.city}{e.building_name ? ` — ${e.building_name}` : ''}</Text>
            </Card>
          ))}
          {elevSearch.length >= 2 && elevResults.length === 0 && (
            <Text c="dimmed" ta="center" size="sm">לא נמצאו תוצאות</Text>
          )}
        </Stack>
      </Modal>
    </Stack>
  )
}
