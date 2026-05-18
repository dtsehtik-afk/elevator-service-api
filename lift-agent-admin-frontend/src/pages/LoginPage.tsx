import { useState } from 'react'
import { TextInput, PasswordInput, Button, Paper, Title, Stack, Alert, Text, Group, PinInput } from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { login, verifyTotp } from '../api/auth'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const [screen, setScreen] = useState<'login' | 'totp'>('login')
  const [pendingToken, setPendingToken] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await login(email, password)
      if (result.mfa_required) {
        setPendingToken(result.pending_token)
        setTotpCode('')
        setScreen('totp')
      } else {
        localStorage.setItem('admin_token', result.access_token)
        navigate('/')
      }
    } catch {
      setError('אימייל או סיסמה שגויים')
    } finally {
      setLoading(false)
    }
  }

  const submitTotp = async (e: React.FormEvent) => {
    e.preventDefault()
    setTotpLoading(true)
    setError('')
    try {
      const token = await verifyTotp(pendingToken, totpCode)
      localStorage.setItem('admin_token', token)
      navigate('/')
    } catch {
      setError('קוד שגוי — בדוק את Google Authenticator ונסה שנית')
      setTotpCode('')
    } finally {
      setTotpLoading(false)
    }
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8f9fa' }}>
      <Paper p="xl" shadow="md" w={360}>
        <Title order={2} mb="lg" ta="center">Lift Agent Admin</Title>

        {screen === 'login' && (
          <form onSubmit={submit}>
            <Stack>
              {error && <Alert color="red">{error}</Alert>}
              <TextInput label="אימייל" value={email} onChange={(e) => setEmail(e.target.value)} required type="email" />
              <PasswordInput label="סיסמה" value={password} onChange={(e) => setPassword(e.target.value)} required />
              <Button type="submit" loading={loading} fullWidth>כניסה</Button>
            </Stack>
          </form>
        )}

        {screen === 'totp' && (
          <form onSubmit={submitTotp}>
            <Stack>
              <Stack gap={4} align="center">
                <Text size="2rem">🔐</Text>
                <Text fw={600}>אימות דו-שלבי</Text>
                <Text size="sm" c="dimmed" ta="center">הזן קוד מ-Google Authenticator</Text>
              </Stack>
              {error && <Alert color="red">{error}</Alert>}
              <Group justify="center">
                <PinInput length={6} type="number" value={totpCode} onChange={setTotpCode} dir="ltr" autoFocus />
              </Group>
              <Button type="submit" loading={totpLoading} fullWidth disabled={totpCode.length < 6}>אמת</Button>
              <Text ta="center" size="sm" style={{ cursor: 'pointer', color: '#228be6' }} onClick={() => { setScreen('login'); setError('') }}>
                חזרה להתחברות
              </Text>
            </Stack>
          </form>
        )}
      </Paper>
    </div>
  )
}
