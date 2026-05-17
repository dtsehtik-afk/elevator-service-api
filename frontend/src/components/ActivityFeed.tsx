import { useEffect, useState } from 'react'
import { Stack, Text, Group, Badge, Anchor, Loader, Paper, ThemeIcon, Box } from '@mantine/core'
import client from '../api/client'

interface ActivityEntry {
  id: string
  actor_name: string | null
  action: string
  message: string
  entity_type: string | null
  entity_id: string | null
  entity_ref: string | null
  category: string
  created_at: string
}

const ACTION_ICONS: Record<string, string> = {
  call_opened: '📞',
  call_assigned: '👤',
  assignment_confirmed: '✅',
  assignment_rejected: '❌',
  call_in_progress: '🔧',
  call_resolved: '✔️',
  call_closed: '🔒',
  call_monitoring: '👁️',
  part_requested: '📦',
  part_approved: '✅',
  part_rejected: '❌',
  part_issued: '🏭',
  quote_created: '📝',
  quote_sent: '📤',
  quote_accepted: '🤝',
  quote_rejected: '❌',
  invoice_created: '🧾',
  invoice_paid: '💰',
}

const ACTION_COLORS: Record<string, string> = {
  call_opened: 'blue',
  call_assigned: 'cyan',
  assignment_confirmed: 'green',
  assignment_rejected: 'red',
  call_in_progress: 'orange',
  call_resolved: 'teal',
  call_closed: 'gray',
  call_monitoring: 'violet',
  part_requested: 'yellow',
  part_approved: 'green',
  part_rejected: 'red',
  part_issued: 'indigo',
  quote_created: 'blue',
  quote_sent: 'cyan',
  quote_accepted: 'green',
  quote_rejected: 'red',
  invoice_created: 'blue',
  invoice_paid: 'green',
}

function entityPath(type: string | null, id: string | null): string | null {
  if (!type || !id) return null
  switch (type) {
    case 'service_call': return `/calls?callId=${id}`
    case 'part_request': return `/calls`
    case 'invoice': return `/invoices`
    case 'quote': return `/quotes`
    default: return null
  }
}

function timeAgo(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return 'לפני רגע'
  if (diff < 3600) return `לפני ${Math.floor(diff / 60)} דקות`
  if (diff < 86400) return `לפני ${Math.floor(diff / 3600)} שעות`
  return `לפני ${Math.floor(diff / 86400)} ימים`
}

interface Props {
  category?: string
  limit?: number
  refreshInterval?: number
}

export default function ActivityFeed({ category, limit = 15, refreshInterval = 30000 }: Props) {
  const [entries, setEntries] = useState<ActivityEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = () => {
    const params: Record<string, string | number> = { limit }
    if (category) params.category = category
    client.get('/activity-log', { params })
      .then(r => setEntries(r.data))
      .catch(() => null)
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
    const id = setInterval(load, refreshInterval)
    return () => clearInterval(id)
  }, [category, limit])

  if (loading) return <Loader size="sm" />

  if (entries.length === 0) {
    return <Text size="sm" c="dimmed" ta="center" py="md">אין פעילות אחרונה</Text>
  }

  return (
    <Stack gap={4}>
      {entries.map(e => {
        const icon = ACTION_ICONS[e.action] ?? '🔔'
        const color = ACTION_COLORS[e.action] ?? 'gray'
        const path = entityPath(e.entity_type, e.entity_id)

        return (
          <Box
            key={e.id}
            style={{
              borderRight: `3px solid var(--mantine-color-${color}-5)`,
              paddingRight: 8,
              paddingTop: 4,
              paddingBottom: 4,
            }}
          >
            <Group gap="xs" wrap="nowrap" align="flex-start">
              <Text size="sm" style={{ flexShrink: 0 }}>{icon}</Text>
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text size="sm" style={{ wordBreak: 'break-word' }}>
                  {path
                    ? <Anchor href={path} size="sm" c="inherit" underline="hover">{e.message}</Anchor>
                    : e.message}
                </Text>
                <Group gap="xs" mt={2}>
                  {e.actor_name && (
                    <Text size="xs" c="dimmed">{e.actor_name}</Text>
                  )}
                  <Text size="xs" c="dimmed">{timeAgo(e.created_at)}</Text>
                  {e.entity_ref && (
                    <Badge size="xs" variant="outline" color={color}>{e.entity_ref}</Badge>
                  )}
                </Group>
              </Box>
            </Group>
          </Box>
        )
      })}
    </Stack>
  )
}
