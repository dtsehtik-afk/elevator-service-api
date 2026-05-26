/**
 * TechAppPage — Mobile technician app
 * Accessible at /tech — no admin shell, optimized for phone
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { Stack, Title, Text, Button, Card, Badge, Group, Divider, Loader, Center, Modal, TextInput, Textarea, Checkbox, Collapse, ActionIcon, Select, Paper, NumberInput } from '@mantine/core'
import { AIRefineButton } from '../components/AIRefineButton'
import { PartRequestsTab } from '../components/PartRequestsTab'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Geolocation } from '@capacitor/geolocation'
import { Capacitor } from '@capacitor/core'
import { BackgroundRunner } from '@capacitor/background-runner'
import { PushNotifications } from '@capacitor/push-notifications'
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
  manufacturer?: string | null
  call_number?: string | null
  created_at?: string | null
  reported_by?: string | null
  inspection_note?: string | null
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
  manufacturer?: string | null
  call_number?: string | null
  created_at?: string | null
  reported_by?: string | null
}

interface MaintenanceItem {
  id: string
  elevator_address: string
  elevator_city: string
  scheduled_date: string
  status: string
  notes: string | null
}

interface ReportDeficiency {
  description: string
  severity: string
  done?: boolean
  done_by?: string
  action_notes?: string
}

interface InspReport {
  id: string
  elevator_address: string
  elevator_id: string | null
  inspection_date: string | null
  inspector_name: string | null
  deficiency_count: number
  deficiencies: ReportDeficiency[] | null
  report_status: 'OPEN' | 'PARTIAL' | 'CLOSED' | 'NA'
  assigned_technician_name: string | null
  deadline_days: number | null
}

interface MapPin {
  type: 'call' | 'inspection' | 'maintenance'
  lat: number
  lng: number
  address: string
  title: string
  detail: string
  color: string
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

async function resolveCall(techId: string, callId: string, notes: string, quoteNeeded: boolean) {
  await client.post(`/webhooks/resolve-call/${techId}/${callId}`, { resolution_notes: notes, quote_needed: quoteNeeded })
}

async function monitorCall(techId: string, callId: string, notes: string) {
  await client.post(`/webhooks/monitor-call/${techId}/${callId}`, { notes })
}

async function transferToTeam(techId: string, callId: string, notes: string) {
  await client.post(`/webhooks/transfer-to-team/${techId}/${callId}`, { notes })
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

async function fetchMaintenance(techId: string): Promise<MaintenanceItem[]> {
  const today = new Date().toISOString().split('T')[0]
  const future = new Date(Date.now() + 30 * 86400000).toISOString().split('T')[0]
  const { data } = await client.get('/maintenance', { params: { technician_id: techId, from: today, to: future, status: 'SCHEDULED', limit: 50 } })
  return data
}

async function fetchMyReports(): Promise<InspReport[]> {
  const { data } = await client.get('/inspections', { params: { limit: 100 } })
  return data
}

async function fetchMapPins(techId: string): Promise<MapPin[]> {
  const { data } = await client.get(`/app/tech/${techId}/map-data`)
  return data.pins ?? []
}

async function toggleDeficiency(reportId: string, idx: number, done: boolean, action_notes?: string) {
  await client.patch(`/inspections/checklist/${reportId}`, [{ index: idx, done, action_notes }])
}

// ── Voice transcription hook ──────────────────────────────────────────────
function useVoice(onResult: (t: string) => void) {
  const [active, setActive] = useState(false)
  const start = useCallback(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (!SR) { notifications.show({ message: 'הדפדפן לא תומך בתמלול קולי', color: 'orange' }); return }
    const r = new SR()
    r.lang = 'he-IL'; r.continuous = false; r.interimResults = false
    r.onstart = () => setActive(true)
    r.onend = () => setActive(false)
    r.onresult = (e: any) => onResult(e.results[0][0].transcript)
    r.onerror = () => setActive(false)
    r.start()
  }, [onResult])
  return { start, active }
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
      const result = await apiLogin(email, password)
      if (result.mfa_required) {
        notifications.show({ message: 'אימות דו-שלבי נדרש — היכנס דרך הדפדפן', color: 'orange' })
        return
      }
      const token = result.access_token
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
  const [lastSentAt, setLastSentAt] = useState<Date | null>(null)
  const watchIdRef = useRef<string | null>(null)
  const cancelledRef = useRef(false)
  const lastSentMsRef = useRef(0)
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stop = () => {
    cancelledRef.current = true
    if (watchIdRef.current !== null) {
      Geolocation.clearWatch({ id: watchIdRef.current }).catch(() => {})
      watchIdRef.current = null
    }
    if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null }
    setStatus('idle')
  }

  const doSend = (tid: string, lat: number, lng: number) => {
    const now = Date.now()
    if (now - lastSentMsRef.current < 30000) return  // throttle: max once per 30s
    lastSentMsRef.current = now
    sendLocation(tid, lat, lng)
      .then(() => { setLastSentAt(new Date()); setStatus('active') })
      .catch(() => {})
  }

  useEffect(() => {
    if (!techId) {
      if (Capacitor.isNativePlatform()) {
        BackgroundRunner.dispatchEvent({
          label: 'com.akord.elevators.location',
          event: 'setTechId',
          details: { techId: '' },
        }).catch(() => {})
      }
      return
    }
    cancelledRef.current = false

    ;(async () => {
      try {
        if (Capacitor.isNativePlatform()) {
          const perm = await Geolocation.requestPermissions()
          if (cancelledRef.current) return
          if (perm.location !== 'granted' && perm.coarseLocation !== 'granted') {
            setStatus('error')
            return
          }
          // Store techId for background WorkManager job and request "always" location
          BackgroundRunner.dispatchEvent({
            label: 'com.akord.elevators.location',
            event: 'setTechId',
            details: { techId },
          }).catch(() => {})
          BackgroundRunner.requestPermissions({ apis: ['geolocation'] }).catch(() => {})
        }

        const id = await Geolocation.watchPosition(
          // maximumAge: 0 — never return a cached GPS position
          { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 },
          (pos, err) => {
            if (err || !pos) { setStatus('error'); return }
            doSend(techId, pos.coords.latitude, pos.coords.longitude)
          }
        )

        if (cancelledRef.current) {
          Geolocation.clearWatch({ id }).catch(() => {})
          return
        }
        watchIdRef.current = id

        // Heartbeat: even if device doesn't move (watchPosition may not fire),
        // force a fresh location every 60s
        heartbeatRef.current = setInterval(() => {
          if (cancelledRef.current) return
          Geolocation.getCurrentPosition({ enableHighAccuracy: true, maximumAge: 0, timeout: 15000 })
            .then(pos => doSend(techId, pos.coords.latitude, pos.coords.longitude))
            .catch(() => {})
        }, 60000)

      } catch {
        if (!cancelledRef.current) setStatus('error')
      }
    })()

    return () => stop()
  }, [techId])

  return { status, lastSentAt }
}


// ── Maintenance Tab ───────────────────────────────────────────────────────
const STATUS_COLOR: Record<string, string> = { SCHEDULED: 'blue', COMPLETED: 'green', OVERDUE: 'red', CANCELLED: 'gray' }
const STATUS_LABEL: Record<string, string> = { SCHEDULED: '📅 מתוכנן', COMPLETED: '✅ הושלם', OVERDUE: '⚠️ באיחור', CANCELLED: 'בוטל' }

function MaintenanceTab({ techId, pendingCalls }: { techId: string; pendingCalls: PendingCall[] }) {
  const { data: items = [], isLoading } = useQuery({ queryKey: ['maint-tech', techId], queryFn: () => fetchMaintenance(techId) })
  if (isLoading) return <Center h={200}><Loader /></Center>
  
  const maintCalls = pendingCalls.filter(c => c.fault_type === 'MAINTENANCE')
  
  if (!items.length && !maintCalls.length) return <Card withBorder p="xl" ta="center"><Text c="dimmed">אין תחזוקה מתוכננת ב-30 הימים הקרובים</Text></Card>
  
  return (
    <Stack gap="sm">
      {maintCalls.map(c => (
        <Card key={c.assignment_id} withBorder radius="md" p="md" style={{ borderRight: '4px solid #1a73e8', background: '#f8f9fa' }}>
          <Group justify="space-between" mb={4}>
            <Badge color="blue">קריאת תחזוקה (פעילה)</Badge>
            {c.created_at && <Text size="xs" c="dimmed">{c.created_at}</Text>}
          </Group>
          <Text fw={700}>📍 {c.address}, {c.city}</Text>
          {c.description && <Text size="sm" c="dimmed" mt={4}>📝 {c.description}</Text>}
        </Card>
      ))}
      
      {items.map(m => (
        <Card key={m.id} withBorder radius="md" p="md">
          <Group justify="space-between" mb={4}>
            <Badge color={STATUS_COLOR[m.status] ?? 'gray'}>{STATUS_LABEL[m.status] ?? m.status}</Badge>
            <Text size="sm" c="dimmed">{new Date(m.scheduled_date).toLocaleDateString('he-IL')}</Text>
          </Group>
          <Text fw={700}>📍 {m.elevator_address}, {m.elevator_city}</Text>
          {m.notes && <Text size="sm" c="dimmed" mt={4}>📝 {m.notes}</Text>}
        </Card>
      ))}
    </Stack>
  )
}

// ── Inspection Reports Tab ────────────────────────────────────────────────
const SEV_COLOR: Record<string, string> = { HIGH: 'red', MEDIUM: 'orange', LOW: 'yellow' }

function ReportsTab() {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<string | null>(null)
  const [defModal, setDefModal] = useState<{ report: InspReport; idx: number; deficiency: ReportDeficiency } | null>(null)
  const [actionNotes, setActionNotes] = useState('')
  const [voiceActive, setVoiceActive] = useState(false)
  const [aiRewriting, setAiRewriting] = useState(false)
  const { data: reports = [], isLoading } = useQuery({ queryKey: ['tech-reports'], queryFn: fetchMyReports })

  const checkMut = useMutation({
    mutationFn: ({ reportId, idx, done, action_notes }: { reportId: string; idx: number; done: boolean; action_notes?: string }) =>
      toggleDeficiency(reportId, idx, done, action_notes),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tech-reports'] }),
    onError: () => notifications.show({ message: 'שגיאה בעדכון', color: 'red' }),
  })

  function onCheck(report: InspReport, idx: number, done: boolean) {
    if (done) {
      setDefModal({ report, idx, deficiency: (report.deficiencies ?? [])[idx] })
      setActionNotes('')
    } else {
      checkMut.mutate({ reportId: report.id, idx, done: false })
    }
  }

  function startVoice() {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (!SR) { notifications.show({ message: 'הדפדפן לא תומך בתמלול קולי', color: 'orange' }); return }
    const r = new SR()
    r.lang = 'he-IL'; r.continuous = false; r.interimResults = false
    r.onstart = () => setVoiceActive(true)
    r.onend = () => setVoiceActive(false)
    r.onresult = (e: any) => setActionNotes(prev => (prev ? prev + ' ' : '') + e.results[0][0].transcript)
    r.onerror = () => setVoiceActive(false)
    r.start()
  }

  async function rewriteNote() {
    if (!actionNotes.trim()) return
    setAiRewriting(true)
    try {
      const { data } = await client.post('/inspections/rewrite-action-note', { text: actionNotes })
      setActionNotes(data.text)
    } catch {
      notifications.show({ message: 'שגיאה בשכתוב', color: 'red' })
    } finally {
      setAiRewriting(false)
    }
  }

  function saveAction() {
    if (!defModal) return
    checkMut.mutate({ reportId: defModal.report.id, idx: defModal.idx, done: true, action_notes: actionNotes.trim() || undefined })
    setDefModal(null)
    setActionNotes('')
  }

  const open = reports.filter(r => r.report_status === 'OPEN' || r.report_status === 'PARTIAL')

  if (isLoading) return <Center h={200}><Loader /></Center>
  if (!open.length) return <Card withBorder p="xl" ta="center"><Text c="dimmed">אין דוחות פתוחים לטיפול</Text></Card>

  return (
    <>
      <Stack gap="sm">
        {open.map(r => (
          <Card key={r.id} withBorder radius="md" p="md" style={{ borderRight: '4px solid #fa5252' }}>
            <Group justify="space-between" mb={4}>
              <Text fw={700} size="sm">📍 {r.elevator_address}</Text>
              <Badge color="red" size="sm">{r.deficiency_count} ליקויים</Badge>
            </Group>
            <Group gap="xs" mb={2}>
              {r.inspection_date && (
                <Text size="xs" c="dimmed">📅 {new Date(r.inspection_date).toLocaleDateString('he-IL')}</Text>
              )}
              {r.inspector_name && <Text size="xs" c="dimmed">👤 {r.inspector_name}</Text>}
            </Group>
            {r.deadline_days != null && (
              <Badge color={r.deadline_days <= 14 ? 'red' : 'orange'} size="xs" mb={4}>
                ⏰ דד-ליין: תוך {r.deadline_days} יום
              </Badge>
            )}
            <Button size="xs" variant="subtle" mt={4}
              onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
              {expanded === r.id ? 'הסתר ▲' : `הצג ליקויים ▼`}
            </Button>
            <Collapse in={expanded === r.id}>
              <Stack gap={6} mt="xs" p="xs" style={{ background: '#fff5f5', borderRadius: 8 }}>
                {(r.deficiencies || []).map((d, i) => (
                  <Checkbox key={i} checked={!!d.done}
                    onChange={e => onCheck(r, i, e.target.checked)}
                    label={
                      <Group gap="xs">
                        <Badge color={SEV_COLOR[d.severity] ?? 'gray'} size="xs">{d.severity}</Badge>
                        <Text size="sm" td={d.done ? 'line-through' : undefined} c={d.done ? 'dimmed' : undefined}>
                          {d.description}
                          {d.done && d.done_by && <Text span size="xs" c="teal"> ({d.done_by}{d.action_notes ? ` — ${d.action_notes}` : ''})</Text>}
                        </Text>
                      </Group>
                    }
                  />
                ))}
              </Stack>
            </Collapse>
          </Card>
        ))}
      </Stack>

      <Modal opened={!!defModal} onClose={() => { setDefModal(null); setActionNotes('') }}
        title="📋 פירוט פעולה שבוצעה" dir="rtl" size="md">
        {defModal && (
          <Stack gap="md">
            <Paper withBorder p="sm" radius="sm" style={{ background: '#fff5f5' }}>
              <Badge color={SEV_COLOR[defModal.deficiency.severity] ?? 'gray'} size="sm" mb={4}>
                {defModal.deficiency.severity}
              </Badge>
              <Text size="sm" fw={600}>{defModal.deficiency.description}</Text>
            </Paper>
            <Textarea
              label="תיאור הפעולה שבוצעה"
              placeholder="תאר מה בוצע לתיקון הליקוי... (ניתן להשתמש בקול)"
              value={actionNotes}
              onChange={e => setActionNotes(e.target.value)}
              minRows={3}
              autosize
            />
            <Group gap="xs">
              <Button size="xs" variant="light" color={voiceActive ? 'red' : 'blue'} onClick={startVoice} loading={voiceActive}>
                🎤 {voiceActive ? 'מקליט...' : 'הקלט קול'}
              </Button>
              <Button size="xs" variant="light" color="violet" onClick={rewriteNote} loading={aiRewriting} disabled={!actionNotes.trim()}>
                ✨ שכתב בעברית מקצועית
              </Button>
            </Group>
            <Text size="xs" c="dimmed">ניתן לדבר בעברית, רוסית, ערבית או אנגלית — הבינה תתרגם ותשכתב לעברית.</Text>
            <Group justify="flex-end" gap="sm">
              <Button variant="subtle" onClick={() => { setDefModal(null); setActionNotes('') }}>ביטול</Button>
              <Button color="teal" onClick={saveAction} loading={checkMut.isPending}>✅ סמן כטופל ושמור</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  )
}

// ── Inventory Tab ─────────────────────────────────────────────────────────
function TechInventoryTab({ techId }: { techId: string }) {
  const [stock, setStock] = useState<{ part_id: string; part_name: string; part_sku?: string; quantity: number; min_quantity: number; is_low_stock: boolean; unit: string; image_url?: string | null }[]>([])
  const [loading, setLoading] = useState(true)
  const [warehouseId, setWarehouseId] = useState<string | null>(null)
  const [usageOpen, setUsageOpen] = useState(false)
  const [usagePart, setUsagePart] = useState<{ id: string; name: string } | null>(null)
  const [usageQty, setUsageQty] = useState(1)
  const [usageNotes, setUsageNotes] = useState('')

  useEffect(() => {
    // Find vehicle warehouse for this technician
    client.get('/inventory/warehouses/list').then(r => {
      const whs: any[] = r.data
      const veh = whs.find((w: any) => w.warehouse_type === 'VEHICLE' && w.technician_id === techId)
      if (veh) {
        setWarehouseId(veh.id)
        client.get(`/inventory/warehouses/${veh.id}/stock`).then(s => {
          setStock(s.data)
        }).finally(() => setLoading(false))
      } else {
        setLoading(false)
      }
    }).catch(() => setLoading(false))
  }, [techId])

  const handleUse = async () => {
    if (!usagePart || !warehouseId) return
    try {
      await client.post('/inventory/stock/issue', {
        part_id: usagePart.id,
        warehouse_id: warehouseId,
        quantity: usageQty,
        notes: usageNotes || undefined,
      })
      notifications.show({ message: `${usagePart.name} × ${usageQty} — נוכה מהמלאי`, color: 'green' })
      setUsageOpen(false)
      setUsageNotes('')
      // Refresh stock
      if (warehouseId) {
        client.get(`/inventory/warehouses/${warehouseId}/stock`).then(s => setStock(s.data)).catch(() => {})
      }
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה בניכוי מלאי', color: 'red' })
    }
  }

  if (loading) return <Center h={200}><Loader /></Center>
  if (!warehouseId) return (
    <Card withBorder p="xl" ta="center">
      <Text c="dimmed">אין מחסן רכב משויך לטכנאי זה</Text>
    </Card>
  )

  return (
    <>
      <Stack gap="sm">
        <Text size="sm" c="dimmed" ta="center">מלאי ברכב שלך — לחץ על חלק לדיווח שימוש</Text>
        {stock.length === 0 && <Card withBorder p="xl" ta="center"><Text c="dimmed">אין חלקים ברכב</Text></Card>}
        {stock.map(s => (
          <Card key={s.part_id} withBorder radius="md" p="sm"
            style={{ cursor: 'pointer', borderRight: s.is_low_stock ? '4px solid #fa5252' : '4px solid #40c057' }}
            onClick={() => { setUsagePart({ id: s.part_id, name: s.part_name }); setUsageQty(1); setUsageOpen(true) }}>
            <Group justify="space-between" wrap="nowrap">
              <Group gap="sm" wrap="nowrap">
                {s.image_url && (
                  <img
                    src={s.image_url}
                    alt={s.part_name}
                    style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }}
                  />
                )}
                <div>
                  <Text fw={600} size="sm">{s.part_name}</Text>
                  {s.part_sku && <Text size="xs" c="dimmed">{s.part_sku}</Text>}
                </div>
              </Group>
              <Badge color={s.is_low_stock ? 'red' : 'green'} size="md">
                {s.quantity} {s.unit}
              </Badge>
            </Group>
            {s.is_low_stock && <Text size="xs" c="red" mt={4}>⚠️ מלאי נמוך — נדרש חידוש</Text>}
          </Card>
        ))}
      </Stack>

      <Modal opened={usageOpen} onClose={() => setUsageOpen(false)}
        title={`ניכוי מלאי — ${usagePart?.name}`} dir="rtl">
        <Stack>
          <NumberInput label="כמות" required value={usageQty} min={1}
            onChange={v => setUsageQty(Number(v) || 1)} />
          <Textarea label="הערות (אופציונלי)" value={usageNotes}
            onChange={e => setUsageNotes(e.target.value)} />
          <Button onClick={handleUse}>אשר ניכוי</Button>
        </Stack>
      </Modal>
    </>
  )
}

// ── Map Tab ───────────────────────────────────────────────────────────────
function MapTab({ techId }: { techId: string }) {
  const { data: pins = [], isLoading } = useQuery({ queryKey: ['map-pins', techId], queryFn: () => fetchMapPins(techId) })
  if (isLoading) return <Center h={200}><Loader /></Center>
  return (
    <Stack gap="sm">
      <MapContainer center={[32.08, 34.78]} zoom={9} style={{ height: 420, borderRadius: 12 }}>
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" />
        {pins.map((p, i) => (
          <CircleMarker key={i} center={[p.lat, p.lng]}
            pathOptions={{ color: p.color, fillColor: p.color, fillOpacity: 0.8 }} radius={10}>
            <Popup>
              <div style={{ direction: 'rtl', minWidth: 160 }}>
                <strong>{p.title}</strong><br />
                <small>📍 {p.address}</small><br />
                <small>{p.detail}</small><br />
                <a href={`https://waze.com/ul?ll=${p.lat},${p.lng}&navigate=yes`} target="_blank" rel="noreferrer">🚘 Waze</a>
              </div>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
      {!pins.length && <Text c="dimmed" ta="center" size="sm">אין פריטים עם קואורדינטות GPS</Text>}
    </Stack>
  )
}

// ── Main App ───────────────────────────────────────────────────────────────
function TechMain() {
  const qc = useQueryClient()
  const { userName, userRole, clear } = useAuthStore()

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: fetchMe })
  const techId = me?.id ?? null

  const { status: gpsStatus, lastSentAt } = useGPS(techId)

  // ── FCM: register push token + handle silent location-request pushes ──────
  useEffect(() => {
    if (!techId || !Capacitor.isNativePlatform()) return

    const setupFCM = async () => {
      try {
        const permission = await PushNotifications.requestPermissions()
        if (permission.receive !== 'granted') return

        await PushNotifications.register()

        // Save FCM token to server whenever it is issued / rotated
        PushNotifications.addListener('registration', async (token) => {
          try {
            await fetch(`${BASE}/webhooks/fcm-token/${techId}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ token: token.value }),
            })
          } catch { /* ignore — server will get the token on next registration */ }
        })

        // Handle push while app is in foreground
        PushNotifications.addListener('pushNotificationReceived', (notification) => {
          if (notification.data?.type === 'location_request') {
            Geolocation.getCurrentPosition({
              enableHighAccuracy: true,
              maximumAge: 0,
              timeout: 15000,
            }).then(pos => {
              sendLocation(techId, pos.coords.latitude, pos.coords.longitude)
            }).catch(() => {})
          }
        })

        // Handle push when app was backgrounded or closed
        PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
          if (action.notification.data?.type === 'location_request') {
            Geolocation.getCurrentPosition({
              enableHighAccuracy: true,
              maximumAge: 0,
              timeout: 15000,
            }).then(pos => {
              sendLocation(techId, pos.coords.latitude, pos.coords.longitude)
            }).catch(() => {})
          }
        })
      } catch { /* FCM not available (web / simulator) — silently skip */ }
    }

    setupFCM()

    return () => {
      PushNotifications.removeAllListeners()
    }
  }, [techId])

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

  const { data: partsForSelect = [] } = useQuery({
    queryKey: ['parts-select'],
    queryFn: () => client.get('/inventory', { params: { limit: 500, is_active: true } }).then(r => r.data as any[]),
  })
  const { data: warehousesForSelect = [] } = useQuery({
    queryKey: ['warehouses-select'],
    queryFn: () => client.get('/inventory/warehouses/list').then(r => r.data as any[]),
  })

  const [activeTab, setActiveTab] = useState<'calls' | 'maint' | 'reports' | 'map' | 'inventory'>('calls')
  const [resolveOpen, setResolveOpen] = useState(false)
  const [resolveCallId, setResolveCallId] = useState<string | null>(null)
  const [resolveNotes, setResolveNotes] = useState('')
  const [resolveQuoteNeeded, setResolveQuoteNeeded] = useState(false)
  const voice = useVoice(t => setResolveNotes(n => n ? n + ' ' + t : t))
  const [monitorOpen, setMonitorOpen] = useState(false)
  const [monitorCallId, setMonitorCallId] = useState<string | null>(null)
  const [monitorNotes, setMonitorNotes] = useState('')
  const [transferOpen, setTransferOpen] = useState(false)
  const [transferCallId, setTransferCallId] = useState<string | null>(null)
  const [transferNotes, setTransferNotes] = useState('')
  const [partReqOpen, setPartReqOpen] = useState(false)
  const [partReqCallId, setPartReqCallId] = useState<string | null>(null)
  const [partReqManufacturer, setPartReqManufacturer] = useState<string | null>(null)
  const [reassignOpen, setReassignOpen] = useState(false)
  const [reassignCallId, setReassignCallId] = useState<string | null>(null)
  const [elevSearch, setElevSearch] = useState('')
  const [elevResults, setElevResults] = useState<{ id: string; address: string; city: string; building_name: string }[]>([])
  const [detailCall, setDetailCall] = useState<PendingCall | OpenCall | null>(null)

  const resolveMutation = useMutation({
    mutationFn: ({ callId, notes, quoteNeeded }: { callId: string; notes: string; quoteNeeded: boolean }) =>
      resolveCall(techId!, callId, notes, quoteNeeded),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      qc.invalidateQueries({ queryKey: ['open-board'] })
      setResolveOpen(false)
      setResolveNotes('')
      setResolveQuoteNeeded(false)
      notifications.show({ message: '✅ הקריאה סגורה בהצלחה', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בסגירת הקריאה', color: 'red' }),
  })

  const monitorMutation = useMutation({
    mutationFn: ({ callId, notes }: { callId: string; notes: string }) =>
      monitorCall(techId!, callId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      qc.invalidateQueries({ queryKey: ['open-board'] })
      setMonitorOpen(false)
      setMonitorNotes('')
      notifications.show({ message: '👁 הקריאה הועברה למעקב', color: 'blue' })
    },
    onError: () => notifications.show({ message: 'שגיאה בהעברה למעקב', color: 'red' }),
  })

  const transferMutation = useMutation({
    mutationFn: ({ callId, notes }: { callId: string; notes: string }) =>
      transferToTeam(techId!, callId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending'] })
      setTransferOpen(false)
      setTransferNotes('')
      notifications.show({ message: '🔧 המשגר קיבל הודעה על בקשת הסיוע', color: 'teal' })
    },
    onError: () => notifications.show({ message: 'שגיאה בבקשת הסיוע', color: 'red' }),
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

  const gpsTimeStr = lastSentAt
    ? lastSentAt.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : null
  const gpsLabel = gpsStatus === 'active'
    ? `🟢 GPS פעיל${gpsTimeStr ? ` — שודר ${gpsTimeStr}` : ''}`
    : gpsStatus === 'error' ? '🔴 GPS שגיאה' : '⚪ GPS לא פעיל'

  return (
    <div style={{ minHeight: '100vh', background: '#f0f2f5', direction: 'rtl' }}>
      {/* Header */}
      <div style={{ background: '#1a73e8', color: 'white', padding: '14px 16px' }}>
        <Group justify="space-between">
          <div>
            <Text fw={700} size="lg">שלום, {userName} 👋</Text>
            <Text size="xs" opacity={0.85}>{gpsLabel}</Text>
          </div>
          <Group gap="xs">
            {userRole && userRole !== 'TECHNICIAN' && (
              <Button size="xs" variant="light" color="gray"
                onClick={() => window.location.href = '/'}>
                🏢 מצב מנהל
              </Button>
            )}
            <Button size="xs" variant="white" color="blue" onClick={clear}>יציאה</Button>
          </Group>
        </Group>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', background: '#fff', borderBottom: '1px solid #e5e7eb', overflowX: 'auto' }}>
        {([['calls','🔧 קריאות'],['maint','🛠 תחזוקה'],['reports','📋 בודק'],['map','🗺 חמ"ל'],['inventory','📦 מלאי']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setActiveTab(id)}
            style={{ flex: 1, padding: '10px 4px', border: 'none', background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: activeTab === id ? 700 : 400, color: activeTab === id ? '#1a73e8' : '#555', borderBottom: activeTab === id ? '3px solid #1a73e8' : '3px solid transparent', whiteSpace: 'nowrap' }}>
            {label}
          </button>
        ))}
      </div>

      <Stack gap="md" p="md">
        {activeTab === 'maint' && techId && <MaintenanceTab techId={techId} pendingCalls={pending} />}
        {activeTab === 'reports' && <ReportsTab />}
        {activeTab === 'map' && techId && <MapTab techId={techId} />}
        {activeTab === 'inventory' && techId && <TechInventoryTab techId={techId} />}

        {activeTab === 'calls' && (isLoading ? <Center h={200}><Loader /></Center> : (
          <>
            {/* ── Active / confirmed calls — always at top ── */}
            {pending.filter(c => c.assignment_status !== 'PENDING_CONFIRMATION' && c.fault_type !== 'MAINTENANCE').map((call) => (
              <Card key={call.assignment_id} withBorder radius="md" p="lg" shadow="md"
                style={{ borderRight: '5px solid #40c057', background: '#f8fff9', cursor: 'pointer' }}
                onClick={() => setDetailCall(call)}>
                <Group justify="space-between" mb="sm">
                  <Group gap="xs">
                    <Badge color="green" size="md" variant="filled">✅ קריאה פעילה</Badge>
                    {call.call_number && <Badge color="gray" size="sm" variant="outline">{call.call_number}</Badge>}
                  </Group>
                  <Badge color={PRIORITY_COLOR[call.priority]} size="md">{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>

                <Text fw={800} size="lg" mb={4}>📍 {call.address}</Text>
                <Text fw={500} size="md" c="dimmed" mb="xs">{call.city}</Text>

                <Stack gap={4} mb="sm">
                  <Text size="sm">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                  {call.description && <Text size="sm" c="dimmed">📝 {call.description}</Text>}
                  {call.created_at && <Text size="xs" c="dimmed">🕐 נפתחה: {call.created_at}</Text>}
                  {call.reported_by && <Text size="xs" c="dimmed">👤 פותח: {call.reported_by}</Text>}
                  {(call as PendingCall).inspection_note && (
                    <Badge color="orange" size="xs" variant="light">⚠️ {(call as PendingCall).inspection_note}</Badge>
                  )}
                  {call.travel_minutes && call.travel_minutes !== '?' &&
                    <Text size="sm" c="dimmed">🚗 ~{call.travel_minutes} דקות נסיעה</Text>}
                </Stack>

                {call.lat && call.lng ? (
                  <Stack gap="xs" mt="sm">
                    <Button size="md" color="blue" fullWidth component="a"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${call.lat},${call.lng}`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🗺 נווט — גוגל מפות</Button>
                    <Button size="md" color="teal" fullWidth variant="light" component="a"
                      href={`https://waze.com/ul?ll=${call.lat},${call.lng}&navigate=yes`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🚘 נווט — Waze</Button>
                  </Stack>
                ) : (
                  <Text size="sm" c="orange" mt="sm">⚠️ אין קואורדינטות — חפש כתובת ידנית</Text>
                )}
                <Divider my="sm" />
                <Group gap="xs">
                  <Button flex={1} size="sm" color="orange" variant="light"
                    onClick={(e) => { e.stopPropagation(); setReassignCallId(call.call_id); setReassignOpen(true) }}>
                    🏢 שנה כתובת</Button>
                  <Button flex={1} size="sm" color="red" variant="light"
                    onClick={(e) => { e.stopPropagation(); setResolveCallId(call.call_id); setResolveNotes(''); setResolveQuoteNeeded(false); setResolveOpen(true) }}>
                    ✅ סגור קריאה</Button>
                </Group>
                <Group gap="xs" mt="xs">
                  <Button flex={1} size="sm" color="blue" variant="light"
                    onClick={(e) => { e.stopPropagation(); setMonitorCallId(call.call_id); setMonitorNotes(''); setMonitorOpen(true) }}>
                    👁 העבר למעקב</Button>
                  <Button flex={1} size="sm" color="grape" variant="light"
                    onClick={(e) => { e.stopPropagation(); setTransferCallId(call.call_id); setTransferNotes(''); setTransferOpen(true) }}>
                    🔧 העבר לצוות טכני</Button>
                </Group>
                <Button fullWidth size="sm" color="yellow" variant="light" mt="xs"
                  onClick={(e) => { e.stopPropagation(); setPartReqCallId(call.call_id); setPartReqManufacturer(call.manufacturer ?? null); setPartReqOpen(true) }}>
                  🔩 החלפת חלק
                </Button>
              </Card>
            ))}

            {/* ── Part replacement modal ── */}
            <Modal opened={partReqOpen} onClose={() => setPartReqOpen(false)} title="🔩 החלפת חלק" size="lg" dir="rtl">
              {partReqCallId && (
                <PartRequestsTab
                  serviceCallId={partReqCallId}
                  parts={partsForSelect.map((p: any) => ({ value: p.id, label: `${p.name}${p.sku ? ` (${p.sku})` : ''}`, category: p.category }))}
                  warehouses={warehousesForSelect.map((w: any) => ({ value: w.id, label: w.name }))}
                  elevatorManufacturer={partReqManufacturer}
                />
              )}
            </Modal>

            {/* ── Resolve call modal ── */}
            <Modal opened={resolveOpen} onClose={() => setResolveOpen(false)} title="✅ סגירת קריאה" size="md" dir="rtl">
              <Stack gap="sm">
                <Group justify="space-between">
                  <Text size="sm" c="dimmed">תאר את הפעולות שבוצעו (אופציונלי)</Text>
                  <Button size="xs" variant={voice.active ? 'filled' : 'subtle'} color={voice.active ? 'red' : 'blue'} onClick={voice.start}>
                    {voice.active ? '🎤 מאזין...' : '🎤 תמלול'}
                  </Button>
                </Group>
                <Textarea
                  placeholder="לדוגמה: הוחלף חיישן הדלת, נבדקה תקינות המנוע..."
                  minRows={4}
                  value={resolveNotes}
                  onChange={e => setResolveNotes(e.target.value)}
                  autoFocus
                  rightSection={<AIRefineButton value={resolveNotes} onChange={setResolveNotes} />}
                  rightSectionPointerEvents="all"
                />
                <Checkbox
                  label="💰 נדרשת הצעת מחיר ללקוח"
                  checked={resolveQuoteNeeded}
                  onChange={e => setResolveQuoteNeeded(e.currentTarget.checked)}
                />
                <Group justify="flex-end" mt="sm">
                  <Button variant="default" onClick={() => setResolveOpen(false)}>ביטול</Button>
                  <Button
                    color="red"
                    loading={resolveMutation.isPending}
                    onClick={() => resolveCallId && resolveMutation.mutate({ callId: resolveCallId, notes: resolveNotes, quoteNeeded: resolveQuoteNeeded })}
                  >
                    סגור קריאה
                  </Button>
                </Group>
              </Stack>
            </Modal>

            {/* ── Monitor call modal ── */}
            <Modal opened={monitorOpen} onClose={() => setMonitorOpen(false)} title="👁 העברה למעקב" size="md" dir="rtl">
              <Stack gap="sm">
                <Text size="sm" c="dimmed">הקריאה תעבור לסטטוס מעקב. העדיפות תרד ל"נמוך" ותסגר אוטומטית לאחר 7 ימים.</Text>
                <Textarea
                  placeholder="הערות (אופציונלי)..."
                  minRows={3}
                  value={monitorNotes}
                  onChange={e => setMonitorNotes(e.target.value)}
                  autoFocus
                />
                <Group justify="flex-end" mt="sm">
                  <Button variant="default" onClick={() => setMonitorOpen(false)}>ביטול</Button>
                  <Button
                    color="blue"
                    loading={monitorMutation.isPending}
                    onClick={() => monitorCallId && monitorMutation.mutate({ callId: monitorCallId, notes: monitorNotes })}
                  >
                    העבר למעקב
                  </Button>
                </Group>
              </Stack>
            </Modal>

            {/* ── Transfer to team modal ── */}
            <Modal opened={transferOpen} onClose={() => setTransferOpen(false)} title="🔧 העברה לצוות טכני" size="md" dir="rtl">
              <Stack gap="sm">
                <Text size="sm" c="dimmed">המשגר יקבל הודעה בווצאפ עם בקשת הסיוע. הקריאה תישאר פעילה.</Text>
                <Textarea
                  placeholder="תאר את הבעיה הטכנית שדורשת סיוע..."
                  minRows={3}
                  value={transferNotes}
                  onChange={e => setTransferNotes(e.target.value)}
                  autoFocus
                />
                <Group justify="flex-end" mt="sm">
                  <Button variant="default" onClick={() => setTransferOpen(false)}>ביטול</Button>
                  <Button
                    color="grape"
                    loading={transferMutation.isPending}
                    onClick={() => transferCallId && transferMutation.mutate({ callId: transferCallId, notes: transferNotes })}
                  >
                    שלח בקשת סיוע
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
            {pending.filter(c => c.assignment_status === 'PENDING_CONFIRMATION' && c.fault_type !== 'MAINTENANCE').length > 0 && (
              <Text fw={700} size="lg">📋 ממתינות לאישורך</Text>
            )}
            {pending.filter(c => c.assignment_status === 'PENDING_CONFIRMATION' && c.fault_type !== 'MAINTENANCE').map((call) => (
              <Card key={call.assignment_id} withBorder radius="md" p="md" shadow="sm"
                style={{ cursor: 'pointer' }}
                onClick={() => setDetailCall(call)}>
                <Group justify="space-between" mb="xs">
                  <Group gap="xs">
                    <Text fw={700} size="md">📍 {call.address}, {call.city}</Text>
                    {call.call_number && <Badge color="gray" size="xs" variant="outline">{call.call_number}</Badge>}
                  </Group>
                  <Badge color={PRIORITY_COLOR[call.priority]}>{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>
                <Text size="sm" c="dimmed">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                {call.description && <Text size="sm" c="dimmed">📝 {call.description}</Text>}
                {call.created_at && <Text size="xs" c="dimmed">🕐 נפתחה: {call.created_at}</Text>}
                {call.reported_by && <Text size="xs" c="dimmed">👤 פותח: {call.reported_by}</Text>}
                {call.inspection_note && (
                  <Badge color="orange" size="xs" variant="light" mt={4}>⚠️ {call.inspection_note}</Badge>
                )}
                <Text size="sm" c="dimmed">🚗 ~{call.travel_minutes} דקות נסיעה</Text>
                {call.lat && call.lng && (
                  <Group mt="xs" gap="xs">
                    <Button size="xs" variant="light" color="blue" component="a"
                      href={`https://maps.google.com/?q=${call.lat},${call.lng}`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🗺 גוגל מפות</Button>
                    <Button size="xs" variant="light" color="teal" component="a"
                      href={`https://waze.com/ul?ll=${call.lat},${call.lng}`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🚘 Waze</Button>
                  </Group>
                )}
                <Divider my="sm" />
                <Group gap="sm">
                  <Button flex={1} color="green" size="md"
                    loading={acceptMutation.isPending && acceptMutation.variables?.aid === call.assignment_id}
                    onClick={(e) => { e.stopPropagation(); acceptMutation.mutate({ aid: call.assignment_id }) }}>
                    ✅ קבל</Button>
                  <Button flex={1} color="red" variant="light" size="md"
                    loading={rejectMutation.isPending && rejectMutation.variables?.aid === call.assignment_id}
                    onClick={(e) => { e.stopPropagation(); rejectMutation.mutate({ aid: call.assignment_id }) }}>
                    ❌ דחה</Button>
                </Group>
              </Card>
            ))}

            {pending.filter(c => c.fault_type !== 'MAINTENANCE').length === 0 && (
              <Card withBorder radius="md" p="xl" ta="center">
                <Text size="xl">✅</Text>
                <Text fw={600} mt="sm">אין קריאות פעילות</Text>
                <Text c="dimmed" size="sm">הרשימה מתרעננת כל 30 שניות</Text>
              </Card>
            )}
          </>
        ))}

        {activeTab === 'calls' && (
          <>
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
                style={{ borderRight: `4px solid ${PRIORITY_COLOR[call.priority] === 'red' ? '#fa5252' : PRIORITY_COLOR[call.priority] === 'orange' ? '#fd7e14' : '#228be6'}`, cursor: 'pointer' }}
                onClick={() => setDetailCall(call)}>
                <Group justify="space-between" mb={4}>
                  <Group gap="xs">
                    <Text fw={700} size="sm">📍 {call.address}, {call.city}</Text>
                    {call.call_number && <Badge color="gray" size="xs" variant="outline">{call.call_number}</Badge>}
                  </Group>
                  <Badge color={PRIORITY_COLOR[call.priority]} size="sm">{PRIORITY_LABEL[call.priority]}</Badge>
                </Group>
                <Text size="xs" c="dimmed">🔧 {FAULT_LABEL[call.fault_type] ?? call.fault_type}</Text>
                {call.description && <Text size="xs" c="dimmed">📝 {call.description}</Text>}
                {call.created_at && <Text size="xs" c="dimmed">🕐 נפתחה: {call.created_at}</Text>}
                {call.reported_by && <Text size="xs" c="dimmed">👤 פותח: {call.reported_by}</Text>}
                {call.primary_tech ? (
                  <Text size="xs" c="blue" mt={4}>🔵 {call.primary_tech} ממתין לאישור</Text>
                ) : (
                  <Text size="xs" c="orange" mt={4}>⚠️ ממתין לשיבוץ</Text>
                )}
                {call.lat && call.lng && (
                  <Group mt="xs" gap="xs">
                    <Button size="xs" variant="subtle" color="blue"
                      component="a" href={`https://maps.google.com/?q=${call.lat},${call.lng}`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🗺 מפות</Button>
                    <Button size="xs" variant="subtle" color="teal"
                      component="a" href={`https://waze.com/ul?ll=${call.lat},${call.lng}`} target="_blank"
                      onClick={(e) => e.stopPropagation()}>
                      🚘 Waze</Button>
                  </Group>
                )}
                <Button
                  fullWidth mt="sm" size="sm" color="grape" variant="light"
                  loading={claimMutation.isPending && claimMutation.variables?.callId === call.call_id}
                  onClick={(e) => { e.stopPropagation(); claimMutation.mutate({ callId: call.call_id }) }}
                >
                  🙋 משוך קריאה אלי
                </Button>
              </Card>
            ))}
          </>
            )}
          </>
        )}
      </Stack>

      {/* ── Call Detail Modal ── */}
      <Modal opened={!!detailCall} onClose={() => setDetailCall(null)} title="📋 פרטי הקריאה" dir="rtl" size="md">
        {detailCall && (
          <Stack gap="md">
            <Group justify="space-between">
              {detailCall.call_number
                ? <Badge color="blue" size="lg" variant="filled">{detailCall.call_number}</Badge>
                : <span />}
              <Badge color={PRIORITY_COLOR[detailCall.priority]} size="lg">{PRIORITY_LABEL[detailCall.priority]}</Badge>
            </Group>
            <Paper withBorder p="sm" radius="sm">
              <Text fw={700} size="lg">📍 {detailCall.address}</Text>
              <Text c="dimmed">{detailCall.city}</Text>
            </Paper>
            <Stack gap={8}>
              <Group gap="xs">
                <Text size="sm" fw={600}>סוג תקלה:</Text>
                <Text size="sm">{FAULT_LABEL[detailCall.fault_type] ?? detailCall.fault_type}</Text>
              </Group>
              {detailCall.description && (
                <Group gap="xs" align="flex-start">
                  <Text size="sm" fw={600}>תיאור:</Text>
                  <Text size="sm" style={{ flex: 1 }}>{detailCall.description}</Text>
                </Group>
              )}
              {detailCall.created_at && (
                <Group gap="xs">
                  <Text size="sm" fw={600}>נפתחה:</Text>
                  <Text size="sm">{detailCall.created_at}</Text>
                </Group>
              )}
              {detailCall.reported_by && (
                <Group gap="xs">
                  <Text size="sm" fw={600}>פותח הקריאה:</Text>
                  <Text size="sm">{detailCall.reported_by}</Text>
                </Group>
              )}
              {(detailCall as PendingCall).inspection_note && (
                <Badge color="orange" variant="light" mt={4}>
                  ⚠️ {(detailCall as PendingCall).inspection_note}
                </Badge>
              )}
            </Stack>
            {detailCall.lat && detailCall.lng && (
              <Group gap="sm">
                <Button flex={1} color="blue" component="a"
                  href={`https://www.google.com/maps/dir/?api=1&destination=${detailCall.lat},${detailCall.lng}`} target="_blank">
                  🗺 גוגל מפות</Button>
                <Button flex={1} color="teal" variant="light" component="a"
                  href={`https://waze.com/ul?ll=${detailCall.lat},${detailCall.lng}&navigate=yes`} target="_blank">
                  🚘 Waze</Button>
              </Group>
            )}
            <Button variant="subtle" onClick={() => setDetailCall(null)}>סגור</Button>
          </Stack>
        )}
      </Modal>
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
