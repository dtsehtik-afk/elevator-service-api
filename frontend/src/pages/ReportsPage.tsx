import { useState, useEffect } from 'react'
import {
  Stack, Title, Paper, Group, Select, Button, Text, Table, Badge,
  ActionIcon, Checkbox, Modal, TextInput, ScrollArea, Divider,
  Loader, Center, Pagination, Tabs, Tooltip, NumberInput, CloseButton,
  Box, rem,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
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

const PAGE_SIZE = 50

export default function ReportsPage() {
  const qc = useQueryClient()
  const [entityType, setEntityType] = useState<string>('service_calls')
  const [selectedCols, setSelectedCols] = useState<string[]>([])
  const [filters, setFilters] = useState<FilterItem[]>([])
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [page, setPage] = useState(1)
  const [result, setResult] = useState<ReportResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [saveModalOpen, { open: openSaveModal, close: closeSaveModal }] = useDisclosure(false)
  const [viewName, setViewName] = useState('')
  const [activeView, setActiveView] = useState<string | null>(null)

  const { data: schemas } = useQuery({
    queryKey: ['report-schemas'],
    queryFn: reportsApi.getAllSchemas,
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

  function handleEntityChange(val: string | null) {
    if (!val) return
    setEntityType(val)
    setSelectedCols([])
    setFilters([])
    setSortBy(undefined)
    setResult(null)
    setPage(1)
    setActiveView(null)
  }

  function addFilter() {
    setFilters(prev => [...prev, { field: currentSchema?.columns[0]?.key ?? 'id', op: 'eq', value: '' }])
  }

  function updateFilter(idx: number, patch: Partial<FilterItem>) {
    setFilters(prev => prev.map((f, i) => i === idx ? { ...f, ...patch } : f))
  }

  function removeFilter(idx: number) {
    setFilters(prev => prev.filter((_, i) => i !== idx))
  }

  async function runReport(pg = page) {
    setLoading(true)
    try {
      const data = await reportsApi.query({
        entity_type: entityType,
        columns: selectedCols.length > 0 ? selectedCols : undefined,
        filters: filters.filter(f => f.op === 'is_null' || f.op === 'is_not_null' || f.value !== ''),
        sort_by: sortBy,
        sort_dir: sortDir,
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
      const filtersJson = filters.length > 0 ? JSON.stringify(filters) : undefined
      const url = reportsApi.exportUrl({
        entity_type: entityType,
        columns: cols,
        filters: filtersJson,
        sort_by: sortBy,
        sort_dir: sortDir,
      })
      const resp = await client.get(url.replace(client.defaults.baseURL || '', ''), {
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

  const totalPages = result ? Math.ceil(result.total / PAGE_SIZE) : 0
  const filterable = currentSchema?.columns.filter(c => c.filterable) ?? []

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>📊 בניית דוחות</Title>
        <Group>
          <Button variant="light" onClick={() => runReport()} loading={loading}>
            הרץ דוח
          </Button>
          <Button variant="outline" onClick={handleExport}>
            ייצא Excel
          </Button>
        </Group>
      </Group>

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
          {/* Filters */}
          <Paper withBorder radius="md" p="md">
            <Group justify="space-between" mb="sm">
              <Title order={5}>סינונים</Title>
              <Button size="xs" variant="light" onClick={addFilter}>+ הוסף סינון</Button>
            </Group>
            {filters.length === 0 && (
              <Text size="sm" c="dimmed">אין סינונים פעילים</Text>
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
                            if (sortBy === col.key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
                            else { setSortBy(col.key); setSortDir('desc') }
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
    </Stack>
  )
}
