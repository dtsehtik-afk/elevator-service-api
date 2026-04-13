import { useState } from 'react'
import {
  Stack, Title, Group, Badge, Text, Button, Paper, Grid, Card,
  Modal, TextInput, Select, NumberInput, PasswordInput, Switch, Divider,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { listTechnicians, createTechnician, updateTechnician, setOnCallTechnician } from '../api/technicians'
import { Technician } from '../types'
import { useAuthStore } from '../stores/authStore'

const ROLE_LABELS: Record<string, string> = { ADMIN: 'מנהל', TECHNICIAN: 'טכנאי', DISPATCHER: 'מוקד' }
const ROLE_COLORS: Record<string, string> = { ADMIN: 'purple', TECHNICIAN: 'blue', DISPATCHER: 'teal' }

const EMPTY_NEW = {
  name: '', email: '', phone: '', whatsapp_number: '', password: '',
  role: 'TECHNICIAN', max_daily_calls: 8,
}

export default function TechniciansPage() {
  const qc = useQueryClient()
  const userRole = useAuthStore((s) => s.userRole)
  const [addOpened, { open: openAdd, close: closeAdd }] = useDisclosure()
  const [editOpened, { open: openEdit, close: closeEdit }] = useDisclosure()
  const [selected, setSelected] = useState<Technician | null>(null)

  const [newForm, setNewForm] = useState(EMPTY_NEW)
  const [editForm, setEditForm] = useState<{
    name: string; phone: string; whatsapp_number: string; role: string;
    max_daily_calls: number; is_active: boolean;
    base_latitude: number | null; base_longitude: number | null;
  }>({
    name: '', phone: '', whatsapp_number: '', role: 'TECHNICIAN',
    max_daily_calls: 8, is_active: true,
    base_latitude: null, base_longitude: null,
  })

  const { data: technicians = [] } = useQuery({
    queryKey: ['technicians'],
    queryFn: listTechnicians,
  })

  const createMutation = useMutation({
    mutationFn: createTechnician,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['technicians'] })
      notifications.show({ message: 'טכנאי נוסף בהצלחה', color: 'green' })
      closeAdd()
      setNewForm(EMPTY_NEW)
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      let msg = 'שגיאה בהוספת טכנאי'
      if (Array.isArray(detail)) {
        if (detail.find((d: any) => d.loc?.includes('password'))) msg = 'הסיסמה חייבת להכיל לפחות 8 תווים'
        else msg = detail[0]?.msg ?? msg
      } else if (typeof detail === 'string') {
        msg = detail.includes('already') ? 'כתובת מייל זו כבר רשומה במערכת' : detail
      }
      notifications.show({ message: msg, color: 'red' })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: any }) => updateTechnician(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['technicians'] })
      notifications.show({ message: 'פרטי הטכנאי עודכנו', color: 'green' })
      closeEdit()
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      let msg = 'שגיאה בעדכון פרטי הטכנאי'
      if (Array.isArray(detail)) {
        const fieldMessages: Record<string, string> = {
          name:             'השם חייב להכיל לפחות 2 תווים',
          max_daily_calls:  'מספר הקריאות חייב להיות בין 1 ל-20',
          phone:            'מספר טלפון לא תקין',
          whatsapp_number:  'מספר WhatsApp לא תקין',
          role:             'תפקיד לא חוקי',
        }
        const first = detail[0]
        const field = first?.loc?.[first.loc.length - 1]
        msg = (field && fieldMessages[field]) ?? first?.msg ?? msg
      }
      notifications.show({ message: msg, color: 'red', autoClose: 6000 })
    },
  })

  const toggleAvailMutation = useMutation({
    mutationFn: ({ id, is_available }: { id: string; is_available: boolean }) =>
      updateTechnician(id, { is_available }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['technicians'] }),
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateTechnician(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['technicians'] }),
  })

  const onCallMutation = useMutation({
    mutationFn: ({ id, isOnCall }: { id: string; isOnCall: boolean }) =>
      setOnCallTechnician(id, isOnCall),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['technicians'] })
      notifications.show({ message: 'תורן עודכן בהצלחה', color: 'teal' })
    },
    onError: () => {
      notifications.show({ message: 'שגיאה בעדכון תורן', color: 'red' })
    },
  })

  const openEditModal = (tech: Technician) => {
    setSelected(tech)
    setEditForm({
      name: tech.name,
      phone: tech.phone ?? '',
      whatsapp_number: tech.whatsapp_number ?? '',
      role: tech.role,
      max_daily_calls: tech.max_daily_calls,
      is_active: tech.is_active,
      base_latitude: tech.base_latitude,
      base_longitude: tech.base_longitude,
    })
    openEdit()
  }

  const active = technicians.filter(t => t.is_active)
  const available = active.filter(t => t.is_available)

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={2}>
          טכנאים — <Text span c="green">{available.length} זמינים</Text> / {active.length} פעילים
        </Title>
        <Button onClick={openAdd}>+ הוסף טכנאי</Button>
      </Group>

      <Grid>
        {technicians.map(tech => (
          <Grid.Col key={tech.id} span={{ base: 12, sm: 6, md: 4 }}>
            <Card withBorder radius="md" p="md">
              <Group justify="space-between" mb="xs">
                <Group gap="xs">
                  <Text fw={700}>{tech.is_available ? '🟢' : '🔴'}</Text>
                  <Text fw={600}>{tech.name}</Text>
                </Group>
                <Group gap="xs">
                  {tech.is_on_call && <Badge color="teal" size="sm">🌙 תורן</Badge>}
                  <Badge color={ROLE_COLORS[tech.role]} size="sm">{ROLE_LABELS[tech.role]}</Badge>
                </Group>
              </Group>

              <Stack gap={4}>
                {tech.phone && <Text size="sm" c="dimmed">📞 {tech.phone}</Text>}
                {tech.whatsapp_number && <Text size="sm" c="dimmed">💬 {tech.whatsapp_number}</Text>}
                <Text size="sm" c="dimmed">✉️ {tech.email}</Text>
                <Text size="sm" c="dimmed">📋 עד {tech.max_daily_calls} קריאות/יום</Text>
                {tech.current_latitude ? (
                  <Text size="sm" c="teal">📍 מיקום חי פעיל</Text>
                ) : tech.base_latitude ? (
                  <Text size="sm" c="dimmed">📍 מיקום בסיס מוגדר</Text>
                ) : (
                  <Text size="sm" c="red">📍 אין מיקום</Text>
                )}
              </Stack>

              <Divider my="sm" />

              <Group justify="space-between">
                <Group gap="sm">
                  <Switch
                    label="זמין"
                    checked={tech.is_available}
                    onChange={e => toggleAvailMutation.mutate({ id: tech.id, is_available: e.target.checked })}
                    disabled={!tech.is_active}
                  />
                  <Switch
                    label="פעיל"
                    checked={tech.is_active}
                    color="blue"
                    onChange={e => toggleActiveMutation.mutate({ id: tech.id, is_active: e.target.checked })}
                  />
                </Group>
                <Group gap="xs">
                  {userRole === 'ADMIN' && !tech.is_on_call && (
                    <Button
                      size="xs"
                      variant="light"
                      color="teal"
                      loading={onCallMutation.isPending && onCallMutation.variables?.id === tech.id}
                      onClick={() => onCallMutation.mutate({ id: tech.id, isOnCall: true })}
                    >
                      🌙 הגדר כתורן
                    </Button>
                  )}
                  <Button size="xs" variant="light" onClick={() => openEditModal(tech)}>
                    ✏️ עריכה
                  </Button>
                </Group>
              </Group>

              {!tech.is_active && <Badge color="gray" size="sm" mt="xs">לא פעיל</Badge>}
            </Card>
          </Grid.Col>
        ))}
      </Grid>

      {/* ── Add technician modal ── */}
      <Modal opened={addOpened} onClose={closeAdd} title="הוסף טכנאי חדש" size="md">
        <Stack gap="sm">
          <TextInput label="שם מלא" required
            value={newForm.name} onChange={e => setNewForm(s => ({ ...s, name: e.target.value }))} />
          <TextInput label="אימייל" required dir="ltr"
            value={newForm.email} onChange={e => setNewForm(s => ({ ...s, email: e.target.value }))} />
          <Group grow>
            <TextInput label="טלפון" dir="ltr"
              value={newForm.phone} onChange={e => setNewForm(s => ({ ...s, phone: e.target.value }))} />
            <TextInput label="WhatsApp" dir="ltr" placeholder="05XXXXXXXX"
              value={newForm.whatsapp_number}
              onChange={e => setNewForm(s => ({ ...s, whatsapp_number: e.target.value }))} />
          </Group>
          <PasswordInput label="סיסמה" required dir="ltr"
            value={newForm.password}
            onChange={e => setNewForm(s => ({ ...s, password: e.target.value }))}
            error={newForm.password.length > 0 && newForm.password.length < 8 ? 'לפחות 8 תווים' : null} />
          <Group grow>
            <Select label="תפקיד"
              data={[
                { value: 'TECHNICIAN', label: 'טכנאי' },
                { value: 'DISPATCHER', label: 'מוקד' },
                { value: 'ADMIN', label: 'מנהל' },
              ]}
              value={newForm.role}
              onChange={v => setNewForm(s => ({ ...s, role: v ?? 'TECHNICIAN' }))} />
            <NumberInput label="קריאות/יום" min={1} max={20}
              value={newForm.max_daily_calls}
              onChange={v => setNewForm(s => ({ ...s, max_daily_calls: Number(v) }))} />
          </Group>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeAdd}>ביטול</Button>
            <Button
              loading={createMutation.isPending}
              disabled={!newForm.name || !newForm.email || newForm.password.length < 8}
              onClick={() => createMutation.mutate({
                ...newForm,
                specializations: [],
                area_codes: [],
              })}>
              הוסף
            </Button>
          </Group>
        </Stack>
      </Modal>

      {/* ── Edit technician modal ── */}
      <Modal opened={editOpened} onClose={closeEdit}
        title={selected ? `עריכת ${selected.name}` : 'עריכת טכנאי'} size="md">
        <Stack gap="sm">
          <TextInput label="שם מלא" required
            value={editForm.name} onChange={e => setEditForm(s => ({ ...s, name: e.target.value }))} />
          <Group grow>
            <TextInput label="טלפון" dir="ltr"
              value={editForm.phone} onChange={e => setEditForm(s => ({ ...s, phone: e.target.value }))} />
            <TextInput label="WhatsApp" dir="ltr" placeholder="05XXXXXXXX"
              value={editForm.whatsapp_number}
              onChange={e => setEditForm(s => ({ ...s, whatsapp_number: e.target.value }))} />
          </Group>
          <Group grow>
            <Select label="תפקיד"
              data={[
                { value: 'TECHNICIAN', label: 'טכנאי' },
                { value: 'DISPATCHER', label: 'מוקד' },
                { value: 'ADMIN', label: 'מנהל' },
              ]}
              value={editForm.role}
              onChange={v => setEditForm(s => ({ ...s, role: v ?? 'TECHNICIAN' }))} />
            <NumberInput label="קריאות/יום" min={1} max={20}
              value={editForm.max_daily_calls}
              onChange={v => setEditForm(s => ({ ...s, max_daily_calls: Math.max(1, Number(v) || 1) }))} />
          </Group>
          <Switch label="טכנאי פעיל"
            checked={editForm.is_active}
            onChange={e => setEditForm(s => ({ ...s, is_active: e.target.checked }))} />
          <Divider label="📍 מיקום בסיס (ברירת מחדל כשאין מיקום חי)" labelPosition="center" />
          <Group grow>
            <NumberInput
              label="קו רוחב (Latitude)"
              placeholder="32.6038"
              decimalScale={6}
              dir="ltr"
              value={editForm.base_latitude ?? ''}
              onChange={v => setEditForm(s => ({ ...s, base_latitude: v === '' ? null : Number(v) }))}
            />
            <NumberInput
              label="קו אורך (Longitude)"
              placeholder="35.2897"
              decimalScale={6}
              dir="ltr"
              value={editForm.base_longitude ?? ''}
              onChange={v => setEditForm(s => ({ ...s, base_longitude: v === '' ? null : Number(v) }))}
            />
          </Group>
          <Text size="xs" c="dimmed">
            💡 מצא קואורדינטות ב-Google Maps: לחץ ימני על המיקום ← העתק קואורדינטות
          </Text>
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeEdit}>ביטול</Button>
            <Button
              loading={updateMutation.isPending}
              disabled={!editForm.name || editForm.name.length < 2}
              onClick={() => {
                if (!selected) return
                const payload = {
                  ...editForm,
                  max_daily_calls: Math.max(1, Math.min(20, editForm.max_daily_calls || 8)),
                }
                updateMutation.mutate({ id: selected.id, payload })
              }}>
              שמור שינויים
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
