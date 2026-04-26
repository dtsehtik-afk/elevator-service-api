import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import { Stack, Title, Group, Select, Text, Badge, Paper, Loader, Center } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import 'leaflet/dist/leaflet.css'

function riskColor(risk: number, status: string): string {
  if (status !== 'ACTIVE') return '#868e96'
  if (risk >= 60) return '#c92a2a'
  if (risk >= 30) return '#f08c00'
  return '#2f9e44'
}

import { useState } from 'react'

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

  const noGeo = elevators.filter(e => !e.latitude || !e.longitude).length

  const center: [number, number] = mapped.length > 0
    ? [mapped.reduce((s, e) => s + e.latitude!, 0) / mapped.length,
       mapped.reduce((s, e) => s + e.longitude!, 0) / mapped.length]
    : [32.08, 34.78]

  return (
    <Stack gap="md">
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

      <Paper withBorder radius="md" style={{ overflow: 'hidden', position: 'relative' }}>
        {isLoading && (
          <Center style={{ position: 'absolute', inset: 0, zIndex: 1000, background: 'rgba(255,255,255,0.7)' }}>
            <Loader />
          </Center>
        )}
        <MapContainer
          center={center}
          zoom={9}
          style={{ height: 600, width: '100%' }}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="© OpenStreetMap"
          />
          {mapped.map(e => (
            <CircleMarker
              key={e.id}
              center={[e.latitude!, e.longitude!]}
              radius={10}
              pathOptions={{
                color: 'white',
                fillColor: riskColor(e.risk_score, e.status),
                fillOpacity: 1,
                weight: 2,
              }}
            >
              <Popup>
                <div style={{ minWidth: 170, fontFamily: 'sans-serif', direction: 'rtl' }}>
                  <b>📍 {e.address}, {e.city}</b><br />
                  {e.internal_number && <><small>מס"ד: {e.internal_number}</small><br /></>}
                  {e.management_company_name && <><small>🏗️ {e.management_company_name}</small><br /></>}
                  <small>סיכון: {Math.round(e.risk_score ?? 0)}</small><br />
                  <a href={`https://waze.com/ul?ll=${e.latitude},${e.longitude}&navigate=yes`}
                     target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>🚘 Waze</a>
                  &nbsp;
                  <a href="#" onClick={e2 => { e2.preventDefault(); navigate(`/elevators/${e.id}`) }}
                     style={{ fontSize: 12 }}>📋 פרטים</a>
                </div>
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </Paper>
    </Stack>
  )
}
