import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Title, Grid, Paper, TextInput, Select, Switch, Button, Group, Badge,
  Stack, Text, Loader, Alert, Tabs, NumberInput, Textarea, Divider,
} from '@mantine/core'
import { getTenant, updateTenant, setModules, getTenantStats, pingTenant, type Module } from '../api/tenants'

const ALL_MODULES = ['WHATSAPP', 'AI_ASSIGN', 'INSPECTIONS', 'MAINTENANCE', 'MAP', 'IMPORT']

function ModulesTab({ tenantId, modules }: { tenantId: string; modules: Module[] }) {
  const qc = useQueryClient()
  const [local, setLocal] = useState<Module[]>(() => {
    const map = Object.fromEntries(modules.map((m) => [m.module, m.enabled]))
    return ALL_MODULES.map((m) => ({ module: m, enabled: map[m] ?? false }))
  })
  const mut = useMutation({
    mutationFn: () => setModules(tenantId, local),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenant', tenantId] }),
  })
  const toggle = (mod: string) =>
    setLocal((p) => p.map((m) => (m.module === mod ? { ...m, enabled: !m.enabled } : m)))

  return (
    <Stack mt="md">
      {local.map((m) => (
        <Group key={m.module} justify="space-between">
          <Text>{m.module}</Text>
          <Switch checked={m.enabled} onChange={() => toggle(m.module)} />
        </Group>
      ))}
      <Button mt="sm" loading={mut.isPending} onClick={() => mut.mutate()}>שמור מודולים</Button>
    </Stack>
  )
}

function StatsTab({ tenantId }: { tenantId: string }) {
  const qc = useQueryClient()
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['tenant-stats', tenantId],
    queryFn: () => getTenantStats(tenantId),
    retry: false,
  })
  const ping = useMutation({ mutationFn: () => pingTenant(tenantId), onSuccess: () => qc.invalidateQueries({ queryKey: ['tenant', tenantId] }) })

  return (
    <Stack mt="md">
      <Group>
        <Button variant="light" onClick={() => refetch()}>רענן סטטיסטיקות</Button>
        <Button variant="outline" loading={ping.isPending} onClick={() => ping.mutate()}>Ping</Button>
      </Group>
      {isLoading && <Loader />}
      {error && <Alert color="red">לא ניתן להתחבר לשרת הדייר</Alert>}
      {data && !data.error && (
        <Grid>
          {Object.entries(data).map(([k, v]) => (
            <Grid.Col key={k} span={6}>
              <Paper p="sm" withBorder>
                <Text size="xs" c="dimmed">{k}</Text>
                <Text fw={600}>{String(v)}</Text>
              </Paper>
            </Grid.Col>
          ))}
        </Grid>
      )}
      {data?.error && <Alert color="orange">שגיאה: {data.error}</Alert>}
    </Stack>
  )
}

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const { data: tenant, isLoading } = useQuery({ queryKey: ['tenant', id], queryFn: () => getTenant(id!) })

  const [form, setForm] = useState<Record<string, unknown>>({})
  const f = (k: string) => (v: unknown) => setForm((p) => ({ ...p, [k]: v }))

  const mut = useMutation({
    mutationFn: () => updateTenant(id!, form as Parameters<typeof updateTenant>[1]),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenant', id] }); setForm({}) },
  })

  if (isLoading) return <Loader m="xl" />
  if (!tenant) return <Alert color="red" m="xl">לא נמצא</Alert>

  const val = (k: string) => (k in form ? form[k] : (tenant as Record<string, unknown>)[k]) as string

  return (
    <>
      <Group mb="md">
        <Button variant="subtle" onClick={() => navigate('/')}>← חזור</Button>
        <Title order={2}>{tenant.name}</Title>
        <Badge color={tenant.is_active ? 'green' : 'red'}>{tenant.is_active ? 'פעיל' : 'מושבת'}</Badge>
      </Group>

      <Tabs defaultValue="details">
        <Tabs.List>
          <Tabs.Tab value="details">פרטים</Tabs.Tab>
          <Tabs.Tab value="modules">מודולים</Tabs.Tab>
          <Tabs.Tab value="stats">סטטיסטיקות</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="details" pt="md">
          <Grid>
            <Grid.Col span={6}>
              <Stack>
                <TextInput label="שם חברה" value={val('name')} onChange={(e) => f('name')(e.target.value)} />
                <Select label="תוכנית" data={['BASIC', 'PRO', 'ENTERPRISE']} value={val('plan')} onChange={(v) => f('plan')(v)} />
                <TextInput label="דומיין" value={val('domain') ?? ''} onChange={(e) => f('domain')(e.target.value)} />
                <TextInput label="API URL" value={val('api_url') ?? ''} onChange={(e) => f('api_url')(e.target.value)} />
                <TextInput label="API Key" value={val('api_key') ?? ''} onChange={(e) => f('api_key')(e.target.value)} />
              </Stack>
            </Grid.Col>
            <Grid.Col span={6}>
              <Stack>
                <TextInput label="איש קשר" value={val('contact_name') ?? ''} onChange={(e) => f('contact_name')(e.target.value)} />
                <TextInput label="אימייל" value={val('contact_email') ?? ''} onChange={(e) => f('contact_email')(e.target.value)} />
                <TextInput label="טלפון" value={val('contact_phone') ?? ''} onChange={(e) => f('contact_phone')(e.target.value)} />
                <NumberInput label="מחיר חודשי (₪)" value={(val('monthly_price') as unknown as number) ?? ''} onChange={(v) => f('monthly_price')(v)} />
                <Textarea label="הערות חיוב" value={val('billing_notes') ?? ''} onChange={(e) => f('billing_notes')(e.target.value)} rows={3} />
              </Stack>
            </Grid.Col>
            <Grid.Col span={12}>
              <Divider my="sm" />
              <Group>
                <Switch label="פעיל" checked={Boolean(val('is_active'))} onChange={(e) => f('is_active')(e.target.checked)} />
                <Switch label="דמו" checked={Boolean(val('is_demo'))} onChange={(e) => f('is_demo')(e.target.checked)} />
              </Group>
            </Grid.Col>
            <Grid.Col span={12}>
              <Group mt="sm">
                <Button loading={mut.isPending} onClick={() => mut.mutate()} disabled={Object.keys(form).length === 0}>שמור שינויים</Button>
                <Button variant="subtle" onClick={() => setForm({})}>בטל</Button>
              </Group>
              {mut.isSuccess && <Text c="green" size="sm" mt="xs">נשמר בהצלחה</Text>}
            </Grid.Col>
          </Grid>
        </Tabs.Panel>

        <Tabs.Panel value="modules">
          <ModulesTab tenantId={id!} modules={tenant.modules} />
        </Tabs.Panel>

        <Tabs.Panel value="stats">
          <StatsTab tenantId={id!} />
        </Tabs.Panel>
      </Tabs>
    </>
  )
}
