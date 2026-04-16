import { useState } from 'react'
import {
  Stack, Title, Text, Button, Paper, Badge, Group,
  FileInput, Center, Collapse, Card, Loader, Alert, Modal, TextInput,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface InspectionReport {
  id: string
  elevator_address: string
  elevator_id: string | null
  suggested_elevator_id: string | null
  suggested_elevator_address: string | null
  raw_address: string | null
  file_name: string | null
  inspection_date: string | null
  result: 'PASS' | 'FAIL' | 'UNKNOWN'
  deficiency_count: number
  deficiencies: { description: string; severity: string }[] | null
  inspector_name: string | null
  service_call_id: string | null
  match_status: 'AUTO_MATCHED' | 'PENDING_REVIEW' | 'MANUALLY_CONFIRMED' | 'UNMATCHED'
  match_score: number | null
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
const MATCH_COLOR: Record<string, string> = {
  AUTO_MATCHED: 'green', PENDING_REVIEW: 'orange', MANUALLY_CONFIRMED: 'blue', UNMATCHED: 'red',
}
const MATCH_LABEL: Record<string, string> = {
  AUTO_MATCHED: 'שויך אוטומטית', PENDING_REVIEW: '⚠️ ממתין לאישור', MANUALLY_CONFIRMED: '✓ אושר ידנית', UNMATCHED: 'לא שויך',
}

export default function InspectionsPage() {
  const qc = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirmReport, setConfirmReport] = useState<InspectionReport | null>(null)
  const [overrideElevId, setOverrideElevId] = useState('')

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['inspections'],
    queryFn: fetchInspections,
  })

  const pendingCount = reports.filter(r => r.match_status === 'PENDING_REVIEW').length

  const uploadMutation = useMutation({
    mutationFn: uploadInspection,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setFile(null)
      const msg = result.status === 'clean'
        ? '✅ ביקורת תקינה — יומן המעלית עודכן'
        : result.status === 'deficiencies_found'
        ? `⚠️ נמצאו ${result.deficiency_count} ליקויים — נפתחה קריאת שירות`
        : result.status === 'pending_review'
        ? '⚠️ כתובת לא ודאית — נשלחה בקשת אישור למוקד'
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

  const confirmMutation = useMutation({
    mutationFn: ({ reportId, elevatorId }: { reportId: string; elevatorId?: string }) =>
      client.post(`/inspections/${reportId}/confirm${elevatorId ? `?elevator_id=${elevatorId}` : ''}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setConfirmReport(null)
      setOverrideElevId('')
      notifications.show({ message: '✅ הדוח אושר ושויך למעלית', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה באישור', color: 'red' }),
  })

  const rejectMutation = useMutation({
    mutationFn: (reportId: string) => client.post(`/inspections/${reportId}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      notifications.show({ message: 'הדוח סומן כ"לא שויך"', color: 'orange' })
    },
    onError: () => notifications.show({ message: 'שגיאה בדחייה', color: 'red' }),
  })

  return (
    <Stack gap="lg">
      <Title order={2}>🔍 דוחות ביקורת תקינות</Title>

      {pendingCount > 0 && (
        <Alert color="orange" title={`${pendingCount} דוחות ממתינים לאישור שיוך`}>
          דוחות אלו הועלו אך המערכת לא הצליחה לזהות את המעלית בוודאות. יש לאשר או לדחות את ההצעה.
        </Alert>
      )}

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
            <Card key={r.id} withBorder radius="md" p="md"
              style={r.match_status === 'PENDING_REVIEW' ? { borderColor: 'var(--mantine-color-orange-4)', borderWidth: 2 } : undefined}
            >
              <Group justify="space-between" mb={4}>
                <Group gap="sm">
                  <Badge color={RESULT_COLOR[r.result]} size="md">{RESULT_LABEL[r.result]}</Badge>
                  <Badge color={MATCH_COLOR[r.match_status]} variant="light" size="sm">
                    {MATCH_LABEL[r.match_status]}
                    {r.match_score != null && r.match_status === 'PENDING_REVIEW' ? ` (${Math.round(r.match_score * 100)}%)` : ''}
                  </Badge>
                  {r.deficiency_count > 0 && (
                    <Badge color="red" variant="light" size="sm">{r.deficiency_count} ליקויים</Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  {r.processed_at ? new Date(r.processed_at).toLocaleDateString('he-IL') : ''}
                </Text>
              </Group>

              {r.match_status === 'PENDING_REVIEW' ? (
                <Stack gap={6} my={6} p="sm" style={{ background: 'var(--mantine-color-orange-0)', borderRadius: 8 }}>
                  <Text size="sm" fw={600}>כתובת בדוח: {r.raw_address || '—'}</Text>
                  {r.suggested_elevator_address && (
                    <Text size="sm">מעלית מוצעת: <strong>{r.suggested_elevator_address}</strong></Text>
                  )}
                  <Group gap="sm" mt={4}>
                    <Button size="xs" color="green" onClick={() => setConfirmReport(r)}>
                      ✅ אשר שיוך
                    </Button>
                    <Button size="xs" color="red" variant="light"
                      loading={rejectMutation.isPending}
                      onClick={() => rejectMutation.mutate(r.id)}
                    >
                      ❌ דחה
                    </Button>
                  </Group>
                </Stack>
              ) : (
                <Text fw={600}>📍 {r.elevator_address}</Text>
              )}

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

      {/* Confirm match modal */}
      <Modal
        opened={!!confirmReport}
        onClose={() => { setConfirmReport(null); setOverrideElevId('') }}
        title="אישור שיוך דוח ביקורת"
        dir="rtl"
      >
        {confirmReport && (
          <Stack gap="md">
            <Text size="sm">כתובת בדוח: <strong>{confirmReport.raw_address}</strong></Text>
            {confirmReport.suggested_elevator_address && (
              <Text size="sm">מעלית מוצעת: <strong>{confirmReport.suggested_elevator_address}</strong></Text>
            )}
            <Button
              color="green"
              loading={confirmMutation.isPending}
              onClick={() => confirmMutation.mutate({ reportId: confirmReport.id })}
            >
              ✅ אשר מעלית מוצעת
            </Button>
            <Text size="xs" c="dimmed" ta="center">— או שייך למעלית אחרת —</Text>
            <TextInput
              placeholder="UUID של מעלית אחרת"
              value={overrideElevId}
              onChange={e => setOverrideElevId(e.target.value)}
              label="ID מעלית"
            />
            <Button
              variant="light"
              disabled={!overrideElevId.trim()}
              loading={confirmMutation.isPending}
              onClick={() => confirmMutation.mutate({ reportId: confirmReport.id, elevatorId: overrideElevId.trim() })}
            >
              שייך למעלית אחרת
            </Button>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}
