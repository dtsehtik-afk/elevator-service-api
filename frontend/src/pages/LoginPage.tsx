import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Center, Paper, Stack, Title, Text, TextInput, PasswordInput,
  Button, Alert,
} from '@mantine/core'
import { useAuthStore } from '../stores/authStore'
import { login } from '../api/auth'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const token = await login(email, password)
      // Decode name from JWT payload (base64)
      const payload = JSON.parse(atob(token.split('.')[1]))
      const name = payload.sub?.split('@')[0] ?? 'משתמש'
      const role = payload.role ?? 'TECHNICIAN'
      setAuth(token, name, role)
      navigate(role === 'TECHNICIAN' ? '/tech' : '/')
    } catch {
      setError('פרטי התחברות שגויים. אנא נסה שנית.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Center h="100vh" bg="gray.0">
      <Paper shadow="md" p="xl" w={380} radius="md" withBorder>
        <Stack gap="lg">
          <Stack gap={4} align="center">
            <Text size="3rem">⚙️</Text>
            <Title order={2} ta="center">אקורד מעליות</Title>
            <Text c="dimmed" size="sm" ta="center">מערכת ניהול שירות</Text>
          </Stack>

          {error && <Alert color="red" variant="light">{error}</Alert>}

          <form onSubmit={handleSubmit}>
            <Stack gap="sm">
              <TextInput
                label="אימייל"
                placeholder="your@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                dir="ltr"
              />
              <PasswordInput
                label="סיסמה"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                dir="ltr"
              />
              <Button type="submit" fullWidth loading={loading} mt="xs">
                התחבר
              </Button>
            </Stack>
          </form>
        </Stack>
      </Paper>
    </Center>
  )
}
