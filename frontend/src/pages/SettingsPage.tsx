import { useState } from 'react'
import { Stack, Title, Paper, Table, Switch, TextInput, Button, Group, Text, Divider } from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

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

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery<Schedule>({
    queryKey: ['working-hours'],
    queryFn: async () => (await client.get('/settings/working-hours')).data,
  })

  const [form, setForm] = useState<Schedule | null>(null)
  const schedule: Schedule = form ?? data ?? DEFAULT

  function setDay(key: string, field: keyof DaySchedule, value: any) {
    setForm(prev => ({
      ...(prev ?? schedule),
      [key]: { ...(prev ?? schedule)[key], [field]: value },
    }))
  }

  const saveMutation = useMutation({
    mutationFn: (payload: Schedule) => client.post('/settings/working-hours', payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['working-hours'] })
      setForm(null)
      notifications.show({ message: '✅ שעות עבודה עודכנו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  return (
    <Stack gap="lg">
      <Title order={2}>⚙️ הגדרות מערכת</Title>

      <Paper withBorder radius="md" p="lg">
        <Title order={4} mb="md">🕐 שעות עבודה</Title>
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
            loading={saveMutation.isPending}
            disabled={!form}
            onClick={() => saveMutation.mutate(schedule)}
          >
            שמור שינויים
          </Button>
        </Group>
      </Paper>
    </Stack>
  )
}
