import { useState } from 'react'
import {
  Button, Group, Title, Badge, Text, Modal, TextInput, Select,
  Stack, Textarea, ActionIcon, Tooltip, Paper,
} from '@mantine/core'
import { DataTable } from 'mantine-datatable'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { useNavigate } from 'react-router-dom'
import { fetchTenants, createTenant, deleteTenant, Tenant } from '../api/client'
import { modals } from '@mantine/modals'
import dayjs from 'dayjs'

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: 'green', PENDING: 'gray', DEPLOYING: 'blue',
  SUSPENDED: 'orange', ERROR: 'red', CANCELLED: 'dark',
}
const PLAN_COLOR: Record<string, string> = {
  TRIAL: 'gray', BASIC: 'blue', PRO: 'violet', ENTERPRISE: 'gold',
}

export default function TenantsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [createOpen, setCreateOpen] = useState(false)

  const { data: tenants = [], isLoading } = useQuery({ queryKey: ['tenants'], queryFn: fetchTenants })

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

  const confirmDelete = (t: Tenant) =>
    modals.openConfirmModal({
      title: `מחיקת ${t.name}`,
      children: <Text size="sm">האם אתה בטוח? פעולה זו אינה הפיכה.</Text>,
      labels: { confirm: 'מחק', cancel: 'ביטול' },
      confirmProps: { color: 'red' },
      onConfirm: () => deleteMutation.mutate(t.id),
    })

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={3}>🏢 דיירים</Title>
        <Button onClick={() => setCreateOpen(true)}>+ דייר חדש</Button>
      </Group>

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
        <Button onClick={() => onSubmit(form)} loading={loading} fullWidth>צור דייר</Button>
      </Stack>
    </Modal>
  )
}
