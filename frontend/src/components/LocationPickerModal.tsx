import { useEffect, useRef, useState } from 'react'
import { Modal, Button, Group, Text, Stack, Box, Loader, Center } from '@mantine/core'

interface Props {
  opened: boolean
  onClose: () => void
  onSave: (lat: number, lng: number) => void
  initialLat?: number | null
  initialLng?: number | null
  loading?: boolean
}

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

export default function LocationPickerModal({ opened, onClose, onSave, initialLat, initialLng, loading }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const markerRef = useRef<any>(null)
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(
    initialLat && initialLng ? { lat: initialLat, lng: initialLng } : null
  )
  const [gpsLoading, setGpsLoading] = useState(false)

  // Init map when modal opens
  useEffect(() => {
    if (!opened) return
    let cancelled = false

    function initMap() {
      if (cancelled || !containerRef.current) return
      const container = containerRef.current
      if ((container as any)._leaflet_id) delete (container as any)._leaflet_id
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }

      const L = (window as any).L
      const defaultCenter: [number, number] = initialLat && initialLng
        ? [initialLat, initialLng] : [32.08, 34.78]
      const map = L.map(container).setView(defaultCenter, initialLat ? 16 : 9)
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
      }).addTo(map)
      mapRef.current = map

      // Place existing marker
      if (initialLat && initialLng) {
        markerRef.current = L.marker([initialLat, initialLng], { draggable: true }).addTo(map)
        markerRef.current.on('dragend', (e: any) => {
          const p = e.target.getLatLng()
          if (!cancelled) setCoords({ lat: +p.lat.toFixed(6), lng: +p.lng.toFixed(6) })
        })
      }

      // Click to place / move marker
      map.on('click', (e: any) => {
        if (cancelled) return
        const { lat, lng } = e.latlng
        const rounded = { lat: +lat.toFixed(6), lng: +lng.toFixed(6) }
        if (markerRef.current) {
          markerRef.current.setLatLng([rounded.lat, rounded.lng])
        } else {
          markerRef.current = L.marker([rounded.lat, rounded.lng], { draggable: true }).addTo(map)
          markerRef.current.on('dragend', (ev: any) => {
            const p = ev.target.getLatLng()
            if (!cancelled) setCoords({ lat: +p.lat.toFixed(6), lng: +p.lng.toFixed(6) })
          })
        }
        setCoords(rounded)
      })
    }

    // Small delay to let the modal finish animating before Leaflet measures the container
    const timer = setTimeout(() => {
      if ((window as any).L) initMap()
      else ensureLeaflet(initMap)
    }, 100)

    return () => {
      cancelled = true
      clearTimeout(timer)
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }
      markerRef.current = null
    }
  }, [opened])

  function useGPS() {
    if (!navigator.geolocation) return
    setGpsLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGpsLoading(false)
        const { latitude: lat, longitude: lng } = pos.coords
        const rounded = { lat: +lat.toFixed(6), lng: +lng.toFixed(6) }
        setCoords(rounded)
        const L = (window as any).L
        if (!mapRef.current || !L) return
        mapRef.current.setView([rounded.lat, rounded.lng], 17)
        if (markerRef.current) {
          markerRef.current.setLatLng([rounded.lat, rounded.lng])
        } else {
          markerRef.current = L.marker([rounded.lat, rounded.lng], { draggable: true }).addTo(mapRef.current)
          markerRef.current.on('dragend', (e: any) => {
            const p = e.target.getLatLng()
            setCoords({ lat: +p.lat.toFixed(6), lng: +p.lng.toFixed(6) })
          })
        }
      },
      () => setGpsLoading(false),
      { enableHighAccuracy: true, timeout: 10000 }
    )
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="📍 עדכן מיקום מעלית"
      size="lg"
      dir="rtl"
    >
      <Stack gap="sm">
        <Text size="sm" c="dimmed">לחץ על המפה לסימון מיקום, גרור את הסמן לדיוק, או השתמש ב-GPS</Text>

        <Box ref={containerRef} style={{ height: 380, width: '100%', borderRadius: 8, overflow: 'hidden' }} />

        {coords && (
          <Text size="xs" c="dimmed" ta="center">
            {coords.lat}, {coords.lng}
          </Text>
        )}

        <Group justify="space-between">
          <Button
            variant="light"
            color="teal"
            leftSection={<span>📡</span>}
            onClick={useGPS}
            loading={gpsLoading}
          >
            השתמש במיקום שלי (GPS)
          </Button>
          <Group gap="xs">
            <Button variant="default" onClick={onClose}>ביטול</Button>
            <Button
              disabled={!coords}
              loading={loading}
              onClick={() => coords && onSave(coords.lat, coords.lng)}
            >
              שמור מיקום
            </Button>
          </Group>
        </Group>
      </Stack>
    </Modal>
  )
}
