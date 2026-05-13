/**
 * PendingCallsPage — Unmatched incoming calls awaiting manual elevator assignment
 */
import { useState } from 'react'
import {
  Stack, Title, Text, Card, Badge, Group, Button, Divider,
  Loader, Center, Modal, TextInput, Alert, Textarea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '../api/client'

const FAULT_LABEL: Record<string, string> = {
  STUCK: 'מעלית תקועה', DOOR: 'תקלת דלת', ELECTRICAL: 'חשמלית',
  MECHANICAL: 'מכנית', SOFTWARE: 'תוכנה', OTHER: 'כללית',
  MAINTENANCE: 'תחזוקה',
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

interface ElevatorOption {
  id: string
  address: string
  city: string
  building_name: string | null
}

async function fetchPending(): Promise<PendingCall[]> {
  const { data } = await client.get('/webhooks/pending-unmatched')
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

async function dismissCall(logId: string, reason: string) {
  const { data } = await client.post(`/webhooks/pending-unmatched/${logId}/dismiss`, { reason })
  return data
}

async function searchElevators(q: string): Promise<ElevatorOption[]> {
  const { data } = await client.get('/elevators', { params: { search: q, limit: 10 } })
  return data
}

function formatDate(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('he-IL', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function PendingCallsPage() {
  const qc = useQueryClient()
  const [matchModalLog, setMatchModalLog] = useState<PendingCall | null>(null)
  const [elevSearch, setElevSearch] = useState('')
  const [elevResults, setElevResults] = useState<ElevatorOption[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState<string | null>(null)

  const [dismissModalLog, setDismissModalLog] = useState<PendingCall | null>(null)
  const [dismissReason, setDismissReason] = useState('')

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['pending-unmatched'],
    queryFn: fetchPending,
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
    mutationFn: ({ logId, reason }: { logId: string; reason: string }) => dismissCall(logId, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-unmatched'] })
      setDismissModalLog(null)
      setDismissReason('')
      notifications.show({ message: '🗑️ הקריאה בוטלה', color: 'gray' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const handleElevSearch = async (q: string) => {
    setElevSearch(q)
    setSearchError(null)
    if (q.length < 2) { setElevResults([]); return }
    setSearchLoading(true)
    try {
      const results = await searchElevators(q)
      setElevResults(Array.isArray(results) ? results : [])
    } catch (e: any) {
      setSearchError(e?.response?.data?.detail ?? 'שגיאה בחיפוש מעליות')
      setElevResults([])
    } finally {
      setSearchLoading(false)
    }
  }

  const handleDismissSubmit = () => {
    if (!dismissModalLog || !dismissReason.trim()) return
    dismissMutation.mutate({ logId: dismissModalLog.id, reason: dismissReason.trim() })
  }

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>⚠️ קריאות ממתינות לשיוך מעלית</Title>
        <Badge color="orange" size="lg">{pending.length} ממתינות</Badge>
      </Group>

      <Text c="dimmed" size="sm">
        קריאות שהגיעו ממוקד הטלפוניה אך המערכת לא זיהתה את המעלית.
        ניתן להוסיף מעלית חדשה, לשייך לכתובת קיימת, או לבטל עם ציון סיבה.
      </Text>

      {isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : pending.length === 0 ? (
        <Alert color="green" title="הכל תקין">אין קריאות ממתינות לטיפול.</Alert>
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
                onClick={() => { setMatchModalLog(call); setElevSearch(''); setElevResults([]); setSearchError(null) }}
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
                size="sm" color="red" variant="light" flex={1}
                onClick={() => { setDismissModalLog(call); setDismissReason('') }}
              >
                🗑️ בטל קריאה
              </Button>
            </Group>
          </Card>
        ))
      )}

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
            rightSection={searchLoading ? <Loader size="xs" /> : null}
          />
          {searchError && <Text c="red" size="sm">{searchError}</Text>}
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
          {!searchLoading && elevSearch.length >= 2 && elevResults.length === 0 && !searchError && (
            <Text c="dimmed" ta="center" size="sm">לא נמצאו תוצאות</Text>
          )}
        </Stack>
      </Modal>

      {/* Dismiss modal */}
      <Modal
        opened={!!dismissModalLog}
        onClose={() => { setDismissModalLog(null); setDismissReason('') }}
        title="🗑️ ביטול קריאה"
        size="sm"
        dir="rtl"
      >
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            קריאה מ: {dismissModalLog?.call_street}, {dismissModalLog?.call_city}
          </Text>
          <Textarea
            label="סיבת ביטול"
            placeholder='למשל: "לא בשירות שלנו", "קריאה כפולה", "כתובת שגויה"'
            required
            minRows={2}
            value={dismissReason}
            onChange={e => setDismissReason(e.target.value)}
            autoFocus
          />
          <Group justify="flex-end" gap="sm">
            <Button variant="subtle" color="gray" onClick={() => { setDismissModalLog(null); setDismissReason('') }}>
              ביטול
            </Button>
            <Button
              color="red"
              disabled={!dismissReason.trim()}
              loading={dismissMutation.isPending}
              onClick={handleDismissSubmit}
            >
              אשר ביטול
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
