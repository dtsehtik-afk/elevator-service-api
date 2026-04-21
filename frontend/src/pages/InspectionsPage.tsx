import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Stack, Title, Text, Button, Paper, Badge, Group,
  FileInput, Center, Collapse, Card, Loader, Alert, Modal, ActionIcon,
  Autocomplete, Divider, Anchor, Checkbox, Tabs, TextInput, Textarea, Select,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'
import { useAuthStore } from '../stores/authStore'

interface Deficiency {
  description: string
  severity: string
  done?: boolean
}

interface InspectionReport {
  id: string
  elevator_address: string
  elevator_id: string | null
  suggested_elevator_id: string | null
  suggested_elevator_address: string | null
  raw_address: string | null
  file_name: string | null
  file_url: string | null
  inspection_date: string | null
  result: 'PASS' | 'FAIL' | 'UNKNOWN'
  deficiency_count: number
  deficiencies: Deficiency[] | null
  inspector_name: string | null
  service_call_id: string | null
  match_status: 'AUTO_MATCHED' | 'PENDING_REVIEW' | 'MANUALLY_CONFIRMED' | 'UNMATCHED'
  match_score: number | null
  processed_at: string | null
  report_status: 'NA' | 'OPEN' | 'PARTIAL' | 'CLOSED'
  assigned_technician_id: string | null
  assigned_technician_name: string | null
  raw_city: string | null
  notes: string | null
}

interface ElevatorOption { id: string; label: string }

async function fetchInspections(params?: string): Promise<InspectionReport[]> {
  const { data } = await client.get(`/inspections${params ? `?${params}` : ''}`)
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

async function openReportFile(fileUrl: string, fileName: string | null) {
  // Drive URLs open directly; local files need authenticated fetch
  if (fileUrl.startsWith('https://drive.google.com')) {
    window.open(fileUrl, '_blank')
    return
  }
  const { data } = await client.get(fileUrl, { responseType: 'blob' })
  const blobUrl = URL.createObjectURL(data)
  window.open(blobUrl, '_blank')
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
const REPORT_STATUS_COLOR: Record<string, string> = { NA: 'gray', OPEN: 'red', PARTIAL: 'orange', CLOSED: 'green' }
const REPORT_STATUS_LABEL: Record<string, string> = { NA: 'תקין', OPEN: 'פתוח', PARTIAL: 'בטיפול', CLOSED: 'טופל' }

export default function InspectionsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const userRole = useAuthStore(s => s.userRole)
  const isAdmin = userRole === 'ADMIN'
  const [file, setFile] = useState<File | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [confirmReport, setConfirmReport] = useState<InspectionReport | null>(null)
  const [elevSearch, setElevSearch] = useState('')
  const [elevOptions, setElevOptions] = useState<ElevatorOption[]>([])
  const [selectedElevId, setSelectedElevId] = useState('')
  const [createMode, setCreateMode] = useState(false)
  const [createElev, setCreateElev] = useState({ address: '', city: '', building_name: '' })
  const [activeTab, setActiveTab] = useState<string | null>('all')
  const [completionModal, setCompletionModal] = useState<{ reportId: string; elevatorAddress: string; deficiencies: Deficiency[] } | null>(null)
  const [completionNotes, setCompletionNotes] = useState('')
  const [addDefFor, setAddDefFor] = useState<string | null>(null)
  const [newDefDesc, setNewDefDesc] = useState('')
  const [newDefSeverity, setNewDefSeverity] = useState('MEDIUM')

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['inspections'],
    queryFn: () => fetchInspections(),
  })

  const pendingCount = reports.filter(r => r.match_status === 'PENDING_REVIEW').length
  const openCount = reports.filter(r => r.report_status === 'OPEN' || r.report_status === 'PARTIAL').length

  const displayedReports = activeTab === 'open'
    ? reports.filter(r => r.report_status === 'OPEN' || r.report_status === 'PARTIAL')
    : activeTab === 'pending'
    ? reports.filter(r => r.match_status === 'PENDING_REVIEW')
    : reports

  const uploadMutation = useMutation({
    mutationFn: uploadInspection,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setFile(null)
      const msg = result.status === 'clean'
        ? '✅ ביקורת תקינה — יומן המעלית עודכן'
        : result.status === 'deficiencies_found'
        ? `⚠️ נמצאו ${result.deficiency_count} ליקויים — הדוח נפתח לטיפול`
        : result.status === 'pending_review'
        ? '⚠️ כתובת לא ודאית — נשלחה בקשת אישור למוקד'
        : result.status === 'no_elevator'
        ? '⚠️ לא נמצאה מעלית מתאימה — נשלחה התראה למוקד'
        : '✅ הדוח עובד בהצלחה'
      notifications.show({ message: msg, color: result.status === 'clean' ? 'green' : 'orange', autoClose: 8000 })
    },
    onError: (e: any) => {
      notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה בעיבוד הדוח', color: 'red', autoClose: 8000 })
    },
  })

  const confirmMutation = useMutation({
    mutationFn: ({ reportId, elevatorId }: { reportId: string; elevatorId?: string }) =>
      client.post(`/inspections/${reportId}/confirm${elevatorId ? `?elevator_id=${elevatorId}` : ''}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setConfirmReport(null); setElevSearch(''); setSelectedElevId(''); setCreateMode(false)
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

  const claimMutation = useMutation({
    mutationFn: (reportId: string) => client.post(`/inspections/claim/${reportId}`),
    onSuccess: (_, reportId) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      notifications.show({ message: '✅ הדוח נלקח לטיפולך', color: 'teal' })
    },
    onError: () => notifications.show({ message: 'שגיאה בקבלת הדוח לטיפול', color: 'red' }),
  })

  const checklistMutation = useMutation({
    mutationFn: ({ reportId, updates }: { reportId: string; updates: { index: number; done: boolean }[] }) =>
      client.patch(`/inspections/checklist/${reportId}`, updates),
    onSuccess: (res, { reportId }) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      const status = res.data?.report_status
      if (status === 'CLOSED') {
        const r = reports.find(r => r.id === reportId)
        const defs = (r?.deficiencies || []).map(d => `• ${d.description}`).join('\n')
        const defaultNotes = `כל הליקויים טופלו:\n${defs}`
        setCompletionNotes(defaultNotes)
        setCompletionModal({ reportId, elevatorAddress: r?.elevator_address ?? '', deficiencies: r?.deficiencies ?? [] })
      }
    },
    onError: () => notifications.show({ message: 'שגיאה בעדכון הרשימה', color: 'red' }),
  })

  const deleteReportMutation = useMutation({
    mutationFn: (reportId: string) => client.delete(`/inspections/${reportId}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inspections'] }); notifications.show({ message: 'הדוח נמחק', color: 'green' }) },
    onError: () => notifications.show({ message: 'שגיאה במחיקה', color: 'red' }),
  })

  const addDeficiencyMutation = useMutation({
    mutationFn: ({ reportId, description, severity }: { reportId: string; description: string; severity: string }) =>
      client.post(`/inspections/${reportId}/add-deficiency`, { description, severity }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setAddDefFor(null); setNewDefDesc(''); setNewDefSeverity('MEDIUM')
      notifications.show({ message: 'הליקוי נוסף', color: 'teal' })
    },
    onError: () => notifications.show({ message: 'שגיאה בהוספת ליקוי', color: 'red' }),
  })

  const createElevatorMutation = useMutation({
    mutationFn: ({ reportId, ...form }: { reportId: string; address: string; city: string; building_name: string }) =>
      client.post(`/inspections/${reportId}/create-elevator`, form),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setConfirmReport(null); setCreateMode(false); setCreateElev({ address: '', city: '', building_name: '' })
      notifications.show({ message: `✅ מעלית נוצרה ושויכה: ${res.data.elevator_address}`, color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e?.response?.data?.detail ?? 'שגיאה ביצירת מעלית', color: 'red' }),
  })

  const completeMutation = useMutation({
    mutationFn: ({ reportId, notes }: { reportId: string; notes: string }) =>
      client.post(`/inspections/${reportId}/complete`, { notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['inspections'] })
      setCompletionModal(null); setCompletionNotes('')
      notifications.show({ message: '✅ דוח סיום נשלח למנהל', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשליחת דוח הסיום', color: 'red' }),
  })

  async function searchElevators(q: string) {
    setElevSearch(q)
    if (q.length < 2) { setElevOptions([]); return }
    const { data } = await client.get(`/inspections/search-elevators?q=${encodeURIComponent(q)}`)
    setElevOptions(data)
  }

  function toggleDeficiency(report: InspectionReport, idx: number, done: boolean) {
    checklistMutation.mutate({ reportId: report.id, updates: [{ index: idx, done }] })
  }

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
          <Text size="sm" c="dimmed">תומך ב-PDF, תמונות (JPEG, PNG, WEBP). Gemini Vision יקרא את הדוח ויעדכן את המערכת אוטומטית.</Text>
          <Group align="flex-end">
            <FileInput label="בחר קובץ" placeholder="PDF או תמונה..."
              accept=".pdf,.jpg,.jpeg,.png,.webp" value={file} onChange={setFile} style={{ flex: 1 }} />
            <Button loading={uploadMutation.isPending} disabled={!file} onClick={() => file && uploadMutation.mutate(file)}>
              עבד דוח
            </Button>
          </Group>
        </Stack>
      </Paper>

      {isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : (
        <Stack gap="sm">
          <Tabs value={activeTab} onChange={setActiveTab}>
            <Tabs.List>
              <Tabs.Tab value="all">הכל ({reports.length})</Tabs.Tab>
              <Tabs.Tab value="open" color="red">פתוח לטיפול ({openCount})</Tabs.Tab>
              <Tabs.Tab value="pending" color="orange">ממתין לאישור ({pendingCount})</Tabs.Tab>
            </Tabs.List>
          </Tabs>

          {displayedReports.length === 0
            ? <Text c="dimmed" ta="center" mt="xl">אין דוחות</Text>
            : displayedReports.map(r => (
            <Card key={r.id} withBorder radius="md" p="md"
              style={r.match_status === 'PENDING_REVIEW' ? { borderColor: 'var(--mantine-color-orange-4)', borderWidth: 2 }
                : (r.report_status === 'OPEN') ? { borderColor: 'var(--mantine-color-red-4)', borderWidth: 2 }
                : undefined}
            >
              <Group justify="space-between" mb={4}>
                <Group gap="sm" wrap="wrap">
                  <Badge color={RESULT_COLOR[r.result]} size="md">{RESULT_LABEL[r.result]}</Badge>
                  <Badge color={MATCH_COLOR[r.match_status]} variant="light" size="sm">
                    {MATCH_LABEL[r.match_status]}
                    {r.match_score != null && r.match_status === 'PENDING_REVIEW' ? ` (${Math.round(r.match_score * 100)}%)` : ''}
                  </Badge>
                  {r.report_status !== 'NA' && (
                    <Badge color={REPORT_STATUS_COLOR[r.report_status]} variant="dot" size="sm">
                      {REPORT_STATUS_LABEL[r.report_status]}
                    </Badge>
                  )}
                  {r.deficiency_count > 0 && (
                    <Badge color="red" variant="light" size="sm">{r.deficiency_count} ליקויים</Badge>
                  )}
                </Group>
                <Group gap="xs">
                  <Text size="xs" c="dimmed">
                    {r.processed_at ? new Date(r.processed_at).toLocaleDateString('he-IL') : ''}
                  </Text>
                  {isAdmin && (
                    <ActionIcon size="sm" color="red" variant="subtle"
                      onClick={() => { if (window.confirm('למחוק דוח זה?')) deleteReportMutation.mutate(r.id) }}>
                      🗑️
                    </ActionIcon>
                  )}
                </Group>
              </Group>

              {r.match_status === 'PENDING_REVIEW' ? (
                <Stack gap={6} my={6} p="sm" style={{ background: 'var(--mantine-color-orange-0)', borderRadius: 8 }}>
                  <Text size="sm" fw={600}>כתובת בדוח: {r.raw_address || '—'}</Text>
                  {r.suggested_elevator_address && (
                    <Text size="sm">מעלית מוצעת: <strong>{r.suggested_elevator_address}</strong></Text>
                  )}
                  <Group gap="sm" mt={4}>
                    <Button size="xs" color="green" onClick={() => setConfirmReport(r)}>✅ אשר שיוך</Button>
                    <Button size="xs" color="red" variant="light"
                      loading={rejectMutation.isPending} onClick={() => rejectMutation.mutate(r.id)}>
                      ❌ דחה
                    </Button>
                  </Group>
                </Stack>
              ) : (
                <Group gap="sm" align="center">
                  <Text fw={600}>📍 {r.elevator_address}</Text>
                  {r.elevator_id && (
                    <Button size="xs" variant="subtle" color="blue"
                      onClick={() => navigate(`/elevators/${r.elevator_id}`)}>
                      🏢 פתח מעלית
                    </Button>
                  )}
                </Group>
              )}

              <Group gap="md" mt={4} wrap="wrap">
                {r.inspection_date && (
                  <Text size="sm" c="dimmed">📅 {new Date(r.inspection_date).toLocaleDateString('he-IL')}</Text>
                )}
                {r.inspector_name && <Text size="sm" c="dimmed">👤 {r.inspector_name}</Text>}
                {r.assigned_technician_name && (
                  <Text size="sm" c="teal">🔧 {r.assigned_technician_name}</Text>
                )}
                {r.file_url ? (
                  <Anchor size="sm" style={{ cursor: 'pointer' }}
                    onClick={() => openReportFile(r.file_url!, r.file_name)}>
                    📄 הצג תסקיר
                  </Anchor>
                ) : r.file_name ? (
                  <Text size="sm" c="dimmed">📄 {r.file_name}</Text>
                ) : null}
              </Group>

              {/* Open/Partial reports: claim + checklist */}
              {(r.report_status === 'OPEN' || r.report_status === 'PARTIAL') && (
                <>
                  <Group gap="sm" mt="sm">
                    {!r.assigned_technician_id && (
                      <Button size="xs" color="teal" variant="light"
                        loading={claimMutation.isPending && claimMutation.variables === r.id}
                        onClick={() => claimMutation.mutate(r.id)}>
                        🙋 קח על עצמי
                      </Button>
                    )}
                    <Button variant="subtle" size="xs"
                      onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                      {expanded === r.id ? 'הסתר ליקויים ▲' : `הצג ליקויים (${r.deficiency_count}) ▼`}
                    </Button>
                  </Group>
                  <Collapse in={expanded === r.id}>
                    <Stack gap={6} mt="xs" p="xs"
                      style={{ background: 'var(--mantine-color-red-0)', borderRadius: 8 }}>
                      {(r.deficiencies || []).map((d, i) => (
                        <Checkbox
                          key={i}
                          checked={!!d.done}
                          onChange={e => toggleDeficiency(r, i, e.target.checked)}
                          label={
                            <Group gap="xs">
                              <Badge color={SEVERITY_COLOR[d.severity] ?? 'gray'} size="xs">{d.severity}</Badge>
                              <Text size="sm" td={d.done ? 'line-through' : undefined} c={d.done ? 'dimmed' : undefined}>
                                {d.description}
                              </Text>
                            </Group>
                          }
                        />
                      ))}
                      {addDefFor === r.id ? (
                        <Paper p="xs" radius="sm" withBorder mt={4}>
                          <Stack gap={6}>
                            <TextInput
                              placeholder="תיאור הליקוי..."
                              size="xs"
                              value={newDefDesc}
                              onChange={e => setNewDefDesc(e.target.value)}
                              autoFocus
                            />
                            <Group gap="xs">
                              <Select
                                size="xs"
                                value={newDefSeverity}
                                onChange={v => setNewDefSeverity(v ?? 'MEDIUM')}
                                data={[{ value: 'HIGH', label: '🔴 גבוה' }, { value: 'MEDIUM', label: '🟡 בינוני' }, { value: 'LOW', label: '🟢 נמוך' }]}
                                style={{ flex: 1 }}
                              />
                              <Button size="xs" color="teal"
                                disabled={!newDefDesc.trim()}
                                loading={addDeficiencyMutation.isPending}
                                onClick={() => addDeficiencyMutation.mutate({ reportId: r.id, description: newDefDesc, severity: newDefSeverity })}>
                                הוסף
                              </Button>
                              <Button size="xs" variant="subtle" color="gray" onClick={() => { setAddDefFor(null); setNewDefDesc('') }}>ביטול</Button>
                            </Group>
                          </Stack>
                        </Paper>
                      ) : (
                        <Button size="xs" variant="subtle" color="blue" mt={4}
                          onClick={() => setAddDefFor(r.id)}>
                          + הוסף ליקוי
                        </Button>
                      )}
                    </Stack>
                  </Collapse>
                </>
              )}

              {/* Closed or clean: show checklist read-only */}
              {r.report_status === 'CLOSED' && r.deficiencies && r.deficiencies.length > 0 && (
                <>
                  <Button variant="subtle" size="xs" mt="xs"
                    onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
                    {expanded === r.id ? 'הסתר ליקויים ▲' : `ליקויים שטופלו (${r.deficiency_count}) ▼`}
                  </Button>
                  <Collapse in={expanded === r.id}>
                    <Stack gap={4} mt="xs">
                      {r.deficiencies.map((d, i) => (
                        <Group key={i} gap="xs">
                          <Badge color={SEVERITY_COLOR[d.severity] ?? 'gray'} size="xs">{d.severity}</Badge>
                          <Text size="sm" td="line-through" c="dimmed">{d.description}</Text>
                        </Group>
                      ))}
                    </Stack>
                  </Collapse>
                </>
              )}

              {r.service_call_id && (
                <Text size="sm" c="orange" mt={4}>🔧 קריאת שירות נפתחה</Text>
              )}
            </Card>
          ))}
        </Stack>
      )}

      {/* Confirm match modal */}
      <Modal
        opened={!!confirmReport}
        onClose={() => { setConfirmReport(null); setElevSearch(''); setSelectedElevId(''); setCreateMode(false) }}
        title="אישור שיוך דוח ביקורת"
        dir="rtl"
        size="md"
      >
        {confirmReport && (
          <Stack gap="md">
            <Paper withBorder p="sm" radius="sm" bg="gray.0">
              <Text size="sm">כתובת בדוח: <strong>{confirmReport.raw_address || '—'}</strong></Text>
              {confirmReport.inspector_name && <Text size="xs" c="dimmed">בודק: {confirmReport.inspector_name}</Text>}
              {confirmReport.file_url && (
                <Anchor size="xs" style={{ cursor: 'pointer' }}
                  onClick={() => openReportFile(confirmReport.file_url!, confirmReport.file_name)}>
                  📄 פתח תסקיר מקורי
                </Anchor>
              )}
            </Paper>

            {confirmReport.suggested_elevator_address && (
              <>
                <Text size="sm" fw={600}>מעלית מוצעת על-ידי המערכת:</Text>
                <Text size="sm">{confirmReport.suggested_elevator_address}</Text>
                <Button color="green" loading={confirmMutation.isPending}
                  onClick={() => confirmMutation.mutate({ reportId: confirmReport.id })}>
                  ✅ אשר מעלית זו
                </Button>
                <Divider label="— או —" labelPosition="center" />
              </>
            )}

            <Text size="sm" fw={600}>חיפוש מעלית אחרת:</Text>
            <Autocomplete
              placeholder="הקלד כתובת, עיר או מס׳ מעלית..."
              value={elevSearch}
              onChange={v => { searchElevators(v); setSelectedElevId('') }}
              onOptionSubmit={v => {
                const opt = elevOptions.find(o => o.label === v)
                if (opt) setSelectedElevId(opt.id)
                setElevSearch(v)
              }}
              data={elevOptions.map(o => o.label)}
            />
            <Button variant="light" disabled={!selectedElevId} loading={confirmMutation.isPending}
              onClick={() => confirmMutation.mutate({ reportId: confirmReport.id, elevatorId: selectedElevId })}>
              שייך למעלית שנבחרה
            </Button>

            <Divider label="— לא מצאת? —" labelPosition="center" />
            <Button variant="subtle" color="blue" onClick={() => {
              setCreateMode(c => !c)
              if (!createMode && confirmReport) {
                const parts = (confirmReport.raw_address || '').split(',')
                setCreateElev({
                  address: parts[0]?.trim() || '',
                  city: confirmReport.raw_city || parts[1]?.trim() || '',
                  building_name: '',
                })
              }
            }}>
              {createMode ? '▲ ביטול' : '+ צור מעלית חדשה על בסיס הדוח'}
            </Button>
            {createMode && confirmReport && (
              <Paper withBorder p="sm" radius="sm">
                <Stack gap="sm">
                  <Text size="xs" c="dimmed">פרטי המעלית החדשה (מולאו מהדוח — ניתן לעדכן):</Text>
                  <TextInput label="כתובת *" size="xs" value={createElev.address}
                    onChange={e => setCreateElev(f => ({ ...f, address: e.target.value }))} />
                  <TextInput label="עיר *" size="xs" value={createElev.city}
                    onChange={e => setCreateElev(f => ({ ...f, city: e.target.value }))} />
                  <TextInput label="שם בניין (אופציונלי)" size="xs" value={createElev.building_name}
                    onChange={e => setCreateElev(f => ({ ...f, building_name: e.target.value }))} />
                  <Button color="green" size="sm"
                    disabled={!createElev.address.trim() || !createElev.city.trim()}
                    loading={createElevatorMutation.isPending}
                    onClick={() => createElevatorMutation.mutate({ reportId: confirmReport.id, ...createElev })}>
                    ✅ צור מעלית ושייך דוח
                  </Button>
                </Stack>
              </Paper>
            )}
          </Stack>
        )}
      </Modal>

      {/* Completion report modal */}
      <Modal
        opened={!!completionModal}
        onClose={() => { setCompletionModal(null); setCompletionNotes('') }}
        title="✅ דוח סיום טיפול"
        dir="rtl"
        size="md"
      >
        {completionModal && (
          <Stack gap="md">
            <Text size="sm">📍 <strong>{completionModal.elevatorAddress}</strong></Text>
            <Text size="sm" c="dimmed">כל הליקויים סומנו כמטופלים. ניתן לערוך את הסיכום לפני שליחה:</Text>
            <Textarea
              label="סיכום הטיפול"
              value={completionNotes}
              onChange={e => setCompletionNotes(e.target.value)}
              minRows={4}
              autosize
            />
            <Group justify="flex-end" gap="sm">
              <Button variant="subtle" onClick={() => { setCompletionModal(null); setCompletionNotes('') }}>סגור ללא שליחה</Button>
              <Button color="green" loading={completeMutation.isPending}
                onClick={() => completeMutation.mutate({ reportId: completionModal.reportId, notes: completionNotes })}>
                📤 שלח דוח למנהל
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  )
}
