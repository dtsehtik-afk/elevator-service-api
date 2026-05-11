import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Title, Tabs, Group, Badge, Text, Button, Stack, Paper, SimpleGrid,
  Switch, Loader, TextInput, PasswordInput, CopyButton, ActionIcon,
  Tooltip, Alert, Code, Divider, Modal, ScrollArea, Select, Table, Box, Center,
} from '@mantine/core'
import { DataTable } from 'mantine-datatable'
import { notifications } from '@mantine/notifications'
import { modals } from '@mantine/modals'
import dayjs from 'dayjs'
import {
  fetchTenant, fetchModules, updateModules, syncModules,
  deployTenant, destroyServer, fetchSnapshots, pollNow, rotateKey,
  createSubscription, cancelSubscription, provisionSSL, updateTenant,
  fetchConsole, clearConsoleLogs, type ConsoleLog,
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
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')

  const { data: tenant, isLoading } = useQuery({
    queryKey: ['tenant', id],
    queryFn: () => fetchTenant(id!),
    refetchInterval: (query) =>
      query.state.data?.status === 'DEPLOYING' ? 5000 : false,
  })

  const renameMutation = useMutation({
    mutationFn: (name: string) => updateTenant(id!, { name }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenant', id] })
      qc.invalidateQueries({ queryKey: ['tenants'] })
      setEditingName(false)
      notifications.show({ message: 'שם עודכן', color: 'green' })
    },
  })

  if (isLoading) return <Loader m="xl" />
  if (!tenant) return <Text>דייר לא נמצא</Text>

  return (
    <>
      <Group mb="md" justify="space-between">
        <Group>
          <ActionIcon variant="subtle" onClick={() => navigate('/tenants')}>←</ActionIcon>
          {editingName ? (
            <Group gap={4}>
              <TextInput value={nameDraft} onChange={(e) => setNameDraft(e.target.value)} size="sm" style={{ width: 180 }} />
              <ActionIcon color="green" variant="subtle" onClick={() => renameMutation.mutate(nameDraft)} loading={renameMutation.isPending}>✓</ActionIcon>
              <ActionIcon variant="subtle" onClick={() => setEditingName(false)}>✕</ActionIcon>
            </Group>
          ) : (
            <Group gap={4}>
              <Title order={3}>{tenant.name}</Title>
              <Tooltip label="שנה שם">
                <ActionIcon size="sm" variant="subtle" onClick={() => { setNameDraft(tenant.name); setEditingName(true) }}>✏️</ActionIcon>
              </Tooltip>
            </Group>
          )}
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
  const [envModalOpen, setEnvModalOpen] = useState(false)
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
  const slug = tenant.slug

  const generateEnvContent = () => {
    const domain = `${slug}.lift-agent.com`
    const lines = [
      `DATABASE_URL=postgresql://user:${form.db_password || 'PASSWORD'}@db:5432/elevator_db`,
      `SECRET_KEY=${form.secret_key || 'SECRET_KEY'}`,
      `WEBHOOK_SECRET=${form.secret_key || 'WEBHOOK_SECRET'}`,
      form.gemini_api_key ? `GEMINI_API_KEY=${form.gemini_api_key}` : '',
      form.gmail_user_calls ? `GMAIL_USER_CALLS=${form.gmail_user_calls}` : '',
      form.gmail_app_password_calls ? `GMAIL_APP_PASSWORD_CALLS=${form.gmail_app_password_calls}` : '',
      form.greenapi_instance_id ? `GREENAPI_INSTANCE_ID=${form.greenapi_instance_id}` : '',
      form.greenapi_api_token ? `GREENAPI_API_TOKEN=${form.greenapi_api_token}` : '',
      form.google_maps_api_key ? `GOOGLE_MAPS_API_KEY=${form.google_maps_api_key}` : '',
      `APP_BASE_URL=https://${domain}`,
      `CORS_ORIGINS=https://${domain}`,
    ].filter(Boolean).join('\n')
    return lines
  }

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

      <Paper withBorder p="md" radius="md">
        <Text fw={600} mb="md">{isDeployed ? '⚙️ הגדרות שרת' : '1-Click Deploy — Hetzner Cloud'}</Text>
        <SimpleGrid cols={2}>
          <PasswordInput label="DB Password" required={!isDeployed} value={form.db_password} onChange={set('db_password')} dir="ltr" />
          <PasswordInput label="Secret Key (JWT)" required={!isDeployed} value={form.secret_key} onChange={set('secret_key')} dir="ltr" />
          <TextInput label="Gemini API Key" value={form.gemini_api_key} onChange={set('gemini_api_key')} dir="ltr" />
          <TextInput label="Gmail (קריאות)" value={form.gmail_user_calls} onChange={set('gmail_user_calls')} dir="ltr" />
          <PasswordInput label="Gmail App Password" value={form.gmail_app_password_calls} onChange={set('gmail_app_password_calls')} dir="ltr" />
          <TextInput label="Green API Instance" value={form.greenapi_instance_id} onChange={set('greenapi_instance_id')} dir="ltr" />
          <PasswordInput label="Green API Token" value={form.greenapi_api_token} onChange={set('greenapi_api_token')} dir="ltr" />
          <TextInput label="Google Maps API Key" value={form.google_maps_api_key} onChange={set('google_maps_api_key')} dir="ltr" />
        </SimpleGrid>

        {!isDeployed && !isDeploying && (
          <Button
            mt="md"
            onClick={() => deployMutation.mutate()}
            loading={deployMutation.isPending}
            disabled={!form.db_password || !form.secret_key}
            fullWidth
          >
            🚀 Deploy to Hetzner
          </Button>
        )}

        {isDeployed && (
          <Button mt="md" variant="light" color="blue" onClick={() => setEnvModalOpen(true)} fullWidth>
            📋 הצג .env לעדכון ידני בשרת
          </Button>
        )}
      </Paper>

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

      <Modal
        opened={envModalOpen}
        onClose={() => setEnvModalOpen(false)}
        title="תוכן .env לעדכון ידני"
        size="lg"
        dir="ltr"
      >
        <Stack>
          <Text size="sm" c="dimmed" dir="rtl">העתק את התוכן הבא ל-/opt/liftapp/.env בשרת, ואז הרץ: docker compose restart app</Text>
          <ScrollArea h={300}>
            <Code block dir="ltr" style={{ whiteSpace: 'pre', fontSize: 12 }}>
              {generateEnvContent()}
            </Code>
          </ScrollArea>
          <CopyButton value={generateEnvContent()}>
            {({ copied, copy }) => (
              <Button onClick={copy} color={copied ? 'green' : 'blue'} fullWidth>
                {copied ? '✓ הועתק!' : '📋 העתק הכל'}
              </Button>
            )}
          </CopyButton>
        </Stack>
      </Modal>
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

const LOG_LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'gray', INFO: 'blue', WARNING: 'yellow', ERROR: 'red', CRITICAL: 'dark',
}

function StackTraceModal({ log, opened, onClose }: { log: ConsoleLog | null; opened: boolean; onClose: () => void }) {
  if (!log) return null
  return (
    <Modal opened={opened} onClose={onClose} title={`${log.level} — ${log.source ?? ''}`} size="xl" dir="ltr">
      <Stack gap="sm">
        <Text size="sm" fw={600}>{log.message}</Text>
        <Text size="xs" c="dimmed">{dayjs(log.created_at).format('DD/MM/YYYY HH:mm:ss')}</Text>
        {log.stack_trace && (
          <Box>
            <Group justify="space-between" mb={4}>
              <Text size="xs" fw={600} c="dimmed">Stack Trace</Text>
              <CopyButton value={log.stack_trace}>
                {({ copied, copy }) => (
                  <Button size="xs" variant="subtle" onClick={copy}>{copied ? 'הועתק' : 'העתק'}</Button>
                )}
              </CopyButton>
            </Group>
            <ScrollArea h={400}>
              <Code block style={{ fontSize: 11, whiteSpace: 'pre-wrap', direction: 'ltr' }}>
                {log.stack_trace}
              </Code>
            </ScrollArea>
          </Box>
        )}
      </Stack>
    </Modal>
  )
}

function MonitoringTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient()
  const [levelFilter, setLevelFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [selectedLog, setSelectedLog] = useState<ConsoleLog | null>(null)
  const [stackOpen, setStackOpen] = useState(false)
  const [showHistory, setShowHistory] = useState(false)

  const { data: console_, isLoading: consoleLoading, error: consoleError, refetch: refetchConsole } = useQuery({
    queryKey: ['console', tenantId, levelFilter, search],
    queryFn: () => fetchConsole(tenantId, { level: levelFilter ?? undefined, search: search || undefined, limit: 300 }),
    refetchInterval: 30_000,
    retry: false,
  })

  const { data: snapshots = [], isLoading: snapshotsLoading } = useQuery({
    queryKey: ['snapshots', tenantId],
    queryFn: () => fetchSnapshots(tenantId),
    refetchInterval: 60_000,
    enabled: showHistory,
  })

  const clearMutation = useMutation({
    mutationFn: (level?: string) => clearConsoleLogs(tenantId, level),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['console', tenantId] })
      notifications.show({ message: `נמחקו ${data.deleted} לוגים`, color: 'orange' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const pollMutation = useMutation({
    mutationFn: () => pollNow(tenantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['snapshots', tenantId] })
      qc.invalidateQueries({ queryKey: ['tenant', tenantId] })
      refetchConsole()
      notifications.show({ message: 'Poll בוצע', color: 'blue' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const h = console_?.health

  return (
    <Stack>
      {/* Health summary */}
      {h && (
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <Paper withBorder p="sm" radius="md">
            <Text size="xs" c="dimmed" mb={2}>DB</Text>
            <Badge color={h.db_ok ? 'green' : 'red'} variant="filled">{h.db_ok ? '✅ תקין' : '❌ ניתוק'}</Badge>
          </Paper>
          <Paper withBorder p="sm" radius="md">
            <Text size="xs" c="dimmed" mb={2}>Uptime</Text>
            <Text fw={600} size="sm">{formatUptime(h.uptime_seconds)}</Text>
          </Paper>
          <Paper withBorder p="sm" radius="md">
            <Text size="xs" c="dimmed" mb={2}>Python</Text>
            <Text fw={600} size="sm" dir="ltr">{h.python_version}</Text>
          </Paper>
          <Paper withBorder p="sm" radius="md">
            <Text size="xs" c="dimmed" mb={2}>זמן שרת</Text>
            <Text fw={600} size="xs" dir="ltr">{dayjs(h.server_time).format('HH:mm:ss')}</Text>
          </Paper>
        </SimpleGrid>
      )}

      {/* Log level counters */}
      {console_?.counts && (
        <Group gap="xs">
          {Object.entries(console_.counts).map(([lvl, cnt]) => (
            <Paper
              key={lvl}
              p="xs"
              radius="md"
              withBorder
              style={{
                cursor: 'pointer',
                borderColor: levelFilter === lvl ? 'var(--mantine-color-blue-5)' : (lvl === 'ERROR' || lvl === 'CRITICAL' ? 'var(--mantine-color-red-4)' : undefined),
                borderWidth: levelFilter === lvl ? 2 : 1,
              }}
              onClick={() => setLevelFilter(levelFilter === lvl ? null : lvl)}
            >
              <Group gap={6}>
                <Badge color={LOG_LEVEL_COLORS[lvl] ?? 'gray'} size="xs">{lvl}</Badge>
                <Text size="sm" fw={700}>{cnt}</Text>
              </Group>
            </Paper>
          ))}
        </Group>
      )}

      {/* Log viewer */}
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <Text fw={600}>לוג אירועים</Text>
          <Group gap="xs">
            <Button size="xs" variant="subtle" onClick={() => refetchConsole()} loading={consoleLoading}>🔄 רענן</Button>
            <Button size="xs" variant="subtle" color="red" onClick={() => clearMutation.mutate(levelFilter ?? undefined)} loading={clearMutation.isPending}>
              🗑 מחק {levelFilter ?? 'הכל'}
            </Button>
            <Button size="xs" variant="subtle" onClick={() => pollMutation.mutate()} loading={pollMutation.isPending}>📡 Poll</Button>
          </Group>
        </Group>

        <Group mb="sm" gap="xs">
          <TextInput
            placeholder="חיפוש..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            size="xs"
            style={{ flex: 1 }}
          />
          <Select
            placeholder="רמה"
            value={levelFilter}
            onChange={setLevelFilter}
            clearable
            size="xs"
            w={120}
            data={['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']}
          />
        </Group>

        {consoleLoading && <Center h={100}><Loader size="sm" /></Center>}
        {consoleError && <Alert color="orange">לא ניתן להתחבר לשרת הדייר</Alert>}

        {console_ && !consoleError && (
          <ScrollArea h={420}>
            <Table striped highlightOnHover style={{ fontSize: 12 }}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ width: 80 }}>רמה</Table.Th>
                  <Table.Th style={{ width: 130 }}>זמן</Table.Th>
                  <Table.Th style={{ width: 130 }}>מקור</Table.Th>
                  <Table.Th>הודעה</Table.Th>
                  <Table.Th style={{ width: 30 }}></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {console_.logs.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={5}>
                      <Center py="lg"><Text c="dimmed" size="sm">אין לוגים</Text></Center>
                    </Table.Td>
                  </Table.Tr>
                ) : console_.logs.map((log) => (
                  <Table.Tr
                    key={log.id}
                    style={{ background: log.level === 'CRITICAL' ? 'var(--mantine-color-red-0)' : log.level === 'ERROR' ? 'var(--mantine-color-red-0)' : undefined }}
                  >
                    <Table.Td>
                      <Badge color={LOG_LEVEL_COLORS[log.level] ?? 'gray'} size="xs" variant="filled">{log.level}</Badge>
                    </Table.Td>
                    <Table.Td style={{ fontSize: 11, direction: 'ltr', color: 'var(--mantine-color-dimmed)' }}>
                      {dayjs(log.created_at).format('DD/MM HH:mm:ss')}
                    </Table.Td>
                    <Table.Td style={{ fontSize: 11, fontFamily: 'monospace', direction: 'ltr', color: 'var(--mantine-color-dimmed)' }}>
                      {log.source ?? '—'}
                    </Table.Td>
                    <Table.Td style={{ maxWidth: 300 }}>
                      <Text size="xs" lineClamp={2}>{log.message}</Text>
                    </Table.Td>
                    <Table.Td>
                      {(log.stack_trace || log.message.length > 80) && (
                        <Tooltip label="פרטים">
                          <ActionIcon size="xs" variant="subtle" onClick={() => { setSelectedLog(log); setStackOpen(true) }}>🔍</ActionIcon>
                        </Tooltip>
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Paper>

      {/* Poll history (collapsible) */}
      <Button
        variant="subtle"
        size="xs"
        onClick={() => setShowHistory((v) => !v)}
        style={{ alignSelf: 'flex-start' }}
      >
        {showHistory ? '▲ הסתר היסטוריית polls' : '▼ הצג היסטוריית polls'}
      </Button>

      {showHistory && (
        <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
          <DataTable
            records={snapshots}
            fetching={snapshotsLoading}
            minHeight={100}
            columns={[
              { accessor: 'captured_at', title: 'זמן', render: (s) => <Text size="sm" dir="ltr">{dayjs(s.captured_at).format('DD/MM HH:mm:ss')}</Text> },
              { accessor: 'is_healthy', title: 'סטטוס', render: (s) => <Text>{s.is_healthy ? '🟢' : '🔴'}</Text> },
              { accessor: 'stats', title: 'קריאות', render: (s) => <Text size="sm">{(s.stats as any)?.calls_open ?? '—'}</Text> },
              { accessor: 'error', title: 'שגיאה', render: (s) => s.error ? <Text size="xs" c="red">{s.error}</Text> : null },
            ]}
          />
        </Paper>
      )}

      <StackTraceModal log={selectedLog} opened={stackOpen} onClose={() => setStackOpen(false)} />
    </Stack>
  )
}
