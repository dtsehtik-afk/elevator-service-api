import { useState } from 'react'
import {
  Stack, Title, Paper, Table, Switch, TextInput, Button, Group, Text, Tabs,
  SegmentedControl, SimpleGrid, Card, useMantineColorScheme, Badge,
} from '@mantine/core'
import { INDUSTRY_OPTIONS, industryIcon } from '../utils/industry'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'
import { DEFAULT_NAV_ITEMS } from '../components/layout/Shell'

const FONT_SIZES: Record<string, string> = { small: '13px', normal: '15px', large: '17px' }
const FONTS = [
  { value: 'Heebo',     label: 'Heebo — עגול ונוח (ברירת מחדל)' },
  { value: 'Assistant', label: 'Assistant — עסקי וקריא' },
  { value: 'Rubik',     label: 'Rubik — מודרני ונקי' },
]

type CompanyInfo = { company_name: string; company_icon?: string; industry?: string }

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

  const { colorScheme, setColorScheme } = useMantineColorScheme()
  const [fontSize, setFontSize] = useState(localStorage.getItem('app-font-size') ?? 'normal')
  const [fontFamily, setFontFamily] = useState(localStorage.getItem('app-font-family') ?? 'Heebo')

  function applyFontSize(size: string) {
    document.documentElement.style.fontSize = FONT_SIZES[size] ?? '15px'
    localStorage.setItem('app-font-size', size)
    setFontSize(size)
  }

  function applyFontFamily(family: string) {
    document.documentElement.style.setProperty('--mantine-font-family', `${family}, Arial, sans-serif`)
    localStorage.setItem('app-font-family', family)
    setFontFamily(family)
  }

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
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null)
  const currentIndustry = selectedIndustry ?? savedCompany?.industry ?? null

  const saveCompany = useMutation({
    mutationFn: (industry: string) =>
      client.put('/settings/company-info', { ...savedCompany, industry }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['company-info'] })
      setSelectedIndustry(null)
      notifications.show({ message: '✅ ענף עודכן', color: 'green' })
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
          <Tabs.Tab value="display">🎨 תצוגה</Tabs.Tab>
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
          <Paper withBorder radius="md" p="lg" maw={560}>
            <Group mb="md" gap="xs">
              <Text size="2rem">{industryIcon(currentIndustry, '🔧')}</Text>
              <Text fw={600} size="lg">{savedCompany?.company_name ?? 'שם החברה'}</Text>
              <Badge color="gray" variant="light" size="sm">קורא בלבד — מנוהל ע"י האדמין</Badge>
            </Group>
            <Text size="sm" c="dimmed" mb="md">בחר את ענף הפעילות — האייקון בראש הדף ובדף ההתחברות יתעדכן בהתאם.</Text>
            <SimpleGrid cols={3} spacing="sm" mb="md">
              {INDUSTRY_OPTIONS.map(opt => (
                <Card
                  key={opt.value}
                  withBorder
                  radius="md"
                  p="sm"
                  style={{
                    cursor: 'pointer',
                    borderColor: currentIndustry === opt.value ? 'var(--mantine-color-blue-5)' : undefined,
                    borderWidth: currentIndustry === opt.value ? 2 : 1,
                    textAlign: 'center',
                  }}
                  onClick={() => setSelectedIndustry(opt.value)}
                >
                  <Text size="xl">{opt.icon}</Text>
                  <Text size="sm" fw={currentIndustry === opt.value ? 600 : 400}>{opt.label}</Text>
                </Card>
              ))}
            </SimpleGrid>
            <Group justify="flex-end">
              <Button
                loading={saveCompany.isPending}
                disabled={!selectedIndustry || selectedIndustry === savedCompany?.industry}
                onClick={() => selectedIndustry && saveCompany.mutate(selectedIndustry)}
              >
                שמור ענף
              </Button>
            </Group>
          </Paper>
        </Tabs.Panel>
        {/* Display settings */}
        <Tabs.Panel value="display">
          <Stack gap="md" maw={520}>
            <Paper withBorder radius="md" p="lg">
              <Text fw={600} mb="xs">🌗 ערכת צבעים</Text>
              <Text size="sm" c="dimmed" mb="md">בחר בין מצב בהיר, כהה, או לפי הגדרות המערכת שלך.</Text>
              <SimpleGrid cols={3} spacing="sm">
                {[
                  { value: 'light', icon: '☀️', label: 'בהיר' },
                  { value: 'dark',  icon: '🌙', label: 'כהה' },
                  { value: 'auto',  icon: '💻', label: 'מערכת' },
                ].map(opt => (
                  <Card
                    key={opt.value}
                    withBorder
                    radius="md"
                    p="sm"
                    style={{
                      cursor: 'pointer',
                      borderColor: colorScheme === opt.value ? 'var(--mantine-color-blue-5)' : undefined,
                      borderWidth: colorScheme === opt.value ? 2 : 1,
                      textAlign: 'center',
                    }}
                    onClick={() => setColorScheme(opt.value as any)}
                  >
                    <Text size="xl">{opt.icon}</Text>
                    <Text size="sm" fw={colorScheme === opt.value ? 600 : 400}>{opt.label}</Text>
                  </Card>
                ))}
              </SimpleGrid>
            </Paper>

            <Paper withBorder radius="md" p="lg">
              <Text fw={600} mb="xs">🔡 גודל טקסט</Text>
              <Text size="sm" c="dimmed" mb="md">משנה את גודל הגופן בכל המערכת.</Text>
              <SegmentedControl
                fullWidth
                value={fontSize}
                onChange={applyFontSize}
                data={[
                  { value: 'small',  label: 'קטן' },
                  { value: 'normal', label: 'רגיל' },
                  { value: 'large',  label: 'גדול' },
                ]}
              />
            </Paper>

            <Paper withBorder radius="md" p="lg">
              <Text fw={600} mb="xs">🖋️ גופן</Text>
              <Text size="sm" c="dimmed" mb="md">כל הגופנים תומכים בעברית ובלטינית.</Text>
              <SegmentedControl
                fullWidth
                value={fontFamily}
                onChange={applyFontFamily}
                data={FONTS.map(f => ({ value: f.value, label: f.value }))}
              />
              <Text size="sm" c="dimmed" mt="sm" ta="center" style={{ fontFamily: `${fontFamily}, Arial, sans-serif` }}>
                דוגמה: מעלית בניין מגורים — Elevator Maintenance System
              </Text>
            </Paper>
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
