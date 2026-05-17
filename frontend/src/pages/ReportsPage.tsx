import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  Stack, Title, Paper, Group, Select, Button, Text, Table, Badge,
  ActionIcon, Checkbox, Modal, TextInput, ScrollArea, Divider,
  Loader, Center, Pagination, Tabs, Tooltip, NumberInput, CloseButton,
  Box, rem, Drawer, Textarea, Avatar, Collapse,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { DateInput } from '@mantine/dates'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { reportsApi, type EntitySchema, type FilterItem, type ReportResult, type SavedView } from '../api/reports'
import client from '../api/client'

const ENTITY_LABELS: Record<string, string> = {
  service_calls: 'קריאות שירות',
  elevators: 'מעליות',
  customers: 'לקוחות',
  invoices: 'חשבוניות',
  inventory: 'מלאי',
  maintenance: 'תחזוקה',
  contracts: 'חוזים',
  leads: 'לידים',
  inspections: 'דוחות בודק',
}

const OPS = [
  { value: 'eq', label: 'שווה ל' },
  { value: 'neq', label: 'שונה מ' },
  { value: 'contains', label: 'מכיל' },
  { value: 'starts_with', label: 'מתחיל ב' },
  { value: 'gt', label: 'גדול מ' },
  { value: 'gte', label: 'גדול שווה' },
  { value: 'lt', label: 'קטן מ' },
  { value: 'lte', label: 'קטן שווה' },
  { value: 'is_null', label: 'ריק' },
  { value: 'is_not_null', label: 'לא ריק' },
]

// Which date field to use per entity for date-range quick filter
const ENTITY_DATE_FIELD: Record<string, string> = {
  service_calls: 'created_at',
  maintenance: 'scheduled_date',
  invoices: 'issue_date',
  contracts: 'start_date',
  leads: 'created_at',
  customers: 'created_at',
  inspections: 'inspection_date',
}

// Which city field per entity
const ENTITY_CITY_FIELD: Record<string, string> = {
  service_calls: 'city',
  maintenance: 'city',
  elevators: 'city',
  customers: 'city',
  inspections: 'raw_city',
}

// Which status field per entity (undefined = no status)
const ENTITY_STATUS_FIELD: Record<string, string> = {
  service_calls: 'status',
  elevators: 'status',
  maintenance: 'status',
  contracts: 'status',
  invoices: 'status',
  leads: 'status',
  inspections: 'result',
}

// Which customer field per entity (undefined = no customer filter)
const ENTITY_CUSTOMER_FIELD: Record<string, string> = {
  elevators: 'customer',
  invoices: 'customer_name',
  contracts: 'customer_name',
  leads: 'customer_name',
}

interface QuickFilters {
  status?: string
  city?: string
  technician?: string
  customer?: string
  dateFrom?: Date | null
  dateTo?: Date | null
}

interface ChatMessage {
  role: 'user' | 'assistant'
  text: string
}

const PAGE_SIZE = 50

export default function ReportsPage() {
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()
  const urlEntity = searchParams.get('entity')
  const [entityType, setEntityType] = useState<string>(urlEntity && ENTITY_LABELS[urlEntity] ? urlEntity : 'service_calls')
  const [selectedCols, setSelectedCols] = useState<string[]>([])
  const [filters, setFilters] = useState<FilterItem[]>([])
  const [quickFilters, setQuickFilters] = useState<QuickFilters>({})
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<ReportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [saveModalOpen, { open: openSaveModal, close: closeSaveModal }] = useDisclosure(false)
  const [viewName, setViewName] = useState('')
  const [activeView, setActiveView] = useState<string | null>(null)
  const [quickOpen, { toggle: toggleQuick }] = useDisclosure(true)

  // Sync entity type when URL param changes (side panel navigation)
  useEffect(() => {
    if (urlEntity && ENTITY_LABELS[urlEntity] && urlEntity !== entityType) {
      setEntityType(urlEntity)
      setFilters([])
      setQuickFilters({})
      setResult(null)
      setPage(1)
    }
  }, [urlEntity])

  // AI chat
  const [chatOpen, { open: openChat, close: closeChat }] = useDisclosure(false)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const chatBottomRef = useRef<HTMLDivElement>(null)

  // AI summary
  const [aiSummary, setAiSummary] = useState<string | null>(null)
  const [aiSummaryLoading, setAiSummaryLoading] = useState(false)

  async function runAiSummary() {
    if (!result || result.rows.length === 0) return
    setAiSummaryLoading(true)
    setAiSummary(null)
    try {
      const { data } = await client.post('/reports/ai-summary', {
        entity_type: entityType,
        columns: selectedCols,
        rows: result.rows,
        total: result.total,
      })
      setAiSummary(data.summary)
    } catch {
      setAiSummary('שגיאה בקבלת הסיכום. נסה שוב.')
    } finally {
      setAiSummaryLoading(false)
    }
  }

  const { data: schemas } = useQuery({
    queryKey: ['report-schemas'],
    queryFn: reportsApi.getAllSchemas,
  })

  const { data: filterOptions } = useQuery({
    queryKey: ['report-filter-options'],
    queryFn: reportsApi.getFilterOptions,
  })

  const { data: views, refetch: refetchViews } = useQuery({
    queryKey: ['report-views', entityType],
    queryFn: () => reportsApi.listViews(entityType),
  })

  const currentSchema: EntitySchema | undefined = schemas?.find(s => s.entity_type === entityType)

  useEffect(() => {
    if (currentSchema && selectedCols.length === 0) {
      setSelectedCols(currentSchema.default_columns)
    }
  }, [currentSchema?.entity_type])

  useEffect(() => {
    if (chatOpen) {
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    }
  }, [chatMessages, chatOpen])

  function handleEntityChange(val: string | null) {
    if (!val) return
    setEntityType(val)
    setSelectedCols([])
    setFilters([])
    setQuickFilters({})
    setSortBy(undefined)
    setResult(null)
    setPage(1)
    setActiveView(null)
  }

  function addFilter() {
    const filterable = currentSchema?.columns.filter(c => c.filterable) ?? []
    setFilters(prev => [...prev, { field: filterable[0]?.key ?? 'id', op: 'eq', value: '' }])
  }

  function updateFilter(idx: number, patch: Partial<FilterItem>) {
    setFilters(prev => prev.map((f, i) => i === idx ? { ...f, ...patch } : f))
  }

  function removeFilter(idx: number) {
    setFilters(prev => prev.filter((_, i) => i !== idx))
  }

  function buildAllFilters(): FilterItem[] {
    const all: FilterItem[] = [...filters.filter(f => f.op === 'is_null' || f.op === 'is_not_null' || f.value !== '')]

    if (quickFilters.status) {
      const field = ENTITY_STATUS_FIELD[entityType]
      if (field) all.push({ field, op: 'eq', value: quickFilters.status })
    }
    if (quickFilters.city) {
      const field = ENTITY_CITY_FIELD[entityType]
      if (field) all.push({ field, op: 'eq', value: quickFilters.city })
    }
    if (quickFilters.technician) {
      all.push({ field: 'technician_name', op: 'eq', value: quickFilters.technician })
    }
    if (quickFilters.customer) {
      const field = ENTITY_CUSTOMER_FIELD[entityType]
      if (field) all.push({ field, op: 'contains', value: quickFilters.customer })
    }
    if (quickFilters.dateFrom) {
      const field = ENTITY_DATE_FIELD[entityType]
      if (field) all.push({ field, op: 'gte', value: quickFilters.dateFrom.toISOString().split('T')[0] })
    }
    if (quickFilters.dateTo) {
      const field = ENTITY_DATE_FIELD[entityType]
      if (field) all.push({ field, op: 'lte', value: quickFilters.dateTo.toISOString().split('T')[0] })
    }

    return all
  }

  const activeQuickCount = Object.values(quickFilters).filter(v => v != null && v !== '').length

  async function runReport(pg = page, sb: string | undefined = sortBy, sd: 'asc' | 'desc' = sortDir) {
    setLoading(true)
    try {
      const data = await reportsApi.query({
        entity_type: entityType,
        columns: selectedCols.length > 0 ? selectedCols : undefined,
        filters: buildAllFilters(),
        sort_by: sb,
        sort_dir: sd,
        skip: (pg - 1) * PAGE_SIZE,
        limit: PAGE_SIZE,
      })
      setResult(data)
    } catch {
      notifications.show({ message: 'שגיאה בהרצת הדוח', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  async function handleExport() {
    try {
      const cols = selectedCols.length > 0 ? selectedCols.join(',') : undefined
      const allFilters = buildAllFilters()
      const filtersJson = allFilters.length > 0 ? JSON.stringify(allFilters) : undefined
      const resp = await client.get('/reports/export', {
        responseType: 'blob',
        params: { entity_type: entityType, columns: cols, filters: filtersJson, sort_by: sortBy, sort_dir: sortDir },
      })
      const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `${entityType}_report.xlsx`
      a.click()
    } catch {
      notifications.show({ message: 'שגיאה בייצוא', color: 'red' })
    }
  }

  const saveViewMutation = useMutation({
    mutationFn: () => reportsApi.createView({
      entity_type: entityType,
      name: viewName,
      columns: selectedCols,
      filters: filters,
      sort_by: sortBy,
      sort_dir: sortDir,
    }),
    onSuccess: () => {
      refetchViews()
      closeSaveModal()
      setViewName('')
      notifications.show({ message: 'תצוגה נשמרה', color: 'green' })
    },
  })

  function loadView(view: SavedView) {
    setSelectedCols(view.columns)
    setFilters(view.filters)
    setSortBy(view.sort_by)
    setSortDir((view.sort_dir as 'asc' | 'desc') || 'desc')
    setActiveView(view.id)
  }

  async function deleteView(id: string) {
    await reportsApi.deleteView(id)
    refetchViews()
    if (activeView === id) setActiveView(null)
  }

  async function sendChatMessage() {
    const q = chatInput.trim()
    if (!q || chatLoading) return
    setChatInput('')
    setChatMessages(prev => [...prev, { role: 'user', text: q }])
    setChatLoading(true)
    try {
      const { answer } = await reportsApi.aiChat(q)
      setChatMessages(prev => [...prev, { role: 'assistant', text: answer }])
    } catch {
      setChatMessages(prev => [...prev, { role: 'assistant', text: 'שגיאה בתקשורת עם ה-AI. נסה שוב.' }])
    } finally {
      setChatLoading(false)
    }
  }

  const totalPages = result ? Math.ceil(result.total / PAGE_SIZE) : 0
  const filterable = currentSchema?.columns.filter(c => c.filterable) ?? []

  const SMART_TEMPLATES = [
    {
      id: 'ops',
      label: '🔧 דוח תפעול',
      desc: 'קריאות פתוחות + חריגות SLA',
      entity: 'service_calls',
      cols: ['call_number', 'created_at', 'address', 'city', 'status', 'priority', 'fault_type', 'technician_name', 'sla_deadline'],
      filters: [{ field: 'status', op: 'neq', value: 'CLOSED' }, { field: 'status', op: 'neq', value: 'RESOLVED' }],
      sort: 'priority', dir: 'asc' as const,
    },
    {
      id: 'finance',
      label: '💰 דוח כספי',
      desc: 'חשבוניות לא שולמו',
      entity: 'invoices',
      cols: ['number', 'customer_name', 'total', 'amount_paid', 'status', 'due_date', 'issue_date'],
      filters: [{ field: 'status', op: 'neq', value: 'PAID' }, { field: 'status', op: 'neq', value: 'CANCELLED' }],
      sort: 'due_date', dir: 'asc' as const,
    },
    {
      id: 'safety',
      label: '🔴 דוח בטיחות',
      desc: 'ליקויים פתוחים + בדיקות',
      entity: 'inspections',
      cols: ['inspection_date', 'raw_address', 'raw_city', 'labor_file_number', 'report_status', 'match_status', 'inspector_name'],
      filters: [{ field: 'report_status', op: 'neq', value: 'CLOSED' }, { field: 'report_status', op: 'neq', value: 'NA' }],
      sort: 'inspection_date', dir: 'asc' as const,
    },
  ]

  function applyTemplate(tpl: typeof SMART_TEMPLATES[0]) {
    setEntityType(tpl.entity)
    setSelectedCols(tpl.cols)
    setFilters(tpl.filters)
    setQuickFilters({})
    setSortBy(tpl.sort)
    setSortDir(tpl.dir)
    setResult(null)
    setPage(1)
    setAiSummary(null)
  }

  // Status options for quick filter
  const statusField = ENTITY_STATUS_FIELD[entityType]
  const statusOptions = currentSchema?.columns.find(c => c.key === statusField)?.options ?? []

  const hasCityFilter = entityType in ENTITY_CITY_FIELD
  const hasTechnicianFilter = entityType === 'maintenance'
  const hasCustomerFilter = entityType in ENTITY_CUSTOMER_FIELD
  const hasDateFilter = entityType in ENTITY_DATE_FIELD

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>📊 בניית דוחות</Title>
        <Group>
          <Button variant="light" color="grape" leftSection="🤖" onClick={openChat}>
            שאל AI
          </Button>
          {result && result.rows.length > 0 && (
            <Button
              variant="light" color="violet"
              leftSection="✨"
              onClick={runAiSummary}
              loading={aiSummaryLoading}
            >
              סכם עם AI
            </Button>
          )}
          <Button variant="light" onClick={() => runReport()} loading={loading}>
            הרץ דוח
          </Button>
          <Button variant="outline" onClick={handleExport}>
            ייצא Excel
          </Button>
        </Group>
      </Group>

      {/* Smart templates */}
      <Paper withBorder radius="md" p="sm">
        <Group gap="xs" wrap="wrap">
          <Text size="sm" fw={600} c="dimmed">תבניות חכמות:</Text>
          {SMART_TEMPLATES.map(tpl => (
            <Tooltip key={tpl.id} label={tpl.desc} position="bottom">
              <Button size="xs" variant="default" onClick={() => applyTemplate(tpl)}>
                {tpl.label}
              </Button>
            </Tooltip>
          ))}
        </Group>
      </Paper>

      {/* AI Summary result */}
      {aiSummary && (
        <Paper withBorder radius="md" p="md" style={{ background: 'var(--mantine-color-violet-0)', borderColor: 'var(--mantine-color-violet-3)' }}>
          <Group justify="space-between" mb="xs">
            <Group gap="xs">
              <Text size="sm">✨</Text>
              <Text size="sm" fw={700} c="violet">סיכום מנהלים — AI</Text>
            </Group>
            <CloseButton size="xs" onClick={() => setAiSummary(null)} />
          </Group>
          <Text size="sm" style={{ lineHeight: 1.7 }}>{aiSummary}</Text>
        </Paper>
      )}

      {/* Entity type selector */}
      <Paper withBorder radius="md" p="md">
        <Group>
          <Select
            label="סוג נתונים"
            value={entityType}
            onChange={handleEntityChange}
            data={Object.entries(ENTITY_LABELS).map(([v, l]) => ({ value: v, label: l }))}
            w={220}
          />
        </Group>
      </Paper>

      {/* Saved views bar */}
      {views && views.length > 0 && (
        <Paper withBorder radius="md" p="sm">
          <Group gap="xs">
            <Text size="sm" fw={500} c="dimmed">תצוגות שמורות:</Text>
            {views.map(view => (
              <Group key={view.id} gap={4}>
                <Button
                  size="xs"
                  variant={activeView === view.id ? 'filled' : 'light'}
                  onClick={() => loadView(view)}
                >
                  {view.name}
                  {view.is_default && ' ★'}
                </Button>
                <CloseButton size="xs" onClick={() => deleteView(view.id)} />
              </Group>
            ))}
          </Group>
        </Paper>
      )}

      <Group align="flex-start" gap="md">
        {/* Column picker */}
        <Paper withBorder radius="md" p="md" style={{ width: 280, flexShrink: 0 }}>
          <Title order={5} mb="sm">בחירת עמודות</Title>
          <ScrollArea h={400}>
            <Stack gap="xs">
              {currentSchema?.columns.map(col => (
                <Checkbox
                  key={col.key}
                  label={col.label_he}
                  checked={selectedCols.includes(col.key)}
                  onChange={e => {
                    if (e.currentTarget.checked) {
                      setSelectedCols(prev => [...prev, col.key])
                    } else {
                      setSelectedCols(prev => prev.filter(c => c !== col.key))
                    }
                  }}
                />
              ))}
            </Stack>
          </ScrollArea>
          <Button size="xs" variant="subtle" mt="sm" onClick={() => setSelectedCols(currentSchema?.columns.map(c => c.key) ?? [])}>
            בחר הכל
          </Button>
          <Button size="xs" variant="subtle" mt="sm" mr="xs" color="red" onClick={() => setSelectedCols([])}>
            נקה
          </Button>
        </Paper>

        {/* Filters + results */}
        <Stack gap="md" style={{ flex: 1, minWidth: 0 }}>

          {/* Quick filters */}
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb={quickOpen ? 'sm' : 0}>
              <Group gap="xs">
                <Title order={5}>סינונים מהירים</Title>
                {activeQuickCount > 0 && (
                  <Badge color="blue" size="sm">{activeQuickCount} פעיל</Badge>
                )}
              </Group>
              <Group gap="xs">
                {activeQuickCount > 0 && (
                  <Button size="xs" variant="subtle" color="red" onClick={() => setQuickFilters({})}>
                    נקה הכל
                  </Button>
                )}
                <Button size="xs" variant="subtle" onClick={toggleQuick}>
                  {quickOpen ? '▲ כווץ' : '▼ הרחב'}
                </Button>
              </Group>
            </Group>

            <Collapse in={quickOpen}>
              <Group gap="sm" align="flex-end" wrap="wrap">
                {statusField && statusOptions.length > 0 && (
                  <Select
                    label="סטטוס"
                    placeholder="כל הסטטוסים"
                    value={quickFilters.status ?? null}
                    onChange={v => setQuickFilters(prev => ({ ...prev, status: v ?? undefined }))}
                    data={statusOptions.map(o => ({ value: o, label: o }))}
                    clearable
                    w={160}
                    size="sm"
                  />
                )}

                {hasCityFilter && (
                  <Select
                    label="עיר / אזור"
                    placeholder="כל הערים"
                    value={quickFilters.city ?? null}
                    onChange={v => setQuickFilters(prev => ({ ...prev, city: v ?? undefined }))}
                    data={(filterOptions?.cities ?? []).map(c => ({ value: c, label: c }))}
                    clearable
                    searchable
                    w={160}
                    size="sm"
                  />
                )}

                {hasTechnicianFilter && (
                  <Select
                    label="טכנאי"
                    placeholder="כל הטכנאים"
                    value={quickFilters.technician ?? null}
                    onChange={v => setQuickFilters(prev => ({ ...prev, technician: v ?? undefined }))}
                    data={(filterOptions?.technicians ?? []).map(t => ({ value: t, label: t }))}
                    clearable
                    searchable
                    w={160}
                    size="sm"
                  />
                )}

                {hasCustomerFilter && (
                  <Select
                    label="לקוח"
                    placeholder="כל הלקוחות"
                    value={quickFilters.customer ?? null}
                    onChange={v => setQuickFilters(prev => ({ ...prev, customer: v ?? undefined }))}
                    data={(filterOptions?.customers ?? []).map(c => ({ value: c.name, label: c.name }))}
                    clearable
                    searchable
                    w={200}
                    size="sm"
                  />
                )}

                {hasDateFilter && (
                  <>
                    <DateInput
                      label="מתאריך"
                      placeholder="בחר תאריך"
                      value={quickFilters.dateFrom ?? null}
                      onChange={v => setQuickFilters(prev => ({ ...prev, dateFrom: v }))}
                      clearable
                      w={150}
                      size="sm"
                      valueFormat="DD/MM/YYYY"
                    />
                    <DateInput
                      label="עד תאריך"
                      placeholder="בחר תאריך"
                      value={quickFilters.dateTo ?? null}
                      onChange={v => setQuickFilters(prev => ({ ...prev, dateTo: v }))}
                      clearable
                      w={150}
                      size="sm"
                      valueFormat="DD/MM/YYYY"
                    />
                  </>
                )}

                {!statusField && !hasCityFilter && !hasTechnicianFilter && !hasCustomerFilter && !hasDateFilter && (
                  <Text size="sm" c="dimmed">אין סינונים מהירים זמינים לסוג זה</Text>
                )}
              </Group>
            </Collapse>
          </Paper>

          {/* Advanced filters */}
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Title order={5}>סינונים מתקדמים</Title>
              <Button size="xs" variant="light" onClick={addFilter} disabled={filterable.length === 0}>+ הוסף סינון</Button>
            </Group>
            {filters.length === 0 && (
              <Text size="sm" c="dimmed">אין סינונים מתקדמים פעילים</Text>
            )}
            <Stack gap="xs">
              {filters.map((f, idx) => (
                <Group key={idx} gap="xs">
                  <Select
                    size="xs"
                    w={160}
                    value={f.field}
                    onChange={v => updateFilter(idx, { field: v || '' })}
                    data={filterable.map(c => ({ value: c.key, label: c.label_he }))}
                    searchable
                  />
                  <Select
                    size="xs"
                    w={120}
                    value={f.op}
                    onChange={v => updateFilter(idx, { op: v || 'eq' })}
                    data={OPS}
                  />
                  {f.op !== 'is_null' && f.op !== 'is_not_null' && (
                    <TextInput
                      size="xs"
                      w={150}
                      value={f.value ?? ''}
                      onChange={e => updateFilter(idx, { value: e.target.value })}
                      placeholder="ערך..."
                    />
                  )}
                  <ActionIcon size="xs" color="red" variant="light" onClick={() => removeFilter(idx)}>✕</ActionIcon>
                </Group>
              ))}
            </Stack>
          </Paper>

          {/* Results table */}
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Group gap="xs">
                <Text size="sm" c="dimmed">
                  {result ? `${result.total} תוצאות` : '—'}
                </Text>
                {result && totalPages > 1 && (
                  <Pagination
                    size="xs"
                    total={totalPages}
                    value={page}
                    onChange={pg => { setPage(pg); runReport(pg) }}
                  />
                )}
              </Group>
              <Group gap="xs">
                <Select
                  size="xs"
                  w={160}
                  placeholder="מיין לפי..."
                  value={sortBy ?? null}
                  onChange={v => setSortBy(v ?? undefined)}
                  data={currentSchema?.columns.map(c => ({ value: c.key, label: c.label_he })) ?? []}
                  clearable
                />
                <Select
                  size="xs"
                  w={100}
                  value={sortDir}
                  onChange={v => setSortDir((v as 'asc' | 'desc') || 'desc')}
                  data={[{ value: 'desc', label: 'יורד' }, { value: 'asc', label: 'עולה' }]}
                />
                <Button size="xs" variant="subtle" onClick={openSaveModal}>שמור תצוגה</Button>
              </Group>
            </Group>

            {loading && <Center p="xl"><Loader /></Center>}

            {!loading && result && (
              <ScrollArea>
                <Table striped withTableBorder withColumnBorders style={{ minWidth: 600 }}>
                  <Table.Thead>
                    <Table.Tr>
                      {result.columns_meta.map(col => (
                        <Table.Th
                          key={col.key}
                          style={{ cursor: 'pointer', whiteSpace: 'nowrap' }}
                          onClick={() => {
                            const newSb = col.key
                            const newSd: 'asc' | 'desc' = sortBy === col.key ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
                            setSortBy(newSb)
                            setSortDir(newSd)
                            runReport(page, newSb, newSd)
                          }}
                        >
                          {col.label_he}
                          {sortBy === col.key && (sortDir === 'asc' ? ' ▲' : ' ▼')}
                        </Table.Th>
                      ))}
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {result.rows.map((row, i) => (
                      <Table.Tr key={i}>
                        {result.columns_meta.map(col => (
                          <Table.Td key={col.key} style={{ whiteSpace: 'nowrap', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {row[col.key] == null ? <Text size="xs" c="dimmed">—</Text> : String(row[col.key])}
                          </Table.Td>
                        ))}
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}

            {!loading && !result && (
              <Center p="xl">
                <Text c="dimmed">לחץ על "הרץ דוח" להצגת תוצאות</Text>
              </Center>
            )}
          </Paper>
        </Stack>
      </Group>

      {/* Save view modal */}
      <Modal opened={saveModalOpen} onClose={closeSaveModal} title="שמירת תצוגה" centered>
        <Stack>
          <TextInput
            label="שם התצוגה"
            placeholder="לדוגמה: קריאות פתוחות החודש"
            value={viewName}
            onChange={e => setViewName(e.target.value)}
          />
          <Button
            onClick={() => saveViewMutation.mutate()}
            loading={saveViewMutation.isPending}
            disabled={!viewName.trim()}
          >
            שמור
          </Button>
        </Stack>
      </Modal>

      {/* AI Chat Drawer */}
      <Drawer
        opened={chatOpen}
        onClose={closeChat}
        title={<Text fw={700} size="lg">🤖 שאל AI על הנתונים</Text>}
        position="left"
        size="md"
        dir="rtl"
      >
        <Stack h="calc(100vh - 120px)" gap={0}>
          {/* Messages */}
          <ScrollArea style={{ flex: 1 }} p="sm">
            {chatMessages.length === 0 && (
              <Stack gap="xs" align="center" pt="xl">
                <Text size="xl">🤖</Text>
                <Text c="dimmed" ta="center" size="sm">
                  שאל אותי על הנתונים בעברית חופשית:
                </Text>
                <Stack gap="xs" w="100%">
                  {[
                    'כמה קריאות פתוחות יש היום?',
                    'מה המעליות עם ציון סיכון גבוה?',
                    'כמה תחזוקות מתוכננות החודש?',
                    'מי הטכנאי הכי עסוק?',
                  ].map(ex => (
                    <Button
                      key={ex}
                      variant="light"
                      size="xs"
                      fullWidth
                      style={{ textAlign: 'right', justifyContent: 'flex-start' }}
                      onClick={() => { setChatInput(ex) }}
                    >
                      {ex}
                    </Button>
                  ))}
                </Stack>
              </Stack>
            )}

            <Stack gap="sm">
              {chatMessages.map((msg, i) => (
                <Box
                  key={i}
                  style={{
                    display: 'flex',
                    justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <Paper
                    p="sm"
                    radius="md"
                    style={{
                      maxWidth: '85%',
                      background: msg.role === 'user' ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-gray-1)',
                      color: msg.role === 'user' ? 'white' : 'inherit',
                      whiteSpace: 'pre-wrap',
                    }}
                  >
                    <Text size="sm">{msg.text}</Text>
                  </Paper>
                </Box>
              ))}
              {chatLoading && (
                <Box style={{ display: 'flex', justifyContent: 'flex-start' }}>
                  <Paper p="sm" radius="md" style={{ background: 'var(--mantine-color-gray-1)' }}>
                    <Loader size="xs" />
                  </Paper>
                </Box>
              )}
              <div ref={chatBottomRef} />
            </Stack>
          </ScrollArea>

          {/* Input area */}
          <Divider />
          <Box p="sm">
            <Group gap="xs" align="flex-end">
              <Textarea
                style={{ flex: 1 }}
                placeholder="שאל שאלה על הנתונים..."
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                autosize
                minRows={1}
                maxRows={4}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendChatMessage()
                  }
                }}
              />
              <Button
                onClick={sendChatMessage}
                loading={chatLoading}
                disabled={!chatInput.trim()}
              >
                שלח
              </Button>
            </Group>
            <Text size="xs" c="dimmed" mt={4}>Enter לשליחה • Shift+Enter לשורה חדשה</Text>
          </Box>
        </Stack>
      </Drawer>
    </Stack>
  )
}
