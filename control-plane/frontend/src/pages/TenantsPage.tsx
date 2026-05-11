import { useState } from 'react'
import {
  Button, Group, Title, Badge, Text, Modal, TextInput, Select,
  Stack, Textarea, ActionIcon, Tooltip, Paper, Checkbox, Collapse,
  Alert, ScrollArea, Code, Progress,
} from '@mantine/core'
import { DataTable } from 'mantine-datatable'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { useNavigate } from 'react-router-dom'
import { fetchTenants, createTenant, deleteTenant, updateTenantCode, bulkUpdateTenants, Tenant } from '../api/client'
import { modals } from '@mantine/modals'
import dayjs from 'dayjs'

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: 'green', PENDING: 'gray', DEPLOYING: 'blue',
  SUSPENDED: 'orange', ERROR: 'red', CANCELLED: 'dark',
}
const PLAN_COLOR: Record<string, string> = {
  TRIAL: 'gray', BASIC: 'blue', PRO: 'violet', ENTERPRISE: 'gold',
}
const DEPLOY_COLOR: Record<string, string> = {
  IDLE: 'gray', UPDATING: 'blue', SUCCESS: 'green', ERROR: 'red',
}

export default function TenantsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deployPanelOpen, setDeployPanelOpen] = useState(false)
  const [outputLog, setOutputLog] = useState<{ name: string; output: string } | null>(null)

  const { data: tenants = [], isLoading } = useQuery({
    queryKey: ['tenants'],
    queryFn: fetchTenants,
    refetchInterval: (query) => {
      const rows = query.state.data ?? []
      return rows.some((t) => t.deploy_status === 'UPDATING') ? 3000 : false
    },
  })

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenants'] })
      setCreateOpen(false)
      notifications.show({ message: 'דייר נוצר בהצלחה', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteTenant,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenants'] })
      notifications.show({ message: 'דייר נמחק', color: 'orange' })
    },
  })

  const singleUpdateMutation = useMutation({
    mutationFn: updateTenantCode,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tenants'] })
      notifications.show({ message: 'עדכון התחיל', color: 'blue' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const bulkUpdateMutation = useMutation({
    mutationFn: (ids: string[]) => bulkUpdateTenants(ids),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['tenants'] })
      notifications.show({
        message: `עדכון התחיל עבור ${data.started.length} שרתים${data.skipped.length ? ` (${data.skipped.length} דולגו)` : ''}`,
        color: 'blue',
      })
      setSelected(new Set())
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail ?? 'שגיאה', color: 'red' }),
  })

  const confirmDelete = (t: Tenant) =>
    modals.openConfirmModal({
      title: `מחיקת ${t.name}`,
      children: <Text size="sm">האם אתה בטוח? פעולה זו אינה הפיכה.</Text>,
      labels: { confirm: 'מחק', cancel: 'ביטול' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(t.id),
    })

  const activeWithServer = tenants.filter((t) => t.status === 'ACTIVE' && t.hetzner_server_ip)
  const updatingCount = tenants.filter((t) => t.deploy_status === 'UPDATING').length
  const allActiveSelected = activeWithServer.length > 0 && activeWithServer.every((t) => selected.has(t.id))

  const toggleAll = () => {
    if (allActiveSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(activeWithServer.map((t) => t.id)))
    }
  }

  const toggleOne = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={3}>🏢 דיירים</Title>
        <Group>
          <Button
            variant={deployPanelOpen ? 'filled' : 'light'}
            color="indigo"
            onClick={() => setDeployPanelOpen((v) => !v)}
          >
            🚀 עדכון קוד {updatingCount > 0 && `(${updatingCount} רצים)`}
          </Button>
          <Button onClick={() => setCreateOpen(true)}>+ דייר חדש</Button>
        </Group>
      </Group>

      {/* Deploy panel */}
      <Collapse in={deployPanelOpen}>
        <Paper withBorder p="md" radius="md" mb="md" style={{ borderColor: 'var(--mantine-color-indigo-4)' }}>
          <Group justify="space-between" mb="sm">
            <Text fw={600} c="indigo">📦 משיכת קוד מ-GitHub → rebuild</Text>
            <Group>
              <Checkbox
                label="בחר כל פעיל"
                checked={allActiveSelected}
                indeterminate={selected.size > 0 && !allActiveSelected}
                onChange={toggleAll}
              />
              <Button
                size="sm"
                color="indigo"
                disabled={selected.size === 0}
                loading={bulkUpdateMutation.isPending}
                onClick={() => bulkUpdateMutation.mutate(Array.from(selected))}
              >
                🚀 Deploy נבחרים ({selected.size})
              </Button>
              <Button
                size="sm"
                variant="light"
                color="indigo"
                loading={bulkUpdateMutation.isPending}
                onClick={() => bulkUpdateMutation.mutate(activeWithServer.map((t) => t.id))}
              >
                Deploy כולם ({activeWithServer.length})
              </Button>
            </Group>
          </Group>

          {updatingCount > 0 && (
            <Alert color="blue" mb="sm">
              <Group gap="xs">
                <Progress value={100} animated size="xs" style={{ flex: 1 }} color="blue" />
                <Text size="sm">{updatingCount} שרתים בתהליך עדכון...</Text>
              </Group>
            </Alert>
          )}

          <Stack gap={6}>
            {activeWithServer.map((t) => (
              <Paper key={t.id} withBorder p="xs" radius="sm" style={{ background: 'var(--mantine-color-default-hover)' }}>
                <Group justify="space-between">
                  <Group gap="sm">
                    <Checkbox
                      checked={selected.has(t.id)}
                      onChange={() => toggleOne(t.id)}
                      onClick={(e) => e.stopPropagation()}
                    />
                    <Text size="sm" fw={500}>{t.name}</Text>
                    <Text size="xs" c="dimmed" dir="ltr">{t.hetzner_server_ip}</Text>
                  </Group>
                  <Group gap="xs">
                    <Badge
                      color={DEPLOY_COLOR[t.deploy_status]}
                      variant={t.deploy_status === 'UPDATING' ? 'dot' : 'light'}
                      size="sm"
                    >
                      {t.deploy_status === 'UPDATING' ? '⟳ מעדכן...' : t.deploy_status}
                    </Badge>
                    {t.last_deploy_at && (
                      <Text size="xs" c="dimmed">{dayjs(t.last_deploy_at).format('DD/MM HH:mm')}</Text>
                    )}
                    {t.deploy_output && (
                      <Tooltip label="הצג פלט">
                        <ActionIcon
                          size="xs"
                          variant="subtle"
                          color={t.deploy_status === 'ERROR' ? 'red' : 'gray'}
                          onClick={() => setOutputLog({ name: t.name, output: t.deploy_output! })}
                        >
                          📋
                        </ActionIcon>
                      </Tooltip>
                    )}
                    <Tooltip label="Deploy עכשיו">
                      <ActionIcon
                        size="xs"
                        variant="light"
                        color="indigo"
                        loading={singleUpdateMutation.isPending && singleUpdateMutation.variables === t.id}
                        disabled={t.deploy_status === 'UPDATING'}
                        onClick={() => singleUpdateMutation.mutate(t.id)}
                      >
                        🚀
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Group>
              </Paper>
            ))}
            {activeWithServer.length === 0 && (
              <Text c="dimmed" size="sm" ta="center" py="sm">אין דיירים פעילים עם שרת</Text>
            )}
          </Stack>
        </Paper>
      </Collapse>

      {/* Tenants table */}
      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        <DataTable
          records={tenants}
          fetching={isLoading}
          minHeight={200}
          highlightOnHover
          onRowClick={({ record }) => navigate(`/tenants/${record.id}`)}
          columns={[
            { accessor: 'name', title: 'שם', render: (t) => <Text fw={500}>{t.name}</Text> },
            { accessor: 'slug', title: 'Slug', render: (t) => <Text size="sm" c="dimmed" dir="ltr">{t.slug}</Text> },
            {
              accessor: 'status', title: 'סטטוס',
              render: (t) => <Badge color={STATUS_COLOR[t.status]} variant="light">{t.status}</Badge>,
            },
            {
              accessor: 'plan', title: 'תכנית',
              render: (t) => <Badge color={PLAN_COLOR[t.plan]} variant="dot">{t.plan}</Badge>,
            },
            {
              accessor: 'is_healthy', title: 'בריאות',
              render: (t) => t.status === 'ACTIVE'
                ? <Text>{t.is_healthy ? '🟢' : '🔴'}</Text>
                : <Text c="dimmed">—</Text>,
            },
            {
              accessor: 'deploy_status', title: 'Deploy',
              render: (t) => t.hetzner_server_ip ? (
                <Badge color={DEPLOY_COLOR[t.deploy_status]} variant="light" size="sm">
                  {t.deploy_status === 'UPDATING' ? '⟳ רץ' : t.deploy_status}
                </Badge>
              ) : <Text c="dimmed" size="sm">—</Text>,
            },
            {
              accessor: 'last_deploy_at', title: 'עדכון אחרון',
              render: (t) => t.last_deploy_at
                ? <Text size="xs" c="dimmed">{dayjs(t.last_deploy_at).format('DD/MM HH:mm')}</Text>
                : <Text c="dimmed">—</Text>,
            },
            {
              accessor: 'last_seen_at', title: 'פעיל לאחרונה',
              render: (t) => t.last_seen_at
                ? <Text size="xs" c="dimmed">{dayjs(t.last_seen_at).format('DD/MM HH:mm')}</Text>
                : <Text c="dimmed">—</Text>,
            },
            {
              accessor: 'actions', title: '',
              render: (t) => (
                <Group gap={4} onClick={(e) => e.stopPropagation()}>
                  <Tooltip label="פתח">
                    <ActionIcon variant="subtle" onClick={() => navigate(`/tenants/${t.id}`)}>🔗</ActionIcon>
                  </Tooltip>
                  <Tooltip label="מחק">
                    <ActionIcon variant="subtle" color="red" onClick={() => confirmDelete(t)}>🗑️</ActionIcon>
                  </Tooltip>
                </Group>
              ),
            },
          ]}
        />
      </Paper>

      <CreateModal
        opened={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={(v) => createMutation.mutate(v)}
        loading={createMutation.isPending}
      />

      {/* Deploy output modal */}
      <Modal
        opened={!!outputLog}
        onClose={() => setOutputLog(null)}
        title={`פלט deploy — ${outputLog?.name}`}
        size="xl"
        dir="ltr"
      >
        <ScrollArea h={400}>
          <Code block style={{ fontSize: 11, whiteSpace: 'pre-wrap' }}>
            {outputLog?.output ?? ''}
          </Code>
        </ScrollArea>
      </Modal>
    </>
  )
}

function CreateModal({ opened, onClose, onSubmit, loading }: {
  opened: boolean; onClose: () => void
  onSubmit: (v: Partial<Tenant>) => void; loading: boolean
}) {
  const [form, setForm] = useState({ name: '', slug: '', contact_email: '', plan: 'TRIAL', notes: '' })
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <Modal opened={opened} onClose={onClose} title="דייר חדש" centered>
      <Stack>
        <TextInput label="שם חברה" required value={form.name} onChange={set('name')} />
        <TextInput label="Slug (subdomain)" required value={form.slug} onChange={set('slug')} dir="ltr"
          description="לדוגמה: acme → acme.lift-agent.com" />
        <TextInput label="אימייל איש קשר" required value={form.contact_email} onChange={set('contact_email')} dir="ltr" />
        <Select
          label="תכנית"
          data={['TRIAL', 'BASIC', 'PRO', 'ENTERPRISE']}
          value={form.plan}
          onChange={(v) => setForm((f) => ({ ...f, plan: v ?? 'TRIAL' }))}
        />
        <Textarea label="הערות" value={form.notes} onChange={set('notes')} />
        <Button onClick={() => onSubmit(form as any)} loading={loading} fullWidth>צור דייר</Button>
      </Stack>
    </Modal>
  )
}
