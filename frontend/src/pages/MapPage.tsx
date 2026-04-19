import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Stack, Title, Group, Select, Text, Badge, Paper, Box, Loader, Center } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import { ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS } from '../utils/constants'

// Leaflet loaded lazily to avoid SSR/module issues
let leafletLoaded = false
function ensureLeaflet(cb: () => void) {
  if (leafletLoaded) { cb(); return }
  const link = document.createElement('link')
  link.rel = 'stylesheet'
  link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
  document.head.appendChild(link)
  const script = document.createElement('script')
  script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
  script.onload = () => { leafletLoaded = true; cb() }
  document.head.appendChild(script)
}

function riskColor(risk: number, status: string) {
  if (status !== 'ACTIVE') return '#868e96'
  if (risk >= 60) return '#c92a2a'
  if (risk >= 30) return '#f08c00'
  return '#2f9e44'
}

export default function MapPage() {
  const navigate = useNavigate()
  const mapRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [mapReady, setMapReady] = useState(false)
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

  // Init map once
  useEffect(() => {
    ensureLeaflet(() => {
      if (mapRef.current || !containerRef.current) return
      const L = (window as any).L
      const map = L.map(containerRef.current, { zoomControl: true })
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
      }).addTo(map)
      map.setView([32.08, 34.78], 9)
      mapRef.current = map
      setMapReady(true)
    })
    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }
    }
  }, [])

  // Update markers when data/filters change
  useEffect(() => {
    if (!mapReady || !mapRef.current) return
    const L = (window as any).L
    const map = mapRef.current

    // Remove old markers layer
    if ((map as any)._markersLayer) map.removeLayer((map as any)._markersLayer)
    const layer = L.layerGroup().addTo(map)
    ;(map as any)._markersLayer = layer

    const bounds: [number, number][] = []
    mapped.forEach(e => {
      const color = riskColor(e.risk_score, e.status)
      const icon = L.divIcon({
        className: '',
        html: `<div style="width:22px;height:22px;border-radius:50%;background:${color};border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.4)"></div>`,
        iconSize: [22, 22], iconAnchor: [11, 11],
      })
      const marker = L.marker([e.latitude, e.longitude], { icon }).addTo(layer)
      const waze = `https://waze.com/ul?ll=${e.latitude},${e.longitude}&navigate=yes`
      marker.bindPopup(`
        <div style="min-width:170px;font-family:sans-serif;direction:rtl">
          <b>📍 ${e.address}, ${e.city}</b><br>
          ${e.internal_number ? `<small>מס"ד: ${e.internal_number}</small><br>` : ''}
          ${e.management_company_name ? `<small>🏗️ ${e.management_company_name}</small><br>` : ''}
          <small>סיכון: ${Math.round(e.risk_score)}</small><br>
          <a href="${waze}" target="_blank" style="font-size:12px">🚘 Waze</a>
          &nbsp;
          <a href="#" onclick="event.preventDefault();window.__navToElev('${e.id}')" style="font-size:12px">📋 פרטים</a>
        </div>
      `)
      bounds.push([e.latitude!, e.longitude!])
    })

    if (bounds.length > 0) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 })
  }, [mapped, mapReady])

  // Expose navigation callback for popup links
  useEffect(() => {
    ;(window as any).__navToElev = (id: string) => navigate(`/elevators/${id}`)
    return () => { delete (window as any).__navToElev }
  }, [navigate])

  const noGeo = elevators.filter(e => !e.latitude || !e.longitude).length

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

      <Paper withBorder radius="md" style={{ overflow: 'hidden' }}>
        {isLoading && <Center h={500}><Loader /></Center>}
        <Box ref={containerRef} style={{ height: 600, width: '100%', display: isLoading ? 'none' : 'block' }} />
      </Paper>
    </Stack>
  )
}
