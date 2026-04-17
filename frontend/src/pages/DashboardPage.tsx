import { useEffect, useState } from 'react'
import {
  Grid, Paper, Text, Title, Stack, Group, Badge, Table, Loader, Center,
  ThemeIcon, RingProgress, ScrollArea, Alert, Divider, Progress, Tooltip,
  ActionIcon,
} from '@mantine/core'
import { DonutChart, BarChart } from '@mantine/charts'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { listElevators } from '../api/elevators'
import { listCalls } from '../api/calls'
import { listMaintenance } from '../api/maintenance'
import { listTechnicians } from '../api/technicians'
import {
  CALL_STATUS_COLORS, CALL_STATUS_LABELS, PRIORITY_COLORS, PRIORITY_LABELS,
} from '../utils/constants'
import { formatDate, isOverdue } from '../utils/dates'

// ── Weather ────────────────────────────────────────────────────────────────────

const WMO_LABELS: Record<number, string> = {
  0: 'שמיים בהירים', 1: 'בהיר בעיקר', 2: 'מעונן חלקית', 3: 'מעונן',
  45: 'ערפל', 48: 'ערפל קפוא', 51: 'טפטוף קל', 53: 'טפטוף', 55: 'טפטוף חזק',
  61: 'גשם קל', 63: 'גשם', 65: 'גשם חזק', 71: 'שלג קל', 73: 'שלג', 75: 'שלג כבד',
  80: 'מקלחות קלות', 81: 'מקלחות', 82: 'מקלחות חזקות', 95: 'סופת רעמים',
  96: 'סופת רעמים עם ברד', 99: 'סופת רעמים עם ברד גדול',
}

const WMO_ICONS: Record<number, string> = {
  0: '☀️', 1: '🌤️', 2: '⛅', 3: '☁️',
  45: '🌫️', 48: '🌫️', 51: '🌦️', 53: '🌦️', 55: '🌧️',
  61: '🌧️', 63: '🌧️', 65: '🌧️', 71: '🌨️', 73: '❄️', 75: '❄️',
  80: '🌦️', 81: '🌧️', 82: '⛈️', 95: '⛈️', 96: '⛈️', 99: '⛈️',
}

interface WeatherData {
  temp: number
  code: number
  wind: number
}

function useWeather() {
  const [weather, setWeather] = useState<WeatherData | null>(null)
  useEffect(() => {
    fetch(
      'https://api.open-meteo.com/v1/forecast?latitude=32.61&longitude=35.29' +
      '&current=temperature_2m,weather_code,wind_speed_10m&timezone=Asia%2FJerusalem'
    )
      .then(r => r.json())
      .then(d => setWeather({
        temp: Math.round(d.current.temperature_2m),
        code: d.current.weather_code,
        wind: Math.round(d.current.wind_speed_10m),
      }))
      .catch(() => null)
  }, [])
  return weather
}

// ── Small components ───────────────────────────────────────────────────────────

function KpiCard({
  label, value, sub, icon, color, onClick,
}: {
  label: string; value: number | string; sub?: string; icon: string
  color: string; onClick?: () => void
}) {
  return (
    <Paper
      withBorder p="md" radius="md" h="100%"
      style={{ cursor: onClick ? 'pointer' : undefined, transition: 'box-shadow 0.15s' }}
      onClick={onClick}
      onMouseEnter={e => onClick && ((e.currentTarget as HTMLElement).style.boxShadow = '0 4px 16px rgba(0,0,0,0.12)')}
      onMouseLeave={e => onClick && ((e.currentTarget as HTMLElement).style.boxShadow = '')}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2}>
          <Text c="dimmed" size="xs" tt="uppercase" fw={600}>{label}</Text>
          <Text fw={800} size="2rem" lh={1}>{value}</Text>
          {sub && <Text size="xs" c="dimmed">{sub}</Text>}
        </Stack>
        <ThemeIcon size={46} radius="xl" color={color} variant="light">
          <Text size="1.4rem">{icon}</Text>
        </ThemeIcon>
      </Group>
    </Paper>
  )
}

function WeatherCard({ weather }: { weather: WeatherData | null }) {
  if (!weather) return (
    <Paper withBorder p="md" radius="md" h="100%">
      <Stack gap={2}>
        <Text c="dimmed" size="xs" tt="uppercase" fw={600}>מזג אוויר — עפולה</Text>
        <Center h={60}><Loader size="sm" /></Center>
      </Stack>
    </Paper>
  )
  const icon = WMO_ICONS[weather.code] ?? '🌡️'
  const label = WMO_LABELS[weather.code] ?? ''
  return (
    <Paper withBorder p="md" radius="md" h="100%" style={{ background: 'linear-gradient(135deg, #e0f7fa 0%, #f3e5f5 100%)' }}>
      <Stack gap={2}>
        <Text c="dimmed" size="xs" tt="uppercase" fw={600}>מזג אוויר — עפולה</Text>
        <Group gap="xs" align="flex-end">
          <Text size="2.2rem" lh={1}>{icon}</Text>
          <Text fw={800} size="2rem" lh={1}>{weather.temp}°C</Text>
        </Group>
        <Text size="xs" c="dimmed">{label} · רוח {weather.wind} קמ"ש</Text>
      </Stack>
    </Paper>
  )
}

// ── Urgency helper ─────────────────────────────────────────────────────────────

function urgencyColor(daysUntil: number): string {
  if (daysUntil < 0) return 'red'
  if (daysUntil <= 2) return 'red'
  if (daysUntil <= 5) return 'orange'
  if (daysUntil <= 10) return 'yellow'
  return 'green'
}

function urgencyLabel(daysUntil: number): string {
  if (daysUntil < 0) return `${Math.abs(daysUntil)} ימים באיחור`
  if (daysUntil === 0) return 'היום!'
  if (daysUntil === 1) return 'מחר'
  return `${daysUntil} ימים`
}

// ── Main ───────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate()
  const weather = useWeather()

  const { data: elevators = [] } = useQuery({
    queryKey: ['elevators'], queryFn: () => listElevators({ limit: 2000 } as any),
  })
  const { data: calls = [], isLoading: callsLoading } = useQuery({
    queryKey: ['calls'], queryFn: () => listCalls({ limit: 500 } as any), refetchInterval: 60_000,
  })
  const { data: maintenance = [] } = useQuery({
    queryKey: ['maintenance'], queryFn: () => listMaintenance(),
  })
  const { data: technicians = [] } = useQuery({
    queryKey: ['technicians'], queryFn: () => listTechnicians(),
  })

  // ── Derived data ──────────────────────────────────────────────────────────────
  const now = dayjs()

  const openCalls = calls.filter(c => ['OPEN', 'ASSIGNED', 'IN_PROGRESS'].includes(c.status))
  const criticalCalls = calls.filter(c => c.priority === 'CRITICAL' && !['RESOLVED', 'CLOSED'].includes(c.status))
  const activeTechs = technicians.filter(t => t.is_active)
  const availableTechs = activeTechs.filter(t => t.is_available)
  const onCallTech = technicians.find(t => t.is_on_call && t.is_active)
  const overdueMaintenance = maintenance.filter(m => m.status === 'SCHEDULED' && isOverdue(m.scheduled_date))

  // Elevators with upcoming next_service_date (within 30 days)
  const urgentService = elevators
    .filter(e => e.next_service_date && e.status !== 'INACTIVE')
    .map(e => ({ ...e, daysUntil: dayjs(e.next_service_date!).diff(now, 'day') }))
    .filter(e => e.daysUntil <= 10)
    .sort((a, b) => a.daysUntil - b.daysUntil)
    .slice(0, 8)

  // Missing data insights
  const missingLabor = elevators.filter(e => !e.labor_file_number && e.status !== 'INACTIVE').length
  const missingService = elevators.filter(e => !e.service_type).length
  const debtElevators = elevators.filter(e => e.has_debt).length
  const highRisk = elevators.filter(e => e.risk_score > 50).length

  // Calls status donut
  const callsByStatus = Object.entries(
    calls.reduce<Record<string, number>>((acc, c) => {
      acc[c.status] = (acc[c.status] ?? 0) + 1
      return acc
    }, {})
  ).map(([status, value]) => ({
    name: CALL_STATUS_LABELS[status] ?? status,
    value,
    color: CALL_STATUS_COLORS[status] ?? 'gray',
  }))

  // Calls by fault type (bar chart) — last 50 non-closed
  const faultLabels: Record<string, string> = {
    MECHANICAL: 'מכאני', ELECTRICAL: 'חשמלי', SOFTWARE: 'תוכנה',
    STUCK: 'תקועה', DOOR: 'דלת', OTHER: 'אחר',
  }
  const callsByFault = Object.entries(
    calls.filter(c => c.status !== 'CLOSED').reduce<Record<string, number>>((acc, c) => {
      acc[c.fault_type] = (acc[c.fault_type] ?? 0) + 1
      return acc
    }, {})
  ).map(([t, count]) => ({ type: faultLabels[t] ?? t, count }))

  // City distribution top-5
  const cityCount = elevators.reduce<Record<string, number>>((acc, e) => {
    if (e.city) acc[e.city] = (acc[e.city] ?? 0) + 1
    return acc
  }, {})
  const topCities = Object.entries(cityCount).sort((a, b) => b[1] - a[1]).slice(0, 5)

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="center">
        <Title order={2}>דשבורד</Title>
        <Text size="sm" c="dimmed">{now.format('dddd, DD/MM/YYYY HH:mm')}</Text>
      </Group>

      {/* Row 1 — KPI cards + weather */}
      <Grid>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <WeatherCard weather={weather} />
        </Grid.Col>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <KpiCard
            label="קריאות פתוחות" value={openCalls.length}
            sub={criticalCalls.length > 0 ? `${criticalCalls.length} קריטיות` : undefined}
            icon="🔧" color={openCalls.length > 5 ? 'red' : 'orange'}
            onClick={() => navigate('/calls')}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <KpiCard
            label="קריאות קריטיות" value={criticalCalls.length}
            icon="🚨" color={criticalCalls.length > 0 ? 'red' : 'green'}
            onClick={() => navigate('/calls')}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <KpiCard
            label="טכנאים זמינים" value={`${availableTechs.length}/${activeTechs.length}`}
            sub={onCallTech ? `תורן: ${onCallTech.name}` : 'אין תורן'}
            icon="👷" color={availableTechs.length === 0 ? 'red' : 'teal'}
            onClick={() => navigate('/technicians')}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <KpiCard
            label="תחזוקה בפיגור" value={overdueMaintenance.length}
            icon="⚠️" color={overdueMaintenance.length > 0 ? 'orange' : 'green'}
          />
        </Grid.Col>
        <Grid.Col span={{ base: 6, sm: 4, md: 2 }}>
          <KpiCard
            label="סה״כ מעליות" value={elevators.length}
            sub={`${elevators.filter(e => e.status === 'ACTIVE').length} פעילות`}
            icon="🏗️" color="blue"
            onClick={() => navigate('/elevators')}
          />
        </Grid.Col>
      </Grid>

      {/* Row 2 — Alerts */}
      {(missingLabor > 0 || debtElevators > 0 || highRisk > 0 || criticalCalls.length > 0) && (
        <Grid>
          {criticalCalls.length > 0 && (
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Alert color="red" variant="light" title="קריאות קריטיות פתוחות" style={{ cursor: 'pointer' }} onClick={() => navigate('/calls')}>
                <Text size="sm">{criticalCalls.length} קריאות דורשות טיפול מיידי</Text>
              </Alert>
            </Grid.Col>
          )}
          {missingLabor > 0 && (
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Alert color="yellow" variant="light" title="נתונים חסרים">
                <Text size="sm">{missingLabor} מעליות ללא מס׳ מ.ע</Text>
                {missingService > 0 && <Text size="sm">{missingService} ללא סוג שירות</Text>}
              </Alert>
            </Grid.Col>
          )}
          {debtElevators > 0 && (
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Alert color="orange" variant="light" title="חוב פתוח">
                <Text size="sm">{debtElevators} מעליות עם חוב מסומן</Text>
              </Alert>
            </Grid.Col>
          )}
          {highRisk > 0 && (
            <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
              <Alert color="red" variant="light" title="סיכון גבוה">
                <Text size="sm">{highRisk} מעליות עם risk score &gt; 50</Text>
              </Alert>
            </Grid.Col>
          )}
        </Grid>
      )}

      {/* Row 3 — Open calls + Technician status */}
      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Group justify="space-between" mb="sm">
              <Title order={4}>קריאות שירות פתוחות</Title>
              <Badge size="sm" color="gray" variant="light">{openCalls.length} קריאות</Badge>
            </Group>
            {callsLoading ? (
              <Center h={180}><Loader /></Center>
            ) : openCalls.length === 0 ? (
              <Center h={180}><Stack align="center" gap="xs"><Text size="2rem">🎉</Text><Text c="dimmed">אין קריאות פתוחות</Text></Stack></Center>
            ) : (
              <ScrollArea h={220}>
                <Table striped fz="xs" withTableBorder withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>עדיפות</Table.Th>
                      <Table.Th>תיאור</Table.Th>
                      <Table.Th>סוג תקלה</Table.Th>
                      <Table.Th>סטטוס</Table.Th>
                      <Table.Th>נפתח</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {openCalls.slice(0, 12).map(call => (
                      <Table.Tr
                        key={call.id}
                        style={{ cursor: 'pointer' }}
                        onClick={() => navigate(`/calls/${call.id}`)}
                      >
                        <Table.Td>
                          <Badge color={PRIORITY_COLORS[call.priority]} size="xs">
                            {PRIORITY_LABELS[call.priority]}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" lineClamp={1}>{call.description}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{faultLabels[call.fault_type] ?? call.fault_type}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge color={CALL_STATUS_COLORS[call.status]} variant="light" size="xs">
                            {CALL_STATUS_LABELS[call.status]}
                          </Badge>
                        </Table.Td>
                        <Table.Td><Text size="xs" c="dimmed">{formatDate(call.created_at)}</Text></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}
          </Paper>
        </Grid.Col>

        {/* Technician cards */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="sm">טכנאים</Title>
            <Stack gap="xs">
              {activeTechs.length === 0 ? (
                <Text c="dimmed" size="sm">אין טכנאים פעילים</Text>
              ) : activeTechs.map(t => (
                <Paper key={t.id} withBorder p="xs" radius="sm">
                  <Group justify="space-between" wrap="nowrap">
                    <Stack gap={2}>
                      <Group gap="xs" wrap="nowrap">
                        <Text size="sm" fw={600}>{t.name}</Text>
                        {t.is_on_call && <Badge size="xs" color="teal">תורן</Badge>}
                      </Group>
                      <Text size="xs" c="dimmed">{t.phone ?? 'אין טלפון'}</Text>
                    </Stack>
                    <Badge
                      size="sm"
                      color={t.is_available ? 'green' : 'red'}
                      variant="dot"
                    >
                      {t.is_available ? 'זמין' : 'לא זמין'}
                    </Badge>
                  </Group>
                </Paper>
              ))}
            </Stack>
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Row 4 — Urgent maintenance + Charts */}
      <Grid>
        {/* Urgent service */}
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="sm">תחזוקה דחופה (≤10 ימים)</Title>
            {urgentService.length === 0 ? (
              <Center h={160}><Stack align="center" gap="xs"><Text size="2rem">✅</Text><Text c="dimmed">אין תחזוקה דחופה</Text></Stack></Center>
            ) : (
              <Stack gap="xs">
                {urgentService.map(e => (
                  <Group
                    key={e.id} justify="space-between" p="xs" wrap="nowrap"
                    style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)', cursor: 'pointer' }}
                    onClick={() => navigate(`/elevators/${e.id}`)}
                  >
                    <Stack gap={2}>
                      <Text size="sm" fw={600} lineClamp={1}>{e.address}, {e.city}</Text>
                      <Group gap="xs">
                        {e.internal_number && <Text size="xs" c="dimmed">מס"ד {e.internal_number}</Text>}
                        <Text size="xs" c="dimmed">{e.service_type === 'COMPREHENSIVE' ? 'מקיף' : e.service_type === 'REGULAR' ? 'רגיל' : ''}</Text>
                      </Group>
                    </Stack>
                    <Tooltip label={e.next_service_date ? formatDate(e.next_service_date) : ''}>
                      <Badge size="sm" color={urgencyColor(e.daysUntil)} variant="filled">
                        {urgencyLabel(e.daysUntil)}
                      </Badge>
                    </Tooltip>
                  </Group>
                ))}
              </Stack>
            )}
          </Paper>
        </Grid.Col>

        {/* Calls by status donut */}
        <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="sm">קריאות לפי סטטוס</Title>
            {callsByStatus.length === 0 ? (
              <Center h={180}><Text c="dimmed">אין נתונים</Text></Center>
            ) : (
              <Center>
                <DonutChart
                  data={callsByStatus}
                  size={170}
                  thickness={28}
                  tooltipDataSource="segment"
                  withTooltip
                  withLabelsLine={false}
                />
              </Center>
            )}
          </Paper>
        </Grid.Col>

        {/* Fault type bar */}
        <Grid.Col span={{ base: 12, sm: 6, md: 3 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="sm">תקלות פתוחות לפי סוג</Title>
            {callsByFault.length === 0 ? (
              <Center h={180}><Text c="dimmed">אין תקלות פתוחות</Text></Center>
            ) : (
              <BarChart
                h={180}
                data={callsByFault}
                dataKey="type"
                series={[{ name: 'count', color: 'blue.6', label: 'קריאות' }]}
                tickLine="none"
                gridAxis="none"
                withLegend={false}
                withTooltip
                barProps={{ radius: 4 }}
              />
            )}
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Row 5 — City distribution + Elevator status ring */}
      <Grid>
        {/* City distribution */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md" radius="md">
            <Title order={4} mb="sm">התפלגות מעליות לפי עיר (Top 5)</Title>
            <Stack gap="xs">
              {topCities.map(([city, count]) => (
                <div key={city}>
                  <Group justify="space-between" mb={2}>
                    <Text size="sm">{city}</Text>
                    <Text size="sm" fw={600}>{count}</Text>
                  </Group>
                  <Progress
                    value={elevators.length > 0 ? (count / elevators.length) * 100 : 0}
                    size="sm" radius="xl"
                    color="blue"
                  />
                </div>
              ))}
            </Stack>
          </Paper>
        </Grid.Col>

        {/* Elevator status ring */}
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Paper withBorder p="md" radius="md" h="100%">
            <Title order={4} mb="sm">סטטוס מעליות</Title>
            <Group justify="center" gap="xl" wrap="wrap">
              {[
                { status: 'ACTIVE', label: 'פעילות', color: 'green' },
                { status: 'UNDER_REPAIR', label: 'בתיקון', color: 'orange' },
                { status: 'INACTIVE', label: 'לא פעילות', color: 'gray' },
              ].map(({ status, label, color }) => {
                const count = elevators.filter(e => e.status === status).length
                const pct = elevators.length > 0 ? Math.round((count / elevators.length) * 100) : 0
                return (
                  <Stack key={status} align="center" gap="xs">
                    <RingProgress
                      size={90} thickness={10}
                      sections={[{ value: pct, color }]}
                      label={<Text ta="center" fw={700} size="lg">{count}</Text>}
                    />
                    <Text size="xs" c="dimmed">{label}</Text>
                  </Stack>
                )
              })}
              <Stack align="center" gap="xs">
                <RingProgress
                  size={90} thickness={10}
                  sections={[{ value: elevators.length > 0 ? Math.round((highRisk / elevators.length) * 100) : 0, color: 'red' }]}
                  label={<Text ta="center" fw={700} size="lg">{highRisk}</Text>}
                />
                <Text size="xs" c="dimmed">סיכון גבוה</Text>
              </Stack>
            </Group>
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
