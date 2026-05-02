import { useState, useEffect } from 'react'
import {
  Title, Group, Button, Text, Badge, Card, Stack, SimpleGrid,
  Modal, TextInput, Select, NumberInput, Textarea, Paper, Table,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { leadsApi } from '../api/leads'
import type { Lead } from '../types'
import { EditViewDrawer } from '../components/EditViewDrawer'

const STATUS_COLORS: Record<string, string> = {
  NEW: 'blue', CONTACTED: 'cyan', QUALIFIED: 'violet', PROPOSAL: 'orange', WON: 'green', LOST: 'gray',
}
const STATUS_LABELS: Record<string, string> = {
  NEW: 'חדש', CONTACTED: 'נוצר קשר', QUALIFIED: 'מוסמך', PROPOSAL: 'הצעה', WON: 'נסגר', LOST: 'אבד',
}
const SOURCE_LABELS: Record<string, string> = {
  WEBSITE: 'אתר', PHONE: 'טלפון', REFERRAL: 'הפנייה', EMAIL: 'מייל', SOCIAL: 'רשתות', OTHER: 'אחר',
}

type KanbanBoard = Record<string, { id: string; name: string; company: string | null; phone: string | null; estimated_value: number | null; owner: string | null; stage: string | null }[]>

export default function LeadsPage() {
  const [view, setView] = useState<'kanban' | 'table'>('kanban')
  const [board, setBoard] = useState<KanbanBoard>({})
  const [leads, setLeads] = useState<Lead[]>([])
  const [loading, setLoading] = useState(true)
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null)
  const [form, setForm] = useState({
    name: '', company: '', phone: '', email: '',
    source: 'OTHER', status: 'NEW', estimated_value: 0, owner: '', notes: '',
  })

  const load = async () => {
    setLoading(true)
    const [b, l] = await Promise.all([leadsApi.kanban(), leadsApi.list()])
    setBoard(b)
    setLeads(l)
    setLoading(false)
  }
  useEffect(() => { load() }, [])

  const handleCreate = async () => {
    try {
      await leadsApi.create({
        ...form,
        estimated_value: form.estimated_value || undefined,
      } as any)
      notifications.show({ message: 'ליד נוצר', color: 'green' })
      setCreateOpen(false)
      load()
    } catch {
      notifications.show({ message: 'שגיאה', color: 'red' })
    }
  }

  const handleStatusChange = async (id: string, status: Lead['status']) => {
    try {
      await leadsApi.update(id, { status })
      notifications.show({ message: 'סטטוס עודכן', color: 'green' })
      load()
    } catch {
      notifications.show({ message: 'שגיאה', color: 'red' })
    }
  }

  const handleConvert = async (id: string) => {
    try {
      const res = await leadsApi.convert(id)
      notifications.show({ message: `לקוח ${res.customer_name} נוצר`, color: 'green' })
      load()
    } catch {
      notifications.show({ message: 'שגיאה בהמרה', color: 'red' })
    }
  }

  const statuses = ['NEW', 'CONTACTED', 'QUALIFIED', 'PROPOSAL', 'WON', 'LOST']

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>🎯 לידים — CRM</Title>
        <Group>
          <EditViewDrawer entityType="leads" entityLabel="לידים" />
          <Button variant={view === 'kanban' ? 'filled' : 'outline'} onClick={() => setView('kanban')} size="sm">לוח</Button>
          <Button variant={view === 'table' ? 'filled' : 'outline'} onClick={() => setView('table')} size="sm">טבלה</Button>
          <Button onClick={() => setCreateOpen(true)}>+ ליד חדש</Button>
        </Group>
      </Group>

      {view === 'kanban' && (
        <SimpleGrid cols={{ base: 2, md: 3, lg: 6 }} spacing="sm">
          {statuses.map(s => (
            <Stack key={s} gap="xs">
              <Group gap={4}>
                <Badge color={STATUS_COLORS[s]} size="sm">{STATUS_LABELS[s]}</Badge>
                <Text size="xs" c="dimmed">({(board[s] || []).length})</Text>
              </Group>
              {(board[s] || []).map(lead => (
                <Card key={lead.id} withBorder shadow="xs" p="xs" style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedLead(leads.find(l => l.id === lead.id) || null)}>
                  <Text size="sm" fw={600} lineClamp={1}>{lead.name}</Text>
                  {lead.company && <Text size="xs" c="dimmed">{lead.company}</Text>}
                  {lead.estimated_value && (
                    <Text size="xs" c="green" fw={500}>₪{Number(lead.estimated_value).toLocaleString()}</Text>
                  )}
                  {lead.owner && <Text size="xs" c="dimmed">👤 {lead.owner}</Text>}
                </Card>
              ))}
            </Stack>
          ))}
        </SimpleGrid>
      )}

      {view === 'table' && (
        <Paper withBorder>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>שם</Table.Th><Table.Th>חברה</Table.Th><Table.Th>טלפון</Table.Th>
                <Table.Th>מקור</Table.Th><Table.Th>סטטוס</Table.Th><Table.Th>ערך משוער</Table.Th><Table.Th>אחראי</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {leads.map(l => (
                <Table.Tr key={l.id} style={{ cursor: 'pointer' }} onClick={() => setSelectedLead(l)}>
                  <Table.Td fw={500}>{l.name}</Table.Td>
                  <Table.Td>{l.company || '—'}</Table.Td>
                  <Table.Td>{l.phone || '—'}</Table.Td>
                  <Table.Td>{SOURCE_LABELS[l.source] || l.source}</Table.Td>
                  <Table.Td><Badge color={STATUS_COLORS[l.status]} size="sm">{STATUS_LABELS[l.status] || l.status}</Badge></Table.Td>
                  <Table.Td>{l.estimated_value ? `₪${Number(l.estimated_value).toLocaleString()}` : '—'}</Table.Td>
                  <Table.Td>{l.owner || '—'}</Table.Td>
                </Table.Tr>
              ))}
              {leads.length === 0 && <Table.Tr><Table.Td colSpan={7}><Text ta="center" py="xl" c="dimmed">אין לידים</Text></Table.Td></Table.Tr>}
            </Table.Tbody>
          </Table>
        </Paper>
      )}

      {/* Create modal */}
      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="ליד חדש" size="lg" dir="rtl">
        <Stack>
          <Group grow>
            <TextInput label="שם" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <TextInput label="חברה" value={form.company} onChange={e => setForm(f => ({ ...f, company: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="טלפון" value={form.phone} onChange={e => setForm(f => ({ ...f, phone: e.target.value }))} />
            <TextInput label="אימייל" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
          </Group>
          <Group grow>
            <Select label="מקור" value={form.source} onChange={v => setForm(f => ({ ...f, source: v || 'OTHER' }))}
              data={Object.entries(SOURCE_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
            <Select label="סטטוס" value={form.status} onChange={v => setForm(f => ({ ...f, status: v || 'NEW' }))}
              data={Object.entries(STATUS_LABELS).map(([v, l]) => ({ value: v, label: l }))} />
          </Group>
          <Group grow>
            <NumberInput label="ערך משוער (₪)" value={form.estimated_value} min={0}
              onChange={v => setForm(f => ({ ...f, estimated_value: Number(v) || 0 }))} />
            <TextInput label="אחראי" value={form.owner} onChange={e => setForm(f => ({ ...f, owner: e.target.value }))} />
          </Group>
          <Textarea label="הערות" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          <Button onClick={handleCreate} disabled={!form.name}>צור ליד</Button>
        </Stack>
      </Modal>

      {/* Lead detail drawer */}
      {selectedLead && (
        <Modal opened={!!selectedLead} onClose={() => setSelectedLead(null)} title={selectedLead.name} dir="rtl">
          <Stack>
            <Group>
              <Badge color={STATUS_COLORS[selectedLead.status]}>{STATUS_LABELS[selectedLead.status]}</Badge>
              <Text size="sm" c="dimmed">{SOURCE_LABELS[selectedLead.source]}</Text>
            </Group>
            {selectedLead.company && <Text size="sm"><b>חברה:</b> {selectedLead.company}</Text>}
            {selectedLead.phone && <Text size="sm"><b>טלפון:</b> {selectedLead.phone}</Text>}
            {selectedLead.email && <Text size="sm"><b>מייל:</b> {selectedLead.email}</Text>}
            {selectedLead.estimated_value && <Text size="sm"><b>ערך:</b> ₪{Number(selectedLead.estimated_value).toLocaleString()}</Text>}
            {selectedLead.owner && <Text size="sm"><b>אחראי:</b> {selectedLead.owner}</Text>}
            {selectedLead.notes && <Text size="sm" c="dimmed">{selectedLead.notes}</Text>}

            <Text size="sm" fw={600}>עדכון סטטוס:</Text>
            <SimpleGrid cols={3}>
              {Object.entries(STATUS_LABELS).map(([s, l]) => (
                <Button key={s} size="xs"
                  variant={selectedLead.status === s ? 'filled' : 'outline'}
                  color={STATUS_COLORS[s]}
                  onClick={() => handleStatusChange(selectedLead.id, s as Lead['status'])}>
                  {l}
                </Button>
              ))}
            </SimpleGrid>

            {selectedLead.status !== 'WON' && !selectedLead.customer_id && (
              <Button color="green" onClick={() => { handleConvert(selectedLead.id); setSelectedLead(null) }}>
                🎉 המר ללקוח
              </Button>
            )}
            {selectedLead.customer_id && (
              <Text size="sm" c="green">✓ הומר ללקוח</Text>
            )}
          </Stack>
        </Modal>
      )}
    </>
  )
}
