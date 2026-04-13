/**
 * TechAppPage — Mobile technician app
 * Accessible at /tech — no admin shell, optimized for phone
 */
import { useEffect, useRef, useState } from 'react'
import { Stack, Title, Text, Button, Card, Badge, Group, Divider, Loader, Center } from '@mantine/core'
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
        ) : pending.length === 0 ? (
          <Card withBorder radius="md" p="xl" ta="center">
            <Text size="xl">✅</Text>
            <Text fw={600} mt="sm">אין קריאות ממתינות</Text>
            <Text c="dimmed" size="sm">הרשימה מתרעננת כל 30 שניות</Text>
          </Card>
        ) : (
          <>
            <Text fw={700} size="lg">📋 קריאות ממתינות לאישורך ({pending.length})</Text>
            {pending.map((call) => (
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
                    <Button
                      size="xs" variant="light" color="blue"
                      component="a"
                      href={`https://maps.google.com/?q=${call.lat},${call.lng}`}
                      target="_blank"
                    >🗺 גוגל מפות</Button>
                    <Button
                      size="xs" variant="light" color="teal"
                      component="a"
                      href={`https://waze.com/ul?ll=${call.lat},${call.lng}`}
                      target="_blank"
                    >🚘 Waze</Button>
                  </Group>
                )}

                <Divider my="sm" />
                <Group gap="sm">
                  <Button
                    flex={1} color="green" size="md"
                    loading={acceptMutation.isPending && acceptMutation.variables?.aid === call.assignment_id}
                    onClick={() => acceptMutation.mutate({ aid: call.assignment_id })}
                  >✅ קבל</Button>
                  <Button
                    flex={1} color="red" variant="light" size="md"
                    loading={rejectMutation.isPending && rejectMutation.variables?.aid === call.assignment_id}
                    onClick={() => rejectMutation.mutate({ aid: call.assignment_id })}
                  >❌ דחה</Button>
                </Group>
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
