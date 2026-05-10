import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Box, Title, Text, Badge, Button, Group, Stack, Paper, Grid, Switch,
  TextInput, Select, Table, ScrollArea, ActionIcon, Tooltip, Divider,
  Alert, Code, Collapse, Loader, Center, ThemeIcon, NumberFormatter,
  CopyButton, Modal,
} from '@mantine/core'
import { useAuthStore } from '../stores/authStore'
import { adminConsoleApi, AdminLog, HealthResponse } from '../api/adminConsole'

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: 'gray',
  INFO: 'blue',
  WARNING: 'yellow',
  ERROR: 'red',
  CRITICAL: 'dark',
}

const MODULE_LABELS: Record<string, string> = {
  whatsapp: 'WhatsApp',
  email_calls: 'דוא"ל — קריאות שירות',
  google_drive: 'Google Drive',
  after_hours: 'אחרי שעות עבודה',
  ai_assignment: 'שיבוץ AI',
  inspection_emails: 'מיילי בדיקות',
  sms_alerts: 'התראות SMS',
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}ש׳`
  if (seconds < 3600) return `${Math.round(seconds / 60)}ד׳`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}ש׳ ${m}ד׳`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('he-IL', { dateStyle: 'short', timeStyle: 'medium' })
}

function StackTraceModal({ log, opened, onClose }: { log: AdminLog | null; opened: boolean; onClose: () => void }) {
  if (!log) return null
  return (
    <Modal opened={opened} onClose={onClose} title={`לוג ${log.level} — ${log.source ?? ''}`} size="xl" dir="ltr">
      <Stack gap="sm">
        <Text size="sm" fw={600}>{log.message}</Text>
        <Text size="xs" c="dimmed">{formatDate(log.created_at)}</Text>
        {log.stack_trace && (
          <Box>
            <Group justify="space-between" mb={4}>
              <Text size="xs" fw={600} c="dimmed">Stack Trace</Text>
              <CopyButton value={log.stack_trace}>
                {({ copied, copy }) => (
                  <Button size="xs" variant="subtle" onClick={copy}>{copied ? 'הועתק' : 'העתק'}</Button>
                )}
              </CopyButton>
            </Group>
            <ScrollArea h={400}>
              <Code block style={{ fontSize: 11, whiteSpace: 'pre-wrap', direction: 'ltr' }}>
                {log.stack_trace}
              </Code>
            </ScrollArea>
          </Box>
        )}
      </Stack>
    </Modal>
  )
}

export default function AdminConsolePage() {
  const token = useAuthStore(s => s.token)
  const userRole = useAuthStore(s => s.userRole)

  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [modules, setModules] = useState<Record<string, boolean>>({})
  const [logs, setLogs] = useState<AdminLog[]>([])
  const [loadingHealth, setLoadingHealth] = useState(true)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [loadingModules, setLoadingModules] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [levelFilter, setLevelFilter] = useState<string | null>(null)
  const [searchFilter, setSearchFilter] = useState('')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const [selectedLog, setSelectedLog] = useState<AdminLog | null>(null)
  const [stackOpen, setStackOpen] = useState(false)

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchHealth = useCallback(async () => {
    try {
      const h = await adminConsoleApi.getHealth()
      setHealth(h)
    } catch {
      setError('שגיאה בטעינת נתוני בריאות המערכת')
    } finally {
      setLoadingHealth(false)
    }
  }, [])

  const fetchLogs = useCallback(async () => {
    setLoadingLogs(true)
    try {
      const data = await adminConsoleApi.getLogs({
        level: levelFilter ?? undefined,
        search: searchFilter || undefined,
        limit: 300,
      })
      setLogs(data)
    } catch {
      // silent
    } finally {
      setLoadingLogs(false)
    }
  }, [levelFilter, searchFilter])

  const fetchModules = useCallback(async () => {
    try {
      const m = await adminConsoleApi.getModules()
      setModules(m)
    } catch {
      // silent
    } finally {
      setLoadingModules(false)
    }
  }, [])

  useEffect(() => {
    if (!token) return
    fetchHealth()
    fetchLogs()
    fetchModules()
  }, [token, fetchHealth, fetchLogs, fetchModules])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        fetchHealth()
        fetchLogs()
      }, 10000)
    } else {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [autoRefresh, fetchHealth, fetchLogs])

  useEffect(() => {
    fetchLogs()
  }, [fetchLogs])

  const toggleModule = async (key: string, val: boolean) => {
    const updated = { ...modules, [key]: val }
    setModules(updated)
    try {
      const result = await adminConsoleApi.updateModules({ [key]: val })
      setModules(result)
    } catch {
      setModules(modules)
    }
  }

  const clearLogs = async (level?: string) => {
    if (!confirm(level ? `למחוק כל הלוגים ברמה ${level}?` : 'למחוק את כל הלוגים?')) return
    await adminConsoleApi.clearLogs(level)
    fetchLogs()
    fetchHealth()
  }

  if (!token || userRole !== 'ADMIN') {
    return (
      <Center h="100vh">
        <Alert color="red" title="גישה נדחתה">
          האדמין קונסול מיועד למנהלי מערכת בלבד.
        </Alert>
      </Center>
    )
  }

  return (
    <Box p="md" dir="rtl" style={{ minHeight: '100vh', background: '#0f0f0f', color: '#e0e0e0' }}>
      <StackTraceModal log={selectedLog} opened={stackOpen} onClose={() => setStackOpen(false)} />

      {/* Header */}
      <Group mb="lg" justify="space-between">
        <Group gap="sm">
          <ThemeIcon size="xl" color="violet" variant="filled" radius="md">
            <span style={{ fontSize: 20 }}>⚙️</span>
          </ThemeIcon>
          <Box>
            <Title order={2} c="white">Admin Console</Title>
            <Text size="xs" c="dimmed">גישה ישירה בלבד — לא מקושר מהמערכת הרגילה</Text>
          </Box>
        </Group>
        <Group>
          <Switch
            label="רענון אוטומטי"
            checked={autoRefresh}
            onChange={e => setAutoRefresh(e.currentTarget.checked)}
            color="violet"
            labelPosition="left"
            styles={{ label: { color: '#aaa', fontSize: 12 } }}
          />
          <Button size="xs" variant="light" color="violet" onClick={() => { fetchHealth(); fetchLogs(); fetchModules() }}>
            🔄 רענן
          </Button>
        </Group>
      </Group>

      {error && <Alert color="red" mb="md" onClose={() => setError(null)} withCloseButton>{error}</Alert>}

      {/* Health Cards */}
      <Grid mb="lg">
        <Grid.Col span={{ base: 6, md: 3 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Text size="xs" c="dimmed" mb={4}>סטטוס</Text>
            {loadingHealth ? <Loader size="xs" /> : (
              <Badge color={health?.status === 'ok' ? 'green' : 'red'} size="lg" variant="filled">
                {health?.status === 'ok' ? '✅ תקין' : '⚠️ בעיה'}
              </Badge>
            )}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Text size="xs" c="dimmed" mb={4}>זמן פעילות</Text>
            <Text size="lg" fw={700} c="white">{health ? formatUptime(health.uptime_seconds) : '—'}</Text>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Text size="xs" c="dimmed" mb={4}>מסד נתונים</Text>
            {loadingHealth ? <Loader size="xs" /> : (
              <Badge color={health?.db_ok ? 'green' : 'red'} size="lg">
                {health?.db_ok ? '✅ מחובר' : '❌ ניתוק'}
              </Badge>
            )}
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 6, md: 3 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Text size="xs" c="dimmed" mb={4}>Python</Text>
            <Text size="sm" c="cyan" fw={600}>{health?.python_version ?? '—'}</Text>
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Log level counters */}
      {health && (
        <Group mb="lg" gap="xs">
          {Object.entries(health.log_counts).map(([lvl, cnt]) => (
            <Paper
              key={lvl}
              p="xs"
              radius="md"
              style={{
                background: '#1a1a2e',
                border: `1px solid ${lvl === 'ERROR' || lvl === 'CRITICAL' ? '#ff4444' : '#333'}`,
                cursor: 'pointer',
              }}
              onClick={() => setLevelFilter(levelFilter === lvl ? null : lvl)}
            >
              <Group gap={6}>
                <Badge color={LEVEL_COLORS[lvl] ?? 'gray'} size="xs">{lvl}</Badge>
                <Text size="sm" fw={700} c="white">{cnt}</Text>
              </Group>
            </Paper>
          ))}
        </Group>
      )}

      <Grid>
        {/* Module Toggles */}
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Title order={4} c="white" mb="md">⚡ מודולים פעילים</Title>
            {loadingModules ? <Loader size="sm" /> : (
              <Stack gap="sm">
                {Object.entries(MODULE_LABELS).map(([key, label]) => (
                  <Group key={key} justify="space-between" p="xs" style={{ borderRadius: 6, background: '#0f0f23' }}>
                    <Text size="sm" c={modules[key] ? 'white' : 'dimmed'}>{label}</Text>
                    <Switch
                      checked={!!modules[key]}
                      onChange={e => toggleModule(key, e.currentTarget.checked)}
                      color="violet"
                      size="sm"
                    />
                  </Group>
                ))}
              </Stack>
            )}
          </Paper>
        </Grid.Col>

        {/* Error Log */}
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper p="md" radius="md" style={{ background: '#1a1a2e', border: '1px solid #333' }}>
            <Group justify="space-between" mb="md">
              <Title order={4} c="white">📋 לוג תקלות</Title>
              <Group gap="xs">
                <Button size="xs" variant="subtle" color="red" onClick={() => clearLogs(levelFilter ?? undefined)}>
                  🗑 מחק {levelFilter ?? 'הכל'}
                </Button>
              </Group>
            </Group>

            <Group mb="sm" gap="xs">
              <TextInput
                placeholder="חיפוש בהודעות..."
                value={searchFilter}
                onChange={e => setSearchFilter(e.currentTarget.value)}
                size="xs"
                style={{ flex: 1 }}
                styles={{ input: { background: '#0f0f23', color: '#e0e0e0', border: '1px solid #444' } }}
              />
              <Select
                placeholder="רמה"
                value={levelFilter}
                onChange={setLevelFilter}
                clearable
                size="xs"
                w={120}
                data={['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']}
                styles={{ input: { background: '#0f0f23', color: '#e0e0e0', border: '1px solid #444' } }}
              />
            </Group>

            {loadingLogs ? (
              <Center h={200}><Loader color="violet" /></Center>
            ) : logs.length === 0 ? (
              <Center h={100}>
                <Text c="dimmed" size="sm">אין לוגים תואמים לחיפוש</Text>
              </Center>
            ) : (
              <ScrollArea h={500}>
                <Table striped highlightOnHover style={{ fontSize: 12 }}>
                  <Table.Thead style={{ background: '#0f0f23' }}>
                    <Table.Tr>
                      <Table.Th style={{ color: '#888', width: 80 }}>רמה</Table.Th>
                      <Table.Th style={{ color: '#888', width: 140 }}>זמן</Table.Th>
                      <Table.Th style={{ color: '#888', width: 140 }}>מקור</Table.Th>
                      <Table.Th style={{ color: '#888' }}>הודעה</Table.Th>
                      <Table.Th style={{ color: '#888', width: 40 }}></Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {logs.map(log => (
                      <Table.Tr
                        key={log.id}
                        style={{ background: log.level === 'CRITICAL' ? '#2d0000' : log.level === 'ERROR' ? '#1a0000' : 'transparent' }}
                      >
                        <Table.Td>
                          <Badge color={LEVEL_COLORS[log.level] ?? 'gray'} size="xs" variant="filled">
                            {log.level}
                          </Badge>
                        </Table.Td>
                        <Table.Td style={{ color: '#888', fontSize: 11, direction: 'ltr' }}>
                          {formatDate(log.created_at)}
                        </Table.Td>
                        <Table.Td style={{ color: '#aaa', fontSize: 11, fontFamily: 'monospace', direction: 'ltr' }}>
                          {log.source ?? '—'}
                        </Table.Td>
                        <Table.Td style={{ color: '#e0e0e0', maxWidth: 300 }}>
                          <Text size="xs" lineClamp={2}>{log.message}</Text>
                        </Table.Td>
                        <Table.Td>
                          {(log.stack_trace || log.message.length > 80) && (
                            <Tooltip label="פרטים מלאים">
                              <ActionIcon
                                size="xs"
                                variant="subtle"
                                color="violet"
                                onClick={() => { setSelectedLog(log); setStackOpen(true) }}
                              >
                                🔍
                              </ActionIcon>
                            </Tooltip>
                          )}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
            )}
          </Paper>
        </Grid.Col>
      </Grid>

      {/* Footer */}
      <Box mt="xl" pt="md" style={{ borderTop: '1px solid #333' }}>
        <Text size="xs" c="dimmed" ta="center">
          Admin Console · Lift Agent · {health?.server_time ? formatDate(health.server_time) : ''}
        </Text>
      </Box>
    </Box>
  )
}
