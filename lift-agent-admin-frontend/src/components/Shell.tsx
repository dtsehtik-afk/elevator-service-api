import { AppShell, NavLink, Group, Text, Button, Burger } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { Outlet, NavLink as RouterLink, useNavigate } from 'react-router-dom'

const NAV = [
  { label: 'דיירים', path: '/' },
]

export default function Shell() {
  const [opened, { toggle }] = useDisclosure()
  const navigate = useNavigate()

  const logout = () => {
    localStorage.removeItem('admin_token')
    navigate('/login')
  }

  return (
    <AppShell header={{ height: 56 }} navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700} size="lg">🛗 Lift Agent Admin</Text>
          </Group>
          <Button variant="subtle" size="xs" onClick={logout}>יציאה</Button>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        {NAV.map((item) => (
          <NavLink key={item.path} component={RouterLink} to={item.path} label={item.label} />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
