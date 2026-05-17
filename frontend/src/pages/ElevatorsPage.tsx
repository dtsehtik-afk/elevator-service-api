import { useState, useMemo, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Stack, Title, Group, TextInput, Select, Badge, Text, Button,
  Paper, Table, Loader, Center, Pagination, Modal, NumberInput, ScrollArea,
  Popover, Checkbox, ActionIcon, Tooltip, Accordion, SegmentedControl,
  Divider, Textarea, Grid,
} from '@mantine/core'
import { DateInput } from '@mantine/dates'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { listElevators, createElevator, importElevatorsFromPdf, importElevatorsFromExcel } from '../api/elevators'
import { EditViewDrawer } from '../components/EditViewDrawer'
import { ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS } from '../utils/constants'
import { formatDate } from '../utils/dates'

const PAGE_SIZE = 20

// ── Column definitions ────────────────────────────────────────────────────────

const ALL_COLUMNS = [
  { key: 'serial_number',    label: 'מס׳',          defaultVisible: true  },
  { key: 'address',          label: 'כתובת',         defaultVisible: true  },
  { key: 'city',             label: 'עיר',           defaultVisible: true  },
  { key: 'contact_phone',    label: 'טלפון',         defaultVisible: true  },
  { key: 'status',           label: 'סטטוס',         defaultVisible: true  },
  { key: 'risk_score',       label: 'סיכון',         defaultVisible: true  },
  { key: 'next_service_date',label: 'שירות הבא',     defaultVisible: true  },
  { key: 'last_service_date',label: 'שירות אחרון',   defaultVisible: true  },
  { key: 'building_name',    label: 'בניין',         defaultVisible: false },
  { key: 'manufacturer',     label: 'יצרן',          defaultVisible: false },
  { key: 'model',            label: 'דגם',           defaultVisible: false },
  { key: 'floor_count',      label: 'קומות',         defaultVisible: false },
]

const STORAGE_KEY = 'elevators_visible_cols'

function loadVisibleCols(): Set<string> {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return new Set(JSON.parse(saved))
  } catch {}
  return new Set(ALL_COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
}

function saveVisibleCols(cols: Set<string>) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...cols]))
}

export default function ElevatorsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()
  const [search, setSearch] = useState(searchParams.get('city') ?? '')
  const [statusFilter, setStatusFilter] = useState<string | null>(searchParams.get('status'))
  const [page, setPage] = useState(1)
  const [opened, { open, close }] = useDisclosure()
  const [colsOpened, setColsOpened] = useState(false)
  const [visibleCols, setVisibleCols] = useState<Set<string>>(loadVisibleCols)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const xlsxInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importingXl, setImportingXl] = useState(false)
  const [viewMode, setViewMode] = useState<'list' | 'groups'>('list')
  const [sortBy, setSortBy] = useState<string | undefined>(undefined)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const [newElev, setNewElev] = useState<Record<string, any>>({
    // Basic
    address: '', city: '', building_name: '', floor_count: 1,
    internal_number: '', labor_file_number: '', serial_number: '',
    status: 'ACTIVE',
    // Contact
    contact_phone: '', intercom_phone: '', entry_code: '',
    // Specs
    manufacturer: '', model: '',
    motor_type: '', controller_model: '', door_type: '',
    pit_depth_cm: '', headroom_cm: '',
    // Service
    service_type: '', maintenance_times_per_year: 6,
    // Dates
    contract_start: null, contract_end: null, warranty_end: null,
    safety_certificate_expiry: null, next_inspection_date: null,
    // Notes
    notes: '',
  })

  const { data: elevators = [], isLoading } = useQuery({
    queryKey: ['elevators', sortBy, sortDir],
    queryFn: () => listElevators({ sort_by: sortBy, sort_dir: sortDir }),
  })

  const filtered = useMemo(() => {
    return elevators.filter(e => {
      const matchSearch = !search ||
        e.address.includes(search) || e.city.includes(search) ||
        (e.serial_number ?? '').includes(search) ||
        (e.building_name ?? '').includes(search) ||
        (e.contact_phone ?? '').includes(search)
      const matchStatus = !statusFilter || e.status === statusFilter
      return matchSearch && matchStatus
    })
  }, [elevators, search, statusFilter])

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const groupedByBuilding = useMemo(() => {
    if (viewMode !== 'groups') return { groups: [], ungrouped: [] as typeof elevators }
    const byBuilding: Record<string, typeof elevators> = {}
    const ungrouped: typeof elevators = []
    for (const e of elevators) {
      if (e.building_id) {
        if (!byBuilding[e.building_id]) byBuilding[e.building_id] = []
        byBuilding[e.building_id].push(e)
      } else {
        ungrouped.push(e)
      }
    }
    const groups = Object.entries(byBuilding)
      .filter(([, list]) => list.length >= 1)
      .sort(([, a], [, b]) => b.length - a.length)
    return { groups, ungrouped }
  }, [elevators, viewMode])

  const createMutation = useMutation({
    mutationFn: createElevator,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: 'מעלית נוספה בהצלחה', color: 'green' })
      close()
      setNewElev({ address: '', city: '', building_name: '', floor_count: 1, internal_number: '', labor_file_number: '', serial_number: '', status: 'ACTIVE', contact_phone: '', intercom_phone: '', entry_code: '', manufacturer: '', model: '', motor_type: '', controller_model: '', door_type: '', pit_depth_cm: '', headroom_cm: '', service_type: '', maintenance_times_per_year: 6, contract_start: null, contract_end: null, warranty_end: null, safety_certificate_expiry: null, next_inspection_date: null, notes: '' })
    },
    onError: () => notifications.show({ message: 'שגיאה בהוספת מעלית', color: 'red' }),
  })

  function toggleCol(key: string) {
    setVisibleCols(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      saveVisibleCols(next)
      return next
    })
  }

  async function handleExcelImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setImportingXl(true)
    try {
      const stats = await importElevatorsFromExcel(file)
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({
        message: `יובאו ${stats.total_parsed} מעליות — נוצרו: ${stats.created}, עודכנו: ${stats.updated}, דולגו: ${stats.skipped}`,
        color: 'teal', autoClose: 8000,
      })
    } catch (err: any) {
      notifications.show({ message: `שגיאה ביבוא: ${err?.response?.data?.detail ?? 'שגיאה לא ידועה'}`, color: 'red' })
    } finally { setImportingXl(false) }
  }

  async function handlePdfImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    setImporting(true)
    try {
      const stats = await importElevatorsFromPdf(file)
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({
        message: `יובאו ${stats.total_parsed} מעליות — נוצרו: ${stats.created}, עודכנו: ${stats.updated}, דולגו: ${stats.skipped}`,
        color: 'teal', autoClose: 8000,
      })
    } catch (err: any) {
      notifications.show({ message: `שגיאה ביבוא: ${err?.response?.data?.detail ?? 'שגיאה לא ידועה'}`, color: 'red' })
    } finally { setImporting(false) }
  }

  const visibleDefs = ALL_COLUMNS.filter(c => visibleCols.has(c.key))
  const show = (key: string) => visibleCols.has(key)

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Group gap="md">
          <Title order={2}>מעליות ({filtered.length})</Title>
          <SegmentedControl
            size="xs"
            value={viewMode}
            onChange={v => setViewMode(v as 'list' | 'groups')}
            data={[
              { label: 'רשימה', value: 'list' },
              { label: 'מעליות בקבוצה', value: 'groups' },
            ]}
          />
        </Group>
        <Group>
          <input ref={xlsxInputRef} type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleExcelImport} />
          <EditViewDrawer entityType="elevators" entityLabel="מעליות" />
          <Button variant="filled" color="teal" loading={importingXl} onClick={() => xlsxInputRef.current?.click()}>יבוא מ-Excel</Button>
          <input ref={fileInputRef} type="file" accept=".pdf" style={{ display: 'none' }} onChange={handlePdfImport} />
          <Button variant="outline" color="teal" loading={importing} onClick={() => fileInputRef.current?.click()}>יבוא מ-PDF</Button>
          <Button onClick={open}>+ הוסף מעלית</Button>
        </Group>
      </Group>

      <Group>
        <TextInput
          placeholder="חיפוש לפי כתובת, עיר, טלפון, מספר סידורי..."
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1) }}
          style={{ flex: 1 }}
        />
        <Select
          placeholder="סטטוס"
          data={[
            { value: 'ACTIVE', label: 'פעילה' },
            { value: 'INACTIVE', label: 'לא פעילה' },
            { value: 'UNDER_REPAIR', label: 'בתיקון' },
          ]}
          value={statusFilter}
          onChange={v => { setStatusFilter(v); setPage(1) }}
          clearable w={160}
        />

        {/* Column visibility toggle */}
        <Popover opened={colsOpened} onChange={setColsOpened} position="bottom-end" withArrow>
          <Popover.Target>
            <Tooltip label="בחר עמודות">
              <ActionIcon variant="default" size="lg" onClick={() => setColsOpened(o => !o)}>
                ⚙️
              </ActionIcon>
            </Tooltip>
          </Popover.Target>
          <Popover.Dropdown>
            <Stack gap="xs">
              <Text size="sm" fw={600}>עמודות מוצגות</Text>
              {ALL_COLUMNS.map(col => (
                <Checkbox
                  key={col.key}
                  label={col.label}
                  checked={visibleCols.has(col.key)}
                  onChange={() => toggleCol(col.key)}
                />
              ))}
            </Stack>
          </Popover.Dropdown>
        </Popover>
      </Group>

      {viewMode === 'list' && <Paper withBorder radius="md">
        {isLoading ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <ScrollArea>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  {visibleDefs.map(col => {
                    const sortable = ['address','city','risk_score','next_service_date','last_service_date','status','manufacturer','floor_count'].includes(col.key)
                    return (
                      <Table.Th
                        key={col.key}
                        style={sortable ? { cursor: 'pointer', userSelect: 'none' } : undefined}
                        onClick={sortable ? () => {
                          if (sortBy === col.key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc') }
                          else { setSortBy(col.key); setSortDir('asc') }
                          setPage(1)
                        } : undefined}
                      >
                        {col.label}{sortable && sortBy === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                      </Table.Th>
                    )
                  })}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paginated.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={visibleDefs.length}>
                      <Center h={100}><Text c="dimmed">לא נמצאו מעליות</Text></Center>
                    </Table.Td>
                  </Table.Tr>
                ) : paginated.map(e => (
                  <Table.Tr key={e.id} onClick={() => navigate(`/elevators/${e.id}`)} style={{ cursor: 'pointer' }}>
                    {show('serial_number') && <Table.Td><Text size="sm" fw={500}>{e.serial_number ?? '—'}</Text></Table.Td>}
                    {show('address') && (
                      <Table.Td>
                        <Stack gap={0}>
                          <Text size="sm">{e.address}</Text>
                          {show('building_name') && e.building_name && <Text size="xs" c="dimmed">{e.building_name}</Text>}
                        </Stack>
                      </Table.Td>
                    )}
                    {show('city') && <Table.Td><Text size="sm">{e.city}</Text></Table.Td>}
                    {show('contact_phone') && (
                      <Table.Td>
                        {e.contact_phone
                          ? <Text size="sm" dir="ltr">{e.contact_phone}</Text>
                          : <Text size="sm" c="dimmed">—</Text>}
                      </Table.Td>
                    )}
                    {show('status') && (
                      <Table.Td>
                        <Badge color={ELEVATOR_STATUS_COLORS[e.status]} variant="light" size="sm">
                          {ELEVATOR_STATUS_LABELS[e.status]}
                        </Badge>
                      </Table.Td>
                    )}
                    {show('risk_score') && (
                      <Table.Td>
                        <Badge color={e.risk_score > 70 ? 'red' : e.risk_score > 40 ? 'orange' : 'green'} variant="light" size="sm">
                          {e.risk_score.toFixed(0)}
                        </Badge>
                      </Table.Td>
                    )}
                    {show('next_service_date') && <Table.Td><Text size="sm">{formatDate(e.next_service_date)}</Text></Table.Td>}
                    {show('last_service_date') && <Table.Td><Text size="sm">{formatDate(e.last_service_date)}</Text></Table.Td>}
                    {show('building_name') && !show('address') && <Table.Td><Text size="sm">{e.building_name ?? '—'}</Text></Table.Td>}
                    {show('manufacturer') && <Table.Td><Text size="sm">{e.manufacturer ?? '—'}</Text></Table.Td>}
                    {show('model') && <Table.Td><Text size="sm">{e.model ?? '—'}</Text></Table.Td>}
                    {show('floor_count') && <Table.Td><Text size="sm">{e.floor_count}</Text></Table.Td>}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Paper>}

      {viewMode === 'list' && filtered.length > PAGE_SIZE && (
        <Group justify="center">
          <Pagination total={Math.ceil(filtered.length / PAGE_SIZE)} value={page} onChange={setPage} />
        </Group>
      )}

      {/* ── Groups view ── */}
      {viewMode === 'groups' && (
        <Stack gap="md">
          <Text fw={600} size="sm" c="dimmed">
            {groupedByBuilding.groups.length} קבוצות · {groupedByBuilding.ungrouped.length} מעליות ללא קבוצה
          </Text>
          <Accordion multiple chevronPosition="right">
            {groupedByBuilding.groups.map(([buildingId, list]) => {
              const rep = list[0]
              return (
                <Accordion.Item key={buildingId} value={buildingId}>
                  <Accordion.Control>
                    <Group gap="xs">
                      <Text fw={600}>{rep.address}, {rep.city}</Text>
                      <Badge size="xs" color="blue" variant="light">{list.length} מעליות</Badge>
                      {rep.building_name && <Text size="xs" c="dimmed">· {rep.building_name}</Text>}
                    </Group>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="xs">
                      {list.map(e => (
                        <Paper key={e.id} withBorder p="xs" radius="sm"
                          style={{ cursor: 'pointer' }}
                          onClick={() => navigate(`/elevators/${e.id}`)}
                        >
                          <Group justify="space-between">
                            <Group gap="xs">
                              <Text size="sm" fw={500}>{e.serial_number ? `#${e.serial_number}` : e.id.slice(0, 8)}</Text>
                              {e.building_name && <Text size="sm" c="dimmed">{e.building_name}</Text>}
                            </Group>
                            <Badge color={ELEVATOR_STATUS_COLORS[e.status]} size="xs" variant="light">
                              {ELEVATOR_STATUS_LABELS[e.status]}
                            </Badge>
                          </Group>
                        </Paper>
                      ))}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              )
            })}
          </Accordion>
          {groupedByBuilding.ungrouped.length > 0 && (
            <Paper withBorder p="md" radius="md">
              <Text fw={600} mb="sm">ללא קבוצה ({groupedByBuilding.ungrouped.length})</Text>
              <Stack gap="xs">
                {groupedByBuilding.ungrouped.slice(0, 50).map(e => (
                  <Paper key={e.id} withBorder p="xs" radius="sm"
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/elevators/${e.id}`)}
                  >
                    <Group justify="space-between">
                      <Text size="sm">{e.address}, {e.city}</Text>
                      <Badge color={ELEVATOR_STATUS_COLORS[e.status]} size="xs" variant="light">
                        {ELEVATOR_STATUS_LABELS[e.status]}
                      </Badge>
                    </Group>
                  </Paper>
                ))}
                {groupedByBuilding.ungrouped.length > 50 && (
                  <Text size="xs" c="dimmed" ta="center">+ {groupedByBuilding.ungrouped.length - 50} נוספות</Text>
                )}
              </Stack>
            </Paper>
          )}
        </Stack>
      )}

      {/* ── Add elevator modal ── */}
      <Modal opened={opened} onClose={close} title="הוסף מעלית חדשה" size="xl" dir="rtl">
        <ScrollArea h={580} pr="xs">
          <Stack gap="xs">

            <Divider label="פרטי מיקום" labelPosition="right" />
            <Grid>
              <Grid.Col span={8}>
                <TextInput label="כתובת" required value={newElev.address} onChange={e => setNewElev((s: any) => ({ ...s, address: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="עיר" required value={newElev.city} onChange={e => setNewElev((s: any) => ({ ...s, city: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={6}>
                <TextInput label="שם/תיאור בניין" value={newElev.building_name} onChange={e => setNewElev((s: any) => ({ ...s, building_name: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={3}>
                <TextInput label="קוד כניסה" value={newElev.entry_code} onChange={e => setNewElev((s: any) => ({ ...s, entry_code: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={3}>
                <NumberInput label="קומות" required min={1} max={200} value={newElev.floor_count} onChange={v => setNewElev((s: any) => ({ ...s, floor_count: Number(v) }))} />
              </Grid.Col>
            </Grid>

            <Divider label="מזהים" labelPosition="right" mt="xs" />
            <Grid>
              <Grid.Col span={4}>
                <TextInput label="מס״ד (מזהה פנימי)" value={newElev.internal_number} onChange={e => setNewElev((s: any) => ({ ...s, internal_number: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="מספר תיק עבודה" value={newElev.labor_file_number} onChange={e => setNewElev((s: any) => ({ ...s, labor_file_number: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="מספר סידורי" value={newElev.serial_number} onChange={e => setNewElev((s: any) => ({ ...s, serial_number: e.target.value }))} />
              </Grid.Col>
            </Grid>

            <Divider label="יצרן ומפרט" labelPosition="right" mt="xs" />
            <Grid>
              <Grid.Col span={4}>
                <TextInput label="יצרן" value={newElev.manufacturer} onChange={e => setNewElev((s: any) => ({ ...s, manufacturer: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="דגם" value={newElev.model} onChange={e => setNewElev((s: any) => ({ ...s, model: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="סוג מנוע" value={newElev.motor_type} onChange={e => setNewElev((s: any) => ({ ...s, motor_type: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="דגם בקר" value={newElev.controller_model} onChange={e => setNewElev((s: any) => ({ ...s, controller_model: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={4}>
                <TextInput label="סוג דלת" value={newElev.door_type} onChange={e => setNewElev((s: any) => ({ ...s, door_type: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={2}>
                <NumberInput label="עומק בור (ס״מ)" value={newElev.pit_depth_cm || ''} onChange={v => setNewElev((s: any) => ({ ...s, pit_depth_cm: v || null }))} min={0} />
              </Grid.Col>
              <Grid.Col span={2}>
                <NumberInput label='חדר מכונות (ס"מ)' value={newElev.headroom_cm || ''} onChange={v => setNewElev((s: any) => ({ ...s, headroom_cm: v || null }))} min={0} />
              </Grid.Col>
            </Grid>

            <Divider label="שירות וחוזה" labelPosition="right" mt="xs" />
            <Grid>
              <Grid.Col span={4}>
                <Select
                  label="סוג שירות"
                  data={[
                    { value: 'REGULAR', label: 'רגיל' },
                    { value: 'COMPREHENSIVE', label: 'מקיף' },
                  ]}
                  value={newElev.service_type || null}
                  onChange={v => setNewElev((s: any) => ({ ...s, service_type: v || '' }))}
                  clearable
                />
              </Grid.Col>
              <Grid.Col span={4}>
                <Select
                  label="תדירות תחזוקה"
                  data={['2', '4', '6', '12'].map(v => ({ value: v, label: `${v}× בשנה` }))}
                  value={String(newElev.maintenance_times_per_year)}
                  onChange={v => setNewElev((s: any) => ({ ...s, maintenance_times_per_year: Number(v) || 6 }))}
                />
              </Grid.Col>
              <Grid.Col span={4}>
                <Select
                  label="סטטוס"
                  data={[
                    { value: 'ACTIVE', label: 'פעיל' },
                    { value: 'INACTIVE', label: 'לא פעיל' },
                    { value: 'UNDER_REPAIR', label: 'בתיקון' },
                  ]}
                  value={newElev.status}
                  onChange={v => setNewElev((s: any) => ({ ...s, status: v || 'ACTIVE' }))}
                />
              </Grid.Col>
              <Grid.Col span={3}>
                <DateInput label="תחילת התקשרות" value={newElev.contract_start} onChange={d => setNewElev((s: any) => ({ ...s, contract_start: d }))} clearable locale="he" />
              </Grid.Col>
              <Grid.Col span={3}>
                <DateInput label="סיום התקשרות" value={newElev.contract_end} onChange={d => setNewElev((s: any) => ({ ...s, contract_end: d }))} clearable locale="he" />
              </Grid.Col>
              <Grid.Col span={3}>
                <DateInput label="תום אחריות" value={newElev.warranty_end} onChange={d => setNewElev((s: any) => ({ ...s, warranty_end: d }))} clearable locale="he" />
              </Grid.Col>
              <Grid.Col span={3}>
                <DateInput label="תוקף תעודת בטיחות" value={newElev.safety_certificate_expiry} onChange={d => setNewElev((s: any) => ({ ...s, safety_certificate_expiry: d }))} clearable locale="he" />
              </Grid.Col>
            </Grid>

            <Divider label="טלפונים" labelPosition="right" mt="xs" />
            <Grid>
              <Grid.Col span={6}>
                <TextInput label="טלפון איש קשר" dir="ltr" placeholder="05XXXXXXXX" value={newElev.contact_phone} onChange={e => setNewElev((s: any) => ({ ...s, contact_phone: e.target.value }))} />
              </Grid.Col>
              <Grid.Col span={6}>
                <TextInput label="טלפון חייגן (אינטרקום)" dir="ltr" value={newElev.intercom_phone} onChange={e => setNewElev((s: any) => ({ ...s, intercom_phone: e.target.value }))} />
              </Grid.Col>
            </Grid>

            <Divider label="הערות" labelPosition="right" mt="xs" />
            <Textarea value={newElev.notes} onChange={e => setNewElev((s: any) => ({ ...s, notes: e.target.value }))} rows={2} placeholder="הערות חופשיות..." />

          </Stack>
        </ScrollArea>
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={close}>ביטול</Button>
          <Button
            loading={createMutation.isPending}
            disabled={!newElev.address || !newElev.city}
            onClick={() => {
              const payload: any = { ...newElev }
              // Convert Date objects to ISO strings
              for (const k of ['contract_start', 'contract_end', 'warranty_end', 'safety_certificate_expiry', 'next_inspection_date']) {
                if (payload[k] instanceof Date) payload[k] = payload[k].toISOString().split('T')[0]
              }
              // Remove empty strings → null
              for (const k of Object.keys(payload)) {
                if (payload[k] === '') payload[k] = null
              }
              createMutation.mutate(payload)
            }}
          >
            הוסף מעלית
          </Button>
        </Group>
      </Modal>
    </Stack>
  )
}
