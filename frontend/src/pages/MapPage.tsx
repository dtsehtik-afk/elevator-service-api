import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Stack, Title, Group, Select, Text, Badge, Button, Paper, Box } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import { ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS } from '../utils/constants'

// Fix leaflet default marker icons broken by webpack
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

function makeIcon(color: string) {
  const svg = encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="36" viewBox="0 0 24 36">
      <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24S24 21 24 12C24 5.4 18.6 0 12 0z" fill="${color}" stroke="white" stroke-width="1.5"/>
      <circle cx="12" cy="12" r="5" fill="white" opacity="0.9"/>
    </svg>`)
  return L.icon({
    iconUrl: `data:image/svg+xml,${svg}`,
    iconSize: [24, 36],
    iconAnchor: [12, 36],
    popupAnchor: [0, -36],
  })
}

const ICON_GREEN  = makeIcon('#2f9e44')
const ICON_ORANGE = makeIcon('#f08c00')
const ICON_RED    = makeIcon('#c92a2a')
const ICON_GRAY   = makeIcon('#868e96')

function elevatorIcon(risk: number, status: string) {
  if (status !== 'ACTIVE') return ICON_GRAY
  if (risk >= 60) return ICON_RED
  if (risk >= 30) return ICON_ORANGE
  return ICON_GREEN
}

function FitBounds({ positions }: { positions: [number, number][] }) {
  const map = useMap()
  useMemo(() => {
    if (positions.length > 0) {
      map.fitBounds(positions, { padding: [40, 40], maxZoom: 14 })
    }
  }, [])
  return null
}

export default function MapPage() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [cityFilter, setCityFilter] = useState<string | null>(null)

  const { data: elevators = [], isLoading } = useQuery({
    queryKey: ['elevators', 'map'],
    queryFn: () => listElevators({ limit: 2000 }),
  })

  const cities = useMemo(() => {
    const s = new Set(elevators.map(e => e.city).filter(Boolean))
    return Array.from(s).sort().map(c => ({ value: c, label: c }))
  }, [elevators])

  const mapped = useMemo(() =>
    elevators.filter(e => {
      if (!e.latitude || !e.longitude) return false
      if (statusFilter && e.status !== statusFilter) return false
      if (cityFilter && e.city !== cityFilter) return false
      return true
    }), [elevators, statusFilter, cityFilter])

  const positions = mapped.map(e => [e.latitude!, e.longitude!] as [number, number])

  const center: [number, number] = positions.length > 0
    ? [positions.reduce((s, p) => s + p[0], 0) / positions.length,
       positions.reduce((s, p) => s + p[1], 0) / positions.length]
    : [32.08, 34.78]

  const noGeo = elevators.filter(e => !e.latitude || !e.longitude).length

  return (
    <Stack gap="md" h="100%">
      <Group justify="space-between">
        <Title order={2}>🗺️ מפת מעליות ({mapped.length})</Title>
        <Group gap="sm">
          <Select placeholder="סטטוס" clearable w={140}
            data={[
              { value: 'ACTIVE', label: 'פעילה' },
              { value: 'INACTIVE', label: 'לא פעילה' },
              { value: 'UNDER_REPAIR', label: 'בתיקון' },
            ]}
            value={statusFilter} onChange={setStatusFilter}
          />
          <Select placeholder="עיר" clearable w={150} searchable
            data={cities} value={cityFilter} onChange={setCityFilter}
          />
        </Group>
      </Group>

      <Group gap="xs">
        <Badge color="green" variant="light">🟢 סיכון נמוך</Badge>
        <Badge color="orange" variant="light">🟠 סיכון בינוני</Badge>
        <Badge color="red" variant="light">🔴 סיכון גבוה</Badge>
        <Badge color="gray" variant="light">⬜ לא פעילה</Badge>
        {noGeo > 0 && <Text size="xs" c="dimmed">{noGeo} מעליות ללא קואורדינטות לא מוצגות</Text>}
      </Group>

      <Paper withBorder radius="md" style={{ overflow: 'hidden', flex: 1, minHeight: 500 }}>
        {isLoading ? (
          <Box h={500} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Text>טוען מפה...</Text>
          </Box>
        ) : (
          <MapContainer
            center={center}
            zoom={10}
            style={{ height: 600, width: '100%' }}
            scrollWheelZoom
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {positions.length > 0 && <FitBounds positions={positions} />}
            {mapped.map(e => (
              <Marker
                key={e.id}
                position={[e.latitude!, e.longitude!]}
                icon={elevatorIcon(e.risk_score, e.status)}
              >
                <Popup>
                  <Stack gap={4} style={{ minWidth: 180 }}>
                    <Text fw={700} size="sm">📍 {e.address}, {e.city}</Text>
                    {e.internal_number && <Text size="xs" c="dimmed">מס"ד: {e.internal_number}</Text>}
                    <Group gap={4}>
                      <Badge color={ELEVATOR_STATUS_COLORS[e.status]} size="xs">
                        {ELEVATOR_STATUS_LABELS[e.status]}
                      </Badge>
                      {e.risk_score > 0 && (
                        <Badge color={e.risk_score >= 60 ? 'red' : e.risk_score >= 30 ? 'orange' : 'green'} size="xs">
                          סיכון {Math.round(e.risk_score)}
                        </Badge>
                      )}
                    </Group>
                    {e.management_company_name && (
                      <Text size="xs" c="dimmed">🏗️ {e.management_company_name}</Text>
                    )}
                    <button
                      onClick={() => navigate(`/elevators/${e.id}`)}
                      style={{
                        marginTop: 6, padding: '4px 8px', background: '#228be6',
                        color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                      }}
                    >
                      פתח פרטי מעלית
                    </button>
                  </Stack>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        )}
      </Paper>
    </Stack>
  )
}
