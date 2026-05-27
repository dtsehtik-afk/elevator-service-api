import { useState } from 'react'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Modal, TextInput,
  Select, Textarea, Table, Tabs, Progress, ActionIcon, Tooltip,
  ScrollArea, Box, Loader, Center, NumberInput, Divider, Checkbox,
  Alert, RingProgress, ThemeIcon,
} from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { projectsApi, Project, ProjectTask, ProjectDetail } from '../api/projects'
import { DocumentUploadPanel } from '../components/DocumentUploadPanel'
import { CustomerSearchSelect } from '../components/CustomerSearchSelect'
import client from '../api/client'

const STATUS_COLORS: Record<string, string> = {
  PLANNING: 'gray', ACTIVE: 'blue', ON_HOLD: 'orange', COMPLETED: 'green', CANCELLED: 'red',
}
const STATUS_LABELS: Record<string, string> = {
  PLANNING: 'תכנון', ACTIVE: 'פעיל', ON_HOLD: 'מושהה', COMPLETED: 'הושלם', CANCELLED: 'בוטל',
}
const TASK_STATUS_COLORS: Record<string, string> = {
  PENDING: 'gray', IN_PROGRESS: 'blue', DONE: 'green', BLOCKED: 'red',
}
const TASK_STATUS_LABELS: Record<string, string> = {
  PENDING: 'ממתין', IN_PROGRESS: 'בביצוע', DONE: 'הושלם', BLOCKED: 'חסום',
}

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}
function toISODate(d: Date | null) { return d ? d.toISOString().slice(0, 10) : null }

// ── Gantt component ──────────────────────────────────────────────────────────

function GanttChart({ tasks }: { tasks: ProjectTask[] }) {
  const datedTasks = tasks.filter(t => t.start_date && t.end_date)
  if (datedTasks.length === 0) {
    return <Text c="dimmed" ta="center" py="md">הוסף תאריכי התחלה וסיום למשימות כדי להציג גאנט</Text>
  }

  const dates = datedTasks.flatMap(t => [new Date(t.start_date!), new Date(t.end_date!)])
  const minDate = new Date(Math.min(...dates.map(d => d.getTime())))
  const maxDate = new Date(Math.max(...dates.map(d => d.getTime())))
  minDate.setDate(minDate.getDate() - 1)
  maxDate.setDate(maxDate.getDate() + 1)
  const totalDays = Math.max(1, (maxDate.getTime() - minDate.getTime()) / 86400000)

  function pct(d: Date) {
    return Math.max(0, Math.min(100, ((d.getTime() - minDate.getTime()) / (maxDate.getTime() - minDate.getTime())) * 100))
  }

  const today = new Date()
  const todayPct = pct(today)

  // Generate month markers
  const months: { label: string; pct: number }[] = []
  const cursor = new Date(minDate)
  cursor.setDate(1)
  while (cursor <= maxDate) {
    months.push({
      label: cursor.toLocaleDateString('he-IL', { month: 'short', year: '2-digit' }),
      pct: pct(cursor),
    })
    cursor.setMonth(cursor.getMonth() + 1)
  }

  return (
    <Box style={{ overflowX: 'auto' }}>
      <Box style={{ minWidth: 600, position: 'relative' }}>
        {/* Month header */}
        <Box style={{ position: 'relative', height: 28, borderBottom: '1px solid var(--mantine-color-gray-3)', marginBottom: 4 }}>
          {months.map(m => (
            <Text
              key={m.label}
              size="xs"
              c="dimmed"
              style={{ position: 'absolute', left: `${m.pct}%`, transform: 'translateX(-50%)', whiteSpace: 'nowrap' }}
            >
              {m.label}
            </Text>
          ))}
        </Box>

        {/* Today line */}
        {todayPct >= 0 && todayPct <= 100 && (
          <Box
            style={{
              position: 'absolute',
              top: 28,
              bottom: 0,
              left: `${todayPct}%`,
              width: 2,
              backgroundColor: 'var(--mantine-color-red-5)',
              opacity: 0.6,
              zIndex: 2,
            }}
          />
        )}

        {/* Task rows */}
        <Stack gap={6} pt={4}>
          {datedTasks.map(t => {
            const start = pct(new Date(t.start_date!))
            const end = pct(new Date(t.end_date!))
            const width = Math.max(1, end - start)
            const color = TASK_STATUS_COLORS[t.status] ?? 'blue'
            return (
              <Box key={t.id} style={{ position: 'relative', height: 36 }}>
                {/* Label on left */}
                <Text
                  size="xs"
                  style={{
                    position: 'absolute',
                    right: `${100 - start + 1}%`,
                    top: '50%',
                    transform: 'translateY(-50%)',
                    whiteSpace: 'nowrap',
                    maxWidth: 160,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    textAlign: 'right',
                  }}
                >
                  {t.assignee ? `${t.name} (${t.assignee})` : t.name}
                </Text>
                {/* Bar */}
                <Box
                  style={{
                    position: 'absolute',
                    left: `${start}%`,
                    width: `${width}%`,
                    top: '15%',
                    height: '70%',
                    borderRadius: 4,
                    backgroundColor: `var(--mantine-color-${color}-${t.status === 'DONE' ? 6 : 4})`,
                    display: 'flex',
                    alignItems: 'center',
                    paddingLeft: 6,
                    overflow: 'hidden',
                  }}
                >
                  {t.progress > 0 && (
                    <Box
                      style={{
                        position: 'absolute',
                        left: 0,
                        top: 0,
                        height: '100%',
                        width: `${t.progress}%`,
                        backgroundColor: `var(--mantine-color-${color}-7)`,
                        borderRadius: 4,
                        opacity: 0.5,
                      }}
                    />
                  )}
                  <Text size="xs" c="white" fw={600} style={{ position: 'relative', zIndex: 1, whiteSpace: 'nowrap' }}>
                    {t.progress > 0 ? `${t.progress}%` : ''}
                  </Text>
                </Box>
              </Box>
            )
          })}
        </Stack>
      </Box>
    </Box>
  )
}

// ── Shared project form ───────────────────────────────────────────────────────

const PROJECT_TYPE_LABELS: Record<string, string> = {
  NEW_INSTALLATION: 'התקנה חדשה',
  RENOVATION: 'שיפוץ',
  REPLACEMENT: 'החלפה',
  MODERNIZATION: 'מודרניזציה',
}

function ProjectForm({ form, setForm, technicians, consultantsList, onSubmit, loading, submitLabel }: {
  form: any; setForm: (fn: (f: any) => any) => void
  technicians: any[]; consultantsList: any[]
  onSubmit: () => void; loading: boolean; submitLabel: string
}) {
  const f = (key: string) => (val: any) => setForm((prev: any) => ({ ...prev, [key]: val === '' ? null : val }))
  const selectedConsultant = consultantsList.find((c: any) => c.id === form.consultant_id) || null

  return (
    <Stack gap="sm">
      <TextInput label="שם פרויקט" required value={form.name || ''} onChange={e => setForm((p: any) => ({ ...p, name: e.target.value }))} />
      <Group grow>
        <Select label="סטטוס" value={form.status} onChange={f('status')}
          data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
        <Select label="סוג פרויקט" value={form.project_type || null} onChange={f('project_type')} clearable
          data={Object.entries(PROJECT_TYPE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
      </Group>

      <Divider label="לקוח ואיש קשר" labelPosition="right" />
      <CustomerSearchSelect
        value={form.customer_id || null}
        onChange={v => setForm((p: any) => ({ ...p, customer_id: v }))}
        onSelect={c => { if (c) setForm((p: any) => ({ ...p, contact_person: p.contact_person || c.contact_name || '', contact_phone: p.contact_phone || c.phone || '' })) }}
      />
      <Group grow>
        <TextInput label="איש קשר" value={form.contact_person || ''} onChange={e => setForm((p: any) => ({ ...p, contact_person: e.target.value }))} />
        <TextInput label="טלפון איש קשר" value={form.contact_phone || ''} onChange={e => setForm((p: any) => ({ ...p, contact_phone: e.target.value }))} />
      </Group>

      <Divider label="יועץ" labelPosition="right" />
      <Select
        label="יועץ"
        placeholder="בחר יועץ..."
        value={form.consultant_id || null}
        onChange={f('consultant_id')}
        clearable searchable
        data={consultantsList.map((c: any) => ({ value: c.id, label: c.name }))}
      />
      {selectedConsultant && (
        <Paper withBorder p="sm" radius="md" bg="gray.0">
          <Stack gap={4}>
            <Text size="sm" fw={600}>🧑‍💼 {selectedConsultant.name}</Text>
            {selectedConsultant.phone && <Text size="xs" c="dimmed">📞 {selectedConsultant.phone}</Text>}
            {selectedConsultant.email && <Text size="xs" c="dimmed">✉️ {selectedConsultant.email}</Text>}
            {(selectedConsultant.consultant_contacts || []).length > 0 && (
              <>
                <Text size="xs" fw={500} mt={4}>אנשי קשר:</Text>
                {(selectedConsultant.consultant_contacts as any[]).map((ct: any, i: number) => (
                  <Text key={i} size="xs" c="dimmed">
                    {ct.name && `${ct.name}`}{ct.phone && ` · ${ct.phone}`}{ct.email && ` · ${ct.email}`}
                  </Text>
                ))}
              </>
            )}
            {selectedConsultant.notes && <Text size="xs" c="dimmed" fs="italic">{selectedConsultant.notes}</Text>}
          </Stack>
        </Paper>
      )}

      <Divider label="מיקום ופרטי אתר" labelPosition="right" />
      <Group grow>
        <TextInput label="כתובת" value={form.address || ''} onChange={e => setForm((p: any) => ({ ...p, address: e.target.value }))} />
        <TextInput label="עיר" value={form.city || ''} onChange={e => setForm((p: any) => ({ ...p, city: e.target.value }))} />
      </Group>
      <TextInput label="שם אתר" value={form.site || ''} onChange={e => setForm((p: any) => ({ ...p, site: e.target.value }))} placeholder="שם הפרויקט / האתר" />

      <Divider label="פרטי פרויקט" labelPosition="right" />
      <Group grow>
        <DateInput label="תאריך התחלה" value={form.start_date} onChange={d => setForm((p: any) => ({ ...p, start_date: d }))} clearable locale="he" />
        <DateInput label="תאריך סיום מתוכנן" value={form.end_date} onChange={d => setForm((p: any) => ({ ...p, end_date: d }))} clearable locale="he" />
      </Group>
      <Group grow>
        <NumberInput label="מספר מעליות" value={form.elevator_count ?? ''} onChange={v => setForm((p: any) => ({ ...p, elevator_count: v || null }))} min={1} max={100} />
        <NumberInput label="שווי חוזה (₪)" value={form.contract_value ?? ''} onChange={v => setForm((p: any) => ({ ...p, contract_value: v || null }))} min={0} thousandSeparator="," />
      </Group>
      <Group grow>
        <TextInput label="יצרן" value={form.manufacturer || ''} onChange={e => setForm((p: any) => ({ ...p, manufacturer: e.target.value }))} placeholder="שם היצרן" />
        <Select label="טכנאי אחראי" value={form.responsible_technician_id || null} onChange={f('responsible_technician_id')} clearable searchable
          data={technicians.map((t: any) => ({ value: t.id, label: t.name }))} />
      </Group>
      <Textarea label="הערות" value={form.notes || ''} onChange={e => setForm((p: any) => ({ ...p, notes: e.target.value || null }))} autosize minRows={2} />
      <Button loading={loading} onClick={onSubmit}>{submitLabel}</Button>
    </Stack>
  )
}

// ── Milestones panel ─────────────────────────────────────────────────────────

const MILESTONES: { field: string; label: string; icon: string; required: boolean }[] = [
  { field: 'milestone_elevator_arrived',     label: 'הגעת מעלית לאתר',         icon: '🚚', required: false },
  { field: 'milestone_installation_started', label: 'תחילת התקנה',              icon: '🔧', required: false },
  { field: 'milestone_phase_a',              label: 'פאזה א — אישור',           icon: '✅', required: true  },
  { field: 'milestone_phase_b',              label: 'פאזה ב — אישור',           icon: '✅', required: true  },
  { field: 'milestone_phase_c',              label: 'פאזה ג — אישור',           icon: '✅', required: true  },
  { field: 'milestone_initial_inspection',   label: 'תסקיר ראשוני (יועץ/מכון)', icon: '📋', required: true  },
  { field: 'milestone_consultant_approved',  label: 'אישור יועץ סופי',          icon: '🏛️', required: true  },
]

function MilestonesPanel({ project }: { project: ProjectDetail }) {
  const qc = useQueryClient()

  const milestoneMut = useMutation({
    mutationFn: ({ field, value }: { field: string; value: boolean }) =>
      projectsApi.updateMilestone(project.id, field, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['project', project.id] })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
    onError: () => notifications.show({ message: 'שגיאה בעדכון עמדת ציון', color: 'red' }),
  })

  const requiredDone = MILESTONES.filter(m => m.required && (project as any)[m.field]).length
  const requiredTotal = MILESTONES.filter(m => m.required).length
  const allRequiredDone = requiredDone === requiredTotal
  const hasContract = project.has_service_contract
  const canComplete = allRequiredDone && hasContract

  return (
    <Stack gap="md">
      {/* Progress ring */}
      <Paper withBorder p="md" radius="md">
        <Group>
          <RingProgress
            size={80}
            thickness={8}
            sections={[{ value: (requiredDone / requiredTotal) * 100, color: allRequiredDone ? 'green' : 'blue' }]}
            label={<Text ta="center" size="xs" fw={700}>{requiredDone}/{requiredTotal}</Text>}
          />
          <Stack gap={4}>
            <Text fw={600}>עמדות ציון חובה</Text>
            <Text size="sm" c="dimmed">נדרשות לסגירת הפרויקט</Text>
            {canComplete
              ? <Badge color="green" size="sm">✅ הפרויקט מוכן לסגירה</Badge>
              : <Badge color="orange" size="sm">⏳ עוד לא מוכן לסגירה</Badge>
            }
          </Stack>
        </Group>
      </Paper>

      {/* Milestone checkboxes */}
      <Paper withBorder p="md" radius="md">
        <Stack gap="xs">
          {MILESTONES.map(m => {
            const checked = !!(project as any)[m.field]
            return (
              <Group key={m.field} justify="space-between" p="xs"
                style={{ borderRadius: 8, background: checked ? 'var(--mantine-color-green-0)' : undefined }}>
                <Group gap="sm">
                  <Text size="lg">{m.icon}</Text>
                  <Stack gap={0}>
                    <Text size="sm" fw={checked ? 600 : 400}
                      style={{ textDecoration: checked ? 'none' : undefined }}>
                      {m.label}
                    </Text>
                    {m.required && <Text size="xs" c="dimmed">חובה לסגירה</Text>}
                  </Stack>
                </Group>
                <Checkbox
                  checked={checked}
                  onChange={e => milestoneMut.mutate({ field: m.field, value: e.currentTarget.checked })}
                  disabled={milestoneMut.isPending}
                  color="green"
                  size="md"
                />
              </Group>
            )
          })}
        </Stack>
      </Paper>

      {/* Service contract status */}
      <Paper withBorder p="md" radius="md"
        style={{ borderColor: hasContract ? 'var(--mantine-color-green-4)' : 'var(--mantine-color-orange-4)' }}>
        <Group>
          <ThemeIcon color={hasContract ? 'green' : 'orange'} variant="light" size="xl" radius="md">
            {hasContract ? '📄' : '⚠️'}
          </ThemeIcon>
          <Stack gap={2}>
            <Text fw={600}>חוזה שירות</Text>
            {hasContract
              ? <Text size="sm" c="green">חוזה שירות פעיל קיים במערכת</Text>
              : <>
                  <Text size="sm" c="orange">לא קיים חוזה שירות פעיל</Text>
                  <Text size="xs" c="dimmed">יש לקשר חוזה שירות לפרויקט לפני הסגירה</Text>
                </>
            }
          </Stack>
        </Group>
      </Paper>

      {/* Completion blockers */}
      {!canComplete && (
        <Alert color="orange" title="מה חסר לסגירה?">
          <Stack gap={4}>
            {MILESTONES.filter(m => m.required && !(project as any)[m.field]).map(m => (
              <Text key={m.field} size="sm">• {m.label}</Text>
            ))}
            {!hasContract && <Text size="sm">• חוזה שירות פעיל</Text>}
          </Stack>
        </Alert>
      )}
    </Stack>
  )
}

// ── Project detail panel ─────────────────────────────────────────────────────

function ProjectPanel({ projectId, onClose }: { projectId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [addTaskOpen, setAddTaskOpen] = useState(false)
  const [editTaskId, setEditTaskId] = useState<string | null>(null)
  const [taskForm, setTaskForm] = useState<any>({ name: '', assignee: '', status: 'PENDING', progress: 0, start_date: null, end_date: null, notes: '' })

  const { data: project, isLoading } = useQuery<ProjectDetail>({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId),
  })

  const createTaskMut = useMutation({
    mutationFn: (data: any) => projectsApi.createTask(projectId, {
      ...data,
      start_date: toISODate(data.start_date),
      end_date: toISODate(data.end_date),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', projectId] }); setAddTaskOpen(false); notifications.show({ message: 'משימה נוספה', color: 'green' }) },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  const updateTaskMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => projectsApi.updateTask(projectId, id, {
      ...data,
      start_date: toISODate(data.start_date),
      end_date: toISODate(data.end_date),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', projectId] }); setEditTaskId(null); notifications.show({ message: 'משימה עודכנה', color: 'green' }) },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  const deleteTaskMut = useMutation({
    mutationFn: (taskId: string) => projectsApi.deleteTask(projectId, taskId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['project', projectId] }); notifications.show({ message: 'משימה נמחקה', color: 'orange' }) },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  function openAddTask() {
    setTaskForm({ name: '', assignee: '', status: 'PENDING', progress: 0, start_date: null, end_date: null, notes: '' })
    setAddTaskOpen(true)
  }

  function openEditTask(t: ProjectTask) {
    setTaskForm({ ...t, start_date: parseDate(t.start_date), end_date: parseDate(t.end_date) })
    setEditTaskId(t.id)
  }

  if (isLoading) return <Center h={200}><Loader /></Center>
  if (!project) return null

  const doneCount = project.tasks.filter(t => t.status === 'DONE').length

  return (
    <>
      <Group mb="md" justify="space-between">
        <Group>
          <Button variant="subtle" size="xs" onClick={onClose}>← חזרה</Button>
          <Text fw={700} size="lg">{project.name}</Text>
          <Badge color={STATUS_COLORS[project.status]}>{STATUS_LABELS[project.status]}</Badge>
          {project.site && <Text size="sm" c="dimmed">{project.site}</Text>}
        </Group>
        <Button size="xs" onClick={openAddTask}>+ משימה</Button>
      </Group>

      {project.tasks.length > 0 && (
        <Text size="xs" c="dimmed" mb="xs">
          {doneCount}/{project.tasks.length} משימות הושלמו
        </Text>
      )}

      <Tabs defaultValue="milestones">
        <Tabs.List>
          <Tabs.Tab value="milestones">
            🏁 עמדות ציון{' '}
            {(() => {
              const done = MILESTONES.filter(m => m.required && (project as any)[m.field]).length
              const total = MILESTONES.filter(m => m.required).length
              return <Badge size="xs" color={done === total ? 'green' : 'orange'} ml={4}>{done}/{total}</Badge>
            })()}
          </Tabs.Tab>
          <Tabs.Tab value="gantt">גאנט</Tabs.Tab>
          <Tabs.Tab value="tasks">משימות ({project.tasks.length})</Tabs.Tab>
          <Tabs.Tab value="documents">📎 מסמכים</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="milestones" pt="md">
          <MilestonesPanel project={project} />
        </Tabs.Panel>

        <Tabs.Panel value="gantt" pt="md">
          <Paper withBorder p="md" radius="md">
            <GanttChart tasks={project.tasks} />
          </Paper>
        </Tabs.Panel>

        <Tabs.Panel value="tasks" pt="md">
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>משימה</Table.Th>
                <Table.Th>אחראי</Table.Th>
                <Table.Th>התחלה</Table.Th>
                <Table.Th>סיום</Table.Th>
                <Table.Th>סטטוס</Table.Th>
                <Table.Th>התקדמות</Table.Th>
                <Table.Th></Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {project.tasks.map(t => (
                <Table.Tr key={t.id}>
                  <Table.Td><Text size="sm" fw={500}>{t.name}</Text></Table.Td>
                  <Table.Td><Text size="sm">{t.assignee || '—'}</Text></Table.Td>
                  <Table.Td><Text size="xs">{t.start_date ? new Date(t.start_date).toLocaleDateString('he-IL') : '—'}</Text></Table.Td>
                  <Table.Td><Text size="xs">{t.end_date ? new Date(t.end_date).toLocaleDateString('he-IL') : '—'}</Text></Table.Td>
                  <Table.Td><Badge size="sm" color={TASK_STATUS_COLORS[t.status]}>{TASK_STATUS_LABELS[t.status]}</Badge></Table.Td>
                  <Table.Td style={{ minWidth: 100 }}>
                    <Group gap={4}>
                      <Progress value={t.progress} size="sm" style={{ flex: 1 }} color={t.progress === 100 ? 'green' : 'blue'} />
                      <Text size="xs" c="dimmed">{t.progress}%</Text>
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4}>
                      <Button size="xs" variant="subtle" onClick={() => openEditTask(t)}>עריכה</Button>
                      <ActionIcon size="sm" color="red" variant="subtle"
                        onClick={() => { if (window.confirm('למחוק משימה?')) deleteTaskMut.mutate(t.id) }}>
                        🗑️
                      </ActionIcon>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
              {project.tasks.length === 0 && (
                <Table.Tr><Table.Td colSpan={7}><Text c="dimmed" ta="center" py="md">אין משימות — הוסף את הראשונה</Text></Table.Td></Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Tabs.Panel>

        <Tabs.Panel value="documents" pt="md">
          <DocumentUploadPanel entityType="PROJECT" entityId={projectId} />
        </Tabs.Panel>
      </Tabs>

      {/* Add/Edit task modal */}
      <Modal
        opened={addTaskOpen || !!editTaskId}
        onClose={() => { setAddTaskOpen(false); setEditTaskId(null) }}
        title={editTaskId ? 'עריכת משימה' : 'משימה חדשה'}
        dir="rtl"
      >
        <Stack gap="sm">
          <TextInput label="שם משימה" required value={taskForm.name} onChange={e => setTaskForm((f: any) => ({ ...f, name: e.target.value }))} />
          <TextInput label="אחראי" value={taskForm.assignee || ''} onChange={e => setTaskForm((f: any) => ({ ...f, assignee: e.target.value || null }))} />
          <Group grow>
            <DateInput label="התחלה" value={taskForm.start_date} onChange={d => setTaskForm((f: any) => ({ ...f, start_date: d }))} clearable locale="he" />
            <DateInput label="סיום" value={taskForm.end_date} onChange={d => setTaskForm((f: any) => ({ ...f, end_date: d }))} clearable locale="he" />
          </Group>
          <Select
            label="סטטוס"
            value={taskForm.status}
            onChange={v => setTaskForm((f: any) => ({ ...f, status: v }))}
            data={Object.entries(TASK_STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          />
          <Group grow align="flex-end">
            <TextInput
              label="התקדמות %"
              type="number"
              value={taskForm.progress}
              onChange={e => setTaskForm((f: any) => ({ ...f, progress: Math.min(100, Math.max(0, Number(e.target.value))) }))}
            />
          </Group>
          <Textarea label="הערות" value={taskForm.notes || ''} onChange={e => setTaskForm((f: any) => ({ ...f, notes: e.target.value || null }))} />
          <Button
            loading={createTaskMut.isPending || updateTaskMut.isPending}
            onClick={() => {
              if (editTaskId) {
                updateTaskMut.mutate({ id: editTaskId, data: taskForm })
              } else {
                createTaskMut.mutate(taskForm)
              }
            }}
          >
            {editTaskId ? 'שמור' : 'הוסף משימה'}
          </Button>
        </Stack>
      </Modal>
    </>
  )
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function ProjectsPage() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const emptyForm = { name: '', site: '', address: '', city: '', status: 'PLANNING', project_type: null, start_date: null, end_date: null, elevator_count: null, manufacturer: '', contract_value: null, customer_id: null, contact_person: '', contact_phone: '', consultant_id: null, responsible_technician_id: null, notes: '' }
  const [form, setForm] = useState<any>(emptyForm)
  const [editProjectId, setEditProjectId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<any>({})

  const { data: technicians = [] } = useQuery<any[]>({
    queryKey: ['technicians-list'],
    queryFn: () => client.get('/technicians').then(r => r.data),
  })
  const { data: consultantsList = [] } = useQuery<any[]>({
    queryKey: ['consultants-list'],
    queryFn: () => client.get('/consultants').then(r => r.data),
  })

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ['projects', statusFilter],
    queryFn: () => projectsApi.list(statusFilter ? { status: statusFilter } : undefined),
  })

  const createMut = useMutation({
    mutationFn: (data: any) => projectsApi.create({
      ...data,
      start_date: toISODate(data.start_date),
      end_date: toISODate(data.end_date),
    }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      notifications.show({ message: 'פרויקט נוסף', color: 'green' })
      setCreateOpen(false)
      setSelectedId(p.id)
    },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: any }) => projectsApi.update(id, {
      ...data,
      start_date: toISODate(data.start_date),
      end_date: toISODate(data.end_date),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      notifications.show({ message: 'פרויקט עודכן', color: 'green' })
      setEditProjectId(null)
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      if (detail?.blockers) {
        notifications.show({
          title: detail.message || 'לא ניתן לסגור פרויקט',
          message: detail.blockers.join(' • '),
          color: 'orange',
          autoClose: 8000,
        })
      } else {
        notifications.show({ message: 'שגיאה בשמירה', color: 'red' })
      }
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => projectsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects'] })
      notifications.show({ message: 'פרויקט נמחק', color: 'orange' })
      if (selectedId && projects.find(p => p.id === selectedId)) setSelectedId(null)
    },
    onError: () => notifications.show({ message: 'שגיאה', color: 'red' }),
  })

  if (selectedId) {
    return (
      <Stack gap="lg">
        <ProjectPanel projectId={selectedId} onClose={() => setSelectedId(null)} />
      </Stack>
    )
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>🏗️ פרויקטים ({projects.length})</Title>
        <Button onClick={() => { setForm({ name: '', site: '', status: 'PLANNING', start_date: null, end_date: null, notes: '' }); setCreateOpen(true) }}>
          + פרויקט חדש
        </Button>
      </Group>

      <Group>
        <Select
          placeholder="כל הסטטוסים"
          clearable
          value={statusFilter}
          onChange={setStatusFilter}
          data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))}
          w={180}
        />
      </Group>

      {isLoading ? (
        <Center h={200}><Loader /></Center>
      ) : (
        <Paper withBorder radius="md">
          <ScrollArea>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>שם פרויקט</Table.Th>
                  <Table.Th>אתר</Table.Th>
                  <Table.Th>סטטוס</Table.Th>
                  <Table.Th>התחלה</Table.Th>
                  <Table.Th>סיום</Table.Th>
                  <Table.Th>ציונים</Table.Th>
                  <Table.Th>משימות</Table.Th>
                  <Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {projects.map(p => (
                  <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedId(p.id)}>
                    <Table.Td><Text size="sm" fw={600}>{p.name}</Text></Table.Td>
                    <Table.Td><Text size="sm">{p.site || '—'}</Text></Table.Td>
                    <Table.Td><Badge color={STATUS_COLORS[p.status]} size="sm">{STATUS_LABELS[p.status]}</Badge></Table.Td>
                    <Table.Td><Text size="xs">{p.start_date ? new Date(p.start_date).toLocaleDateString('he-IL') : '—'}</Text></Table.Td>
                    <Table.Td><Text size="xs">{p.end_date ? new Date(p.end_date).toLocaleDateString('he-IL') : '—'}</Text></Table.Td>
                    <Table.Td>
                      {(() => {
                        const done = MILESTONES.filter(m => m.required && (p as any)[m.field]).length
                        const total = MILESTONES.filter(m => m.required).length
                        return (
                          <Tooltip label={`${done}/${total} עמדות ציון חובה`} withArrow>
                            <Badge size="sm" color={done === total ? 'green' : done > 0 ? 'blue' : 'gray'} variant="light">
                              {done}/{total}
                            </Badge>
                          </Tooltip>
                        )
                      })()}
                    </Table.Td>
                    <Table.Td><Badge variant="light" size="sm">{p.task_count}</Badge></Table.Td>
                    <Table.Td onClick={e => e.stopPropagation()}>
                      <Group gap={4}>
                        <Button size="xs" variant="subtle" onClick={() => {
                          setEditForm({ ...p, start_date: parseDate(p.start_date), end_date: parseDate(p.end_date) })
                          setEditProjectId(p.id)
                        }}>עריכה</Button>
                        <Tooltip label="מחק פרויקט">
                          <ActionIcon size="sm" color="red" variant="subtle"
                            onClick={() => { if (window.confirm('למחוק פרויקט זה ואת כל משימותיו?')) deleteMut.mutate(p.id) }}>
                            🗑️
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
                {projects.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={7}>
                      <Text c="dimmed" ta="center" py="xl">אין פרויקטים — צור את הראשון</Text>
                    </Table.Td>
                  </Table.Tr>
                )}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        </Paper>
      )}

      {/* Create project modal */}
      <Modal opened={createOpen} onClose={() => { setCreateOpen(false); setForm(emptyForm) }} title="פרויקט חדש" dir="rtl" size="lg">
        <ProjectForm
          form={form} setForm={setForm}
          technicians={technicians} consultantsList={consultantsList}
          onSubmit={() => createMut.mutate(form)}
          loading={createMut.isPending} submitLabel="צור פרויקט"
        />
      </Modal>

      {/* Edit project modal */}
      <Modal opened={!!editProjectId} onClose={() => setEditProjectId(null)} title="עריכת פרויקט" dir="rtl" size="lg">
        <ProjectForm
          form={editForm} setForm={setEditForm}
          technicians={technicians} consultantsList={consultantsList}
          onSubmit={() => updateMut.mutate({ id: editProjectId!, data: editForm })}
          loading={updateMut.isPending} submitLabel="שמור"
        />
      </Modal>
    </Stack>
  )
}
