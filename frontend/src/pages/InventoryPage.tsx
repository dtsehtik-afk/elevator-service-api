import { useState, useEffect } from 'react'
import {
  Title, Table, Badge, Button, Group, Select, Modal, Stack, Text,
  Paper, TextInput, NumberInput, Textarea, Alert,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { inventoryApi } from '../api/inventory'
import type { Part } from '../types'

export default function InventoryPage() {
  const [parts, setParts] = useState<Part[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [adjustOpen, setAdjustOpen] = useState<{ id: string; name: string; qty: number } | null>(null)
  const [adjustDelta, setAdjustDelta] = useState(0)
  const [form, setForm] = useState({
    name: '', sku: '', category: '', unit: "יח'", description: '',
    quantity: 0, min_quantity: 1, cost_price: 0, sell_price: 0,
    supplier_name: '', supplier_phone: '', notes: '',
  })

  const load = () => {
    setLoading(true)
    inventoryApi.list({ search: search || undefined, category: categoryFilter || undefined, low_stock: lowStockOnly || undefined })
      .then(setParts).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [search, categoryFilter, lowStockOnly])
  useEffect(() => { inventoryApi.categories().then(setCategories) }, [])

  const handleCreate = async () => {
    try {
      await inventoryApi.create({
        ...form,
        cost_price: form.cost_price || undefined,
        sell_price: form.sell_price || undefined,
      } as any)
      notifications.show({ message: 'חלק נוסף למלאי', color: 'green' })
      setCreateOpen(false)
      load()
    } catch {
      notifications.show({ message: 'שגיאה', color: 'red' })
    }
  }

  const handleAdjust = async () => {
    if (!adjustOpen) return
    try {
      await inventoryApi.adjustStock(adjustOpen.id, adjustDelta)
      notifications.show({ message: 'מלאי עודכן', color: 'green' })
      setAdjustOpen(null)
      load()
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה', color: 'red' })
    }
  }

  const lowStockCount = parts.filter(p => p.is_low_stock).length

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>📦 מלאי חלקי חילוף</Title>
        <Button onClick={() => setCreateOpen(true)}>+ חלק חדש</Button>
      </Group>

      {lowStockCount > 0 && (
        <Alert color="orange" mb="md">⚠️ {lowStockCount} חלקים במלאי נמוך מהמינימום</Alert>
      )}

      <Group mb="md" grow>
        <TextInput placeholder="חיפוש שם / מקט..." value={search} onChange={e => setSearch(e.target.value)} />
        <Select placeholder="קטגוריה" clearable value={categoryFilter} onChange={setCategoryFilter}
          data={categories.map(c => ({ value: c, label: c }))} />
        <Button variant={lowStockOnly ? 'filled' : 'outline'} color="orange"
          onClick={() => setLowStockOnly(v => !v)}>
          מלאי נמוך בלבד
        </Button>
      </Group>

      <Paper withBorder>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>מקט</Table.Th><Table.Th>שם</Table.Th><Table.Th>קטגוריה</Table.Th>
              <Table.Th>כמות</Table.Th><Table.Th>מינימום</Table.Th><Table.Th>מחיר קנייה</Table.Th>
              <Table.Th>מחיר מכירה</Table.Th><Table.Th>ספק</Table.Th><Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {loading ? (
              <Table.Tr><Table.Td colSpan={9}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
            ) : parts.length === 0 ? (
              <Table.Tr><Table.Td colSpan={9}><Text ta="center" py="xl" c="dimmed">אין חלקים במלאי</Text></Table.Td></Table.Tr>
            ) : parts.map(p => (
              <Table.Tr key={p.id}>
                <Table.Td>{p.sku || '—'}</Table.Td>
                <Table.Td fw={500}>{p.name}</Table.Td>
                <Table.Td>{p.category || '—'}</Table.Td>
                <Table.Td>
                  <Badge color={p.is_low_stock ? 'red' : 'green'} size="sm">
                    {p.quantity} {p.unit}
                  </Badge>
                </Table.Td>
                <Table.Td>{p.min_quantity}</Table.Td>
                <Table.Td>{p.cost_price ? `₪${Number(p.cost_price).toLocaleString()}` : '—'}</Table.Td>
                <Table.Td>{p.sell_price ? `₪${Number(p.sell_price).toLocaleString()}` : '—'}</Table.Td>
                <Table.Td>{p.supplier_name || '—'}</Table.Td>
                <Table.Td>
                  <Button size="xs" variant="light"
                    onClick={() => { setAdjustOpen({ id: p.id, name: p.name, qty: p.quantity }); setAdjustDelta(0) }}>
                    עדכן מלאי
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Paper>

      {/* Create modal */}
      <Modal opened={createOpen} onClose={() => setCreateOpen(false)} title="חלק חדש" size="lg" dir="rtl">
        <Stack>
          <Group grow>
            <TextInput label="שם" required value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <TextInput label="מקט (SKU)" value={form.sku} onChange={e => setForm(f => ({ ...f, sku: e.target.value }))} />
          </Group>
          <Group grow>
            <TextInput label="קטגוריה" value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} />
            <TextInput label="יחידה" value={form.unit} onChange={e => setForm(f => ({ ...f, unit: e.target.value }))} />
          </Group>
          <Group grow>
            <NumberInput label="כמות במלאי" value={form.quantity} min={0} onChange={v => setForm(f => ({ ...f, quantity: Number(v) || 0 }))} />
            <NumberInput label="מינימום" value={form.min_quantity} min={1} onChange={v => setForm(f => ({ ...f, min_quantity: Number(v) || 1 }))} />
          </Group>
          <Group grow>
            <NumberInput label="מחיר קנייה (₪)" value={form.cost_price} min={0} onChange={v => setForm(f => ({ ...f, cost_price: Number(v) || 0 }))} />
            <NumberInput label="מחיר מכירה (₪)" value={form.sell_price} min={0} onChange={v => setForm(f => ({ ...f, sell_price: Number(v) || 0 }))} />
          </Group>
          <TextInput label="שם ספק" value={form.supplier_name} onChange={e => setForm(f => ({ ...f, supplier_name: e.target.value }))} />
          <TextInput label="טלפון ספק" value={form.supplier_phone} onChange={e => setForm(f => ({ ...f, supplier_phone: e.target.value }))} />
          <Textarea label="תיאור" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <Button onClick={handleCreate} disabled={!form.name}>הוסף לחמלאי</Button>
        </Stack>
      </Modal>

      {/* Adjust stock modal */}
      <Modal opened={!!adjustOpen} onClose={() => setAdjustOpen(null)} title={`עדכון מלאי — ${adjustOpen?.name}`} dir="rtl">
        <Stack>
          <Text size="sm">מלאי נוכחי: <b>{adjustOpen?.qty}</b></Text>
          <NumberInput
            label="שינוי (+להוסיף / -להפחית)"
            value={adjustDelta}
            onChange={v => setAdjustDelta(Number(v) || 0)}
          />
          <Text size="sm" c="dimmed">מלאי חדש: {(adjustOpen?.qty || 0) + adjustDelta}</Text>
          <Button onClick={handleAdjust} disabled={adjustDelta === 0}>אשר עדכון</Button>
        </Stack>
      </Modal>
    </>
  )
}
