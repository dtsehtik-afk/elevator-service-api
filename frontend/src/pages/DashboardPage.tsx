import { Grid, Paper, Text, Title, Stack, Group, Badge, Table, Loader, Center, ThemeIcon, RingProgress } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import { listCalls } from '../api/calls'
import { listMaintenance } from '../api/maintenance'
import { listTechnicians } from '../api/technicians'
import { CALL_STATUS_COLORS, CALL_STATUS_LABELS, PRIORITY_COLORS, PRIORITY_LABELS, ELEVATOR_STATUS_COLORS } from '../utils/constants'
import { formatDate, isOverdue, isSoon } from '../utils/dates'

function StatCard({ label, value, icon, color }: { label: string; value: number | string; icon: string; color: string }) {
  return (
    <Paper withBorder p="lg" radius="md">
      <Group justify="space-between">
        <div>
          <Text c="dimmed" size="sm">{label}</Text>
          <Text fw={700} size="2rem" lh={1.2}>{value}</Text>
        </div>
        <ThemeIcon size={50} radius="xl" color={color} variant="light">
          <Text size="1.5rem">{icon}</Text>
        </ThemeIcon>
      </Group>
    </Paper>
  )
}

export default function DashboardPage() {
  const { data: elevators = [] } = useQuery({ queryKey: ['elevators'], queryFn: () => listElevators() })
  const { data: calls = [], isLoading: callsLoading } = useQuery({ queryKey: ['calls'], queryFn: () => listCalls(), refetchInterval: 60_000 })
  const { data: maintenance = [] } = useQuery({ queryKey: ['maintenance'], queryFn: () => listMaintenance() })
  const { data: technicians = [] } = useQuery({ queryKey: ['technicians'], queryFn: () => listTechnicians() })

  const openCalls = calls.filter(c => ['OPEN', 'ASSIGNED', 'IN_PROGRESS'].includes(c.status))
  const criticalCalls = calls.filter(c => c.priority === 'CRITICAL' && c.status !== 'CLOSED')
  const availableTechs = technicians.filter(t => t.is_available && t.is_active)
  const onCallTech = technicians.find(t => t.is_on_call)
  const upcomingMaintenance = maintenance
    .filter(m => m.status === 'SCHEDULED' && isSoon(m.scheduled_date, 14))
    .sort((a, b) => a.scheduled_date.localeCompare(b.scheduled_date))
    .slice(0, 8)
  const atRiskElevators = elevators.filter(e => e.risk_score > 50).length
  const overdueMaintenance = maintenance.filter(m => m.status === 'SCHEDULED' && isOverdue(m.scheduled_date)).length

  return (
    <Stack gap="lg">
      <Title order={2}>דשבורד</Title>

      {/* KPI Cards */}
      <Grid>
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <StatCard label="קריאות פתוחות" value={openCalls.length} icon="🔧" color="orange" />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <StatCard label="קריאות קריטיות" value={criticalCalls.length} icon="🚨" color="red" />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <StatCard label="טכנאים זמינים" value={`${availableTechs.length}/${technicians.length}`} icon="👷" color="green" />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <StatCard label="תחזוקה בפיגור" value={overdueMaintenance} icon="⚠️" color="yellow" />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <StatCard
            label="תורן"
            value={onCallTech ? `🌙 ${onCallTech.name}` : 'אין תורן'}
            icon="🌙"
            color="teal"
          />
        </Grid.Col>
      </Grid>

      <Grid>
        {/* Recent open calls */}
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="md">קריאות שירות פתוחות אחרונות</Title>
            {callsLoading ? (
              <Center h={200}><Loader /></Center>
            ) : openCalls.length === 0 ? (
              <Center h={200}><Text c="dimmed">אין קריאות פתוחות 🎉</Text></Center>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>עדיפות</Table.Th>
                    <Table.Th>תיאור</Table.Th>
                    <Table.Th>סטטוס</Table.Th>
                    <Table.Th>תאריך</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {openCalls.slice(0, 8).map(call => (
                    <Table.Tr key={call.id}>
                      <Table.Td>
                        <Badge color={PRIORITY_COLORS[call.priority]} size="sm">
                          {PRIORITY_LABELS[call.priority]}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" lineClamp={1}>{call.description}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge color={CALL_STATUS_COLORS[call.status]} variant="light" size="sm">
                          {CALL_STATUS_LABELS[call.status]}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">{formatDate(call.created_at)}</Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Paper>
        </Grid.Col>

        {/* Upcoming maintenance */}
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="md">תחזוקה קרובה (14 יום)</Title>
            {upcomingMaintenance.length === 0 ? (
              <Center h={200}><Text c="dimmed">אין תחזוקה מתוזמנת</Text></Center>
            ) : (
              <Stack gap="xs">
                {upcomingMaintenance.map(m => (
                  <Group key={m.id} justify="space-between" p="xs" style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
                    <Text size="sm">{formatDate(m.scheduled_date)}</Text>
                    <Badge size="sm" variant="light" color={isOverdue(m.scheduled_date) ? 'red' : 'blue'}>
                      {isOverdue(m.scheduled_date) ? 'באיחור' : 'מתוזמן'}
                    </Badge>
                  </Group>
                ))}
              </Stack>
            )}
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Elevator status summary */}
      <Paper withBorder p="md" radius="md">
        <Title order={4} mb="md">סטטוס מעליות ({elevators.length} סה"כ)</Title>
        <Group gap="xl">
          {['ACTIVE', 'INACTIVE', 'UNDER_REPAIR'].map(status => {
            const count = elevators.filter(e => e.status === status).length
            const labels: Record<string, string> = { ACTIVE: 'פעילות', INACTIVE: 'לא פעילות', UNDER_REPAIR: 'בתיקון' }
            return (
              <Group key={status} gap="xs">
                <Badge size="lg" color={ELEVATOR_STATUS_COLORS[status]}>{count}</Badge>
                <Text size="sm">{labels[status]}</Text>
              </Group>
            )
          })}
          <Group gap="xs">
            <Badge size="lg" color="red">{atRiskElevators}</Badge>
            <Text size="sm">בסיכון גבוה (risk &gt; 50)</Text>
          </Group>
        </Group>
      </Paper>
    </Stack>
  )
}
