import { useState } from 'react'
import { Center, Paper, TextInput, PasswordInput, Button, Title, Text, Stack } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/client'
import { useAuthStore } from '../stores/authStore'

export default function LoginPage() {
  const [email, setEmail] = useState('admin@lift-agent.com')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const setToken = useAuthStore((s) => s.setToken)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const { data } = await login(email, password)
      setToken(data.access_token)
      navigate('/')
    } catch {
      notifications.show({ title: 'שגיאה', message: 'פרטי התחברות שגויים', color: 'red' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Center h="100vh" bg="gray.0">
      <Paper withBorder shadow="md" p={36} w={380} radius="md">
        <Stack gap="xs" mb="lg" align="center">
          <Title order={2}>⚙️ Control Plane</Title>
          <Text c="dimmed" size="sm">Lift-Agent SaaS Admin</Text>
        </Stack>
        <form onSubmit={handleSubmit}>
          <Stack>
            <TextInput
              label="אימייל"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              dir="ltr"
            />
            <PasswordInput
              label="סיסמה"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              dir="ltr"
            />
            <Button type="submit" loading={loading} fullWidth mt="xs">
              התחבר
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  )
}
