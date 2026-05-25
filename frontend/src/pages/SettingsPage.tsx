import { useState, useEffect } from 'react'
import {
  Stack, Title, Paper, Table, Switch, TextInput, Button, Group, Text, Tabs,
  SegmentedControl, SimpleGrid, Card, useMantineColorScheme, Badge, Alert,
  PinInput, Loader, ActionIcon,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'
import { DEFAULT_NAV_ITEMS } from '../components/layout/Shell'
import { totpSetup, totpConfirm, totpDisable, totpStatus, loginHistory } from '../api/auth'

const FONT_SIZES: Record<string, string> = { small: '13px', normal: '15px', large: '17px' }
const FONTS = [
  { value: 'Heebo',     label: 'Heebo — עגול ונוח (ברירת מחדל)' },
  { value: 'Assistant', label: 'Assistant — עסקי וקריא' },
  { value: 'Rubik',     label: 'Rubik — מודרני ונקי' },
]


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

  // ── Holidays ──────────────────────────────────────────────────────────────
  const { data: holidaysData } = useQuery<string[]>({
    queryKey: ['holidays'],
    queryFn: async () => (await client.get('/settings/holidays')).data,
  })
  const [holidayDates, setHolidayDates] = useState<string[] | null>(null)
  const effectiveHolidays: string[] = holidayDates ?? holidaysData ?? []
  const [newHoliday, setNewHoliday] = useState('')

  const saveHolidays = useMutation({
    mutationFn: (dates: string[]) => client.post('/settings/holidays', { dates }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['holidays'] })
      setHolidayDates(null)
      notifications.show({ message: '✅ ימי חג עודכנו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  const autoFetchHolidays = useMutation({
    mutationFn: () => client.post('/settings/holidays/auto-fetch'),
    onSuccess: (res) => {
      if (!res.data.ok) {
        notifications.show({ message: `שגיאה משרת: ${res.data.error || res.data.errors?.join(', ')}`, color: 'red' })
        return
      }
      qc.invalidateQueries({ queryKey: ['holidays'] })
      setHolidayDates(null)
      notifications.show({ message: `✅ נמשכו ${res.data.fetched} ימי חג, סה"כ ${res.data.total} תאריכים`, color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה במשיכת לוח שנה', color: 'red' }),
  })

  function addHoliday() {
    const d = newHoliday.trim()
    if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d)) return
    if (effectiveHolidays.includes(d)) return
    setHolidayDates([...effectiveHolidays, d].sort())
    setNewHoliday('')
  }

  function removeHoliday(d: string) {
    setHolidayDates(effectiveHolidays.filter(x => x !== d))
  }

  return (
    <Stack gap="lg" dir="rtl">
      <Title order={2}>⚙️ הגדרות מערכת</Title>

      <Tabs defaultValue="hours">
        <Tabs.List mb="md">
          <Tabs.Tab value="hours">🕐 שעות עבודה</Tabs.Tab>
          <Tabs.Tab value="holidays">📅 ימי חג</Tabs.Tab>
          <Tabs.Tab value="nav">🗂️ עריכת תפריט</Tabs.Tab>
          <Tabs.Tab value="display">🎨 תצוגה</Tabs.Tab>
          <Tabs.Tab value="security">🔐 אבטחה</Tabs.Tab>
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

        {/* Holidays */}
        <Tabs.Panel value="holidays">
          <Paper withBorder radius="md" p="lg">
            <Group justify="space-between" mb="md" align="flex-start">
              <Text size="sm" c="dimmed" maw={480}>
                הגדר תאריכים שבהם המשרד סגור (חגים, מועדים מיוחדים). בתאריכים אלו המערכת תתנהג כמחוץ לשעות עבודה.
              </Text>
              <Button
                variant="light"
                color="grape"
                loading={autoFetchHolidays.isPending}
                onClick={() => autoFetchHolidays.mutate()}
              >
                🗓️ רענן מלוח שנה עברי
              </Button>
            </Group>
            <Group mb="md" align="flex-end">
              <TextInput
                label="הוסף תאריך (YYYY-MM-DD)"
                placeholder="2026-09-22"
                value={newHoliday}
                onChange={e => setNewHoliday(e.target.value)}
                w={200}
                dir="ltr"
                onKeyDown={e => e.key === 'Enter' && addHoliday()}
              />
              <Button onClick={addHoliday} variant="light">הוסף</Button>
            </Group>
            {effectiveHolidays.length === 0 ? (
              <Text size="sm" c="dimmed">אין ימי חג מוגדרים</Text>
            ) : (
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>תאריך</Table.Th>
                    <Table.Th>יום בשבוע</Table.Th>
                    <Table.Th></Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {effectiveHolidays.map(d => {
                    const dayName = new Date(d + 'T12:00:00').toLocaleDateString('he-IL', { weekday: 'long' })
                    return (
                      <Table.Tr key={d}>
                        <Table.Td style={{ fontFamily: 'monospace' }}>{d}</Table.Td>
                        <Table.Td>{dayName}</Table.Td>
                        <Table.Td>
                          <ActionIcon color="red" variant="subtle" onClick={() => removeHoliday(d)} title="הסר">
                            ✕
                          </ActionIcon>
                        </Table.Td>
                      </Table.Tr>
                    )
                  })}
                </Table.Tbody>
              </Table>
            )}
            <Group justify="flex-end" mt="md">
              <Button
                loading={saveHolidays.isPending}
                disabled={holidayDates === null}
                onClick={() => saveHolidays.mutate(effectiveHolidays)}
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
        {/* Security */}
        <Tabs.Panel value="security">
          <SecurityTab />
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

function SecurityTab() {
  const qc = useQueryClient()

  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['totp-status'],
    queryFn: totpStatus,
  })

  const { data: history } = useQuery({
    queryKey: ['login-history'],
    queryFn: loginHistory,
  })

  // Setup flow
  const [setupData, setSetupData] = useState<{ secret: string; otpauth_uri: string } | null>(null)
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [setupCode, setSetupCode] = useState('')
  const [setupLoading, setSetupLoading] = useState(false)

  useEffect(() => {
    if (!setupData) { setQrUrl(null); return }
    client.get('/auth/totp/qr', { responseType: 'blob' }).then(r => {
      setQrUrl(URL.createObjectURL(r.data))
    }).catch(() => {})
    return () => { if (qrUrl) URL.revokeObjectURL(qrUrl) }
  }, [setupData])

  // Disable flow
  const [disableCode, setDisableCode] = useState('')
  const [disableLoading, setDisableLoading] = useState(false)
  const [showDisable, setShowDisable] = useState(false)

  async function handleSetup() {
    setSetupLoading(true)
    try {
      const data = await totpSetup()
      setSetupData(data)
      setSetupCode('')
    } catch {
      notifications.show({ message: 'שגיאה בהכנת אימות דו-שלבי', color: 'red' })
    } finally {
      setSetupLoading(false)
    }
  }

  async function handleConfirm() {
    setSetupLoading(true)
    try {
      await totpConfirm(setupCode)
      notifications.show({ message: '✅ אימות דו-שלבי הופעל', color: 'green' })
      setSetupData(null)
      setSetupCode('')
      qc.invalidateQueries({ queryKey: ['totp-status'] })
    } catch (err: any) {
      notifications.show({ message: err?.response?.data?.detail ?? 'קוד שגוי', color: 'red' })
    } finally {
      setSetupLoading(false)
    }
  }

  async function handleDisable() {
    setDisableLoading(true)
    try {
      await totpDisable(disableCode)
      notifications.show({ message: 'אימות דו-שלבי בוטל', color: 'orange' })
      setShowDisable(false)
      setDisableCode('')
      qc.invalidateQueries({ queryKey: ['totp-status'] })
    } catch (err: any) {
      notifications.show({ message: err?.response?.data?.detail ?? 'קוד שגוי', color: 'red' })
    } finally {
      setDisableLoading(false)
    }
  }

  if (statusLoading) return <Loader />

  const totpEnabled = status?.totp_enabled ?? false

  return (
    <Stack gap="md" maw={560}>
      {/* TOTP Section */}
      <Paper withBorder radius="md" p="lg">
        <Group justify="space-between" mb="sm">
          <div>
            <Text fw={600}>🔑 אימות דו-שלבי (Google Authenticator)</Text>
            <Text size="sm" c="dimmed">הגן על חשבונך עם קוד חד-פעמי בנוסף לסיסמה</Text>
          </div>
          <Badge color={totpEnabled ? 'green' : 'gray'} size="lg">
            {totpEnabled ? 'פעיל' : 'לא פעיל'}
          </Badge>
        </Group>

        {!totpEnabled && !setupData && (
          <Button onClick={handleSetup} loading={setupLoading}>
            הפעל אימות דו-שלבי
          </Button>
        )}

        {setupData && (
          <Stack gap="md">
            <Alert color="blue" variant="light">
              סרוק את קוד ה-QR עם Google Authenticator, ואז הזן את הקוד בן 6 הספרות שמוצג באפליקציה לאישור.
            </Alert>
            <Group justify="center">
              {qrUrl && (
                <img src={qrUrl} width={200} height={200} alt="TOTP QR Code" style={{ borderRadius: 8 }} />
              )}
            </Group>
            <Text size="xs" c="dimmed" ta="center" style={{ fontFamily: 'monospace' }}>
              {setupData.secret}
            </Text>
            <Stack gap="xs">
              <Text size="sm" fw={500}>הזן קוד לאישור:</Text>
              <Group justify="center">
                <PinInput
                  length={6}
                  type="number"
                  value={setupCode}
                  onChange={setSetupCode}
                  dir="ltr"
                />
              </Group>
              <Group>
                <Button
                  onClick={handleConfirm}
                  loading={setupLoading}
                  disabled={setupCode.length < 6}
                >
                  אשר והפעל
                </Button>
                <Button variant="subtle" color="gray" onClick={() => setSetupData(null)}>
                  ביטול
                </Button>
              </Group>
            </Stack>
          </Stack>
        )}

        {totpEnabled && !showDisable && (
          <Button color="red" variant="light" onClick={() => setShowDisable(true)}>
            בטל אימות דו-שלבי
          </Button>
        )}

        {totpEnabled && showDisable && (
          <Stack gap="xs">
            <Text size="sm">הזן קוד מ-Google Authenticator לביטול:</Text>
            <Group>
              <PinInput
                length={6}
                type="number"
                value={disableCode}
                onChange={setDisableCode}
                dir="ltr"
              />
              <Button
                color="red"
                onClick={handleDisable}
                loading={disableLoading}
                disabled={disableCode.length < 6}
              >
                בטל
              </Button>
              <Button variant="subtle" color="gray" onClick={() => { setShowDisable(false); setDisableCode('') }}>
                חזרה
              </Button>
            </Group>
          </Stack>
        )}
      </Paper>

      {/* Login history */}
      <Paper withBorder radius="md" p="lg">
        <Text fw={600} mb="sm">🕓 היסטוריית התחברויות אחרונות</Text>
        {!history || history.length === 0 ? (
          <Text size="sm" c="dimmed">אין רישומים</Text>
        ) : (
          <Table fz="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>IP</Table.Th>
                <Table.Th>סטטוס</Table.Th>
                <Table.Th>תאריך</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {history.map((h, i) => (
                <Table.Tr key={i}>
                  <Table.Td style={{ fontFamily: 'monospace' }}>{h.ip_address}</Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={h.success ? 'green' : 'red'}>
                      {h.success ? 'הצלחה' : 'כישלון'}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{new Date(h.created_at).toLocaleString('he-IL')}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </Stack>
  )
}
