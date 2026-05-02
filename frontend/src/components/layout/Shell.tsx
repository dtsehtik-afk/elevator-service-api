import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppShell, Burger, Group, NavLink, Text, Avatar, Menu, ActionIcon,
  Divider, Box, rem, Button, Collapse,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { useAuthStore } from '../../stores/authStore'

interface NavItem {
  label: string
  path: string
  icon: string
  children?: NavItem[]
}

const NAV_ITEMS: NavItem[] = [
  { label: 'דשבורד', path: '/', icon: '📊' },
  {
    label: 'שירות שטח', path: '/elevators', icon: '🔧',
    children: [
      { label: 'מעליות', path: '/elevators', icon: '🏢' },
      { label: 'קריאות שירות', path: '/calls', icon: '🔧' },
      { label: 'קריאות ממתינות', path: '/pending-calls', icon: '⚠️' },
      { label: 'טכנאים', path: '/technicians', icon: '👷' },
      { label: 'תחזוקה', path: '/maintenance', icon: '📅' },
      { label: 'דוחות בודק', path: '/inspections', icon: '🔍' },
      { label: 'מפת מעליות', path: '/map', icon: '🗺️' },
      { label: 'חברות ניהול', path: '/management-companies', icon: '🏗️' },
      { label: 'ייבוא נתונים', path: '/import', icon: '📥' },
    ],
  },
  {
    label: 'ERP', path: '/erp', icon: '🏭',
    children: [
      { label: 'דשבורד ERP', path: '/erp', icon: '🏭' },
      { label: 'לקוחות', path: '/customers', icon: '👤' },
      { label: 'לידים', path: '/leads', icon: '🎯' },
      { label: 'הצעות מחיר', path: '/quotes', icon: '📄' },
      { label: 'חוזים', path: '/contracts', icon: '📋' },
      { label: 'חשבוניות', path: '/invoices', icon: '💰' },
      { label: 'מלאי', path: '/inventory', icon: '📦' },
    ],
  },
  { label: 'דוחות', path: '/reports', icon: '📈' },
  {
    label: 'הגדרות', path: '/settings', icon: '⚙️',
    children: [
      { label: 'שעות עבודה', path: '/settings', icon: '🕐' },
      { label: 'שדות מותאמים', path: '/custom-fields', icon: '🗂️' },
      { label: 'הרשאות תפקיד', path: '/roles', icon: '🔐' },
    ],
  },
]

function NavGroup({ item, depth = 0 }: { item: NavItem; depth?: number }) {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const isActive = pathname === item.path || (item.path !== '/' && pathname.startsWith(item.path))
  const hasChildren = item.children && item.children.length > 0
  const [open, setOpen] = useDisclosure(isActive || (hasChildren && item.children!.some(c => pathname.startsWith(c.path))))

  if (hasChildren) {
    return (
      <>
        <NavLink
          label={item.label}
          leftSection={<span style={{ fontSize: rem(16) }}>{item.icon}</span>}
          rightSection={<span style={{ fontSize: rem(10) }}>{open ? '▲' : '▼'}</span>}
          active={isActive}
          onClick={() => setOpen.toggle()}
          mb={2}
          pl={depth * 12}
          style={{ borderRadius: 8 }}
        />
        <Collapse in={open}>
          {item.children!.map(child => (
            <NavGroup key={child.path} item={child} depth={depth + 1} />
          ))}
        </Collapse>
      </>
    )
  }

  return (
    <NavLink
      key={item.path}
      label={item.label}
      leftSection={<span style={{ fontSize: rem(depth > 0 ? 14 : 16) }}>{item.icon}</span>}
      active={pathname === item.path || (item.path !== '/' && pathname.startsWith(item.path))}
      onClick={() => navigate(item.path)}
      mb={2}
      pl={depth * 12 + 8}
      style={{ borderRadius: 8 }}
    />
  )
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const [opened, { toggle }] = useDisclosure()
  const navigate = useNavigate()
  const { userName, clear } = useAuthStore()

  function logout() {
    clear()
    notifications.show({ message: 'התנתקת בהצלחה', color: 'blue' })
    navigate('/login')
  }

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="lg" c="blue" style={{ cursor: 'pointer' }} onClick={() => navigate('/erp')}>
              ⚙️ אקורד מעליות ERP
            </Text>
          </Group>
          <Menu shadow="md" width={180} position="bottom-end">
            <Menu.Target>
              <Group gap="xs" style={{ cursor: 'pointer' }}>
                <Avatar size="sm" color="blue" radius="xl">
                  {userName?.charAt(0) ?? 'A'}
                </Avatar>
                <Text size="sm" fw={500}>{userName ?? 'משתמש'}</Text>
              </Group>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item onClick={logout} color="red">התנתק</Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <Box mt="xs" style={{ overflowY: 'auto', flex: 1 }}>
          {NAV_ITEMS.map(item => (
            <NavGroup key={item.path} item={item} />
          ))}
        </Box>
        <Divider mt="xs" mb="xs" />
        <Button
          variant="light"
          color="blue"
          fullWidth
          mb="xs"
          leftSection={<span>📱</span>}
          onClick={() => navigate('/tech')}
          style={{ borderRadius: 8 }}
        >
          מצב טכנאי
        </Button>
        <Text size="xs" c="dimmed" ta="center">v2.0.0 ERP</Text>
      </AppShell.Navbar>

      <AppShell.Main style={{ overflowX: 'hidden' }}>{children}</AppShell.Main>
    </AppShell>
  )
}
