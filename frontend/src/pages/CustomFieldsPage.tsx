import { useState } from 'react'
import {
  Stack, Title, Paper, Tabs, Table, Badge, ActionIcon, Button, Modal,
  TextInput, Select, Checkbox, Group, Text, TagsInput, Switch, NumberInput,
  Loader, Center,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { customFieldsApi, type CustomField } from '../api/customFields'

const ENTITY_TYPES = [
  { value: 'elevators', label: 'מעליות' },
  { value: 'service_calls', label: 'קריאות שירות' },
  { value: 'customers', label: 'לקוחות' },
  { value: 'invoices', label: 'חשבוניות' },
  { value: 'inventory', label: 'מלאי' },
  { value: 'maintenance', label: 'תחזוקה' },
  { value: 'contracts', label: 'חוזים' },
  { value: 'leads', label: 'לידים' },
  { value: 'inspections', label: 'דוחות בודק' },
]

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

const EMPTY_FORM: FieldForm = {
  field_label: '',
  field_type: 'TEXT',
  options: [],
  required: false,
}

export default function CustomFieldsPage() {
  const qc = useQueryClient()
  const [activeTab, setActiveTab] = useState<string>('elevators')
  const [modalOpen, { open: openModal, close: closeModal }] = useDisclosure(false)
  const [editField, setEditField] = useState<CustomField | null>(null)
  const [form, setForm] = useState<FieldForm>(EMPTY_FORM)

  const { data: fields, isLoading } = useQuery({
    queryKey: ['custom-fields', activeTab],
    queryFn: () => customFieldsApi.list(activeTab, true),
  })

  const createMutation = useMutation({
    mutationFn: () => customFieldsApi.create({
      entity_type: activeTab,
      field_label: form.field_label,
      field_type: form.field_type,
      options: form.options.length > 0 ? form.options : undefined,
      required: form.required,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', activeTab] })
      closeModal()
      setForm(EMPTY_FORM)
      notifications.show({ message: 'שדה נוצר בהצלחה', color: 'green' })
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
      qc.invalidateQueries({ queryKey: ['custom-fields', activeTab] })
      closeModal()
      setEditField(null)
      setForm(EMPTY_FORM)
      notifications.show({ message: 'שדה עודכן', color: 'green' })
    },
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      customFieldsApi.update(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['custom-fields', activeTab] }),
  })

  const deleteMutation = useMutation({
    mutationFn: customFieldsApi.delete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields', activeTab] })
      notifications.show({ message: 'שדה נמחק', color: 'orange' })
    },
  })

  function openCreate() {
    setEditField(null)
    setForm(EMPTY_FORM)
    openModal()
  }

  function openEdit(field: CustomField) {
    setEditField(field)
    setForm({
      field_label: field.field_label,
      field_type: field.field_type,
      options: field.options ?? [],
      required: field.required,
    })
    openModal()
  }

  function handleSubmit() {
    if (!form.field_label.trim()) return
    if (editField) {
      updateMutation.mutate(editField.id)
    } else {
      createMutation.mutate()
    }
  }

  const fieldTypeLabel = (type: string) => FIELD_TYPES.find(t => t.value === type)?.label ?? type

  return (
    <Stack gap="md" dir="rtl">
      <Group justify="space-between">
        <Title order={2}>🗂️ שדות מותאמים אישית</Title>
        <Button onClick={openCreate}>+ הוסף שדה</Button>
      </Group>

      <Tabs value={activeTab} onChange={v => setActiveTab(v ?? 'elevators')}>
        <Tabs.List>
          {ENTITY_TYPES.map(et => (
            <Tabs.Tab key={et.value} value={et.value}>{et.label}</Tabs.Tab>
          ))}
        </Tabs.List>

        {ENTITY_TYPES.map(et => (
          <Tabs.Panel key={et.value} value={et.value} pt="md">
            {isLoading && <Center p="xl"><Loader /></Center>}
            {!isLoading && (
              <Paper withBorder radius="md">
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>תווית</Table.Th>
                      <Table.Th>שם מערכת</Table.Th>
                      <Table.Th>סוג</Table.Th>
                      <Table.Th>חובה</Table.Th>
                      <Table.Th>סדר</Table.Th>
                      <Table.Th>פעיל</Table.Th>
                      <Table.Th>פעולות</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(fields ?? []).length === 0 ? (
                      <Table.Tr>
                        <Table.Td colSpan={7}>
                          <Text ta="center" c="dimmed" p="md">אין שדות — לחץ "הוסף שדה"</Text>
                        </Table.Td>
                      </Table.Tr>
                    ) : (fields ?? []).map(field => (
                      <Table.Tr key={field.id} style={{ opacity: field.is_active ? 1 : 0.5 }}>
                        <Table.Td>{field.field_label}</Table.Td>
                        <Table.Td><Text size="xs" c="dimmed">{field.field_name}</Text></Table.Td>
                        <Table.Td><Badge size="sm" variant="light">{fieldTypeLabel(field.field_type)}</Badge></Table.Td>
                        <Table.Td>{field.required ? '✓' : '—'}</Table.Td>
                        <Table.Td>{field.display_order}</Table.Td>
                        <Table.Td>
                          <Switch
                            size="xs"
                            checked={field.is_active}
                            onChange={e => toggleActiveMutation.mutate({ id: field.id, is_active: e.currentTarget.checked })}
                          />
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs">
                            <ActionIcon size="sm" variant="light" onClick={() => openEdit(field)}>✏️</ActionIcon>
                            <ActionIcon size="sm" variant="light" color="red" onClick={() => deleteMutation.mutate(field.id)}>🗑️</ActionIcon>
                          </Group>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Paper>
            )}
          </Tabs.Panel>
        ))}
      </Tabs>

      {/* Create/Edit modal */}
      <Modal
        opened={modalOpen}
        onClose={closeModal}
        title={editField ? 'עריכת שדה' : 'שדה חדש'}
        centered
        dir="rtl"
      >
        <Stack gap="sm">
          <TextInput
            label="תווית (עברית)"
            placeholder="לדוגמה: מספר חוזה"
            required
            value={form.field_label}
            onChange={e => setForm(prev => ({ ...prev, field_label: e.target.value }))}
          />
          <Select
            label="סוג שדה"
            data={FIELD_TYPES}
            value={form.field_type}
            onChange={v => setForm(prev => ({ ...prev, field_type: v || 'TEXT' }))}
          />
          {(form.field_type === 'SELECT' || form.field_type === 'MULTISELECT') && (
            <TagsInput
              label="אפשרויות בחירה"
              placeholder="הקלד ולחץ Enter"
              value={form.options}
              onChange={v => setForm(prev => ({ ...prev, options: v }))}
            />
          )}
          <Checkbox
            label="שדה חובה"
            checked={form.required}
            onChange={e => setForm(prev => ({ ...prev, required: e.currentTarget.checked }))}
          />
          <Button
            onClick={handleSubmit}
            loading={createMutation.isPending || updateMutation.isPending}
            disabled={!form.field_label.trim()}
          >
            {editField ? 'עדכן שדה' : 'צור שדה'}
          </Button>
        </Stack>
      </Modal>
    </Stack>
  )
}
