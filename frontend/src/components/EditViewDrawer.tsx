import { useState } from 'react'
import {
  Drawer, Stack, Title, Tabs, Table, Badge, ActionIcon, Button, Modal,
  TextInput, Select, Checkbox, Group, Text, TagsInput, Switch,
  Loader, Center, Divider,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { customFieldsApi, type CustomField } from '../api/customFields'
import { reportsApi, type ColumnMeta } from '../api/reports'
import client from '../api/client'

const FIELD_TYPES = [
  { value: 'TEXT', label: 'טקסט' },
  { value: 'NUMBER', label: 'מספר' },
  { value: 'DATE', label: 'תאריך' },
  { value: 'BOOLEAN', label: 'כן/לא' },
  { value: 'SELECT', label: 'בחירה יחידה' },
  { value: 'MULTISELECT', label: 'בחירה מרובה' },
  { value: 'PHONE', label: 'טלפון' },
  { value: 'EMAIL', label: 'אימייל' },
  { value: 'URL', label: 'קישור' },
]

interface FieldForm {
  field_label: string
  field_type: string
  options: string[]
  required: boolean
}

const EMPTY: FieldForm = { field_label: '', field_type: 'TEXT', options: [], required: false }

interface Props {
  entityType: string
  entityLabel: string
}

export function EditViewDrawer({ entityType, entityLabel }: Props) {
  const qc = useQueryClient()
  const [drawerOpen, { open: openDrawer, close: closeDrawer }] = useDisclosure(false)
  const [modalOpen, { open: openModal, close: closeModal }] = useDisclosure(false)
  const [editField, setEditField] = useState<CustomField | null>(null)
  const [form, setForm] = useState<FieldForm>(EMPTY)
  // label overrides for built-in fields: fieldKey → customLabel (initialised from server on first load)
  const [labelEdits, setLabelEdits] = useState<Record<string, string> | null>(null)
  const [labelsDirty, setLabelsDirty] = useState(false)

  // Built-in columns from report schema
  const { data: schemaData } = useQuery({
    queryKey: ['report-schema', entityType],
    queryFn: () => reportsApi.getEntitySchema(entityType),
    enabled: drawerOpen,
  })

  // Current label overrides
  const { data: savedLabels } = useQuery<Record<string, string>>({
    queryKey: ['field-labels', entityType],
    queryFn: () => client.get(`/settings/field-labels/${entityType}`).then(r => r.data),
    enabled: drawerOpen,
  })

  // Custom fields
  const { data: customFields, isLoading: cfLoading } = useQuery({
    queryKey: ['custom-fields', entityType],
    queryFn: () => customFieldsApi.list(entityType, true),
    enabled: drawerOpen,
  })

  const saveLabels = useMutation({
    mutationFn: (labels: Record<string, string>) =>
      client.put(`/settings/field-labels/${entityType}`, labels),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['report-schema', entityType] })
      qc.invalidateQueries({ queryKey: ['report-schemas'] })
      qc.invalidateQueries({ queryKey: ['field-labels', entityType] })
      setLabelsDirty(false)
      notifications.show({ message: 'תוויות נשמרו', color: 'green' })
    },
  })

  const createMutation = useMutation({
    mutationFn: () => customFieldsApi.create({
      entity_type: entityType,
      field_label: form.field_label,
      field_type: form.field_type,
      options: form.options.length > 0 ? form.options : undefined,
      required: form.required,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', entityType] })
      closeModal(); setForm(EMPTY)
      notifications.show({ message: 'שדה נוסף', color: 'green' })
    },
    onError: (e: any) => notifications.show({ message: e.response?.data?.detail || 'שגיאה', color: 'red' }),
  })

  const updateMutation = useMutation({
    mutationFn: (id: string) => customFieldsApi.update(id, {
      field_label: form.field_label,
      field_type: form.field_type,
      options: form.options.length > 0 ? form.options : undefined,
      required: form.required,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', entityType] })
      closeModal(); setEditField(null); setForm(EMPTY)
      notifications.show({ message: 'שדה עודכן', color: 'green' })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      customFieldsApi.update(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields', entityType] }),
  })

  const deleteMutation = useMutation({
    mutationFn: customFieldsApi.delete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', entityType] })
      notifications.show({ message: 'שדה נמחק', color: 'orange' })
    },
  })

  function openCreate() { setEditField(null); setForm(EMPTY); openModal() }

  function openEdit(f: CustomField) {
    setEditField(f)
    setForm({ field_label: f.field_label, field_type: f.field_type, options: f.options ?? [], required: f.required })
    openModal()
  }

  function handleSubmit() {
    if (!form.field_label.trim()) return
    editField ? updateMutation.mutate(editField.id) : createMutation.mutate()
  }

  // Merge saved labels into local state once loaded
  const effectiveLabelEdits: Record<string, string> = labelEdits ?? savedLabels ?? {}

  function setLabelOverride(key: string, val: string) {
    setLabelEdits(prev => ({ ...(prev ?? savedLabels ?? {}), [key]: val }))
    setLabelsDirty(true)
  }

  const builtinCols: ColumnMeta[] = schemaData?.columns ?? []

  return (
    <>
      <Button size="sm" variant="light" onClick={openDrawer}>
        ✏️ עריכת תצוגה
      </Button>

      <Drawer
        opened={drawerOpen}
        onClose={closeDrawer}
        title={`עריכת תצוגה — ${entityLabel}`}
        position="right"
        size="lg"
        dir="rtl"
      >
        <Tabs defaultValue="builtin">
          <Tabs.List mb="md">
            <Tabs.Tab value="builtin">שדות מובנים</Tabs.Tab>
            <Tabs.Tab value="custom">שדות מותאמים</Tabs.Tab>
          </Tabs.List>

          {/* Built-in fields — rename labels */}
          <Tabs.Panel value="builtin">
            <Stack gap="xs">
              <Text size="xs" c="dimmed">ערוך את השמות המוצגים. השינויים יסתנכרנו עם הדוחות.</Text>
              {builtinCols.map(col => (
                <Group key={col.key} gap="sm">
                  <Text size="sm" c="dimmed" style={{ width: 120, flexShrink: 0 }}>{col.key}</Text>
                  <TextInput
                    size="xs"
                    style={{ flex: 1 }}
                    value={effectiveLabelEdits[col.key] ?? col.label_he}
                    onChange={e => setLabelOverride(col.key, e.target.value)}
                    placeholder={col.label_he}
                  />
                </Group>
              ))}
              {labelsDirty && (
                <Button
                  mt="sm"
                  onClick={() => saveLabels.mutate(effectiveLabelEdits)}
                  loading={saveLabels.isPending}
                >
                  שמור תוויות
                </Button>
              )}
            </Stack>
          </Tabs.Panel>

          {/* Custom fields */}
          <Tabs.Panel value="custom">
            <Stack gap="md">
              <Group justify="space-between">
                <Text size="sm" c="dimmed">שדות מותאמים אישית</Text>
                <Button size="xs" onClick={openCreate}>+ הוסף שדה</Button>
              </Group>

              {cfLoading && <Center><Loader size="sm" /></Center>}
              {!cfLoading && (customFields ?? []).length === 0 && (
                <Text size="sm" c="dimmed" ta="center">אין שדות — לחץ "הוסף שדה"</Text>
              )}

              {(customFields ?? []).map(f => (
                <Group key={f.id} justify="space-between" style={{ borderBottom: '1px solid #eee', paddingBottom: 8 }}>
                  <Stack gap={2}>
                    <Text size="sm" fw={500}>{f.field_label}</Text>
                    <Group gap={4}>
                      <Badge size="xs" variant="light">
                        {FIELD_TYPES.find(t => t.value === f.field_type)?.label ?? f.field_type}
                      </Badge>
                      {f.required && <Badge size="xs" color="red" variant="light">חובה</Badge>}
                    </Group>
                  </Stack>
                  <Group gap={4}>
                    <Switch
                      size="xs"
                      checked={f.is_active}
                      onChange={e => toggleMutation.mutate({ id: f.id, is_active: e.currentTarget.checked })}
                    />
                    <ActionIcon size="sm" variant="light" onClick={() => openEdit(f)}>✏️</ActionIcon>
                    <ActionIcon size="sm" variant="light" color="red" onClick={() => deleteMutation.mutate(f.id)}>🗑️</ActionIcon>
                  </Group>
                </Group>
              ))}
            </Stack>
          </Tabs.Panel>
        </Tabs>
      </Drawer>

      <Modal opened={modalOpen} onClose={closeModal} title={editField ? 'עריכת שדה' : 'שדה חדש'} centered dir="rtl">
        <Stack gap="sm">
          <TextInput
            label="תווית (עברית)"
            placeholder="לדוגמה: מספר חוזה"
            required
            value={form.field_label}
            onChange={e => setForm(p => ({ ...p, field_label: e.target.value }))}
          />
          <Select
            label="סוג שדה"
            data={FIELD_TYPES}
            value={form.field_type}
            onChange={v => setForm(p => ({ ...p, field_type: v || 'TEXT' }))}
          />
          {(form.field_type === 'SELECT' || form.field_type === 'MULTISELECT') && (
            <TagsInput
              label="אפשרויות בחירה"
              placeholder="הקלד ולחץ Enter"
              value={form.options}
              onChange={v => setForm(p => ({ ...p, options: v }))}
            />
          )}
          <Checkbox
            label="שדה חובה"
            checked={form.required}
            onChange={e => setForm(p => ({ ...p, required: e.currentTarget.checked }))}
          />
          <Button
            onClick={handleSubmit}
            loading={createMutation.isPending || updateMutation.isPending}
            disabled={!form.field_label.trim()}
          >
            {editField ? 'עדכן' : 'צור שדה'}
          </Button>
        </Stack>
      </Modal>
    </>
  )
}
