import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Title, Table, Badge, Button, Group, TextInput, Modal, Stack, Select,
  Switch, Text, ActionIcon, Tooltip, Loader, Alert, NumberInput,
} from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { listTenants, createTenant, deleteTenant, type Tenant } from '../api/tenants'

const PLAN_COLORS: Record<string, string> = { BASIC: 'gray', PRO: 'blue', ENTERPRISE: 'violet' }

function CreateModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({ name: '', slug: '', plan: 'BASIC', contact_email: '', api_url: '', api_key: '', monthly_price: '' as string | number, is_demo: false })
  const mut = useMutation({
    mutationFn: () => createTenant({ ...form, monthly_price: form.monthly_price ? Number(form.monthly_price) : undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenants'] }); onClose() },
  })
  const f = (k: string) => (v: string | boolean | number) => setForm((p) => ({ ...p, [k]: v }))

  return (
    <Modal opened={opened} onClose={onClose} title="צור דייר חדש" size="md">
      <Stack>
        <TextInput label="שם חברה" required value={form.name} onChange={(e) => f('name')(e.target.value)} />
        <TextInput label="Slug (ייחודי)" required value={form.slug} onChange={(e) => f('slug')(e.target.value.toLowerCase())} />
        <Select label="תוכנית" data={['BASIC', 'PRO', 'ENTERPRISE']} value={form.plan} onChange={(v) => f('plan')(v || 'BASIC')} />
        <TextInput label="אימייל איש קשר" value={form.contact_email} onChange={(e) => f('contact_email')(e.target.value)} />
        <TextInput label="API URL (שרת הדייר)" value={form.api_url} onChange={(e) => f('api_url')(e.target.value)} placeholder="https://client.lift-agent.com" />
        <TextInput label="API Key" value={form.api_key} onChange={(e) => f('api_key')(e.target.value)} />
        <NumberInput label="מחיר חודשי (₪)" value={form.monthly_price as number} onChange={(v) => f('monthly_price')(v)} />
        <Switch label="דמו" checked={form.is_demo} onChange={(e) => f('is_demo')(e.target.checked)} />
        {mut.isError && <Alert color="red">שגיאה ביצירה</Alert>}
        <Button loading={mut.isPending} onClick={() => mut.mutate()}>צור</Button>
      </Stack>
    </Modal>
  )
}

export default function TenantsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [search, setSearch] = useState('')

  const { data: tenants, isLoading, error } = useQuery({ queryKey: ['tenants'], queryFn: listTenants })

  const deleteMut = useMutation({
    mutationFn: deleteTenant,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenants'] }),
  })

  const filtered = (tenants ?? []).filter(
    (t) => t.name.toLowerCase().includes(search.toLowerCase()) || t.slug.includes(search.toLowerCase())
  )

  if (isLoading) return <Loader m="xl" />
  if (error) return <Alert color="red" m="xl">שגיאה בטעינת דיירים</Alert>

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>דיירים ({filtered.length})</Title>
        <Group>
          <TextInput placeholder="חיפוש..." value={search} onChange={(e) => setSearch(e.target.value)} w={200} />
          <Button onClick={() => setCreateOpen(true)}>+ דייר חדש</Button>
        </Group>
      </Group>

      <Table striped highlightOnHover>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>שם</Table.Th>
            <Table.Th>Slug</Table.Th>
            <Table.Th>תוכנית</Table.Th>
            <Table.Th>סטטוס</Table.Th>
            <Table.Th>מחיר ₪</Table.Th>
            <Table.Th>עדכון אחרון</Table.Th>
            <Table.Th />
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {filtered.map((t: Tenant) => (
            <Table.Tr key={t.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/tenants/${t.id}`)}>
              <Table.Td fw={500}>{t.name}{t.is_demo && <Badge ml={6} size="xs" color="orange">DEMO</Badge>}</Table.Td>
              <Table.Td><Text size="sm" c="dimmed">{t.slug}</Text></Table.Td>
              <Table.Td><Badge color={PLAN_COLORS[t.plan] ?? 'gray'}>{t.plan}</Badge></Table.Td>
              <Table.Td><Badge color={t.is_active ? 'green' : 'red'}>{t.is_active ? 'פעיל' : 'מושבת'}</Badge></Table.Td>
              <Table.Td>{t.monthly_price ? `₪${t.monthly_price}` : '—'}</Table.Td>
              <Table.Td><Text size="xs" c="dimmed">{t.last_seen_at ? new Date(t.last_seen_at).toLocaleDateString('he-IL') : '—'}</Text></Table.Td>
              <Table.Td onClick={(e) => e.stopPropagation()}>
                <Tooltip label="מחק">
                  <ActionIcon color="red" variant="subtle" onClick={() => { if (confirm(`למחוק את ${t.name}?`)) deleteMut.mutate(t.id) }}>✕</ActionIcon>
                </Tooltip>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      <CreateModal opened={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  )
}
