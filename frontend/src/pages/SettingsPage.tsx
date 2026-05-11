import { useState } from 'react'
import {
  Stack, Title, Paper, Table, Switch, TextInput, Button, Group, Text, Tabs,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'
import { DEFAULT_NAV_ITEMS } from '../components/layout/Shell'

type CompanyInfo = { company_name: string; company_icon: string }

const DAYS = [
  { key: 'sun', label: 'ראשון' },
  { key: 'mon', label: 'שני' },
  { key: 'tue', label: 'שלישי' },
  { key: 'wed', label: 'רביעי' },
  { key: 'thu', label: 'חמישי' },
  { key: 'fri', label: 'שישי' },
  { key: 'sat', label: 'שבת' },
]

type DaySchedule = { enabled: boolean; start: string; end: string }
type Schedule = Record<string, DaySchedule>

const DEFAULT: Schedule = {
  sun: { enabled: true,  start: '07:30', end: '16:30' },
  mon: { enabled: true,  start: '07:30', end: '16:30' },
  tue: { enabled: true,  start: '07:30', end: '16:30' },
  wed: { enabled: true,  start: '07:30', end: '16:30' },
  thu: { enabled: true,  start: '07:30', end: '16:30' },
  fri: { enabled: true,  start: '07:30', end: '13:00' },
  sat: { enabled: false, start: '00:00', end: '00:00' },
}

type NavConfig = Record<string, { label?: string; visible?: boolean }>

type NavItem = { label: string; path: string; icon: string; children?: { label: string; path: string; icon: string }[] }

function flattenNav(items: NavItem[], depth = 0): { path: string; defaultLabel: string; depth: number }[] {
  return items.flatMap(item => [
    { path: item.path, defaultLabel: item.label, depth },
    ...(item.children?.length ? flattenNav(item.children, depth + 1) : []),
  ])
}

const ALL_NAV_ITEMS = flattenNav(DEFAULT_NAV_ITEMS)

export default function SettingsPage() {
  const qc = useQueryClient()

  // ── Working hours ──────────────────────────────────────────────────────────
  const { data: hoursData } = useQuery<Schedule>({
    queryKey: ['working-hours'],
    queryFn: async () => (await client.get('/settings/working-hours')).data,
  })
  const [hoursForm, setHoursForm] = useState<Schedule | null>(null)
  const schedule: Schedule = hoursForm ?? hoursData ?? DEFAULT

  function setDay(key: string, field: keyof DaySchedule, value: any) {
    setHoursForm(prev => ({
      ...(prev ?? schedule),
      [key]: { ...(prev ?? schedule)[key], [field]: value },
    }))
  }

  const saveHours = useMutation({
    mutationFn: (payload: Schedule) => client.post('/settings/working-hours', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['working-hours'] })
      setHoursForm(null)
      notifications.show({ message: '✅ שעות עבודה עודכנו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  // ── Company info ───────────────────────────────────────────────────────────
  const { data: savedCompany } = useQuery<CompanyInfo>({
    queryKey: ['company-info'],
    queryFn: () => client.get('/settings/company-info').then(r => r.data),
  })
  const [companyForm, setCompanyForm] = useState<CompanyInfo | null>(null)
  const effectiveCompany: CompanyInfo = companyForm ?? savedCompany ?? { company_name: 'אקורד מעליות', company_icon: '⚡' }

  const saveCompany = useMutation({
    mutationFn: (info: CompanyInfo) => client.put('/settings/company-info', info),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['company-info'] })
      setCompanyForm(null)
      notifications.show({ message: '✅ פרטי החברה עודכנו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  // ── Nav config ─────────────────────────────────────────────────────────────
  const { data: savedNav } = useQuery<NavConfig>({
    queryKey: ['nav-config'],
    queryFn: () => client.get('/settings/nav-config').then(r => r.data),
  })
  const [navEdits, setNavEdits] = useState<NavConfig | null>(null)
  const effectiveNav: NavConfig = navEdits ?? savedNav ?? {}

  function setNavLabel(path: string, label: string) {
    setNavEdits(prev => ({ ...(prev ?? effectiveNav), [path]: { ...(effectiveNav[path] ?? {}), label } }))
  }
  function setNavVisible(path: string, visible: boolean) {
    setNavEdits(prev => ({ ...(prev ?? effectiveNav), [path]: { ...(effectiveNav[path] ?? {}), visible } }))
  }

  const saveNav = useMutation({
    mutationFn: (cfg: NavConfig) => client.put('/settings/nav-config', cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['nav-config'] })
      setNavEdits(null)
      notifications.show({ message: '✅ תפריט עודכן', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  return (
    <Stack gap="lg" dir="rtl">
      <Title order={2}>⚙️ הגדרות מערכת</Title>

      <Tabs defaultValue="hours">
        <Tabs.List mb="md">
          <Tabs.Tab value="hours">🕐 שעות עבודה</Tabs.Tab>
          <Tabs.Tab value="nav">🗂️ עריכת תפריט</Tabs.Tab>
          <Tabs.Tab value="company">🏢 פרטי החברה</Tabs.Tab>
        </Tabs.List>

        {/* Working hours */}
        <Tabs.Panel value="hours">
          <Paper withBorder radius="md" p="lg">
            <Text size="sm" c="dimmed" mb="md">
              מחוץ לשעות אלו — קריאות רגילות ישלחו לאישור לקוח לפני שיבוץ. קריאות חילוץ תמיד מיידיות.
            </Text>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>יום</Table.Th>
                  <Table.Th>פעיל</Table.Th>
                  <Table.Th>התחלה</Table.Th>
                  <Table.Th>סיום</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {DAYS.map(({ key, label }) => (
                  <Table.Tr key={key}>
                    <Table.Td><Text size="sm" fw={500}>{label}</Text></Table.Td>
                    <Table.Td>
                      <Switch
                        checked={schedule[key]?.enabled ?? false}
                        onChange={e => setDay(key, 'enabled', e.currentTarget.checked)}
                      />
                    </Table.Td>
                    <Table.Td>
                      <TextInput
                        size="xs" w={90}
                        disabled={!schedule[key]?.enabled}
                        value={schedule[key]?.start ?? ''}
                        onChange={e => setDay(key, 'start', e.target.value)}
                        placeholder="07:30"
                      />
                    </Table.Td>
                    <Table.Td>
                      <TextInput
                        size="xs" w={90}
                        disabled={!schedule[key]?.enabled}
                        value={schedule[key]?.end ?? ''}
                        onChange={e => setDay(key, 'end', e.target.value)}
                        placeholder="16:30"
                      />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Group justify="flex-end" mt="md">
              <Button
                loading={saveHours.isPending}
                disabled={!hoursForm}
                onClick={() => saveHours.mutate(schedule)}
              >
                שמור שינויים
              </Button>
            </Group>
          </Paper>
        </Tabs.Panel>

        {/* Nav editor */}
        <Tabs.Panel value="nav">
          <Paper withBorder radius="md" p="lg">
            <Text size="sm" c="dimmed" mb="md">
              שנה שמות ותצוגה של פריטי התפריט. כיבוי פריט מסתיר אותו מהניווט בלבד — הדף עדיין נגיש ישירות.
            </Text>
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>פריט</Table.Th>
                  <Table.Th>שם מוצג</Table.Th>
                  <Table.Th>מוצג בתפריט</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {ALL_NAV_ITEMS.map(({ path, defaultLabel, depth }) => (
                  <Table.Tr key={path}>
                    <Table.Td>
                      <Text size="sm" c="dimmed" pl={depth * 16}>{defaultLabel}</Text>
                    </Table.Td>
                    <Table.Td>
                      <TextInput
                        size="xs"
                        w={200}
                        placeholder={defaultLabel}
                        value={effectiveNav[path]?.label ?? ''}
                        onChange={e => setNavLabel(path, e.target.value)}
                      />
                    </Table.Td>
                    <Table.Td>
                      <Switch
                        checked={effectiveNav[path]?.visible !== false}
                        onChange={e => setNavVisible(path, e.currentTarget.checked)}
                      />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Group justify="space-between" mt="md">
              <Button
                variant="subtle"
                color="gray"
                onClick={() => { setNavEdits({}); }}
              >
                איפוס לברירת מחדל
              </Button>
              <Button
                loading={saveNav.isPending}
                disabled={!navEdits}
                onClick={() => saveNav.mutate(effectiveNav)}
              >
                שמור תפריט
              </Button>
            </Group>
          </Paper>
        </Tabs.Panel>
        {/* Company info */}
        <Tabs.Panel value="company">
          <Paper withBorder radius="md" p="lg" maw={480}>
            <Text size="sm" c="dimmed" mb="md">
              שם החברה יוצג בראש הדף ובדף ההתחברות. האייקון הוא תו/אמוג׳י בודד.
            </Text>
            <Stack gap="sm">
              <TextInput
                label="שם החברה"
                value={effectiveCompany.company_name}
                onChange={e => setCompanyForm(prev => ({ ...(prev ?? effectiveCompany), company_name: e.target.value }))}
              />
              <TextInput
                label="אייקון"
                placeholder="⚡"
                value={effectiveCompany.company_icon}
                w={120}
                onChange={e => setCompanyForm(prev => ({ ...(prev ?? effectiveCompany), company_icon: e.target.value }))}
              />
              <Group justify="flex-end" mt="xs">
                <Button
                  loading={saveCompany.isPending}
                  disabled={!companyForm}
                  onClick={() => saveCompany.mutate(effectiveCompany)}
                >
                  שמור
                </Button>
              </Group>
            </Stack>
          </Paper>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
