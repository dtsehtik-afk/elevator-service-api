/**
 * TechAppPage — Mobile technician app
 * Accessible at /tech — no admin shell, optimized for phone
 */
import { useState, useEffect, useRef } from 'react'
import { Stack, Title, Text, Button, Card, Badge, Group, Divider, Loader, Center, Modal, TextInput, Textarea } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import { login as apiLogin } from '../api/auth'
import client from '../api/client'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const PRIORITY_COLOR: Record<string, string> = {
  CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'yellow', LOW: 'green',
}
const PRIORITY_LABEL: Record<string, string> = {
  CRITICAL: '🔴 קריטי', HIGH: '🟠 גבוה', MEDIUM: '🟡 בינוני', LOW: '🟢 נמוך',
}
const FAULT_LABEL: Record<string, string> = {
  STUCK: 'מעלית תקועה 🚨', DOOR: 'תקלת דלת', ELECTRICAL: 'חשמלית',
  MECHANICAL: 'מכנית', SOFTWARE: 'תוכנה', OTHER: 'כללית',
}

// ── Types ──────────────────────────────────────────────────────────────────
interface PendingCall {
  assignment_id: string
  call_id: string
  assignment_status: string
  address: string
  city: string
  fault_type: string
  priority: string
  description: string
  travel_minutes: number | string
  lat: number | null
  lng: number | null
}

interface TechInfo {
  id: string
  name: string
  role: string
}

interface OpenCall {
  call_id: string
  address: string
  city: string
  fault_type: string
  priority: string
  description: string
  primary_tech: string | null
  lat: number | null
  lng: number | null
}

// ── API helpers ────────────────────────────────────────────────────────────
async function fetchMe(): Promise<TechInfo> {
  const { data } = await client.get('/auth/me')
  return data
}

async function fetchPending(techId: string): Promise<PendingCall[]> {
  const { data } = await client.get(`/webhooks/my-calls/${techId}/data`)
  return data
}

async function acceptCall(techId: string, assignmentId: string) {
  await client.post(`/webhooks/my-calls/${techId}/accept/${assignmentId}`)
}

async function rejectCall(techId: string, assignmentId: string) {
  await client.post(`/webhooks/my-calls/${techId}/reject/${assignmentId}`)
}

async function fetchOpenBoard(): Promise<OpenCall[]> {
  const { data } = await client.get('/webhooks/open-calls-board')
  return data
}

async function claimCall(techId: string, callId: string) {
  await client.post(`/webhooks/claim-call-by-tech/${techId}/${callId}`)
}

async function resolveCall(techId: string, callId: string, notes: string) {
  await client.post(`/webhooks/resolve-call/${techId}/${callId}`, { resolution_notes: notes })
}

async function searchElevators(techId: string, q: string) {
  const { data } = await client.get(`/app/tech/${techId}/elevators`, { params: { q } })
  return data as { id: string; address: string; city: string; building_name: string }[]
}

async function reassignElevator(techId: string, elevatorId: string) {
  await client.post(`/webhooks/reassign-elevator-json/${techId}`, null, { params: { elevator_id: elevatorId } })
}

async function sendLocation(techId: string, lat: number, lng: number) {
  await client.post(`/webhooks/location/${techId}`, { latitude: lat, longitude: lng })
}

// ── Login Screen ───────────────────────────────────────────────────────────
function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const setAuth = useAuthStore((s) => s.setAuth)

  const handleLogin = async () => {
    if (!email || !password) return
    setLoading(true)
    try {
      const token = await apiLogin(email, password)
      const { data: me } = await client.get('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      })
      setAuth(token, me.name, me.role)
      onLogin()
    } catch {
      notifications.show({ message: 'שם משתמש או סיסמה שגויים', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#1a73e8', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <Card shadow="xl" radius="lg" p="xl" style={{ width: '100%', maxWidth: 360 }}>
        <Stack gap="md">
          <Title order={2} ta="center">🔧 אקורד מעליות</Title>
          <Text ta="center" c="dimmed" size="sm">כניסה לטכנאים</Text>
          <Divider />
          <input
            type="email"
            placeholder="אימייל"
            value={email}
            onChange={e => setEmail(e.target.value)}
            style={{ padding: '12px', borderRadius: 8, border: '1px solid #ddd', fontSize: 16, direction: 'rtl' }}
          />
          <input
            type="password"
            placeholder="סיסמה"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
            style={{ padding: '12px', borderRadius: 8, border: '1px solid #ddd', fontSize: 16, direction: 'rtl' }}
          />
          <Button size="lg" loading={loading} onClick={handleLogin} fullWidth>
            כניסה
          </Button>
        </Stack>
      </Card>
    </div>
  )
}

// ── GPS Hook ───────────────────────────────────────────────────────────────
function useGPS(techId: string | null) {
  const [status, setStatus] = useState<'idle' | 'active' | 'error'>('idle')
  const watchRef = useRef<number | null>(null)

  const start = () => {
    if (!techId || !navigator.geolocation) {
      setStatus('error')
      return
    }
    watchRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        sendLocation(techId, pos.coords.latitude, pos.coords.longitude).catch(() => {})
        setStatus('active')
      },
      () => setStatus('error'),
      { enableHighAccuracy: true, maximumAge: 30000 }
    )
    setStatus('active')
  }

  const stop = () => {
    if (watchRef.current !== null) {
      navigator.geolocation.clearWatch(watchRef.current)
      watchRef.current = null
    }
    setStatus('idle')
  }

  // Auto-start on mount
  useEffect(() => {
    if (techId) start()
    return () => stop()
  }, [techId])

  return { status, start, stop }
}

// ── Main App ───────────────────────────────────────────────────────────────
function TechMain() {
  const qc = useQueryClient()
  const { userName, clear } = useAuthStore()

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: fetchMe })
  const techId = me?.id ?? null

  const { status: gpsStatus } = useGPS(techId)

  const { data: pending = [], isLoading } = useQuery({
    queryKey: ['pending', techId],
    queryFn: () => fetchPending(techId!),
    enabled: !!techId,
    refetchInterval: 30000,
  })

  const { data: openBoard = [], isLoading: boardLoading } = useQuery({
    queryKey: ['open-board'],
    queryFn: fetchOpenBoard,
    enabled: !!techId,
    refetchInterval: 30000,
  })

  const [resolveOpen, setResolveOpen] = useState(false)
  const [resolveCallId, setResolveCallId] = useState<string | null>(null)
  const [resolveNotes, setResolveNotes] = useState('')
  const [reassignOpen, setReassignOpen] = useState(false)
  const [reassignCallId, setReassignCallId] = useState<string | null>(null)
  const [elevSearch, setElevSearch] = useState('')
  const [elevResults, setElevResults] = useState<{ id: string; address: string; city: string; building_name: string }[]>([])

  const resolveMutation = useMutation({
    mutationFn: ({ callId, notes }: { callId: string; notes: string }) =>
      resolveCall(techId!, callId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      qc.invalidateQueries({ queryKey: ['open-board'] })
      setResolveOpen(false)
      setResolveNotes('')
      notifications.show({ message: '✅ הקריאה סגורה בהצלחה', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בסגירת הקריאה', color: 'red' }),
  })

  const reassignMutation = useMutation({
    mutationFn: ({ elevId }: { elevId: string }) => reassignElevator(techId!, elevId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      setReassignOpen(false)
      setElevSearch('')
      setElevResults([])
      notifications.show({ message: '🏢 הכתובת עודכנה', color: 'teal' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בעדכון כתובת', color: 'red' }),
  })

  const handleElevSearch = async (q: string) => {
    setElevSearch(q)
    if (q.length < 2) { setElevResults([]); return }
    const results = await searchElevators(techId!, q)
    setElevResults(results)
  }

  const claimMutation = useMutation({
    mutationFn: ({ callId }: { callId: string }) => claimCall(techId!, callId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['open-board'] })
      qc.invalidateQueries({ queryKey: ['pending'] })
      notifications.show({ message: '✅ הקריאה שויכה אליך!', color: 'green' })
    },
    onError: (e: any) => {
      notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה במשיכת הקריאה', color: 'red' })
    },
  })

  const acceptMutation = useMutation({
    mutationFn: ({ aid }: { aid: string }) => acceptCall(techId!, aid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      notifications.show({ message: '✅ קריאה התקבלה!', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בקבלת הקריאה', color: 'red' }),
  })

  const rejectMutation = useMutation({
    mutationFn: ({ aid }: { aid: string }) => rejectCall(techId!, aid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      notifications.show({ message: '↩️ קריאה נדחתה', color: 'orange' })
    },
    onError: () => notifications.show({ message: 'שגיאה בדחיית הקריאה', color: 'red' }),
  })

  const gpsLabel = gpsStatus === 'active' ? '🟢 GPS פעיל' : gpsStatus === 'error' ? '🔴 GPS שגיאה' : '⚪ GPS לא פעיל'

  return (
    <div style={{ minHeight: '100vh', background: '#f0f2f5', direction: 'rtl' }}>
      {/* Header */}
      <div style={{ background: '#1a73e8', color: 'white', padding: '14px 16px' }}>
        <Group justify="space-between">
          <div>
            <Text fw={700} size="lg">שלום, {userName} 👋</Text>
            <Text size="xs" opacity={0.85}>{gpsLabel}</Text>
          </div>
          <Button size="xs" variant="white" color="blue" onClick={clear}>יציאה</Button>
        </Group>
      </div>

      <Stack gap="md" p="md">
        {isLoading ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <>
            {/* ── Active / confirmed calls — always at top ── */}
            {pending.filter(c => c.assignment_status !== 'PENDING_CONFIRMATION').map((call) => (
              <Card key={call.assignment_id} withBorder radius="md" p="lg" shadow="md"
                style={{ borderRight: '5px solid #40c057', background: '#f8fff9' }}>
                <Group justify="space-between" mb="sm">
                  <Badge color="green" size="md" variant="filled">✅ קריאה פעילה</Badge>
                  <Badge color={PRIORITY_COLOR[call.priority]} size="md">{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>

                <Text fw={800} size="lg" mb={4}>📍 {call.address}</Text>
                <Text fw={500} size="md" c="dimmed" mb="xs">{call.city}</Text>

                <Stack gap={4} mb="sm">
                  <Text size="sm">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                  {call.description && <Text size="sm" c="dimmed">📝 {call.description}</Text>}
                  {call.travel_minutes && call.travel_minutes !== '?' &&
                    <Text size="sm" c="dimmed">🚗 ~{call.travel_minutes} דקות נסיעה</Text>}
                </Stack>

                {call.lat && call.lng ? (
                  <Stack gap="xs" mt="sm">
                    <Button size="md" color="blue" fullWidth component="a"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${call.lat},${call.lng}`} target="_blank">
                      🗺 נווט — גוגל מפות</Button>
                    <Button size="md" color="teal" fullWidth variant="light" component="a"
                      href={`https://waze.com/ul?ll=${call.lat},${call.lng}&navigate=yes`} target="_blank">
                      🚘 נווט — Waze</Button>
                  </Stack>
                ) : (
                  <Text size="sm" c="orange" mt="sm">⚠️ אין קואורדינטות — חפש כתובת ידנית</Text>
                )}
                <Divider my="sm" />
                <Group gap="xs">
                  <Button flex={1} size="sm" color="orange" variant="light"
                    onClick={() => { setReassignCallId(call.call_id); setReassignOpen(true) }}>
                    🏢 שנה כתובת</Button>
                  <Button flex={1} size="sm" color="red" variant="light"
                    onClick={() => { setResolveCallId(call.call_id); setResolveNotes(''); setResolveOpen(true) }}>
                    ✅ סגור קריאה</Button>
                </Group>
              </Card>
            ))}

            {/* ── Resolve call modal ── */}
            <Modal opened={resolveOpen} onClose={() => setResolveOpen(false)} title="✅ סגירת קריאה" size="md" dir="rtl">
              <Stack gap="sm">
                <Text size="sm" c="dimmed">תאר את הפעולות שבוצעו (אופציונלי)</Text>
                <Textarea
                  placeholder="לדוגמה: הוחלף חיישן הדלת, נבדקה תקינות המנוע..."
                  minRows={4}
                  value={resolveNotes}
                  onChange={e => setResolveNotes(e.target.value)}
                  autoFocus
                />
                <Group justify="flex-end" mt="sm">
                  <Button variant="default" onClick={() => setResolveOpen(false)}>ביטול</Button>
                  <Button
                    color="red"
                    loading={resolveMutation.isPending}
                    onClick={() => resolveCallId && resolveMutation.mutate({ callId: resolveCallId, notes: resolveNotes })}
                  >
                    סגור קריאה
                  </Button>
                </Group>
              </Stack>
            </Modal>

            {/* ── Elevator reassign modal ── */}
            <Modal opened={reassignOpen} onClose={() => setReassignOpen(false)} title="🏢 שיוך מעלית אחרת" size="md" dir="rtl">
              <Stack gap="sm">
                <TextInput
                  placeholder="חפש לפי כתובת / עיר / שם בניין"
                  value={elevSearch}
                  onChange={e => handleElevSearch(e.target.value)}
                  autoFocus
                />
                {elevResults.map(e => (
                  <Card key={e.id} withBorder p="sm" style={{ cursor: 'pointer' }}
                    onClick={() => {
                      if (confirm(`לשייך ל: ${e.address}, ${e.city}?`))
                        reassignMutation.mutate({ elevId: e.id })
                    }}>
                    <Text fw={600}>{e.address}</Text>
                    <Text size="sm" c="dimmed">{e.city} {e.building_name && `— ${e.building_name}`}</Text>
                  </Card>
                ))}
                {elevSearch.length >= 2 && elevResults.length === 0 && (
                  <Text c="dimmed" ta="center" size="sm">לא נמצאו תוצאות</Text>
                )}
              </Stack>
            </Modal>

            {/* ── Pending confirmation calls ── */}
            {pending.filter(c => c.assignment_status === 'PENDING_CONFIRMATION').length > 0 && (
              <Text fw={700} size="lg">📋 ממתינות לאישורך</Text>
            )}
            {pending.filter(c => c.assignment_status === 'PENDING_CONFIRMATION').map((call) => (
              <Card key={call.assignment_id} withBorder radius="md" p="md" shadow="sm">
                <Group justify="space-between" mb="xs">
                  <Text fw={700} size="md">📍 {call.address}, {call.city}</Text>
                  <Badge color={PRIORITY_COLOR[call.priority]}>{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>
                <Text size="sm" c="dimmed">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                {call.description && <Text size="sm" c="dimmed">📝 {call.description}</Text>}
                <Text size="sm" c="dimmed">🚗 ~{call.travel_minutes} דקות נסיעה</Text>
                {call.lat && call.lng && (
                  <Group mt="xs" gap="xs">
                    <Button size="xs" variant="light" color="blue" component="a"
                      href={`https://maps.google.com/?q=${call.lat},${call.lng}`} target="_blank">
                      🗺 גוגל מפות</Button>
                    <Button size="xs" variant="light" color="teal" component="a"
                      href={`https://waze.com/ul?ll=${call.lat},${call.lng}`} target="_blank">
                      🚘 Waze</Button>
                  </Group>
                )}
                <Divider my="sm" />
                <Group gap="sm">
                  <Button flex={1} color="green" size="md"
                    loading={acceptMutation.isPending && acceptMutation.variables?.aid === call.assignment_id}
                    onClick={() => acceptMutation.mutate({ aid: call.assignment_id })}>
                    ✅ קבל</Button>
                  <Button flex={1} color="red" variant="light" size="md"
                    loading={rejectMutation.isPending && rejectMutation.variables?.aid === call.assignment_id}
                    onClick={() => rejectMutation.mutate({ aid: call.assignment_id })}>
                    ❌ דחה</Button>
                </Group>
              </Card>
            ))}

            {pending.length === 0 && (
              <Card withBorder radius="md" p="xl" ta="center">
                <Text size="xl">✅</Text>
                <Text fw={600} mt="sm">אין קריאות פעילות</Text>
                <Text c="dimmed" size="sm">הרשימה מתרעננת כל 30 שניות</Text>
              </Card>
            )}
          </>
        )}

        {/* ── Open calls board ── */}
        <Divider label="📋 לוח קריאות פתוחות" labelPosition="center" mt="md" />
        {boardLoading ? (
          <Center h={80}><Loader size="sm" /></Center>
        ) : openBoard.length === 0 ? (
          <Card withBorder radius="md" p="md" ta="center">
            <Text c="dimmed" size="sm">אין קריאות פתוחות כרגע</Text>
          </Card>
        ) : (
          <>
            <Text size="sm" c="dimmed">כל הקריאות הפתוחות שלא שויכו סופית — לחץ "משוך" כדי לקחת</Text>
            {openBoard.map((call) => (
              <Card key={call.call_id} withBorder radius="md" p="md" shadow="xs"
                style={{ borderRight: `4px solid ${PRIORITY_COLOR[call.priority] === 'red' ? '#fa5252' : PRIORITY_COLOR[call.priority] === 'orange' ? '#fd7e14' : '#228be6'}` }}>
                <Group justify="space-between" mb={4}>
                  <Text fw={700} size="sm">📍 {call.address}, {call.city}</Text>
                  <Badge color={PRIORITY_COLOR[call.priority]} size="sm">{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>
                <Text size="xs" c="dimmed">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                {call.description && <Text size="xs" c="dimmed">📝 {call.description}</Text>}
                {call.primary_tech ? (
                  <Text size="xs" c="blue" mt={4}>🔵 {call.primary_tech} ממתין לאישור</Text>
                ) : (
                  <Text size="xs" c="orange" mt={4}>⚠️ ממתין לשיבוץ</Text>
                )}
                {call.lat && call.lng && (
                  <Group mt="xs" gap="xs">
                    <Button size="xs" variant="subtle" color="blue"
                      component="a" href={`https://maps.google.com/?q=${call.lat},${call.lng}`} target="_blank">
                      🗺 מפות</Button>
                    <Button size="xs" variant="subtle" color="teal"
                      component="a" href={`https://waze.com/ul?ll=${call.lat},${call.lng}`} target="_blank">
                      🚘 Waze</Button>
                  </Group>
                )}
                <Button
                  fullWidth mt="sm" size="sm" color="grape" variant="light"
                  loading={claimMutation.isPending && claimMutation.variables?.callId === call.call_id}
                  onClick={() => claimMutation.mutate({ callId: call.call_id })}
                >
                  🙋 משוך קריאה אלי
                </Button>
              </Card>
            ))}
          </>
        )}
      </Stack>
    </div>
  )
}

// ── Root ───────────────────────────────────────────────────────────────────
export default function TechAppPage() {
  const token = useAuthStore((s) => s.token)
  const [loggedIn, setLoggedIn] = useState(!!token)

  useEffect(() => { setLoggedIn(!!token) }, [token])

  if (!loggedIn) return <LoginScreen onLogin={() => setLoggedIn(true)} />
  return <TechMain />
}
