import { useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Stack, Title, Group, TextInput, Select, Badge, Text, Button,
  Paper, Table, Loader, Center, Pagination, Modal, NumberInput, ScrollArea,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { listElevators, createElevator, importElevatorsFromPdf, importElevatorsFromExcel } from '../api/elevators'
import { ELEVATOR_STATUS_LABELS, ELEVATOR_STATUS_COLORS } from '../utils/constants'
import { formatDate } from '../utils/dates'

const PAGE_SIZE = 20

export default function ElevatorsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [opened, { open, close }] = useDisclosure()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const xlsxInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importingXl, setImportingXl] = useState(false)

  const [newElev, setNewElev] = useState({
    address: '', city: '', floor_count: 1,
    model: '', manufacturer: '', serial_number: '', building_name: '',
    status: 'ACTIVE',
  })

  const { data: elevators = [], isLoading } = useQuery({
    queryKey: ['elevators'],
    queryFn: () => listElevators(),
  })

  const filtered = useMemo(() => {
    return elevators.filter(e => {
      const matchSearch = !search ||
        e.address.includes(search) || e.city.includes(search) ||
        (e.serial_number ?? '').includes(search) || (e.building_name ?? '').includes(search)
      const matchStatus = !statusFilter || e.status === statusFilter
      return matchSearch && matchStatus
    })
  }, [elevators, search, statusFilter])

  const paginated = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const createMutation = useMutation({
    mutationFn: createElevator,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['elevators'] })
      notifications.show({ message: 'מעלית נוספה בהצלחה', color: 'green' })
      close()
      setNewElev({ address: '', city: '', floor_count: 1, model: '', manufacturer: '', serial_number: '', building_name: '', status: 'ACTIVE' })
    },
    onError: () => notifications.show({ message: 'שגיאה בהוספת מעלית', color: 'red' }),
  })

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
        color: 'teal',
        autoClose: 8000,
      })
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? 'שגיאה לא ידועה'
      notifications.show({ message: `שגיאה ביבוא: ${detail}`, color: 'red' })
    } finally {
      setImportingXl(false)
    }
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
        color: 'teal',
        autoClose: 8000,
      })
    } catch (err: any) {
      const detail = err?.response?.data?.detail ?? 'שגיאה לא ידועה'
      notifications.show({ message: `שגיאה ביבוא: ${detail}`, color: 'red' })
    } finally {
      setImporting(false)
    }
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>מעליות ({filtered.length})</Title>
        <Group>
          <input
            ref={xlsxInputRef}
            type="file"
            accept=".xlsx,.xls"
            style={{ display: 'none' }}
            onChange={handleExcelImport}
          />
          <Button
            variant="filled"
            color="teal"
            loading={importingXl}
            onClick={() => xlsxInputRef.current?.click()}
          >
            יבוא מ-Excel
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            style={{ display: 'none' }}
            onChange={handlePdfImport}
          />
          <Button
            variant="outline"
            color="teal"
            loading={importing}
            onClick={() => fileInputRef.current?.click()}
          >
            יבוא מ-PDF
          </Button>
          <Button onClick={open}>+ הוסף מעלית</Button>
        </Group>
      </Group>

      <Group>
        <TextInput
          placeholder="חיפוש לפי כתובת, עיר, מספר סידורי..."
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
          clearable
          w={160}
        />
      </Group>

      <Paper withBorder radius="md">
        {isLoading ? (
          <Center h={200}><Loader /></Center>
        ) : (
          <ScrollArea>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>מס׳</Table.Th>
                  <Table.Th>כתובת</Table.Th>
                  <Table.Th>עיר</Table.Th>
                  <Table.Th>סטטוס</Table.Th>
                  <Table.Th>סיכון</Table.Th>
                  <Table.Th>שירות הבא</Table.Th>
                  <Table.Th>שירות אחרון</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {paginated.length === 0 ? (
                  <Table.Tr>
                    <Table.Td colSpan={7}>
                      <Center h={100}><Text c="dimmed">לא נמצאו מעליות</Text></Center>
                    </Table.Td>
                  </Table.Tr>
                ) : paginated.map(e => (
                  <Table.Tr
                    key={e.id}
                    onClick={() => navigate(`/elevators/${e.id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <Table.Td><Text size="sm" fw={500}>{e.serial_number ?? '—'}</Text></Table.Td>
                    <Table.Td>
                      <Stack gap={0}>
                        <Text size="sm">{e.address}</Text>
                        {e.building_name && <Text size="xs" c="dimmed">{e.building_name}</Text>}
                      </Stack>
                    </Table.Td>
                    <Table.Td><Text size="sm">{e.city}</Text></Table.Td>
                    <Table.Td>
                      <Badge color={ELEVATOR_STATUS_COLORS[e.status]} variant="light" size="sm">
                        {ELEVATOR_STATUS_LABELS[e.status]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        color={e.risk_score > 70 ? 'red' : e.risk_score > 40 ? 'orange' : 'green'}
                        variant="light" size="sm"
                      >
                        {e.risk_score.toFixed(0)}
                      </Badge>
                    </Table.Td>
                    <Table.Td><Text size="sm">{formatDate(e.next_service_date)}</Text></Table.Td>
                    <Table.Td><Text size="sm">{formatDate(e.last_service_date)}</Text></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea>
        )}
      </Paper>

      {filtered.length > PAGE_SIZE && (
        <Group justify="center">
          <Pagination total={Math.ceil(filtered.length / PAGE_SIZE)} value={page} onChange={setPage} />
        </Group>
      )}

      <Modal opened={opened} onClose={close} title="הוסף מעלית חדשה" size="lg">
        <Stack gap="sm">
          <TextInput label="כתובת" required value={newElev.address} onChange={e => setNewElev(s => ({ ...s, address: e.target.value }))} />
          <Group grow>
            <TextInput label="עיר" required value={newElev.city} onChange={e => setNewElev(s => ({ ...s, city: e.target.value }))} />
            <TextInput label="שם בניין" value={newElev.building_name} onChange={e => setNewElev(s => ({ ...s, building_name: e.target.value }))} />
          </Group>
          <Group grow>
            <NumberInput label="מספר קומות" required min={1} max={200} value={newElev.floor_count} onChange={v => setNewElev(s => ({ ...s, floor_count: Number(v) }))} />
            <TextInput label="מספר סידורי" value={newElev.serial_number} onChange={e => setNewElev(s => ({ ...s, serial_number: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="יצרן" value={newElev.manufacturer} onChange={e => setNewElev(s => ({ ...s, manufacturer: e.target.value }))} />
            <TextInput label="דגם" value={newElev.model} onChange={e => setNewElev(s => ({ ...s, model: e.target.value }))} />
          </Group>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={close}>ביטול</Button>
            <Button loading={createMutation.isPending} onClick={() => createMutation.mutate(newElev as any)}>
              הוסף
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
