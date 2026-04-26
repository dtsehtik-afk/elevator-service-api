import { useQuery } from '@tanstack/react-query'
import { Title, Paper, Text, Badge, Group, SimpleGrid, Loader, Progress } from '@mantine/core'
import { DataTable } from 'mantine-datatable'
import { useNavigate } from 'react-router-dom'
import { fetchHealthOverview, HealthOverviewItem } from '../api/client'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'

dayjs.extend(relativeTime)

const STATUS_COLOR: Record<string, string> = {
  ACTIVE: 'green', PENDING: 'gray', DEPLOYING: 'blue',
  SUSPENDED: 'orange', ERROR: 'red', CANCELLED: 'dark',
}

export default function MonitoringPage() {
  const navigate = useNavigate()
  const { data: tenants = [], isLoading } = useQuery({
    queryKey: ['health-overview'],
    queryFn: fetchHealthOverview,
    refetchInterval: 30_000,
  })

  const active = tenants.filter((t) => t.status === 'ACTIVE')
  const healthy = active.filter((t) => t.is_healthy)
  const healthPct = active.length ? Math.round((healthy.length / active.length) * 100) : 0

  return (
    <>
      <Title order={3} mb="md">📊 ניטור — כל הדיירים</Title>

      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="lg">
        <StatCard label="סה״כ דיירים" value={tenants.length} />
        <StatCard label="פעילים" value={active.length} color="green" />
        <StatCard label="בריאים" value={healthy.length} color="teal" />
        <StatCard label="לא תקינים" value={active.length - healthy.length} color={active.length - healthy.length > 0 ? 'red' : 'gray'} />
      </SimpleGrid>

      {active.length > 0 && (
        <Paper withBorder p="md" radius="md" mb="lg">
          <Group justify="space-between" mb={4}>
            <Text size="sm" fw={600}>Health Rate</Text>
            <Text size="sm" c={healthPct === 100 ? 'green' : healthPct > 70 ? 'orange' : 'red'}>
              {healthPct}%
            </Text>
          </Group>
          <Progress value={healthPct} color={healthPct === 100 ? 'green' : healthPct > 70 ? 'orange' : 'red'} />
        </Paper>
      )}

      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        <DataTable
          records={tenants}
          fetching={isLoading}
          minHeight={200}
          highlightOnHover
          onRowClick={({ record }) => navigate(`/tenants/${record.tenant_id}`)}
          columns={[
            {
              accessor: 'tenant_name', title: 'שם',
              render: (t) => <Text fw={500}>{t.tenant_name}</Text>,
            },
            {
              accessor: 'status', title: 'סטטוס',
              render: (t) => <Badge color={STATUS_COLOR[t.status]} variant="light">{t.status}</Badge>,
            },
            {
              accessor: 'is_healthy', title: 'בריאות',
              render: (t) => t.status === 'ACTIVE'
                ? <Text>{t.is_healthy ? '🟢 תקין' : '🔴 לא תקין'}</Text>
                : <Text c="dimmed">—</Text>,
            },
            {
              accessor: 'calls_open', title: 'קריאות פתוחות',
              render: (t) => <Text size="sm">{(t.last_stats as any)?.calls_open ?? '—'}</Text>,
            },
            {
              accessor: 'elevators', title: 'מעליות',
              render: (t) => <Text size="sm">{(t.last_stats as any)?.elevators_total ?? '—'}</Text>,
            },
            {
              accessor: 'technicians', title: 'טכנאים',
              render: (t) => <Text size="sm">{(t.last_stats as any)?.technicians_active ?? '—'}</Text>,
            },
            {
              accessor: 'last_seen_at', title: 'פעיל לפני',
              render: (t) => t.last_seen_at
                ? <Text size="xs" c="dimmed">{dayjs(t.last_seen_at).fromNow()}</Text>
                : <Text c="dimmed">—</Text>,
            },
          ]}
        />
      </Paper>
    </>
  )
}

function StatCard({ label, value, color = 'blue' }: { label: string; value: number; color?: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text size="xs" c="dimmed" mb={4}>{label}</Text>
      <Text size="xl" fw={700} c={color}>{value}</Text>
    </Paper>
  )
}
