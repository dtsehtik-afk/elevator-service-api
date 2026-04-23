import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  AppShell, Burger, Group, NavLink, Text, Avatar, Menu, ActionIcon,
  Divider, Box, rem, Button,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { notifications } from '@mantine/notifications'
import { useAuthStore } from '../../stores/authStore'

const NAV_ITEMS = [
  { label: 'דשבורד', path: '/', icon: '📊' },
  { label: 'מעליות', path: '/elevators', icon: '🏢' },
  { label: 'קריאות שירות', path: '/calls', icon: '🔧' },
  { label: 'קריאות ממתינות', path: '/pending-calls', icon: '⚠️' },
  { label: 'טכנאים', path: '/technicians', icon: '👷' },
  { label: 'תחזוקה', path: '/maintenance', icon: '📅' },
  { label: 'דוחות בודק', path: '/inspections', icon: '🔍' },
  { label: 'מפת מעליות', path: '/map', icon: '🗺️' },
  { label: 'חברות ניהול', path: '/management-companies', icon: '🏗️' },
  { label: 'ייבוא נתונים', path: '/import', icon: '📥' },
]

const ADMIN_NAV_ITEMS: { label: string; path: string; icon: string }[] = []

export default function Shell({ children }: { children: React.ReactNode }) {
  const [opened, { toggle }] = useDisclosure()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { userName, userRole, clear } = useAuthStore()

  function logout() {
    clear()
    notifications.show({ message: 'התנתקת בהצלחה', color: 'blue' })
    navigate('/login')
  }

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="lg" c="blue">⚙️ אקורד מעליות</Text>
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
        <Box mt="xs">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              label={item.label}
              leftSection={<span style={{ fontSize: rem(18) }}>{item.icon}</span>}
              active={pathname === item.path || (item.path !== '/' && pathname.startsWith(item.path))}
              onClick={() => navigate(item.path)}
              mb={4}
              style={{ borderRadius: 8 }}
            />
          ))}
          {userRole === 'ADMIN' && ADMIN_NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              label={item.label}
              leftSection={<span style={{ fontSize: rem(18) }}>{item.icon}</span>}
              active={pathname === item.path || (item.path !== '/' && pathname.startsWith(item.path))}
              onClick={() => navigate(item.path)}
              mb={4}
              style={{ borderRadius: 8 }}
            />
          ))}
        </Box>
        <Divider mt="auto" mb="xs" />
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
        <Text size="xs" c="dimmed" ta="center">v1.0.0</Text>
      </AppShell.Navbar>

      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  )
}
