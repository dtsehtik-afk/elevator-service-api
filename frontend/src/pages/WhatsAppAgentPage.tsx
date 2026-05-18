import { useState } from 'react'
import {
  Stack, Title, Tabs, Textarea, Button, Group, Text, Paper, Badge,
  TextInput, ScrollArea, Timeline, Box, Loader, Center, Divider,
  ActionIcon, Tooltip, ThemeIcon, SimpleGrid, Card, Table, Switch, Modal,
} from '@mantine/core'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

// ── Types ────────────────────────────────────────────────────────────────────

interface AgentConfig {
  system_prompt: string
}

interface ConversationMessage {
  id: string
  direction: 'in' | 'out'
  msg_type: string
  text: string | null
  transcription: string | null
  timestamp: string | null
}

interface Conversation {
  phone: string
  technician_name: string | null
  messages: ConversationMessage[]
}

// ── API ──────────────────────────────────────────────────────────────────────

const agentApi = {
  getConfig: () =>
    client.get<AgentConfig>('/settings/agent-config').then(r => r.data),
  saveConfig: (data: AgentConfig) =>
    client.post('/settings/agent-config', data).then(r => r.data),
  listConversations: () =>
    client.get<Conversation[]>('/conversations').then(r => r.data),
  cleanupUnknown: () =>
    client.delete('/conversations/cleanup-unknown').then(r => r.data),
}

// ── Settings tab ─────────────────────────────────────────────────────────────

function AgentSettingsTab() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['agent-config'],
    queryFn: agentApi.getConfig,
  })
  const [prompt, setPrompt] = useState<string | null>(null)
  const effective = prompt ?? data?.system_prompt ?? ''

  const saveMutation = useMutation({
    mutationFn: () => agentApi.saveConfig({ system_prompt: effective }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agent-config'] })
      setPrompt(null)
      notifications.show({ message: 'הגדרות הסוכן נשמרו', color: 'green' })
    },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  const isDirty = prompt !== null && prompt !== data?.system_prompt

  if (isLoading) return <Center p="xl"><Loader /></Center>

  return (
    <Stack gap="md">
      <Paper withBorder p="md" radius="md">
        <Group justify="space-between" mb="sm">
          <Stack gap={2}>
            <Text fw={600}>הוראות מערכת (System Prompt)</Text>
            <Text size="xs" c="dimmed">
              ההוראות שמנחות את הסוכן בשיחות ווצאפ עם טכנאים ומנהלים
            </Text>
          </Stack>
          {isDirty && <Badge color="orange" size="sm">לא נשמר</Badge>}
        </Group>
        <Textarea
          value={effective}
          onChange={e => setPrompt(e.target.value)}
          rows={16}
          styles={{
            input: { fontFamily: 'monospace', fontSize: 13, direction: 'rtl' },
          }}
          placeholder="הכנס הוראות מערכת לסוכן..."
        />
        <Group mt="sm" justify="flex-end">
          {isDirty && (
            <Button
              variant="subtle"
              color="gray"
              onClick={() => setPrompt(null)}
              disabled={saveMutation.isPending}
            >
              בטל שינויים
            </Button>
          )}
          <Button
            onClick={() => saveMutation.mutate()}
            loading={saveMutation.isPending}
            disabled={!isDirty}
          >
            שמור הגדרות
          </Button>
        </Group>
      </Paper>

      <Paper withBorder p="md" radius="md">
        <Text fw={600} mb="xs">כלים זמינים לסוכן</Text>
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
          {[
            { icon: '🔍', name: 'חיפוש מעליות', desc: 'חיפוש לפי כתובת, עיר, מספר' },
            { icon: '📞', name: 'קריאות שירות', desc: 'צפייה בקריאות פתוחות ובסגורות' },
            { icon: '👷', name: 'טכנאים', desc: 'זמינות ופרטי טכנאים' },
            { icon: '📅', name: 'תחזוקה', desc: 'לוח תחזוקה מתוכנן' },
            { icon: '🔍', name: 'דוחות בודק', desc: 'בדיקות בטיחות ממתינות' },
            { icon: '📊', name: 'סטטיסטיקות', desc: 'נתוני מערכת כלליים' },
          ].map(tool => (
            <Card key={tool.name} withBorder p="sm" radius="sm">
              <Group gap="xs">
                <Text size="lg">{tool.icon}</Text>
                <Stack gap={0}>
                  <Text size="sm" fw={600}>{tool.name}</Text>
                  <Text size="xs" c="dimmed">{tool.desc}</Text>
                </Stack>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      </Paper>
    </Stack>
  )
}

// ── Conversations tab ─────────────────────────────────────────────────────────

function ConversationsTab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Conversation | null>(null)

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: agentApi.listConversations,
  })

  const cleanupMutation = useMutation({
    mutationFn: agentApi.cleanupUnknown,
    onSuccess: (d: { deleted: number }) => {
      qc.invalidateQueries({ queryKey: ['conversations'] })
      notifications.show({ message: `נמחקו ${d.deleted} הודעות מגורמים לא מזוהים`, color: 'blue' })
    },
  })

  const filtered = conversations.filter(c => {
    const q = search.toLowerCase()
    return (
      c.phone.includes(q) ||
      (c.technician_name ?? '').toLowerCase().includes(q)
    )
  })

  if (isLoading) return <Center p="xl"><Loader /></Center>

  return (
    <Group align="flex-start" gap="md" wrap="nowrap" style={{ height: '70vh' }}>
      {/* Left: conversation list */}
      <Paper withBorder radius="md" style={{ width: 280, flexShrink: 0, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Box p="xs">
          <TextInput
            placeholder="חיפוש לפי שם / טלפון..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            size="xs"
            mb="xs"
          />
          <Group justify="space-between">
            <Text size="xs" c="dimmed">{filtered.length} שיחות</Text>
            <Tooltip label="מחק הודעות מגורמים לא מזוהים">
              <Button
                size="xs"
                variant="subtle"
                color="red"
                loading={cleanupMutation.isPending}
                onClick={() => cleanupMutation.mutate()}
              >
                ניקוי
              </Button>
            </Tooltip>
          </Group>
        </Box>
        <Divider />
        <ScrollArea style={{ flex: 1 }}>
          {filtered.map(c => {
            const lastMsg = c.messages[c.messages.length - 1]
            const lastText = lastMsg?.transcription || lastMsg?.text || ''
            const isSelected = selected?.phone === c.phone
            return (
              <Box
                key={c.phone}
                p="xs"
                style={{
                  cursor: 'pointer',
                  background: isSelected ? 'var(--mantine-color-blue-0)' : undefined,
                  borderBottom: '1px solid var(--mantine-color-default-border)',
                }}
                onClick={() => setSelected(c)}
              >
                <Group gap="xs" wrap="nowrap">
                  <ThemeIcon size="sm" radius="xl" color={c.technician_name ? 'blue' : 'gray'} variant="light">
                    <Text size="xs">{c.technician_name ? '👷' : '❓'}</Text>
                  </ThemeIcon>
                  <Stack gap={0} style={{ flex: 1, minWidth: 0 }}>
                    <Text size="sm" fw={600} truncate>
                      {c.technician_name ?? c.phone}
                    </Text>
                    {c.technician_name && (
                      <Text size="xs" c="dimmed" truncate>{c.phone}</Text>
                    )}
                    <Text size="xs" c="dimmed" lineClamp={1}>{lastText}</Text>
                  </Stack>
                  <Badge size="xs" variant="light" color="gray">{c.messages.length}</Badge>
                </Group>
              </Box>
            )
          })}
        </ScrollArea>
      </Paper>

      {/* Right: message thread */}
      <Paper withBorder radius="md" style={{ flex: 1, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {!selected ? (
          <Center style={{ flex: 1 }}>
            <Stack align="center" gap="xs">
              <Text size="2rem">💬</Text>
              <Text c="dimmed">בחר שיחה מהרשימה</Text>
            </Stack>
          </Center>
        ) : (
          <>
            <Box p="md" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
              <Group gap="xs">
                <Text fw={700}>{selected.technician_name ?? selected.phone}</Text>
                {selected.technician_name && <Text size="sm" c="dimmed">{selected.phone}</Text>}
                <Badge size="sm" variant="light">{selected.messages.length} הודעות</Badge>
              </Group>
            </Box>
            <ScrollArea style={{ flex: 1 }} p="md">
              <Stack gap="xs" p="xs">
                {selected.messages.map(msg => {
                  const isIn = msg.direction === 'in'
                  const text = msg.transcription || msg.text || '(ללא תוכן)'
                  const time = msg.timestamp
                    ? new Date(msg.timestamp).toLocaleString('he-IL', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })
                    : ''
                  return (
                    <Group
                      key={msg.id}
                      justify={isIn ? 'flex-end' : 'flex-start'}
                    >
                      <Box
                        p="xs"
                        style={{
                          maxWidth: '75%',
                          borderRadius: 12,
                          background: isIn
                            ? 'var(--mantine-color-blue-1)'
                            : 'var(--mantine-color-gray-1)',
                          direction: 'rtl',
                        }}
                      >
                        <Text size="sm">{text}</Text>
                        <Group gap={4} justify="flex-end" mt={2}>
                          {msg.transcription && (
                            <Badge size="xs" variant="dot" color="teal">🎤 תמלול</Badge>
                          )}
                          <Text size="xs" c="dimmed">{time}</Text>
                        </Group>
                      </Box>
                    </Group>
                  )
                })}
              </Stack>
            </ScrollArea>
          </>
        )}
      </Paper>
    </Group>
  )
}

// ── Stats tab ─────────────────────────────────────────────────────────────────

function StatsTab() {
  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: agentApi.listConversations,
  })

  if (isLoading) return <Center p="xl"><Loader /></Center>

  const totalMessages = conversations.reduce((s, c) => s + c.messages.length, 0)
  const incoming = conversations.reduce((s, c) => s + c.messages.filter(m => m.direction === 'in').length, 0)
  const outgoing = conversations.reduce((s, c) => s + c.messages.filter(m => m.direction === 'out').length, 0)
  const withVoice = conversations.reduce((s, c) => s + c.messages.filter(m => m.transcription).length, 0)
  const identified = conversations.filter(c => c.technician_name).length

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }}>
      {[
        { label: 'סה"כ שיחות', value: conversations.length, icon: '💬', color: 'blue' },
        { label: 'סה"כ הודעות', value: totalMessages, icon: '📨', color: 'teal' },
        { label: 'הודעות נכנסות', value: incoming, icon: '📥', color: 'green' },
        { label: 'תשובות סוכן', value: outgoing, icon: '🤖', color: 'violet' },
        { label: 'הודעות קוליות', value: withVoice, icon: '🎤', color: 'orange' },
        { label: 'גורמים מזוהים', value: identified, icon: '👷', color: 'cyan' },
        { label: 'גורמים לא מזוהים', value: conversations.length - identified, icon: '❓', color: 'gray' },
        { label: 'ממוצע הודעות/שיחה', value: conversations.length ? Math.round(totalMessages / conversations.length) : 0, icon: '📊', color: 'pink' },
      ].map(stat => (
        <Card key={stat.label} withBorder radius="md" p="md">
          <Group gap="xs" mb="xs">
            <Text size="lg">{stat.icon}</Text>
            <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{stat.label}</Text>
          </Group>
          <Text fw={800} size="2rem" c={stat.color}>{stat.value}</Text>
        </Card>
      ))}
    </SimpleGrid>
  )
}

// ── Bot QA Tab ────────────────────────────────────────────────────────────────

interface BotQA {
  id: string
  question: string
  answer: string
  tags: string | null
  use_count: number
  active: boolean
  created_at: string
}

function BotQATab() {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<BotQA | null>(null)
  const [form, setForm] = useState({ question: '', answer: '', tags: '' })

  const { data: pairs = [], isLoading } = useQuery<BotQA[]>({
    queryKey: ['bot-qa'],
    queryFn: () => client.get('/bot-qa?active_only=false').then(r => r.data),
  })

  const createMut = useMutation({
    mutationFn: (body: object) => client.post('/bot-qa', body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bot-qa'] }); setModalOpen(false) },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) => client.put(`/bot-qa/${id}`, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['bot-qa'] }); setModalOpen(false) },
    onError: () => notifications.show({ message: 'שגיאה בשמירה', color: 'red' }),
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => client.delete(`/bot-qa/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bot-qa'] }),
  })

  function openNew() {
    setEditing(null)
    setForm({ question: '', answer: '', tags: '' })
    setModalOpen(true)
  }

  function openEdit(qa: BotQA) {
    setEditing(qa)
    setForm({ question: qa.question, answer: qa.answer, tags: qa.tags ?? '' })
    setModalOpen(true)
  }

  function save() {
    const body = { question: form.question, answer: form.answer, tags: form.tags || null }
    if (editing) updateMut.mutate({ id: editing.id, body })
    else createMut.mutate(body)
  }

  const filtered = pairs.filter(p =>
    !search || p.question.includes(search) || p.answer.includes(search)
  )

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          שאלות ותשובות שהסוכן לומד מהן — מוצגות כהקשר כשהשאלה רלוונטית.
        </Text>
        <Button size="xs" onClick={openNew}>+ הוסף Q&A</Button>
      </Group>
      <TextInput
        placeholder="חיפוש..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        w={260}
      />
      {isLoading ? <Loader /> : (
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>שאלה</Table.Th>
              <Table.Th>תשובה</Table.Th>
              <Table.Th>תגיות</Table.Th>
              <Table.Th>שימושים</Table.Th>
              <Table.Th>פעיל</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {filtered.map(qa => (
              <Table.Tr key={qa.id}>
                <Table.Td style={{ maxWidth: 220 }}>
                  <Text size="sm" lineClamp={2} title={qa.question}>{qa.question}</Text>
                </Table.Td>
                <Table.Td style={{ maxWidth: 260 }}>
                  <Text size="sm" lineClamp={2} c="dimmed" title={qa.answer}>{qa.answer}</Text>
                </Table.Td>
                <Table.Td>
                  {qa.tags ? <Badge size="xs" variant="light">{qa.tags}</Badge> : null}
                </Table.Td>
                <Table.Td><Text size="sm">{qa.use_count}</Text></Table.Td>
                <Table.Td>
                  <Switch
                    size="xs"
                    checked={qa.active}
                    onChange={e => updateMut.mutate({ id: qa.id, body: { active: e.currentTarget.checked } })}
                  />
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    <ActionIcon size="sm" variant="subtle" onClick={() => openEdit(qa)}>✏️</ActionIcon>
                    <ActionIcon
                      size="sm" variant="subtle" color="red"
                      onClick={() => { if (confirm('למחוק?')) deleteMut.mutate(qa.id) }}
                    >🗑️</ActionIcon>
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      <Modal
        opened={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? 'עריכת Q&A' : 'Q&A חדש'}
        dir="rtl"
        size="lg"
      >
        <Stack gap="sm">
          <Textarea
            label="שאלה"
            placeholder="מה הטכנאי כתב / שאל?"
            value={form.question}
            onChange={e => setForm(f => ({ ...f, question: e.target.value }))}
            autosize
            minRows={2}
          />
          <Textarea
            label="תשובה"
            placeholder="מה הסוכן צריך להגיד / לעשות?"
            value={form.answer}
            onChange={e => setForm(f => ({ ...f, answer: e.target.value }))}
            autosize
            minRows={2}
          />
          <TextInput
            label="תגיות (אופציונלי)"
            placeholder="intent,assign,info"
            value={form.tags}
            onChange={e => setForm(f => ({ ...f, tags: e.target.value }))}
          />
          <Group justify="flex-end" mt="sm">
            <Button variant="subtle" onClick={() => setModalOpen(false)}>ביטול</Button>
            <Button
              loading={createMut.isPending || updateMut.isPending}
              disabled={!form.question || !form.answer}
              onClick={save}
            >שמור</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function WhatsAppAgentPage() {
  return (
    <Stack gap="md" dir="rtl">
      <Group gap="xs">
        <Text size="2rem">💬</Text>
        <Title order={2}>סוכן ווצאפ</Title>
      </Group>

      <Tabs defaultValue="conversations">
        <Tabs.List>
          <Tabs.Tab value="conversations" leftSection={<span>💬</span>}>
            היסטוריית שיחות
          </Tabs.Tab>
          <Tabs.Tab value="settings" leftSection={<span>⚙️</span>}>
            הגדרות סוכן
          </Tabs.Tab>
          <Tabs.Tab value="stats" leftSection={<span>📊</span>}>
            סטטיסטיקות
          </Tabs.Tab>
          <Tabs.Tab value="qa" leftSection={<span>🧠</span>}>
            בסיס ידע QA
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="conversations" pt="md">
          <ConversationsTab />
        </Tabs.Panel>
        <Tabs.Panel value="settings" pt="md">
          <AgentSettingsTab />
        </Tabs.Panel>
        <Tabs.Panel value="stats" pt="md">
          <StatsTab />
        </Tabs.Panel>
        <Tabs.Panel value="qa" pt="md">
          <BotQATab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
