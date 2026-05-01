import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import { Stack, Title, Group, Text, Badge, Paper, Loader, Center } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listElevators } from '../api/elevators'
import { listCalls } from '../api/calls'
import { getMe } from '../api/auth'
import 'leaflet/dist/leaflet.css'

import { useState } from 'react'

export default function MapPage() {
  const navigate = useNavigate()
  const [, setDummy] = useState(0) // for re-render

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: getMe })
  const { data: elevators = [], isLoading: loadingElevs } = useQuery({
    queryKey: ['elevators', 'map'],
    queryFn: () => listElevators({ limit: 2000 }),
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

  const isLoading = loadingElevs || loadingMy || loadingOpen

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

      <Group gap="xs">
        <Badge color="blue" variant="light">🔵 הקריאות שלי ({myCalls.filter(c => !['CLOSED','CANCELLED'].includes(c.status) && elevMap[c.elevator_id]?.latitude).length})</Badge>
        <Badge color="red" variant="light">🔴 ממתינות לשיוך ({unassigned.filter(c => elevMap[c.elevator_id]?.latitude).length})</Badge>
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
        </MapContainer>
      </Paper>
    </Stack>
  )
}
