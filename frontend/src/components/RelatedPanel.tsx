import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Paper, Text, Group, Badge, Stack, Anchor, Loader, Divider, SimpleGrid } from '@mantine/core'
import { erpApi } from '../api/erp'

interface RelatedPanelProps {
  entityType: 'elevator' | 'customer' | 'contract'
  entityId: string
}

interface LinkItem {
  id: string
  label: string
  sub?: string
  badge?: string
  badgeColor?: string
  path?: string
}

interface RelatedSection {
  title: string
  icon: string
  items: LinkItem[]
  path?: string
}

export default function RelatedPanel({ entityType, entityId }: RelatedPanelProps) {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    setLoading(true)
    erpApi.related(entityType, entityId)
      .then(setData)
      .finally(() => setLoading(false))
  }, [entityType, entityId])

  if (loading) return <Loader size="sm" />
  if (!data) return null

  const sections: RelatedSection[] = buildSections(entityType, data)

  return (
    <Paper withBorder p="md" radius="md">
      <Text fw={600} size="sm" mb="md" c="dimmed">🔗 קישורים מהירים</Text>
      <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="xs">
        {sections.map((section) => (
          <Stack key={section.title} gap={4}>
            <Group gap={4}>
              <Text size="xs">{section.icon}</Text>
              <Text size="xs" fw={600} c="dimmed">{section.title}</Text>
            </Group>
            {section.items.length === 0 ? (
              <Text size="xs" c="dimmed" pl="sm">—</Text>
            ) : (
              section.items.map((item, i) => (
                <Group key={i} gap={4} pl="sm">
                  {item.path ? (
                    <Anchor size="xs" onClick={() => navigate(item.path!)} style={{ cursor: 'pointer' }}>
                      {item.label}
                    </Anchor>
                  ) : (
                    <Text size="xs">{item.label}</Text>
                  )}
                  {item.sub && <Text size="xs" c="dimmed">{item.sub}</Text>}
                  {item.badge && (
                    <Badge size="xs" color={item.badgeColor || 'gray'}>{item.badge}</Badge>
                  )}
                </Group>
              ))
            )}
          </Stack>
        ))}
      </SimpleGrid>
    </Paper>
  )
}

function buildSections(entityType: string, data: any): RelatedSection[] {
  const links = data.links || data

  if (entityType === 'elevator') {
    return [
      {
        title: 'לקוח',
        icon: '👤',
        items: links.customer
          ? [{ id: links.customer.id, label: links.customer.name, path: `/customers/${links.customer.id}` }]
          : [],
      },
      {
        title: 'חברת ניהול',
        icon: '🏗️',
        items: links.management_company
          ? [{ id: links.management_company.id, label: links.management_company.name, path: `/management-companies` }]
          : [],
      },
      {
        title: 'קריאות פתוחות',
        icon: '🔧',
        items: links.open_service_calls > 0
          ? [{ id: 'calls', label: `${links.open_service_calls} קריאות`, path: `/calls` }]
          : [],
      },
      {
        title: 'חוזים',
        icon: '📋',
        items: (links.contracts || []).map((c: any) => ({
          id: c.id,
          label: c.number,
          badge: c.status,
          badgeColor: c.status === 'ACTIVE' ? 'green' : 'gray',
          path: `/contracts/${c.id}`,
        })),
      },
      {
        title: 'חשבוניות',
        icon: '💰',
        items: (links.invoices || []).slice(0, 3).map((inv: any) => ({
          id: inv.id,
          label: inv.number,
          sub: `₪${inv.total.toLocaleString()}`,
          badge: inv.status,
          badgeColor: statusColor(inv.status),
          path: `/invoices/${inv.id}`,
        })),
      },
    ]
  }

  if (entityType === 'customer') {
    return [
      {
        title: 'לקוח אב',
        icon: '👥',
        items: links.parent
          ? [{ id: links.parent.id, label: links.parent.name, path: `/customers/${links.parent.id}` }]
          : [],
      },
      {
        title: 'לקוחות משנה',
        icon: '👤',
        items: (links.children || []).map((c: any) => ({
          id: c.id,
          label: c.name,
          sub: c.type,
          path: `/customers/${c.id}`,
        })),
      },
      {
        title: 'מעליות',
        icon: '🏢',
        items: (links.elevators || []).slice(0, 4).map((e: any) => ({
          id: e.id,
          label: e.address,
          sub: e.city,
          badge: e.status === 'ACTIVE' ? undefined : e.status,
          path: `/elevators/${e.id}`,
        })),
      },
      {
        title: 'בניינים',
        icon: '🏗️',
        items: (links.buildings || []).map((b: any) => ({
          id: b.id,
          label: b.address,
          sub: b.city,
        })),
      },
      {
        title: 'חוזים',
        icon: '📋',
        items: (links.contracts || []).map((c: any) => ({
          id: c.id,
          label: c.number,
          badge: c.status,
          badgeColor: c.status === 'ACTIVE' ? 'green' : 'gray',
          path: `/contracts/${c.id}`,
        })),
      },
      {
        title: 'חשבוניות',
        icon: '💰',
        items: (links.invoices || []).slice(0, 3).map((inv: any) => ({
          id: inv.id,
          label: inv.number,
          sub: `₪${Number(inv.total).toLocaleString()}`,
          badge: inv.status,
          badgeColor: statusColor(inv.status),
          path: `/invoices/${inv.id}`,
        })),
      },
    ]
  }

  if (entityType === 'contract') {
    return [
      {
        title: 'לקוח',
        icon: '👤',
        items: links.customer
          ? [{ id: links.customer.id, label: links.customer.name, path: `/customers/${links.customer.id}` }]
          : [],
      },
      {
        title: 'מעליות',
        icon: '🏢',
        items: (links.elevators || []).map((e: any) => ({
          id: e.id,
          label: e.address,
          path: `/elevators/${e.id}`,
        })),
      },
      {
        title: 'הצעות מחיר',
        icon: '📄',
        items: (links.quotes || []).map((q: any) => ({
          id: q.id,
          label: q.number,
          badge: q.status,
          path: `/quotes/${q.id}`,
        })),
      },
      {
        title: 'חשבוניות',
        icon: '💰',
        items: (links.invoices || []).slice(0, 3).map((inv: any) => ({
          id: inv.id,
          label: inv.number,
          sub: `₪${Number(inv.total).toLocaleString()}`,
          badge: inv.status,
          badgeColor: statusColor(inv.status),
          path: `/invoices/${inv.id}`,
        })),
      },
    ]
  }

  return []
}

function statusColor(status: string): string {
  switch (status) {
    case 'PAID': return 'green'
    case 'OVERDUE': return 'red'
    case 'PARTIAL': return 'orange'
    case 'SENT': return 'blue'
    case 'DRAFT': return 'gray'
    default: return 'gray'
  }
}
