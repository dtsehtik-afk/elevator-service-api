import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Title, Tabs, Group, Badge, Text, Button, Stack, Paper, SimpleGrid,
  Switch, Loader, TextInput, PasswordInput, CopyButton, ActionIcon,
  Tooltip, Alert, Code, Divider,
} from '@mantine/core'
import { DataTable } from 'mantine-datatable'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import dayjs from 'dayjs'
import {
  fetchTenant, fetchModules, updateModules, syncModules,
  deployTenant, destroyServer, fetchSnapshots, pollNow, rotateKey,
  createSubscription, cancelSubscription, provisionSSL, updateTenant,
} from '../api/client'
import { loadStripe } from '@stripe/stripe-js'
import { Elements, CardElement, useStripe, useElements } from '@stripe/react-stripe-js'

const _stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY ?? '')

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: 'green', PENDING: 'gray', DEPLOYING: 'blue',
  SUSPENDED: 'orange', ERROR: 'red', CANCELLED: 'dark',
}

const MODULE_LABELS: Record<string, string> = {
  whatsapp: 'WhatsApp',
  email_calls: 'קריאות מאימייל',
  inspection_emails: 'דוחות ביקורת (מייל)',
  google_drive: 'Google Drive',
  openai_transcription: 'תמלול קולי (OpenAI)',
  maps: 'מפות (Google Maps)',
  whatsapp_reminders: 'תזכורות WhatsApp',
}

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: tenant, isLoading } = useQuery({
    queryKey: ['tenant', id],
    queryFn: () => fetchTenant(id!),
    refetchInterval: (query) =>
      query.state.data?.status === 'DEPLOYING' ? 5000 : false,
  })

  if (isLoading) return <Loader m="xl" />
  if (!tenant) return <Text>דייר לא נמצא</Text>

  return (
    <>
      <Group mb="md" justify="space-between">
        <Group>
          <ActionIcon variant="subtle" onClick={() => navigate('/tenants')}>←</ActionIcon>
          <Title order={3}>{tenant.name}</Title>
          <Badge color={STATUS_COLOR[tenant.status]} variant="light">{tenant.status}</Badge>
          {tenant.status === 'ACTIVE' && (
            <Text>{tenant.is_healthy ? '🟢' : '🔴'}</Text>
          )}
        </Group>
        <Text size="sm" c="dimmed" dir="ltr">{tenant.slug}.lift-agent.com</Text>
      </Group>

      <Tabs defaultValue="overview">
        <Tabs.List mb="md">
          <Tabs.Tab value="overview">📋 סקירה</Tabs.Tab>
          <Tabs.Tab value="modules">🔧 מודולים</Tabs.Tab>
          <Tabs.Tab value="deploy">🚀 פריסה</Tabs.Tab>
          <Tabs.Tab value="billing">💳 חיוב</Tabs.Tab>
          <Tabs.Tab value="monitoring">📊 ניטור</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview">
          <OverviewTab tenant={tenant} qc={qc} />
        </Tabs.Panel>
        <Tabs.Panel value="modules">
          <ModulesTab tenantId={id!} />
        </Tabs.Panel>
        <Tabs.Panel value="deploy">
          <DeployTab tenant={tenant} qc={qc} />
        </Tabs.Panel>
        <Tabs.Panel value="billing">
          <Elements stripe={_stripePromise}>
            <BillingTab tenant={tenant} qc={qc} />
          </Elements>
        </Tabs.Panel>
        <Tabs.Panel value="monitoring">
          <MonitoringTab tenantId={id!} />
        </Tabs.Panel>
      </Tabs>
    </>
  )
}

// ── Overview ──────────────────────────────────────────────────────────────────

function OverviewTab({ tenant, qc }: { tenant: any; qc: any }) {
  const [editingUrl, setEditingUrl] = useState(false)
  const [apiUrlDraft, setApiUrlDraft] = useState(tenant.api_url ?? '')

  const rotateMutation = useMutation({
    mutationFn: () => rotateKey(tenant.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      notifications.show({ message: 'מפתח API חודש', color: 'green' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: (body: Partial<any>) => updateTenant(tenant.id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      setEditingUrl(false)
      notifications.show({ message: 'עודכן', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const stats = tenant.last_stats as Record<string, any> | null

  return (
    <Stack>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        <StatCard label="מעליות" value={stats?.elevators_total ?? '—'} />
        <StatCard label="קריאות פתוחות" value={stats?.calls_open ?? '—'} color="orange" />
        <StatCard label="טכנאים פעילים" value={stats?.technicians_active ?? '—'} />
        <StatCard label="Uptime" value={stats ? formatUptime(stats.uptime_seconds) : '—'} color="green" />
      </SimpleGrid>

      <Paper withBorder p="md" radius="md">
        <Stack gap="xs">
          <Text fw={600}>פרטי חיבור</Text>
          <Group>
            <Text size="sm" c="dimmed" w={140}>API URL</Text>
            {editingUrl ? (
              <Group gap={4} style={{ flex: 1 }}>
                <TextInput
                  value={apiUrlDraft}
                  onChange={(e) => setApiUrlDraft(e.target.value)}
                  size="xs"
                  dir="ltr"
                  style={{ flex: 1 }}
                  placeholder="https://example.lift-agent.com"
                />
                <ActionIcon size="sm" color="green" variant="subtle" onClick={() => updateMutation.mutate({ api_url: apiUrlDraft })} loading={updateMutation.isPending}>✓</ActionIcon>
                <ActionIcon size="sm" variant="subtle" onClick={() => setEditingUrl(false)}>✕</ActionIcon>
              </Group>
            ) : (
              <Group gap={4}>
                <Code>{tenant.api_url ?? '—'}</Code>
                <Tooltip label="ערוך">
                  <ActionIcon size="sm" variant="subtle" onClick={() => { setApiUrlDraft(tenant.api_url ?? ''); setEditingUrl(true) }}>✏️</ActionIcon>
                </Tooltip>
              </Group>
            )}
          </Group>
          <Group>
            <Text size="sm" c="dimmed" w={140}>API Key</Text>
            <Code style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }} dir="ltr">
              {tenant.api_key}
            </Code>
            <CopyButton value={tenant.api_key}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? 'הועתק!' : 'העתק'}>
                  <ActionIcon variant="subtle" onClick={copy}>{copied ? '✓' : '📋'}</ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
            <Tooltip label="חדש מפתח">
              <ActionIcon variant="subtle" color="orange" onClick={() => rotateMutation.mutate()} loading={rotateMutation.isPending}>🔄</ActionIcon>
            </Tooltip>
          </Group>
          <Group>
            <Text size="sm" c="dimmed" w={140}>Hetzner Server</Text>
            <Text size="sm" dir="ltr">{tenant.hetzner_server_ip ?? '—'} {tenant.hetzner_server_id ? `(#${tenant.hetzner_server_id})` : ''}</Text>
          </Group>
          <Group>
            <Text size="sm" c="dimmed" w={140}>תכנית</Text>
            <Badge variant="dot">{tenant.plan}</Badge>
            <Badge color={tenant.billing_active ? 'green' : 'gray'} variant="light">
              {tenant.billing_active ? '✓ תשלום פעיל' : 'ללא תשלום'}
            </Badge>
          </Group>
          <Group>
            <Text size="sm" c="dimmed" w={140}>נוצר</Text>
            <Text size="sm">{dayjs(tenant.created_at).format('DD/MM/YYYY')}</Text>
          </Group>
          {tenant.notes && (
            <Group align="flex-start">
              <Text size="sm" c="dimmed" w={140}>הערות</Text>
              <Text size="sm">{tenant.notes}</Text>
            </Group>
          )}
        </Stack>
      </Paper>
    </Stack>
  )
}

function StatCard({ label, value, color = 'blue' }: { label: string; value: any; color?: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text size="xs" c="dimmed" mb={4}>{label}</Text>
      <Text size="xl" fw={700} c={color}>{value}</Text>
    </Paper>
  )
}

function formatUptime(seconds: number): string {
  if (!seconds) return '0s'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 48) return `${Math.floor(h / 24)}d`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

// ── Modules ───────────────────────────────────────────────────────────────────

function ModulesTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['modules', tenantId],
    queryFn: () => fetchModules(tenantId),
  })

  const updateMutation = useMutation({
    mutationFn: (modules: Record<string, boolean>) => updateModules(tenantId, modules),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modules', tenantId] })
      qc.invalidateQueries({ queryKey: ['tenant', tenantId] })
      notifications.show({ message: 'מודולים עודכנו', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const syncMutation = useMutation({
    mutationFn: () => syncModules(tenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['modules', tenantId] })
      notifications.show({ message: 'סונכרן מהשרת', color: 'blue' })
    },
  })

  if (isLoading) return <Loader m="xl" />

  const modules = data?.modules ?? {}

  const toggle = (key: string, val: boolean) => {
    updateMutation.mutate({ [key]: val })
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Text fw={600}>מודולים פעילים</Text>
        <Button variant="subtle" size="xs" onClick={() => syncMutation.mutate()} loading={syncMutation.isPending}>
          🔄 סנכרן מהשרת
        </Button>
      </Group>
      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          {Object.entries(MODULE_LABELS).map(([key, label]) => (
            <Group key={key} justify="space-between">
              <Text size="sm">{label}</Text>
              <Switch
                checked={modules[key] ?? false}
                onChange={(e) => toggle(key, e.currentTarget.checked)}
                disabled={updateMutation.isPending}
              />
            </Group>
          ))}
        </Stack>
      </Paper>
    </Stack>
  )
}

// ── Deploy ────────────────────────────────────────────────────────────────────

function DeployTab({ tenant, qc }: { tenant: any; qc: any }) {
  const [form, setForm] = useState({
    db_password: '', secret_key: '', gemini_api_key: '',
    gmail_user_calls: '', gmail_app_password_calls: '',
    greenapi_instance_id: '', greenapi_api_token: '', google_maps_api_key: '',
  })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const deployMutation = useMutation({
    mutationFn: () => deployTenant(tenant.id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      notifications.show({ message: 'פריסה התחילה — בדוק סטטוס בעוד כמה דקות', color: 'blue' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const destroyMutation = useMutation({
    mutationFn: () => destroyServer(tenant.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      notifications.show({ message: 'שרת נמחק', color: 'orange' })
    },
  })

  const confirmDestroy = () =>
    modals.openConfirmModal({
      title: 'מחיקת שרת Hetzner',
      children: <Text size="sm">האם אתה בטוח? כל הנתונים על השרת יימחקו.</Text>,
      labels: { confirm: 'מחק שרת', cancel: 'ביטול' },
      confirmProps: { color: 'red' },
      onConfirm: () => destroyMutation.mutate(),
    })

  const isDeployed = !!tenant.hetzner_server_id
  const isDeploying = tenant.status === 'DEPLOYING'

  return (
    <Stack>
      {isDeploying && (
        <Alert color="blue" title="פריסה בתהליך">
          <Group>
            <Loader size="xs" />
            <Text size="sm">השרת נוצר על Hetzner... עדכון אוטומטי כל 5 שניות</Text>
          </Group>
        </Alert>
      )}

      {isDeployed && (
        <Alert color="green" title="שרת פעיל">
          <Text size="sm" dir="ltr">IP: {tenant.hetzner_server_ip} | Server ID: #{tenant.hetzner_server_id}</Text>
          <Text size="sm" dir="ltr">URL: {tenant.api_url}</Text>
        </Alert>
      )}

      {!isDeployed && !isDeploying && (
        <Paper withBorder p="md" radius="md">
          <Text fw={600} mb="md">1-Click Deploy — Hetzner Cloud</Text>
          <SimpleGrid cols={2}>
            <PasswordInput label="DB Password" required value={form.db_password} onChange={set('db_password')} dir="ltr" />
            <PasswordInput label="Secret Key (JWT)" required value={form.secret_key} onChange={set('secret_key')} dir="ltr" />
            <TextInput label="Gemini API Key" value={form.gemini_api_key} onChange={set('gemini_api_key')} dir="ltr" />
            <TextInput label="Gmail (קריאות)" value={form.gmail_user_calls} onChange={set('gmail_user_calls')} dir="ltr" />
            <PasswordInput label="Gmail App Password" value={form.gmail_app_password_calls} onChange={set('gmail_app_password_calls')} dir="ltr" />
            <TextInput label="Green API Instance" value={form.greenapi_instance_id} onChange={set('greenapi_instance_id')} dir="ltr" />
            <PasswordInput label="Green API Token" value={form.greenapi_api_token} onChange={set('greenapi_api_token')} dir="ltr" />
            <TextInput label="Google Maps API Key" value={form.google_maps_api_key} onChange={set('google_maps_api_key')} dir="ltr" />
          </SimpleGrid>
          <Button
            mt="md"
            onClick={() => deployMutation.mutate()}
            loading={deployMutation.isPending}
            disabled={!form.db_password || !form.secret_key}
            fullWidth
          >
            🚀 Deploy to Hetzner
          </Button>
        </Paper>
      )}

      {isDeployed && (
        <>
          <Divider label="פעולות" labelPosition="left" />
          <SslButton tenantId={tenant.id} />
          <Divider label="פעולות מסוכנות" labelPosition="left" />
          <Button color="red" variant="outline" onClick={confirmDestroy} loading={destroyMutation.isPending}>
            🗑️ מחק שרת Hetzner
          </Button>
        </>
      )}
    </Stack>
  )
}

function SslButton({ tenantId }: { tenantId: string }) {
  const sslMutation = useMutation({
    mutationFn: () => provisionSSL(tenantId),
    onSuccess: () => notifications.show({ message: 'SSL בתהליך הפקה — ~30 שניות', color: 'teal' }),
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })
  return (
    <Button variant="outline" color="teal" onClick={() => sslMutation.mutate()} loading={sslMutation.isPending}>
      🔒 הפק SSL (Let's Encrypt)
    </Button>
  )
}

// ── Billing ───────────────────────────────────────────────────────────────────

const PLAN_FEATURES: Record<string, string[]> = {
  BASIC:      ['עד 100 מעליות', 'קריאות מאימייל', 'עד 3 טכנאים'],
  PRO:        ['עד 500 מעליות', 'WhatsApp + מייל', 'טכנאים ללא הגבלה', 'Google Drive'],
  ENTERPRISE: ['מעליות ללא הגבלה', 'כל המודולים', 'SLA 99.9%', 'תמיכה ייעודית'],
}

function BillingTab({ tenant, qc }: { tenant: any; qc: any }) {
  const stripe = useStripe()
  const elements = useElements()
  const [selectedPlan, setSelectedPlan] = useState<string>(tenant.plan === 'TRIAL' ? 'BASIC' : tenant.plan)
  const [loading, setLoading] = useState(false)

  const cancelMutation = useMutation({
    mutationFn: () => cancelSubscription(tenant.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      notifications.show({ message: 'מנוי בוטל — יופסק בסוף תקופת החיוב', color: 'orange' })
    },
  })

  const handleSubscribe = async () => {
    if (!stripe || !elements) return
    setLoading(true)
    try {
      const card = elements.getElement(CardElement)
      if (!card) throw new Error('No card element')
      const { error, paymentMethod } = await stripe.createPaymentMethod({ type: 'card', card })
      if (error) throw new Error(error.message)
      await createSubscription(tenant.id, selectedPlan, paymentMethod!.id)
      qc.invalidateQueries({ queryKey: ['tenant', tenant.id] })
      notifications.show({ message: `מנוי ${selectedPlan} הופעל בהצלחה`, color: 'green' })
    } catch (e: any) {
      notifications.show({ message: e.message ?? 'שגיאה בתשלום', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack>
      {/* Current status */}
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between">
          <Stack gap={2}>
            <Text fw={600}>מצב מנוי נוכחי</Text>
            <Group>
              <Badge variant="dot" size="lg">{tenant.plan}</Badge>
              <Badge color={tenant.billing_active ? 'green' : 'gray'} variant="light">
                {tenant.billing_active ? '✓ פעיל' : 'לא פעיל'}
              </Badge>
            </Group>
          </Stack>
          {tenant.billing_active && (
            <Button
              size="xs" color="red" variant="subtle"
              onClick={() => cancelMutation.mutate()}
              loading={cancelMutation.isPending}
            >
              ביטול מנוי
            </Button>
          )}
        </Group>
      </Paper>

      {/* Plan picker */}
      <Text fw={600}>בחר תכנית</Text>
      <SimpleGrid cols={3}>
        {(['BASIC', 'PRO', 'ENTERPRISE'] as const).map((plan) => (
          <Paper
            key={plan}
            withBorder p="md" radius="md"
            style={{
              cursor: 'pointer',
              borderColor: selectedPlan === plan ? 'var(--mantine-color-blue-5)' : undefined,
              borderWidth: selectedPlan === plan ? 2 : 1,
            }}
            onClick={() => setSelectedPlan(plan)}
          >
            <Text fw={700} mb={4}>{plan}</Text>
            <Stack gap={2}>
              {PLAN_FEATURES[plan].map((f) => (
                <Text key={f} size="xs" c="dimmed">✓ {f}</Text>
              ))}
            </Stack>
          </Paper>
        ))}
      </SimpleGrid>

      {/* Card input */}
      <Paper withBorder p="md" radius="md">
        <Text size="sm" fw={600} mb="sm">פרטי כרטיס אשראי</Text>
        <div style={{ padding: '10px', border: '1px solid #dee2e6', borderRadius: 6 }}>
          <CardElement options={{ style: { base: { fontSize: '16px' } } }} />
        </div>
        <Button
          mt="md" fullWidth
          onClick={handleSubscribe}
          loading={loading}
          disabled={!stripe}
        >
          💳 הפעל מנוי {selectedPlan}
        </Button>
      </Paper>
    </Stack>
  )
}

// ── Monitoring ────────────────────────────────────────────────────────────────

function MonitoringTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient()
  const { data: snapshots = [], isLoading } = useQuery({
    queryKey: ['snapshots', tenantId],
    queryFn: () => fetchSnapshots(tenantId),
    refetchInterval: 60_000,
  })

  const pollMutation = useMutation({
    mutationFn: () => pollNow(tenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['snapshots', tenantId] })
      qc.invalidateQueries({ queryKey: ['tenant', tenantId] })
      notifications.show({ message: 'Poll בוצע', color: 'blue' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  return (
    <Stack>
      <Group justify="space-between">
        <Text fw={600}>היסטוריית בריאות (48 polls אחרונים)</Text>
        <Button variant="subtle" size="xs" onClick={() => pollMutation.mutate()} loading={pollMutation.isPending}>
          📡 Poll עכשיו
        </Button>
      </Group>

      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        <DataTable
          records={snapshots}
          fetching={isLoading}
          minHeight={150}
          columns={[
            {
              accessor: 'captured_at', title: 'זמן',
              render: (s) => <Text size="sm" dir="ltr">{dayjs(s.captured_at).format('DD/MM HH:mm:ss')}</Text>,
            },
            {
              accessor: 'is_healthy', title: 'סטטוס',
              render: (s) => <Text>{s.is_healthy ? '🟢 תקין' : '🔴 לא תקין'}</Text>,
            },
            {
              accessor: 'stats', title: 'קריאות פתוחות',
              render: (s) => <Text size="sm">{(s.stats as any)?.calls_open ?? '—'}</Text>,
            },
            {
              accessor: 'stats2', title: 'מעליות',
              render: (s) => <Text size="sm">{(s.stats as any)?.elevators_total ?? '—'}</Text>,
            },
            {
              accessor: 'error', title: 'שגיאה',
              render: (s) => s.error ? <Text size="xs" c="red">{s.error}</Text> : null,
            },
          ]}
        />
      </Paper>
    </Stack>
  )
}
