import { useState } from 'react'
import { TextInput, PasswordInput, Button, Paper, Title, Stack, Alert } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { login } from '../api/auth'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await login(email, password)
      localStorage.setItem('admin_token', data.access_token)
      navigate('/')
    } catch {
      setError('אימייל או סיסמה שגויים')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8f9fa' }}>
      <Paper p="xl" shadow="md" w={360}>
        <Title order={2} mb="lg" ta="center">Lift Agent Admin</Title>
        <form onSubmit={submit}>
          <Stack>
            {error && <Alert color="red">{error}</Alert>}
            <TextInput label="אימייל" value={email} onChange={(e) => setEmail(e.target.value)} required type="email" />
            <PasswordInput label="סיסמה" value={password} onChange={(e) => setPassword(e.target.value)} required />
            <Button type="submit" loading={loading} fullWidth>כניסה</Button>
          </Stack>
        </form>
      </Paper>
    </div>
  )
}
