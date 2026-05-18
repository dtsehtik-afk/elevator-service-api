import { useRef, useState, useEffect } from 'react'
import {
  Title, Table, Badge, Button, Group, Select, Modal, Stack, Text,
  Paper, TextInput, NumberInput, Textarea, Alert, Tooltip, Tabs,
  ActionIcon, Menu, Divider, Image,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { inventoryApi, type Warehouse, type StockItem } from '../api/inventory'
import type { Part } from '../types'
import client from '../api/client'
import { useAuthStore } from '../stores/authStore'

const WH_TYPE_LABEL: Record<string, string> = {
  MAIN: '🏭 מחסן ראשי',
  VEHICLE: '🚐 רכב טכנאי',
  LAB: '🔬 מעבדה',
  EXTERNAL: '🏗️ חיצוני',
}

const WH_TYPE_COLOR: Record<string, string> = {
  MAIN: 'blue',
  VEHICLE: 'orange',
  LAB: 'violet',
  EXTERNAL: 'gray',
}

export default function InventoryPage() {
  const userRole = useAuthStore(s => s.userRole)
  const canUploadImage = userRole === 'ADMIN' || userRole === 'DISPATCHER'
  const imageInputRef = useRef<HTMLInputElement>(null)
  const [imageUploadPartId, setImageUploadPartId] = useState<string | null>(null)

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !imageUploadPartId) return
    const form = new FormData()
    form.append('file', file)
    try {
      await client.post(`/inventory/${imageUploadPartId}/upload-image`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      notifications.show({ message: 'תמונה הועלתה בהצלחה', color: 'green' })
      loadParts()
    } catch {
      notifications.show({ message: 'שגיאה בהעלאת תמונה', color: 'red' })
    } finally {
      e.target.value = ''
      setImageUploadPartId(null)
    }
  }

  const [parts, setParts] = useState<Part[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [barcodeInput, setBarcodeInput] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null)
  const [lowStockOnly, setLowStockOnly] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [adjustOpen, setAdjustOpen] = useState<{ id: string; name: string; qty: number } | null>(null)
  const [adjustDelta, setAdjustDelta] = useState(0)
  const [activeTab, setActiveTab] = useState<string>('all')

  // Warehouse state
  const [warehouses, setWarehouses] = useState<Warehouse[]>([])
  const [whStock, setWhStock] = useState<StockItem[]>([])
  const [whStockLoading, setWhStockLoading] = useState(false)
  const [whSearch, setWhSearch] = useState('')
  const [whLowOnly, setWhLowOnly] = useState(false)
  const [newWhOpen, setNewWhOpen] = useState(false)
  const [newWh, setNewWh] = useState({ name: '', warehouse_type: 'MAIN', address: '' })
  const [transferOpen, setTransferOpen] = useState(false)
  const [transfer, setTransfer] = useState({ part_id: '', source_warehouse_id: '', target_warehouse_id: '', quantity: 1, notes: '' })
  const [receiveOpen, setReceiveOpen] = useState(false)
  const [receive, setReceive] = useState({ part_id: '', warehouse_id: '', quantity: 1, unit_price: 0, reference_number: '', notes: '' })
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: string; name: string } | null>(null)

  const [form, setForm] = useState({
    name: '', sku: '', category: '', unit: "יח'", description: '',
    quantity: 0, min_quantity: 1, cost_price: 0, sell_price: 0,
    supplier_name: '', supplier_phone: '', notes: '',
  })

  const handleDelete = async (id: string) => {
    try {
      await inventoryApi.delete(id)
      notifications.show({ message: 'החלק נמחק', color: 'green' })
      setDeleteConfirm(null)
      loadParts()
    } catch {
      notifications.show({ message: 'שגיאה במחיקה', color: 'red' })
    }
  }

  const loadParts = () => {
    setLoading(true)
    inventoryApi.list({ search: search || undefined, category: categoryFilter || undefined, low_stock: lowStockOnly || undefined })
      .then(setParts).finally(() => setLoading(false))
  }

  const loadWarehouses = () =>
    inventoryApi.listWarehouses().then(setWarehouses).catch(() => {})

  const loadWhStock = (warehouseId: string) => {
    setWhStockLoading(true)
    inventoryApi.getWarehouseStock(warehouseId, { search: whSearch || undefined, low_stock_only: whLowOnly || undefined })
      .then(setWhStock).catch(() => setWhStock([])).finally(() => setWhStockLoading(false))
  }

  useEffect(() => { loadParts() }, [search, categoryFilter, lowStockOnly])
  useEffect(() => { inventoryApi.categories().then(setCategories) }, [])
  useEffect(() => { loadWarehouses() }, [])
  useEffect(() => {
    if (activeTab !== 'all' && activeTab !== 'manage') loadWhStock(activeTab)
  }, [activeTab, whSearch, whLowOnly])

  const handleCreate = async () => {
    try {
      await inventoryApi.create({
        ...form,
        cost_price: form.cost_price || undefined,
        sell_price: form.sell_price || undefined,
      } as any)
      notifications.show({ message: 'חלק נוסף למלאי', color: 'green' })
      setCreateOpen(false)
      loadParts()
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
      loadParts()
      if (activeTab !== 'all' && activeTab !== 'manage') loadWhStock(activeTab)
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה', color: 'red' })
    }
  }

  const handleCreateWarehouse = async () => {
    try {
      await inventoryApi.createWarehouse(newWh)
      notifications.show({ message: 'מחסן נוצר', color: 'green' })
      setNewWhOpen(false)
      setNewWh({ name: '', warehouse_type: 'MAIN', address: '' })
      loadWarehouses()
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה', color: 'red' })
    }
  }

  const handleTransfer = async () => {
    try {
      await inventoryApi.transferStock(transfer)
      notifications.show({ message: 'העברה בוצעה', color: 'green' })
      setTransferOpen(false)
      if (activeTab !== 'all' && activeTab !== 'manage') loadWhStock(activeTab)
      loadParts()
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה', color: 'red' })
    }
  }

  const handleReceive = async () => {
    try {
      await inventoryApi.receiveStock({ ...receive, unit_price: receive.unit_price || undefined })
      notifications.show({ message: 'קבלה נרשמה', color: 'green' })
      setReceiveOpen(false)
      if (activeTab !== 'all' && activeTab !== 'manage') loadWhStock(activeTab)
      loadParts()
    } catch (e: any) {
      notifications.show({ message: e?.response?.data?.detail || 'שגיאה', color: 'red' })
    }
  }

  const lowStockCount = parts.filter(p => p.is_low_stock).length

  return (
    <>
      <Group justify="space-between" mb="md">
        <Title order={2}>📦 מלאי חלקי חילוף</Title>
        <Group gap="xs">
          <Button variant="light" onClick={() => setReceiveOpen(true)}>📥 קבלת סחורה</Button>
          <Button variant="light" color="orange" onClick={() => setTransferOpen(true)}>🔄 העברה בין מחסנים</Button>
          <Button onClick={() => setCreateOpen(true)}>+ חלק חדש</Button>
        </Group>
      </Group>

      {lowStockCount > 0 && (
        <Alert color="orange" mb="md">⚠️ {lowStockCount} חלקים במלאי נמוך מהמינימום</Alert>
      )}

      <Tabs value={activeTab} onChange={v => setActiveTab(v || 'all')} mb="md">
        <Tabs.List>
          <Tabs.Tab value="all">📋 כל המלאי</Tabs.Tab>
          {warehouses.map(w => (
            <Tabs.Tab key={w.id} value={w.id}>
              {WH_TYPE_LABEL[w.warehouse_type] || w.name} — {w.name}
            </Tabs.Tab>
          ))}
          <Tabs.Tab value="manage">⚙️ ניהול מחסנים</Tabs.Tab>
        </Tabs.List>
      </Tabs>

      {/* All parts tab */}
      {activeTab === 'all' && (
        <>
          <Group mb="xs">
            <Tooltip label="חבר סורק ברקוד USB — מקד כאן וסרוק חלק לחיפוש מיידי" position="right">
              <TextInput
                placeholder="📷 סורק ברקוד — לחץ כאן וסרוק"
                style={{ width: 280 }}
                value={barcodeInput}
                onChange={e => setBarcodeInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && barcodeInput.trim()) {
                    setSearch(barcodeInput.trim())
                    setBarcodeInput('')
                  }
                }}
              />
            </Tooltip>
          </Group>
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
                  <Table.Th>תמונה</Table.Th>
                  <Table.Th>מקט</Table.Th><Table.Th>שם</Table.Th><Table.Th>קטגוריה</Table.Th>
                  <Table.Th>כמות</Table.Th><Table.Th>מינימום</Table.Th><Table.Th>מחיר קנייה</Table.Th>
                  <Table.Th>מחיר מכירה</Table.Th><Table.Th>ספק</Table.Th><Table.Th></Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {loading ? (
                  <Table.Tr><Table.Td colSpan={10}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
                ) : parts.length === 0 ? (
                  <Table.Tr><Table.Td colSpan={10}><Text ta="center" py="xl" c="dimmed">אין חלקים במלאי</Text></Table.Td></Table.Tr>
                ) : parts.map(p => (
                  <Table.Tr key={p.id}>
                    <Table.Td style={{ width: 56 }}>
                      {p.image_url ? (
                        <Tooltip label={p.name} position="right">
                          <Image
                            src={p.image_url}
                            w={44} h={44}
                            radius="sm"
                            fit="cover"
                            style={{ cursor: canUploadImage ? 'pointer' : 'default' }}
                            onClick={canUploadImage ? () => { setImageUploadPartId(p.id); imageInputRef.current?.click() } : undefined}
                          />
                        </Tooltip>
                      ) : canUploadImage ? (
                        <ActionIcon
                          variant="light" size="lg"
                          title="העלה תמונה"
                          onClick={() => { setImageUploadPartId(p.id); imageInputRef.current?.click() }}
                        >📷</ActionIcon>
                      ) : <Text size="xs" c="dimmed">—</Text>}
                    </Table.Td>
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
                      <Group gap={4} wrap="nowrap">
                        <Button size="xs" variant="light"
                          onClick={() => { setAdjustOpen({ id: p.id, name: p.name, qty: p.quantity }); setAdjustDelta(0) }}>
                          עדכן מלאי
                        </Button>
                        <ActionIcon size="sm" color="red" variant="subtle"
                          onClick={() => setDeleteConfirm({ id: p.id, name: p.name })}
                          title="מחק חלק">
                          🗑️
                        </ActionIcon>
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </>
      )}

      {/* Per-warehouse stock tab */}
      {activeTab !== 'all' && activeTab !== 'manage' && (() => {
        const wh = warehouses.find(w => w.id === activeTab)
        return (
          <>
            <Group mb="md" justify="space-between">
              <Group gap="xs">
                <Badge color={WH_TYPE_COLOR[wh?.warehouse_type || 'MAIN']} size="lg">
                  {WH_TYPE_LABEL[wh?.warehouse_type || 'MAIN']}
                </Badge>
                {wh?.address && <Text size="sm" c="dimmed">{wh.address}</Text>}
                {wh?.technician_name && <Text size="sm" c="dimmed">טכנאי: {wh.technician_name}</Text>}
              </Group>
              <Group gap="xs">
                <TextInput
                  placeholder="חיפוש..."
                  value={whSearch}
                  onChange={e => setWhSearch(e.target.value)}
                  w={200}
                />
                <Button variant={whLowOnly ? 'filled' : 'outline'} color="orange" size="xs"
                  onClick={() => setWhLowOnly(v => !v)}>מלאי נמוך</Button>
              </Group>
            </Group>
            <Paper withBorder>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>מקט</Table.Th>
                    <Table.Th>שם חלק</Table.Th>
                    <Table.Th>קטגוריה</Table.Th>
                    <Table.Th>כמות במחסן</Table.Th>
                    <Table.Th>מינימום</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {whStockLoading ? (
                    <Table.Tr><Table.Td colSpan={5}><Text ta="center" py="xl" c="dimmed">טוען...</Text></Table.Td></Table.Tr>
                  ) : whStock.length === 0 ? (
                    <Table.Tr><Table.Td colSpan={5}><Text ta="center" py="xl" c="dimmed">אין פריטים במחסן זה</Text></Table.Td></Table.Tr>
                  ) : whStock.map(s => (
                    <Table.Tr key={s.part_id}>
                      <Table.Td>{s.part_sku || '—'}</Table.Td>
                      <Table.Td fw={500}>{s.part_name}</Table.Td>
                      <Table.Td>{s.category || '—'}</Table.Td>
                      <Table.Td>
                        <Badge color={s.is_low_stock ? 'red' : 'green'} size="sm">
                          {s.quantity} {s.unit}
                        </Badge>
                      </Table.Td>
                      <Table.Td>{s.min_quantity}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Paper>
          </>
        )
      })()}

      {/* Manage warehouses tab */}
      {activeTab === 'manage' && (
        <>
          <Group justify="flex-end" mb="md">
            <Button onClick={() => setNewWhOpen(true)}>+ מחסן חדש</Button>
          </Group>
          <Paper withBorder>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>שם</Table.Th>
                  <Table.Th>סוג</Table.Th>
                  <Table.Th>כתובת</Table.Th>
                  <Table.Th>טכנאי</Table.Th>
                  <Table.Th>סטטוס</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {warehouses.map(w => (
                  <Table.Tr key={w.id}>
                    <Table.Td fw={500}>{w.name}</Table.Td>
                    <Table.Td>
                      <Badge color={WH_TYPE_COLOR[w.warehouse_type]} variant="light">
                        {WH_TYPE_LABEL[w.warehouse_type] || w.warehouse_type}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{w.address || '—'}</Table.Td>
                    <Table.Td>{w.technician_name || '—'}</Table.Td>
                    <Table.Td>
                      <Badge color={w.is_active ? 'green' : 'gray'} size="xs">
                        {w.is_active ? 'פעיל' : 'לא פעיל'}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        </>
      )}

      {/* Create part modal */}
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
          <Button onClick={handleCreate} disabled={!form.name}>הוסף למלאי</Button>
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

      {/* New warehouse modal */}
      <Modal opened={newWhOpen} onClose={() => setNewWhOpen(false)} title="מחסן חדש" dir="rtl">
        <Stack>
          <TextInput label="שם המחסן" required value={newWh.name} onChange={e => setNewWh(w => ({ ...w, name: e.target.value }))} />
          <Select
            label="סוג"
            value={newWh.warehouse_type}
            onChange={v => setNewWh(w => ({ ...w, warehouse_type: v || 'MAIN' }))}
            data={[
              { value: 'MAIN', label: '🏭 מחסן ראשי' },
              { value: 'VEHICLE', label: '🚐 רכב טכנאי' },
              { value: 'LAB', label: '🔬 מעבדה / תיקון' },
              { value: 'EXTERNAL', label: '🏗️ חיצוני' },
            ]}
          />
          <TextInput label="כתובת (אופציונלי)" value={newWh.address} onChange={e => setNewWh(w => ({ ...w, address: e.target.value }))} />
          <Button onClick={handleCreateWarehouse} disabled={!newWh.name}>צור מחסן</Button>
        </Stack>
      </Modal>

      {/* Transfer modal */}
      <Modal opened={transferOpen} onClose={() => setTransferOpen(false)} title="העברה בין מחסנים" size="lg" dir="rtl">
        <Stack>
          <Select
            label="חלק"
            required
            searchable
            value={transfer.part_id}
            onChange={v => setTransfer(t => ({ ...t, part_id: v || '' }))}
            data={parts.map(p => ({ value: p.id, label: `${p.name}${p.sku ? ` (${p.sku})` : ''}` }))}
          />
          <Group grow>
            <Select
              label="ממחסן"
              required
              value={transfer.source_warehouse_id}
              onChange={v => setTransfer(t => ({ ...t, source_warehouse_id: v || '' }))}
              data={warehouses.map(w => ({ value: w.id, label: w.name }))}
            />
            <Select
              label="למחסן"
              required
              value={transfer.target_warehouse_id}
              onChange={v => setTransfer(t => ({ ...t, target_warehouse_id: v || '' }))}
              data={warehouses.map(w => ({ value: w.id, label: w.name }))}
            />
          </Group>
          <NumberInput label="כמות" required value={transfer.quantity} min={1}
            onChange={v => setTransfer(t => ({ ...t, quantity: Number(v) || 1 }))} />
          <Textarea label="הערות" value={transfer.notes} onChange={e => setTransfer(t => ({ ...t, notes: e.target.value }))} />
          <Button
            onClick={handleTransfer}
            disabled={!transfer.part_id || !transfer.source_warehouse_id || !transfer.target_warehouse_id}
          >בצע העברה</Button>
        </Stack>
      </Modal>

      {/* Receive stock modal */}
      <Modal opened={receiveOpen} onClose={() => setReceiveOpen(false)} title="קבלת סחורה" size="lg" dir="rtl">
        <Stack>
          <Select
            label="חלק"
            required
            searchable
            value={receive.part_id}
            onChange={v => setReceive(r => ({ ...r, part_id: v || '' }))}
            data={parts.map(p => ({ value: p.id, label: `${p.name}${p.sku ? ` (${p.sku})` : ''}` }))}
          />
          <Select
            label="מחסן יעד"
            required
            value={receive.warehouse_id}
            onChange={v => setReceive(r => ({ ...r, warehouse_id: v || '' }))}
            data={warehouses.map(w => ({ value: w.id, label: w.name }))}
          />
          <Group grow>
            <NumberInput label="כמות" required value={receive.quantity} min={1}
              onChange={v => setReceive(r => ({ ...r, quantity: Number(v) || 1 }))} />
            <NumberInput label="מחיר ליחידה (₪)" value={receive.unit_price} min={0}
              onChange={v => setReceive(r => ({ ...r, unit_price: Number(v) || 0 }))} />
          </Group>
          <TextInput label="מספר הזמנה / תעודת משלוח" value={receive.reference_number}
            onChange={e => setReceive(r => ({ ...r, reference_number: e.target.value }))} />
          <Textarea label="הערות" value={receive.notes} onChange={e => setReceive(r => ({ ...r, notes: e.target.value }))} />
          <Button
            onClick={handleReceive}
            disabled={!receive.part_id || !receive.warehouse_id}
          >אשר קבלה</Button>
        </Stack>
      </Modal>

      <Modal opened={!!deleteConfirm} onClose={() => setDeleteConfirm(null)} title="מחיקת חלק" size="sm" dir="rtl">
        <Stack>
          <Text size="sm">האם למחוק את <strong>{deleteConfirm?.name}</strong>? פעולה זו בלתי הפיכה.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setDeleteConfirm(null)}>ביטול</Button>
            <Button color="red" onClick={() => deleteConfirm && handleDelete(deleteConfirm.id)}>מחק</Button>
          </Group>
        </Stack>
      </Modal>

      {/* Hidden image file input — triggered by image upload buttons */}
      <input
        ref={imageInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp,image/gif"
        style={{ display: 'none' }}
        onChange={handleImageUpload}
      />
    </>
  )
}
