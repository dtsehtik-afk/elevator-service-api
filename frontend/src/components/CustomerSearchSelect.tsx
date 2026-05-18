/**
 * CustomerSearchSelect — searchable customer picker with auto-fill contact preview.
 * When a customer is selected, shows their phone / email / contact person below the
 * select and fires onSelect(customer) so the parent can populate its own fields.
 */
import { useEffect, useState } from 'react'
import { Select, Paper, Group, Text, Badge, Stack } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import client from '../api/client'

interface Props {
  value: string | null
  onChange: (id: string | null) => void
  /** Called with the full customer object (or null) whenever selection changes */
  onSelect?: (customer: any | null) => void
  label?: string
  required?: boolean
  placeholder?: string
  disabled?: boolean
  /** Hide the contact-info preview card */
  hidePreview?: boolean
}

const PAYMENT_LABEL: Record<string, string> = {
  CASH: 'מזומן',
  NET_5: 'שוטף +5',
  NET_10: 'שוטף +10',
  NET_15: 'שוטף +15',
  NET_30: 'שוטף +30',
  NET_45: 'שוטף +45',
  NET_60: 'שוטף +60',
  OTHER: 'אחר',
}

export function CustomerSearchSelect({
  value,
  onChange,
  onSelect,
  label = 'לקוח',
  required = false,
  placeholder = 'חפש לקוח...',
  disabled = false,
  hidePreview = false,
}: Props) {
  const [previewId, setPreviewId] = useState<string | null>(value)

  // Full list for the select dropdown
  const { data: customers = [] } = useQuery<any[]>({
    queryKey: ['customers-list'],
    queryFn: () => client.get('/customers?limit=500').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  // Full details for the selected customer (for the preview card)
  const { data: detail } = useQuery<any>({
    queryKey: ['customer-detail', previewId],
    queryFn: () => client.get(`/customers/${previewId}`).then(r => r.data),
    enabled: !!previewId && !hidePreview,
    staleTime: 60 * 1000,
  })

  // Keep previewId in sync with external value changes (e.g. form reset)
  useEffect(() => { setPreviewId(value) }, [value])

  // Fire onSelect whenever detail changes (customer data available)
  useEffect(() => {
    if (detail && detail.id === previewId) onSelect?.(detail)
  }, [detail, previewId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = (id: string | null) => {
    setPreviewId(id)
    onChange(id)
    if (!id) onSelect?.(null)
  }

  const selectData = customers.map((c: any) => ({
    value: c.id,
    label: c.name + (c.phone ? ` · ${c.phone}` : ''),
  }))

  return (
    <Stack gap={6}>
      <Select
        label={label}
        required={required}
        placeholder={placeholder}
        disabled={disabled}
        searchable
        clearable
        data={selectData}
        value={value}
        onChange={handleChange}
        filter={({ options, search }) => {
          const q = search.toLowerCase()
          return (options as any[]).filter(o =>
            o.label.toLowerCase().includes(q)
          )
        }}
      />
      {!hidePreview && detail && detail.id === previewId && (
        <Paper withBorder p="xs" radius="sm" bg="blue.0">
          <Group gap="xs" wrap="wrap">
            {detail.phone && (
              <Text size="xs">📞 <a href={`tel:${detail.phone}`} style={{ color: 'inherit' }}>{detail.phone}</a></Text>
            )}
            {detail.email && (
              <Text size="xs">✉️ <a href={`mailto:${detail.email}`} style={{ color: 'inherit' }}>{detail.email}</a></Text>
            )}
            {detail.contact_person && (
              <Text size="xs">👤 {detail.contact_person}</Text>
            )}
            {detail.payment_terms_type && (
              <Badge size="xs" variant="light" color="teal">
                {PAYMENT_LABEL[detail.payment_terms_type] ?? detail.payment_terms_type}
              </Badge>
            )}
            {detail.parent_name && (
              <Badge size="xs" variant="light" color="grape">אב: {detail.parent_name}</Badge>
            )}
          </Group>
        </Paper>
      )}
    </Stack>
  )
}
