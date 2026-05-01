import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Title, SimpleGrid, Card, Text, Badge, Group, Stack, Alert,
  Paper, Table, Loader, Divider, RingProgress, ThemeIcon,
} from '@mantine/core'
import { erpApi } from '../api/erp'
import type { ERPDashboard } from '../types'

function StatCard({ label, value, color, sub, onClick }: { label: string; value: string | number; color?: string; sub?: string; onClick?: () => void }) {
  return (
    <Card withBorder shadow="xs" style={{ cursor: onClick ? 'pointer' : 'default' }} onClick={onClick}>
      <Text size="xs" c="dimmed" mb={4}>{label}</Text>
      <Text fw={700} size="xl" c={color}>{value}</Text>
      {sub && <Text size="xs" c="dimmed">{sub}</Text>}
    </Card>
  )
}

export default function ERPDashboardPage() {
  const navigate = useNavigate()
  const [data, setData] = useState<ERPDashboard | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    erpApi.dashboard().then(setData).finally(() => setLoading(false))
  }, [])

  if (loading) return <Group justify="center" mt="xl"><Loader /></Group>
  if (!data) return <Text c="red">שגיאה בטעינת הדשבורד</Text>

  const alertColor = (level: string) => level === 'error' ? 'red' : level === 'warning' ? 'orange' : 'blue'

  return (
    <>
      <Title order={2} mb="md">🏭 ERP דשבורד</Title>

      {/* Alerts */}
      {data.alerts.length > 0 && (
        <Stack mb="md" gap="xs">
          {data.alerts.map((a, i) => (
            <Alert key={i} color={alertColor(a.level)} py={6}>{a.message}</Alert>
          ))}
        </Stack>
      )}

      {/* Service */}
      <Text size="sm" fw={600} c="dimmed" mb="xs">🔧 שירות שטח</Text>
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="lg">
        <StatCard label="קריאות פתוחות" value={data.service.open_calls}
          color={data.service.open_calls > 0 ? 'orange' : 'green'}
          onClick={() => navigate('/calls')} />
        <StatCard label="קריאות קריטיות" value={data.service.critical_calls}
          color={data.service.critical_calls > 0 ? 'red' : 'green'}
          onClick={() => navigate('/calls')} />
        <StatCard label="תחזוקות באיחור" value={data.service.overdue_maintenance}
          color={data.service.overdue_maintenance > 0 ? 'red' : 'green'}
          onClick={() => navigate('/maintenance')} />
        <StatCard label="תחזוקות קרובות (30 יום)" value={data.service.upcoming_maintenance}
          onClick={() => navigate('/maintenance')} />
      </SimpleGrid>

      <Divider mb="md" />

      {/* CRM */}
      <Text size="sm" fw={600} c="dimmed" mb="xs">👤 CRM</Text>
      <SimpleGrid cols={{ base: 2, sm: 4 }} mb="lg">
        <StatCard label="לקוחות פעילים" value={data.crm.total_customers} onClick={() => navigate('/customers')} />
        <StatCard label="חוזים פעילים" value={data.crm.active_contracts}
          color="green" onClick={() => navigate('/contracts')} />
        <StatCard label="חוזים פגים ב-30 יום" value={data.crm.expiring_contracts}
          color={data.crm.expiring_contracts > 0 ? 'orange' : 'green'}
          onClick={() => navigate('/contracts')} />
        <StatCard label="לידים חדשים" value={data.crm.new_leads}
          color={data.crm.new_leads > 0 ? 'blue' : 'gray'}
          onClick={() => navigate('/leads')} />
      </SimpleGrid>

      <Divider mb="md" />

      {/* Financial */}
      <Text size="sm" fw={600} c="dimmed" mb="xs">💰 פיננסי (החודש)</Text>
      <SimpleGrid cols={{ base: 2, sm: 3 }} mb="lg">
        <StatCard label="הכנסות החודש" value={`₪${Number(data.financial.month_revenue).toLocaleString()}`}
          color="green" onClick={() => navigate('/invoices')} />
        <StatCard label="חובות פתוחים" value={`₪${Number(data.financial.open_receivables).toLocaleString()}`}
          color={data.financial.open_receivables > 0 ? 'orange' : 'green'}
          onClick={() => navigate('/invoices')} />
        <StatCard label="חשבוניות באיחור" value={data.financial.overdue_invoices}
          color={data.financial.overdue_invoices > 0 ? 'red' : 'green'}
          onClick={() => navigate('/invoices?status=OVERDUE')} />
      </SimpleGrid>

      <Divider mb="md" />

      {/* Elevators + Inventory */}
      <SimpleGrid cols={{ base: 1, md: 2 }} mb="lg">
        <Stack>
          <Text size="sm" fw={600} c="dimmed">🏢 מעליות</Text>
          <SimpleGrid cols={3}>
            <StatCard label="פעילות" value={data.elevators.total_active} onClick={() => navigate('/elevators')} />
            <StatCard label="סיכון גבוה" value={data.elevators.high_risk}
              color={data.elevators.high_risk > 0 ? 'red' : 'green'}
              onClick={() => navigate('/elevators')} />
            <StatCard label="עם חוב" value={data.elevators.with_debt}
              color={data.elevators.with_debt > 0 ? 'orange' : 'green'}
              onClick={() => navigate('/elevators')} />
          </SimpleGrid>
        </Stack>
        <Stack>
          <Text size="sm" fw={600} c="dimmed">📦 מלאי</Text>
          <StatCard label="חלקים במלאי נמוך" value={data.inventory.low_stock_parts}
            color={data.inventory.low_stock_parts > 0 ? 'orange' : 'green'}
            sub={data.inventory.low_stock_parts > 0 ? 'דרושה הזמנה' : 'מלאי תקין'}
            onClick={() => navigate('/inventory')} />
        </Stack>
      </SimpleGrid>
    </>
  )
}
