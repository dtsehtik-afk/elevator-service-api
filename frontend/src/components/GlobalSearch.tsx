import { useState, useEffect, useRef, useCallback } from 'react'
import { Modal, TextInput, Stack, Text, Group, Paper, Badge, Loader, Box, Kbd, Divider } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { searchApi, SearchResult } from '../api/search'

const TYPE_ICON: Record<string, string> = {
  elevator: '🛗',
  customer: '🏢',
  call: '📞',
  technician: '👷',
}

const TYPE_LABEL: Record<string, string> = {
  elevator: 'מעלית',
  customer: 'לקוח',
  call: 'קריאה',
  technician: 'טכנאי',
}

const TYPE_COLOR: Record<string, string> = {
  elevator: 'blue',
  customer: 'teal',
  call: 'orange',
  technician: 'violet',
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

interface Props {
  opened: boolean
  onClose: () => void
}

export function GlobalSearch({ opened, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [activeIdx, setActiveIdx] = useState(0)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  const debouncedQuery = useDebounce(query, 250)

  useEffect(() => {
    if (!opened) {
      setQuery('')
      setResults([])
      setActiveIdx(0)
    } else {
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [opened])

  useEffect(() => {
    if (debouncedQuery.length < 2) {
      setResults([])
      return
    }
    let cancelled = false
    setLoading(true)
    searchApi.search(debouncedQuery).then(data => {
      if (!cancelled) {
        setResults(data)
        setActiveIdx(0)
      }
    }).catch(() => {
      if (!cancelled) setResults([])
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [debouncedQuery])

  const navigateTo = useCallback((url: string) => {
    onClose()
    navigate(url)
  }, [navigate, onClose])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && results[activeIdx]) {
      navigateTo(results[activeIdx].url)
    }
  }

  // Group by type
  const grouped: Record<string, SearchResult[]> = {}
  for (const r of results) {
    if (!grouped[r.type]) grouped[r.type] = []
    grouped[r.type].push(r)
  }

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      withCloseButton={false}
      size={560}
      padding={0}
      radius="lg"
      overlayProps={{ blur: 3 }}
      styles={{
        content: { overflow: 'hidden' },
        body: { padding: 0 },
      }}
    >
      <Box p="md" style={{ borderBottom: '1px solid #eee' }}>
        <Group gap="sm">
          <Text size="xl" style={{ lineHeight: 1 }}>🔍</Text>
          <TextInput
            ref={inputRef}
            placeholder="חפש מעלית, לקוח, קריאה, טכנאי..."
            value={query}
            onChange={e => setQuery(e.currentTarget.value)}
            onKeyDown={handleKeyDown}
            variant="unstyled"
            size="md"
            style={{ flex: 1 }}
            styles={{ input: { fontSize: 16, direction: 'rtl' } }}
          />
          {loading && <Loader size="xs" />}
          <Kbd size="sm">Esc</Kbd>
        </Group>
      </Box>

      {results.length === 0 && query.length >= 2 && !loading && (
        <Box p="xl" ta="center">
          <Text c="dimmed" size="sm">לא נמצאו תוצאות עבור "{query}"</Text>
        </Box>
      )}

      {results.length === 0 && query.length < 2 && (
        <Box p="lg">
          <Text size="xs" c="dimmed" ta="center" mb="sm">חיפוש גלובלי</Text>
          <Group justify="center" gap="xs">
            {Object.entries(TYPE_LABEL).map(([type, label]) => (
              <Badge key={type} color={TYPE_COLOR[type]} variant="light" size="sm">
                {TYPE_ICON[type]} {label}
              </Badge>
            ))}
          </Group>
          <Text size="xs" c="dimmed" ta="center" mt="md">
            הקלד לפחות 2 תווים לחיפוש
          </Text>
        </Box>
      )}

      {Object.keys(grouped).length > 0 && (
        <Stack gap={0} style={{ maxHeight: 420, overflowY: 'auto' }} pb="xs">
          {Object.entries(grouped).map(([type, items], gIdx) => (
            <Box key={type}>
              <Box px="md" py={6} style={{ background: '#f8f9fa' }}>
                <Text size="xs" fw={600} c="dimmed" tt="uppercase">
                  {TYPE_ICON[type]} {TYPE_LABEL[type]}
                </Text>
              </Box>
              {items.map(item => {
                const flatIdx = results.indexOf(item)
                const isActive = flatIdx === activeIdx
                return (
                  <Box
                    key={item.id}
                    px="md"
                    py="sm"
                    style={{
                      cursor: 'pointer',
                      background: isActive ? '#f0f4ff' : 'white',
                      borderLeft: isActive ? '3px solid #4c6ef5' : '3px solid transparent',
                    }}
                    onClick={() => navigateTo(item.url)}
                    onMouseEnter={() => setActiveIdx(flatIdx)}
                  >
                    <Group justify="space-between">
                      <Box>
                        <Text size="sm" fw={500}>{item.title}</Text>
                        {item.subtitle && (
                          <Text size="xs" c="dimmed">{item.subtitle}</Text>
                        )}
                      </Box>
                      <Badge color={TYPE_COLOR[type]} size="xs" variant="light">
                        {TYPE_LABEL[type]}
                      </Badge>
                    </Group>
                  </Box>
                )
              })}
            </Box>
          ))}
        </Stack>
      )}

      <Box px="md" py="xs" style={{ borderTop: '1px solid #eee', background: '#f8f9fa' }}>
        <Group gap="xs" justify="center">
          <Group gap={4}><Kbd size="xs">↑↓</Kbd><Text size="xs" c="dimmed">ניווט</Text></Group>
          <Group gap={4}><Kbd size="xs">Enter</Kbd><Text size="xs" c="dimmed">פתח</Text></Group>
          <Group gap={4}><Kbd size="xs">Esc</Kbd><Text size="xs" c="dimmed">סגור</Text></Group>
        </Group>
      </Box>
    </Modal>
  )
}

export function useGlobalSearch() {
  const [opened, setOpened] = useState(false)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        setOpened(o => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return { opened, open: () => setOpened(true), close: () => setOpened(false) }
}
