import { useState, useEffect } from 'react'
import { industryIcon } from '../../utils/industry'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppShell, Burger, Group, NavLink, Text, Avatar, Menu,
  Divider, Box, rem, Button, ActionIcon, Tooltip,
  ScrollArea, Badge, Kbd,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { useAuthStore } from '../../stores/authStore'
import client from '../../api/client'
import { GlobalSearch, useGlobalSearch } from '../GlobalSearch'

// ── Types ──────────────────────────────────────────────────────────────────────

interface SubItem {
  label: string
  path: string
  icon: string
}

interface Section {
  id: string
  label: string
  icon: string
  path: string            // default nav target when clicking the section tab
  children: SubItem[]     // items for the contextual side panel (empty = no panel)
}

// ── Nav structure ──────────────────────────────────────────────────────────────

const SECTIONS: Section[] = [
  {
    id: 'dashboard',
    label: 'דשבורד',
    icon: '📊',
    path: '/',
    children: [],
  },
  {
    id: 'service',
    label: 'שירות',
    icon: '🔧',
    path: '/calls',
    children: [
      { label: 'מעליות', path: '/elevators', icon: '🏢' },
      { label: 'קריאות שירות', path: '/calls', icon: '📞' },
      { label: 'קריאות ממתינות', path: '/pending-calls', icon: '⚠️' },
      { label: 'טכנאים', path: '/technicians', icon: '👷' },
      { label: 'תחזוקה', path: '/maintenance', icon: '📅' },
      { label: 'דוחות בודק', path: '/inspections', icon: '🔍' },
      { label: 'מפת מעליות', path: '/map', icon: '🗺️' },
      { label: 'חברות ניהול', path: '/management-companies', icon: '🏗️' },
      { label: 'יועצים', path: '/consultants', icon: '🧑‍💼' },
      { label: 'ייבוא נתונים', path: '/import', icon: '📥' },
    ],
  },
  {
    id: 'finance',
    label: 'כספים',
    icon: '💰',
    path: '/erp',
    children: [
      { label: 'דשבורד כספי', path: '/erp', icon: '🏭' },
      { label: 'הצעות מחיר', path: '/quotes', icon: '📄' },
      { label: 'חוזים', path: '/contracts', icon: '📋' },
      { label: 'חשבוניות', path: '/invoices', icon: '💰' },
      { label: 'מלאי', path: '/inventory', icon: '📦' },
      { label: 'בקשות חלפים', path: '/part-requests', icon: '🔩' },
    ],
  },
  {
    id: 'crm',
    label: 'קשרי לקוחות',
    icon: '👤',
    path: '/customers',
    children: [
      { label: 'לקוחות', path: '/customers', icon: '👤' },
      { label: 'לידים', path: '/leads', icon: '🎯' },
    ],
  },
  {
    id: 'reports',
    label: 'דוחות',
    icon: '📈',
    path: '/reports',
    children: [
      { label: 'קריאות שירות', path: '/reports?entity=service_calls', icon: '📞' },
      { label: 'מעליות', path: '/reports?entity=elevators', icon: '🏢' },
      { label: 'לקוחות', path: '/reports?entity=customers', icon: '👤' },
      { label: 'חשבוניות', path: '/reports?entity=invoices', icon: '💰' },
      { label: 'חוזים', path: '/reports?entity=contracts', icon: '📋' },
      { label: 'תחזוקה', path: '/reports?entity=maintenance', icon: '📅' },
      { label: 'דוחות בודק', path: '/reports?entity=inspections', icon: '🔍' },
      { label: 'לידים', path: '/reports?entity=leads', icon: '🎯' },
    ],
  },
  {
    id: 'projects',
    label: 'פרויקטים',
    icon: '🏗️',
    path: '/projects',
    children: [],
  },
  {
    id: 'hr',
    label: 'כח אדם',
    icon: '👥',
    path: '/hr',
    children: [],
  },
  {
    id: 'settings',
    label: 'הגדרות',
    icon: '⚙️',
    path: '/settings',
    children: [
      { label: 'שעות עבודה', path: '/settings', icon: '🕐' },
      { label: 'שדות מותאמים', path: '/custom-fields', icon: '🗂️' },
      { label: 'הרשאות תפקיד', path: '/roles', icon: '🔐' },
    ],
  },
  {
    id: 'support',
    label: 'תמיכה',
    icon: '🛠️',
    path: '/support',
    children: [],
  },
  {
    id: 'whatsapp',
    label: 'סוכן ווצאפ',
    icon: '💬',
    path: '/whatsapp-agent',
    children: [],
  },
]

// navConfig override key for each section/sub-item is its path
type NavConfig = Record<string, { label?: string; visible?: boolean }>

function applyConfigToSubItems(items: SubItem[], config: NavConfig): SubItem[] {
  return items
    .map(item => {
      const ov = config[item.path] ?? {}
      if (ov.visible === false) return null
      return { ...item, label: ov.label || item.label }
    })
    .filter(Boolean) as SubItem[]
}

// Build flat list of all sub-item paths for active section detection
function allPaths(section: Section): string[] {
  return [section.path, ...section.children.map(c => c.path)]
}

function getActiveSection(pathname: string): Section | undefined {
  // Exact match on section default path first (dashboard '/')
  for (const s of SECTIONS) {
    if (s.path === pathname) return s
  }
  // Then prefix match on sub-items
  for (const s of SECTIONS) {
    for (const child of s.children) {
      if (child.path !== '/' && pathname.startsWith(child.path)) return s
    }
  }
  // Fallback to section prefix
  for (const s of SECTIONS) {
    if (s.path !== '/' && pathname.startsWith(s.path)) return s
  }
  return undefined
}

// ── DEFAULT_NAV_ITEMS export keeps settings page compatibility ─────────────────

export const DEFAULT_NAV_ITEMS = SECTIONS.map(s => ({
  label: s.label,
  path: s.path,
  icon: s.icon,
  children: s.children,
}))

// ── Sub-item link ──────────────────────────────────────────────────────────────

function SideLink({ item }: { item: SubItem }) {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const fullPath = pathname + search
  const active = item.path === '/'
    ? pathname === '/'
    : fullPath === item.path || pathname === item.path || pathname.startsWith(item.path + '/')

  return (
    <NavLink
      label={item.label}
      leftSection={<span style={{ fontSize: rem(14) }}>{item.icon}</span>}
      active={active}
      onClick={() => navigate(item.path)}
      mb={2}
      style={{ borderRadius: 8 }}
    />
  )
}

// ── Main Shell ─────────────────────────────────────────────────────────────────

export default function Shell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, { toggle: toggleMobile }] = useDisclosure(false)
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { userName, clear } = useAuthStore()
  const search = useGlobalSearch()

  const { data: navConfig = {} } = useQuery<NavConfig>({
    queryKey: ['nav-config'],
    queryFn: () => client.get('/settings/nav-config').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })

  const { data: companyInfo } = useQuery<{ company_name: string; company_icon?: string; industry?: string }>({
    queryKey: ['company-info'],
    queryFn: () => client.get('/settings/company-info').then(r => r.data),
    staleTime: 10 * 60 * 1000,
  })
  const companyName = companyInfo?.company_name ?? 'אקורד מעליות'
  const companyIcon = industryIcon(companyInfo?.industry, companyInfo?.company_icon ?? '⚡')

  const activeSection = getActiveSection(pathname)
  const hasPanel = (activeSection?.children.length ?? 0) > 0

  // Visible children for the side panel of the active section
  const panelItems = activeSection
    ? applyConfigToSubItems(activeSection.children, navConfig)
    : []

  function logout() {
    clear()
    notifications.show({ message: 'התנתקת בהצלחה', color: 'blue' })
    navigate('/login')
  }

  function handleSectionClick(s: Section) {
    navigate(s.path)
    if (mobileNavOpen) toggleMobile()
  }

  return (
    <>
      <GlobalSearch opened={search.opened} onClose={search.close} />
      <AppShell
        header={{ height: 64 }}
        navbar={{
          width: hasPanel ? 220 : 0,
          breakpoint: 'sm',
          collapsed: { mobile: !mobileNavOpen, desktop: !hasPanel },
        }}
        padding="md"
      >
        {/* ── Header ── */}
        <AppShell.Header style={{ background: 'var(--mantine-color-body)', borderBottom: '1px solid var(--mantine-color-default-border)' }}>
          <Group h="100%" px="lg" justify="space-between" wrap="nowrap">

            {/* Left: logo + mobile burger */}
            <Group gap="sm" wrap="nowrap">
              <Burger
                opened={mobileNavOpen}
                onClick={toggleMobile}
                hiddenFrom="sm"
                size="sm"
              />
              <Text
                fw={800}
                size="lg"
                style={{ cursor: 'pointer', color: 'var(--mantine-color-blue-7)', whiteSpace: 'nowrap', letterSpacing: '-0.3px' }}
                onClick={() => navigate('/')}
              >
                {companyIcon} {companyName}
              </Text>
            </Group>

            {/* Center: horizontal section tabs (hidden on mobile) */}
            <ScrollArea
              type="auto"
              style={{ flex: 1 }}
              visibleFrom="sm"
              styles={{ scrollbar: { display: 'none' } }}
            >
              <Group gap={2} wrap="nowrap" justify="center" px="md">
                {SECTIONS.map(s => {
                  const ov = navConfig[s.path] ?? {}
                  if (ov.visible === false) return null
                  const label = ov.label || s.label
                  const isActive = activeSection?.id === s.id
                  return (
                    <Button
                      key={s.id}
                      variant={isActive ? 'light' : 'subtle'}
                      size="sm"
                      onClick={() => handleSectionClick(s)}
                      style={{
                        color: isActive ? 'var(--mantine-color-blue-7)' : 'var(--mantine-color-dimmed)',
                        borderBottom: isActive ? '2px solid var(--mantine-color-blue-5)' : '2px solid transparent',
                        borderRadius: '6px 6px 0 0',
                        fontWeight: isActive ? 600 : 400,
                        whiteSpace: 'nowrap',
                        padding: '6px 10px',
                        height: 40,
                        fontSize: 13,
                        transition: 'all 0.15s',
                        minWidth: 0,
                      }}
                    >
                      <span style={{ fontSize: 13, marginInlineEnd: 4 }}>{s.icon}</span>{label}
                    </Button>
                  )
                })}
              </Group>
            </ScrollArea>

            {/* Right: search + user */}
            <Group gap="sm" wrap="nowrap">
              <Tooltip
                label={<Group gap={4}><Text size="xs">חיפוש</Text><Kbd size="xs">Ctrl+K</Kbd></Group>}
                position="bottom"
              >
                <Button
                  variant="default"
                  size="sm"
                  leftSection={<span>🔍</span>}
                  onClick={search.open}
                  visibleFrom="sm"
                  style={{ borderRadius: 20, minWidth: 110 }}
                >
                  <Group gap="xs" justify="space-between" style={{ flex: 1 }}>
                    <Text size="xs" c="dimmed">חפש...</Text>
                    <Kbd size="xs">⌘K</Kbd>
                  </Group>
                </Button>
              </Tooltip>
              <ActionIcon variant="default" size="md" onClick={search.open} hiddenFrom="sm">
                <span>🔍</span>
              </ActionIcon>

              <Menu shadow="md" width={180} position="bottom-end">
                <Menu.Target>
                  <Group gap="xs" style={{ cursor: 'pointer' }} wrap="nowrap">
                    <Avatar size="sm" color="blue" radius="xl">
                      {userName?.charAt(0) ?? 'A'}
                    </Avatar>
                    <Text size="sm" fw={500} visibleFrom="sm">{userName ?? 'משתמש'}</Text>
                  </Group>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item leftSection={<span>📱</span>} onClick={() => navigate('/tech')}>
                    מצב טכנאי
                  </Menu.Item>
                  <Menu.Divider />
                  <Menu.Item onClick={logout} color="red" leftSection={<span>🚪</span>}>
                    התנתק
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </AppShell.Header>

        {/* ── Side panel (contextual nav for active section) ── */}
        <AppShell.Navbar
          p="xs"
          style={{
            background: 'var(--mantine-color-body)',
            borderLeft: '1px solid var(--mantine-color-default-border)',
          }}
        >
          {/* Mobile: show all sections */}
          <Box hiddenFrom="sm" mb="xs">
            {SECTIONS.map(s => {
              const ov = navConfig[s.path] ?? {}
              if (ov.visible === false) return null
              return (
                <NavLink
                  key={s.id}
                  label={ov.label || s.label}
                  leftSection={<span style={{ fontSize: rem(14) }}>{s.icon}</span>}
                  active={activeSection?.id === s.id}
                  onClick={() => handleSectionClick(s)}
                  mb={2}
                  style={{ borderRadius: 8, fontWeight: activeSection?.id === s.id ? 600 : 400 }}
                />
              )
            })}
            <Divider my="xs" />
          </Box>

          {/* Panel title */}
          {activeSection && panelItems.length > 0 && (
            <Text size="xs" c="dimmed" fw={600} px="xs" mb="xs" tt="uppercase" style={{ letterSpacing: '0.5px' }}>
              {activeSection.icon} {activeSection.label}
            </Text>
          )}

          <ScrollArea style={{ flex: 1 }}>
            {panelItems.map(item => (
              <SideLink key={item.path} item={item} />
            ))}
          </ScrollArea>

          <Divider mt="auto" mb="xs" />
          <Text size="xs" c="dimmed" ta="center">v2.1.0</Text>
        </AppShell.Navbar>

        <AppShell.Main style={{ overflowX: 'hidden' }}>{children}</AppShell.Main>
      </AppShell>
    </>
  )
}
