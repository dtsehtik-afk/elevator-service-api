import { useState } from 'react'
import {
  Stack, Title, Text, Button, Paper, Group, Alert, Table, Badge,
  FileInput, Checkbox, Loader, Center, ScrollArea,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface PreviewRow {
  internal_number: string
  action: 'CREATE' | 'UPDATE'
  address: string
  city: string
  contact_name: string | null
  main_phone: string | null
  labor_file_number: string | null
  service_type: string | null
  last_service_date: string
  next_service_date: string
}

interface PreviewResult {
  total: number
  create: number
  update: number
  rows: PreviewRow[]
}

interface CommitResult {
  created: number
  updated: number
  skipped: number
  errors: { internal_number: string; error: string }[]
  total_processed: number
}

export default function ImportPage() {
  const [file1, setFile1] = useState<File | null>(null)
  const [file2, setFile2] = useState<File | null>(null)
  const [geocode, setGeocode] = useState(false)
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [result, setResult] = useState<CommitResult | null>(null)
  const [loading, setLoading] = useState(false)

  async function runPreview() {
    if (!file1) return
    setLoading(true)
    setPreview(null)
    setResult(null)
    try {
      const fd = new FormData()
      fd.append('file1', file1)
      if (file2) fd.append('file2', file2)
      const { data } = await client.post('/import/elevators/preview', fd)
      setPreview(data)
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בתצוגה מקדימה', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  async function runCommit() {
    if (!file1) return
    if (!window.confirm(`מיובאים ${preview?.total} רשומות. האם להמשיך?`)) return
    setLoading(true)
    try {
      const fd = new FormData()
      fd.append('file1', file1)
      if (file2) fd.append('file2', file2)
      const { data } = await client.post(`/import/elevators/commit?geocode=${geocode}`, fd)
      setResult(data)
      notifications.show({ message: `ייבוא הושלם: ${data.created} חדשות, ${data.updated} עודכנו`, color: 'green' })
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בייבוא', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Stack gap="lg">
      <Title order={2}>📥 ייבוא נתונים</Title>

      <Paper withBorder p="lg" radius="md">
        <Stack gap="md">
          <Text fw={600} size="sm">קבצי Excel / CSV</Text>

          <FileInput
            label="קובץ ראשי (sysnumber, sysname, contactName, mainPhone...)"
            placeholder="בחר קובץ"
            value={file1}
            onChange={setFile1}
            accept=".csv,.txt,.tsv,.xlsx,.xls"
            required
          />
          <FileInput
            label="קובץ פרטים — אופציונלי (מעלית, מס׳ מע׳, ד.בודק, ט.מ...)"
            placeholder="בחר קובץ שני (אופציונלי)"
            value={file2}
            onChange={setFile2}
            accept=".csv,.txt,.tsv,.xlsx,.xls"
          />
          <Checkbox
            label="גאוקוד אוטומטי (Nominatim / OpenStreetMap) — חינמי, אך איטי"
            checked={geocode}
            onChange={e => setGeocode(e.target.checked)}
          />

          <Alert color="blue" variant="light">
            <Text size="sm">
              <strong>שלב 1:</strong> לחץ "תצוגה מקדימה" לראות מה ייובא.<br />
              <strong>שלב 2:</strong> לאחר אישור, לחץ "בצע ייבוא" לכתיבה לDB.<br />
              עדכון קיים — ממלא רק שדות <em>חסרים</em>, לא מחליף נתונים קיימים.
            </Text>
          </Alert>

          <Group>
            <Button disabled={!file1} loading={loading} onClick={runPreview}>
              🔍 תצוגה מקדימה
            </Button>
            {preview && (
              <Button color="green" loading={loading} onClick={runCommit}>
                ✅ בצע ייבוא ({preview.total})
              </Button>
            )}
          </Group>
        </Stack>
      </Paper>

      {loading && <Center><Loader /></Center>}

      {preview && !result && (
        <Paper withBorder radius="md" p="md">
          <Group mb="sm" gap="lg">
            <Text fw={600}>תצוגה מקדימה — {preview.total} רשומות</Text>
            <Badge color="green">{preview.create} חדשות</Badge>
            <Badge color="blue">{preview.update} עדכונים</Badge>
          </Group>
          <ScrollArea h={400}>
            <Table striped fz="xs" withTableBorder withColumnBorders>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>מס״ד</Table.Th>
                  <Table.Th>פעולה</Table.Th>
                  <Table.Th>כתובת</Table.Th>
                  <Table.Th>עיר</Table.Th>
                  <Table.Th>איש קשר</Table.Th>
                  <Table.Th>טלפון</Table.Th>
                  <Table.Th>מ.ע</Table.Th>
                  <Table.Th>שירות</Table.Th>
                  <Table.Th>טיפול אחרון</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {preview.rows.map(r => (
                  <Table.Tr key={r.internal_number}>
                    <Table.Td>{r.internal_number}</Table.Td>
                    <Table.Td>
                      <Badge color={r.action === 'CREATE' ? 'green' : 'blue'} size="xs">{r.action === 'CREATE' ? 'חדש' : 'עדכון'}</Badge>
                    </Table.Td>
                    <Table.Td>{r.address}</Table.Td>
                    <Table.Td>{r.city}</Table.Td>
                    <Table.Td>{r.contact_name ?? '—'}</Table.Td>
                    <Table.Td>{r.main_phone ?? '—'}</Table.Td>
                    <Table.Td>{r.labor_file_number ?? '—'}</Table.Td>
                    <Table.Td>{r.service_type === 'COMPREHENSIVE' ? 'מקיף' : r.service_type === 'REGULAR' ? 'רגיל' : '—'}</Table.Td>
                    <Table.Td>{r.last_service_date || '—'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Paper>
      )}

      {result && (
        <Paper withBorder p="lg" radius="md">
          <Stack gap="sm">
            <Text fw={700} size="lg" c="green">✅ ייבוא הושלם</Text>
            <Group gap="lg">
              <Badge color="green" size="lg">{result.created} נוצרו</Badge>
              <Badge color="blue" size="lg">{result.updated} עודכנו</Badge>
              {result.errors.length > 0 && <Badge color="red" size="lg">{result.errors.length} שגיאות</Badge>}
            </Group>
            {result.errors.length > 0 && (
              <Alert color="red" title="שגיאות בייבוא">
                {result.errors.map(e => (
                  <Text key={e.internal_number} size="xs">#{e.internal_number}: {e.error}</Text>
                ))}
              </Alert>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  )
}
