import { AppShell, Burger, Group, NavLink, Text, ActionIcon, useMantineColorScheme, Avatar } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { notifications } from '@mantine/notifications'

const NAV = [
  { label: 'דיירים', path: '/tenants', icon: '🏢' },
  { label: 'ניטור', path: '/monitoring', icon: '📊' },
  { label: 'יכולות המערכת', path: '/features', icon: '🗺️' },
]

export default function Shell() {
  const [opened, { toggle }] = useDisclosure()
  const navigate = useNavigate()
  const location = useLocation()
  const clear = useAuthStore((s) => s.clear)

  const handleLogout = () => {
    clear()
    notifications.show({ message: 'התנתקת בהצלחה', color: 'gray' })
    navigate('/login')
  }

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="lg" c="blue">⚙️ Control Plane</Text>
          </Group>
          <Group>
            <Text size="sm" c="dimmed">admin@lift-agent.com</Text>
            <ActionIcon variant="subtle" color="red" onClick={handleLogout} title="התנתק">
              🚪
            </ActionIcon>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {NAV.map((item) => (
          <NavLink
            key={item.path}
            label={item.label}
            leftSection={<span>{item.icon}</span>}
            active={location.pathname.startsWith(item.path)}
            onClick={() => navigate(item.path)}
            mb={4}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
