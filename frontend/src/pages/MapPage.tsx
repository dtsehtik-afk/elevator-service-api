import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Popup, Marker, Tooltip } from 'react-leaflet'
import { Stack, Title, Group, Text, Badge, Paper, Loader, Center, Switch } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import { listCalls } from '../api/calls'
import { getMe } from '../api/auth'
import { listTechnicians } from '../api/technicians'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

import { useState } from 'react'

// Build a coloured SVG pin for technicians
function techIcon(color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="
      width:36px;height:36px;border-radius:50% 50% 50% 0;
      background:${color};border:3px solid white;
      transform:rotate(-45deg);
      box-shadow:0 2px 6px rgba(0,0,0,.4)">
    </div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 36],
    popupAnchor: [0, -38],
  })
}

function staleness(ts: string | null): { label: string; color: string } {
  if (!ts) return { label: 'לא ידוע', color: '#868e96' }
  const mins = Math.floor((Date.now() - new Date(ts).getTime()) / 60000)
  if (mins < 5)  return { label: `לפני ${mins} דק'`, color: '#2f9e44' }
  if (mins < 30) return { label: `לפני ${mins} דק'`, color: '#f59f00' }
  return { label: `לפני ${mins} דק'`, color: '#e03131' }
}

export default function MapPage() {
  const navigate = useNavigate()
  const [, setDummy] = useState(0) // for re-render
  const [showTechs, setShowTechs] = useState(true)

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe })
  const { data: elevators = [], isLoading: loadingElevs } = useQuery({
    queryKey: ['elevators', 'map'],
    queryFn: () => listElevators({ limit: 2000 }),
  })
  const { data: technicians = [], isLoading: loadingTechs } = useQuery({
    queryKey: ['technicians', 'map'],
    queryFn: listTechnicians,
    refetchInterval: 30000, // refresh every 30s
  })

  // Calls assigned to me (ASSIGNED/IN_PROGRESS) + open unassigned calls
  const { data: myCalls = [], isLoading: loadingMy } = useQuery({
    queryKey: ['calls', 'map', 'mine', me?.id],
    queryFn: () => listCalls({ technician_id: me!.id, limit: 500 }),
    enabled: !!me,
  })
  const { data: openCalls = [], isLoading: loadingOpen } = useQuery({
    queryKey: ['calls', 'map', 'open'],
    queryFn: () => listCalls({ status: 'OPEN', limit: 500 }),
  })

  const isLoading = loadingElevs || loadingMy || loadingOpen || loadingTechs

  const techsWithLocation = useMemo(
    () => technicians.filter(t => t.current_latitude && t.current_longitude),
    [technicians]
  )

  const elevMap = useMemo(() => {
    const m: Record<string, typeof elevators[0]> = {}
    for (const e of elevators) m[e.id] = e
    return m
  }, [elevators])

  // Merge: my active calls + open unassigned (exclude already in myCalls)
  const myCallIds = new Set(myCalls.map(c => c.id))
  const unassigned = openCalls.filter(c => !c.technician_id && !myCallIds.has(c.id))

  type MapCall = { call: typeof myCalls[0]; elev: typeof elevators[0]; mine: boolean }
  const mapped: MapCall[] = useMemo(() => {
    const result: MapCall[] = []
    for (const c of [...myCalls, ...unassigned]) {
      const e = elevMap[c.elevator_id]
      if (!e?.latitude || !e?.longitude) continue
      if (['CLOSED', 'CANCELLED'].includes(c.status)) continue
      result.push({ call: c, elev: e, mine: myCallIds.has(c.id) })
    }
    return result
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [myCalls, unassigned, elevMap])

  const center: [number, number] = mapped.length > 0
    ? [mapped.reduce((s, m) => s + m.elev.latitude!, 0) / mapped.length,
       mapped.reduce((s, m) => s + m.elev.longitude!, 0) / mapped.length]
    : [32.08, 34.78]

  const priorityLabel = (p: string) =>
    p === 'LOW' ? 'נמוך' : p === 'MEDIUM' ? 'בינוני' : p === 'HIGH' ? 'גבוה' : 'קריטי'

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={2}>🗺️ מפת קריאות ({mapped.length})</Title>
      </Group>

      <Group gap="xs" justify="space-between">
        <Group gap="xs">
          <Badge color="blue" variant="light">🔵 הקריאות שלי ({myCalls.filter(c => !['CLOSED','CANCELLED'].includes(c.status) && elevMap[c.elevator_id]?.latitude).length})</Badge>
          <Badge color="red" variant="light">🔴 ממתינות לשיוך ({unassigned.filter(c => elevMap[c.elevator_id]?.latitude).length})</Badge>
          <Badge color="green" variant="light">📍 טכנאים עם מיקום ({techsWithLocation.length})</Badge>
        </Group>
        <Switch
          label="הצג טכנאים"
          checked={showTechs}
          onChange={e => setShowTechs(e.currentTarget.checked)}
        />
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
          {mapped.map(({ call: c, elev: e, mine }) => (
            <CircleMarker
              key={c.id}
              center={[e.latitude!, e.longitude!]}
              radius={12}
              pathOptions={{
                color: 'white',
                fillColor: mine ? '#1c7ed6' : '#c92a2a',
                fillOpacity: 1,
                weight: 2,
              }}
            >
              <Popup>
                <div style={{ minWidth: 190, fontFamily: 'sans-serif', direction: 'rtl' }}>
                  <b>📍 {e.address}, {e.city}</b><br />
                  {e.internal_number && <><small>מס"ד: {e.internal_number}</small><br /></>}
                  <small>סטטוס: {c.status}</small><br />
                  <small>עדיפות: {priorityLabel(c.priority)}</small><br />
                  {c.description && <><small>{c.description.slice(0, 60)}</small><br /></>}
                  <a href={`https://waze.com/ul?ll=${e.latitude},${e.longitude}&navigate=yes`}
                     target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>🚘 Waze</a>
                  &nbsp;
                  <a href="#" onClick={e2 => { e2.preventDefault(); navigate(`/calls/${c.id}`) }}
                     style={{ fontSize: 12 }}>📋 פרטים</a>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {showTechs && techsWithLocation.map(t => {
            const { label, color } = staleness(t.last_location_at)
            const lat = t.current_latitude!
            const lng = t.current_longitude!
            return (
              <Marker key={t.id} position={[lat, lng]} icon={techIcon(color)}>
                <Tooltip permanent direction="top" offset={[0, -38]}
                  className="" opacity={0.95}>
                  <span style={{ fontWeight: 600, fontSize: 12 }}>{t.name}</span>
                </Tooltip>
                <Popup>
                  <div style={{ minWidth: 210, fontFamily: 'sans-serif', direction: 'rtl' }}>
                    <b>👷 {t.name}</b><br />
                    <small style={{ color }}>⏱ {label}</small><br />
                    <small style={{ color: '#555' }}>
                      {lat.toFixed(6)}, {lng.toFixed(6)}
                    </small><br />
                    <div style={{ marginTop: 6, display: 'flex', gap: 8 }}>
                      <a href={`https://maps.google.com/?q=${lat},${lng}`}
                         target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>🗺 Google Maps</a>
                      <a href={`https://waze.com/ul?ll=${lat},${lng}`}
                         target="_blank" rel="noreferrer" style={{ fontSize: 12 }}>🚘 Waze</a>
                    </div>
                  </div>
                </Popup>
              </Marker>
            )
          })}
        </MapContainer>
      </Paper>
    </Stack>
  )
}
