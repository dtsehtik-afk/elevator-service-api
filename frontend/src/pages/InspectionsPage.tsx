import { useState } from 'react'
import {
  Stack, Title, Text, Button, Paper, Badge, Group,
  FileInput, Center, Collapse, Card, Loader,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface InspectionReport {
  id: string
  elevator_address: string
  elevator_id: string | null
  file_name: string | null
  inspection_date: string | null
  result: 'PASS' | 'FAIL' | 'UNKNOWN'
  deficiency_count: number
  deficiencies: { description: string; severity: string }[] | null
  inspector_name: string | null
  service_call_id: string | null
  processed_at: string | null
}

async function fetchInspections(): Promise<InspectionReport[]> {
  const { data } = await client.get('/inspections')
  return data
}

async function uploadInspection(file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/inspections/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

const RESULT_COLOR: Record<string, string> = { PASS: 'green', FAIL: 'red', UNKNOWN: 'gray' }
const RESULT_LABEL: Record<string, string> = { PASS: '✅ תקין', FAIL: '❌ ליקויים', UNKNOWN: '❓ לא ידוע' }
const SEVERITY_COLOR: Record<string, string> = { HIGH: 'red', MEDIUM: 'orange', LOW: 'yellow' }

export default function InspectionsPage() {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['inspections'],
    queryFn: fetchInspections,
  })

  const uploadMutation = useMutation({
    mutationFn: uploadInspection,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setFile(null)
      const msg = result.status === 'clean'
        ? '✅ ביקורת תקינה — יומן המעלית עודכן'
        : result.status === 'deficiencies_found'
        ? `⚠️ נמצאו ${result.deficiency_count} ליקויים — נפתחה קריאת שירות`
        : result.status === 'no_elevator'
        ? '⚠️ לא נמצאה מעלית מתאימה — נשלחה התראה למוקד'
        : '✅ הדוח עובד בהצלחה'
      notifications.show({ message: msg, color: result.status === 'clean' ? 'green' : 'orange', autoClose: 8000 })
    },
    onError: (e: any) => {
      notifications.show({
        message: e?.response?.data?.detail ?? 'שגיאה בעיבוד הדוח',
        color: 'red',
        autoClose: 8000,
      })
    },
  })

  return (
    <Stack gap="lg">
      <Title order={2}>🔍 דוחות ביקורת תקינות</Title>

      <Paper withBorder p="lg" radius="md">
        <Stack gap="sm">
          <Text fw={600}>העלאת דוח ביקורת חדש</Text>
          <Text size="sm" c="dimmed">
            תומך ב-PDF, תמונות (JPEG, PNG, WEBP). Gemini Vision יקרא את הדוח ויעדכן את המערכת אוטומטית.
          </Text>
          <Group align="flex-end">
            <FileInput
              label="בחר קובץ"
              placeholder="PDF או תמונה..."
              accept=".pdf,.jpg,.jpeg,.png,.webp"
              value={file}
              onChange={setFile}
              style={{ flex: 1 }}
            />
            <Button
              loading={uploadMutation.isPending}
              disabled={!file}
              onClick={() => file && uploadMutation.mutate(file)}
            >
              עבד דוח
            </Button>
          </Group>
        </Stack>
      </Paper>

      {isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : reports.length === 0 ? (
        <Text c="dimmed" ta="center" mt="xl">אין דוחות ביקורת עדיין</Text>
      ) : (
        <Stack gap="sm">
          <Text size="sm" c="dimmed">{reports.length} דוחות</Text>
          {reports.map(r => (
            <Card key={r.id} withBorder radius="md" p="md">
              <Group justify="space-between" mb={4}>
                <Group gap="sm">
                  <Badge color={RESULT_COLOR[r.result]} size="md">
                    {RESULT_LABEL[r.result]}
                  </Badge>
                  {r.deficiency_count > 0 && (
                    <Badge color="red" variant="light" size="sm">{r.deficiency_count} ליקויים</Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  {r.processed_at ? new Date(r.processed_at).toLocaleDateString('he-IL') : ''}
                </Text>
              </Group>

              <Text fw={600}>📍 {r.elevator_address}</Text>
              <Group gap="md" mt={4}>
                {r.inspection_date && (
                  <Text size="sm" c="dimmed">📅 {new Date(r.inspection_date).toLocaleDateString('he-IL')}</Text>
                )}
                {r.inspector_name && (
                  <Text size="sm" c="dimmed">👤 {r.inspector_name}</Text>
                )}
                {r.file_name && (
                  <Text size="sm" c="dimmed">📄 {r.file_name}</Text>
                )}
              </Group>

              {r.service_call_id && (
                <Text size="sm" c="orange" mt={4}>🔧 קריאת שירות נפתחה</Text>
              )}

              {r.deficiencies && r.deficiencies.length > 0 && (
                <>
                  <Button
                    variant="subtle" size="xs" mt="xs"
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                  >
                    {expanded === r.id ? 'הסתר ליקויים ▲' : `הצג ליקויים (${r.deficiencies.length}) ▼`}
                  </Button>
                  <Collapse in={expanded === r.id}>
                    <Stack gap={4} mt="xs">
                      {r.deficiencies.map((d, i) => (
                        <Group key={i} gap="xs">
                          <Badge color={SEVERITY_COLOR[d.severity] ?? 'gray'} size="xs">{d.severity}</Badge>
                          <Text size="sm">{d.description}</Text>
                        </Group>
                      ))}
                    </Stack>
                  </Collapse>
                </>
              )}
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  )
}
