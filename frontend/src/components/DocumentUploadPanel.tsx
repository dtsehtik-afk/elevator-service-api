/**
 * DocumentUploadPanel — upload a PDF/contract/agreement for AI analysis.
 * Embeds anywhere (contract detail, lead, project, elevator detail).
 *
 * Props:
 *   entityType  — "ELEVATOR" | "PROJECT" | "CONTRACT" | "LEAD" | "CUSTOMER"
 *   entityId    — UUID string of the linked record
 */

import { useRef, useState } from 'react'
import {
  Paper, Text, Group, Button, Stack, Badge, Accordion, Loader,
  ActionIcon, Tooltip, Divider,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import client from '../api/client'

interface DocumentAnalysis {
  id: string
  filename: string
  document_type: string | null
  summary_text: string | null
  extracted_data: Record<string, unknown> | null
  auto_filled: Record<string, unknown> | null
  status: string
  error_message: string | null
  created_at: string
}

const DOC_TYPE_LABEL: Record<string, string> = {
  SERVICE_AGREEMENT: '📋 הסכם שירות',
  MAINTENANCE_CONTRACT: '🔧 חוזה תחזוקה',
  INSPECTION_REPORT: '🔍 תסקיר בדיקה',
  QUOTE: '💰 הצעת מחיר',
  SALES_CONTRACT: '🤝 חוזה מכירה',
  OTHER: '📄 מסמך',
}

interface Props {
  entityType: string
  entityId: string
  readOnly?: boolean
}

export function DocumentUploadPanel({ entityType, entityId, readOnly = false }: Props) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const { data: docs = [], isLoading } = useQuery<DocumentAnalysis[]>({
    queryKey: ['doc-analyses', entityType, entityId],
    queryFn: () => client.get(`/documents/${entityType}/${entityId}`).then(r => r.data),
    enabled: !!entityId,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/documents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['doc-analyses', entityType, entityId] }),
  })

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const form = new FormData()
    form.append('file', file)
    form.append('entity_type', entityType)
    form.append('entity_id', entityId)
    try {
      await client.post('/documents/analyze', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      notifications.show({ message: '✅ המסמך נותח ונשמר', color: 'green' })
      qc.invalidateQueries({ queryKey: ['doc-analyses', entityType, entityId] })
    } catch (err: any) {
      notifications.show({
        message: err?.response?.data?.detail || 'שגיאה בניתוח המסמך',
        color: 'red',
      })
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  return (
    <Paper withBorder radius="md" p="md">
      <Group justify="space-between" mb="xs">
        <Text fw={600} size="sm">📎 מסמכים וניתוח AI</Text>
        {!readOnly && (
          <Button
            size="xs"
            variant="light"
            loading={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? 'מנתח...' : '+ העלה מסמך'}
          </Button>
        )}
      </Group>
      <Text size="xs" c="dimmed" mb="sm">
        חוזים, הסכמי שירות, תסקירים — הבינה המלאכותית תחלץ שדות ותמלא אוטומטית.
      </Text>

      <input
        ref={fileRef}
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={handleFile}
      />

      {isLoading && <Loader size="xs" />}

      {docs.length === 0 && !isLoading && (
        <Text size="xs" c="dimmed" ta="center" py="sm">אין מסמכים מנותחים עדיין</Text>
      )}

      <Stack gap="xs">
        {docs.map(doc => (
          <Paper key={doc.id} withBorder radius="sm" p="xs" bg="var(--mantine-color-default-hover)">
            <Group justify="space-between" mb={4}>
              <Group gap="xs">
                <Badge size="xs" variant="light" color="blue">
                  {DOC_TYPE_LABEL[doc.document_type || ''] || '📄 מסמך'}
                </Badge>
                <Text size="xs" c="dimmed">{doc.filename}</Text>
                <Text size="xs" c="dimmed">{new Date(doc.created_at).toLocaleDateString('he-IL')}</Text>
              </Group>
              <Group gap={4}>
                {doc.status === 'ERROR' && (
                  <Tooltip label={doc.error_message || 'שגיאה'}>
                    <Badge size="xs" color="red">שגיאה</Badge>
                  </Tooltip>
                )}
                {!readOnly && (
                  <ActionIcon
                    size="xs" variant="subtle" color="red"
                    onClick={() => { if (confirm('למחוק?')) deleteMut.mutate(doc.id) }}
                  >🗑️</ActionIcon>
                )}
              </Group>
            </Group>

            {doc.summary_text && (
              <Text size="xs" mb={4}>{doc.summary_text}</Text>
            )}

            {doc.auto_filled && Object.keys(doc.auto_filled).length > 0 && (
              <Group gap={4} mb={4}>
                <Text size="xs" c="dimmed">שדות שמולאו אוטומטית:</Text>
                {Object.keys(doc.auto_filled).map(f => (
                  <Badge key={f} size="xs" color="green" variant="dot">{f}</Badge>
                ))}
              </Group>
            )}

            {doc.extracted_data && (
              <Accordion variant="filled" chevronSize={12}>
                <Accordion.Item value="data">
                  <Accordion.Control py={2}>
                    <Text size="xs" c="dimmed">נתונים מחולצים</Text>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap={2}>
                      {Object.entries(doc.extracted_data).map(([key, val]) => {
                        if (!val || key === 'summary') return null
                        const display = typeof val === 'object' ? JSON.stringify(val, null, 2) : String(val)
                        return (
                          <Group key={key} gap="xs" align="flex-start">
                            <Text size="xs" fw={500} w={120}>{key}:</Text>
                            <Text size="xs" style={{ whiteSpace: 'pre-wrap' }}>{display}</Text>
                          </Group>
                        )
                      })}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            )}
          </Paper>
        ))}
      </Stack>
    </Paper>
  )
}
