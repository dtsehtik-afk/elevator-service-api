import { useState, useEffect } from 'react'
import {
  Stack, Title, Paper, Tabs, Table, Checkbox, Button, Group, Text,
  Loader, Center, Badge, Alert,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

const ROLES = [
  { value: 'ADMIN', label: 'מנהל מערכת' },
  { value: 'CEO', label: 'מנכ"ל' },
  { value: 'VP', label: 'סמנכ"ל' },
  { value: 'SERVICE_MANAGER', label: 'מנהל שירות' },
  { value: 'DISPATCHER', label: 'מוקדן' },
  { value: 'TECHNICIAN', label: 'טכנאי' },
  { value: 'ACCOUNTANT', label: 'רואה חשבון' },
  { value: 'SECRETARY', label: 'מזכירה' },
  { value: 'SALES', label: 'מכירות' },
  { value: 'INVENTORY_MANAGER', label: 'מנהל מלאי' },
]

const MODULES = [
  { key: 'service_calls', label: 'קריאות שירות' },
  { key: 'invoices', label: 'חשבוניות' },
  { key: 'inventory', label: 'מלאי' },
  { key: 'crm', label: 'לקוחות / CRM' },
  { key: 'hr', label: 'HR' },
  { key: 'reports', label: 'דוחות' },
  { key: 'settings', label: 'הגדרות' },
  { key: 'users', label: 'ניהול משתמשים' },
]

const ACTIONS: Record<string, string[]> = {
  service_calls: ['view', 'create', 'assign', 'close', 'delete'],
  invoices:      ['view', 'create', 'send', 'mark_paid', 'delete'],
  inventory:     ['view', 'manage', 'purchase_orders'],
  crm:           ['view', 'manage'],
  hr:            ['view', 'manage'],
  reports:       ['view', 'export'],
  settings:      ['view', 'edit'],
  users:         ['view', 'manage', 'assign_roles'],
}

const ACTION_LABELS: Record<string, string> = {
  view: 'צפייה',
  create: 'יצירה',
  assign: 'שיבוץ',
  close: 'סגירה',
  delete: 'מחיקה',
  send: 'שליחה',
  mark_paid: 'סימון תשלום',
  manage: 'ניהול',
  purchase_orders: 'הזמנות רכש',
  edit: 'עריכה',
  export: 'ייצוא',
  assign_roles: 'הקצאת תפקידים',
}

type PermissionsMap = Record<string, Record<string, string[]>>

export default function RolesPage() {
  const qc = useQueryClient()
  const [activeRole, setActiveRole] = useState('ADMIN')
  const [localPerms, setLocalPerms] = useState<PermissionsMap | null>(null)
  const [dirty, setDirty] = useState(false)

  const { data: perms, isLoading } = useQuery<PermissionsMap>({
    queryKey: ['role-permissions'],
    queryFn: () => client.get('/settings/roles').then(r => r.data),
  })

  const { data: defaults } = useQuery<PermissionsMap>({
    queryKey: ['role-defaults'],
    queryFn: () => client.get('/settings/roles/defaults').then(r => r.data),
  })

  useEffect(() => {
    if (perms && !localPerms) setLocalPerms(perms)
  }, [perms])

  const saveMutation = useMutation({
    mutationFn: (data: PermissionsMap) => client.put('/settings/roles', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['role-permissions'] })
      setDirty(false)
      notifications.show({ message: 'הרשאות נשמרו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  function toggleAction(role: string, module: string, action: string) {
    setLocalPerms(prev => {
      if (!prev) return prev
      const rolePerms = { ...(prev[role] ?? {}) }
      const actions = [...(rolePerms[module] ?? [])]
      const idx = actions.indexOf(action)
      if (idx >= 0) actions.splice(idx, 1)
      else actions.push(action)
      rolePerms[module] = actions
      return { ...prev, [role]: rolePerms }
    })
    setDirty(true)
  }

  function resetToDefaults() {
    if (!defaults) return
    setLocalPerms(defaults)
    setDirty(true)
  }

  const currentPerms = localPerms ?? perms ?? {}

  if (isLoading) return <Center p="xl"><Loader /></Center>

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>🔐 הרשאות תפקיד</Title>
        <Group>
          <Button variant="subtle" color="orange" onClick={resetToDefaults}>
            איפוס לברירת מחדל
          </Button>
          <Button
            onClick={() => localPerms && saveMutation.mutate(localPerms)}
            loading={saveMutation.isPending}
            disabled={!dirty}
          >
            שמור הגדרות
          </Button>
        </Group>
      </Group>

      {dirty && (
        <Alert color="yellow" title="שינויים לא שמורים">
          יש שינויים שלא נשמרו — לחץ "שמור הגדרות" לשמירה.
        </Alert>
      )}

      <Tabs value={activeRole} onChange={v => setActiveRole(v ?? 'ADMIN')}>
        <Tabs.List>
          {ROLES.map(r => (
            <Tabs.Tab key={r.value} value={r.value}>{r.label}</Tabs.Tab>
          ))}
        </Tabs.List>

        {ROLES.map(role => {
          const rolePerms = currentPerms[role.value] ?? {}
          return (
            <Tabs.Panel key={role.value} value={role.value} pt="md">
              <Paper withBorder radius="md">
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>מודול</Table.Th>
                      {Array.from(new Set(Object.values(ACTIONS).flat())).map(action => (
                        <Table.Th key={action} style={{ textAlign: 'center', whiteSpace: 'nowrap' }}>
                          {ACTION_LABELS[action] ?? action}
                        </Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {MODULES.map(mod => {
                      const allowedActions = ACTIONS[mod.key] ?? []
                      const currentActions = rolePerms[mod.key] ?? []
                      const allActionKeys = Array.from(new Set(Object.values(ACTIONS).flat()))
                      return (
                        <Table.Tr key={mod.key}>
                          <Table.Td>
                            <Text size="sm" fw={500}>{mod.label}</Text>
                          </Table.Td>
                          {allActionKeys.map(action => (
                            <Table.Td key={action} style={{ textAlign: 'center' }}>
                              {allowedActions.includes(action) ? (
                                <Checkbox
                                  checked={currentActions.includes(action)}
                                  onChange={() => toggleAction(role.value, mod.key, action)}
                                />
                              ) : (
                                <Text c="dimmed" size="xs">—</Text>
                              )}
                            </Table.Td>
                          ))}
                        </Table.Tr>
                      )
                    })}
                  </Table.Tbody>
                </Table>
              </Paper>
            </Tabs.Panel>
          )
        })}
      </Tabs>
    </Stack>
  )
}
