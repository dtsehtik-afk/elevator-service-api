import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Center, Paper, Stack, Title, Text, TextInput, PasswordInput,
  Button, Alert, Anchor, PinInput, Group,
} from '@mantine/core'
import { useAuthStore } from '../stores/authStore'
import { login, verifyTotp, forgotPassword, resetPassword } from '../api/auth'
import client from '../api/client'
import { industryIcon } from '../utils/industry'

type Screen = 'login' | 'totp' | 'forgot' | 'reset'

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)

  const [screen, setScreen] = useState<Screen>('login')
  const [companyName, setCompanyName] = useState('מערכת ניהול')
  const [companyIcon, setCompanyIcon] = useState('⚙️')

  useEffect(() => {
    client.get('/settings/company-info').then(r => {
      setCompanyName(r.data.company_name ?? 'מערכת ניהול')
      setCompanyIcon(industryIcon(r.data.industry, r.data.company_icon ?? '⚙️'))
    }).catch(() => {})
  }, [])

  // Login state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState('')

  // MFA state
  const [pendingToken, setPendingToken] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)
  const [totpError, setTotpError] = useState('')

  // Forgot password state
  const [phone, setPhone] = useState('')
  const [forgotLoading, setForgotLoading] = useState(false)
  const [forgotError, setForgotError] = useState('')

  // Reset password state
  const [otp, setOtp] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [resetLoading, setResetLoading] = useState(false)
  const [resetError, setResetError] = useState('')
  const [resetSuccess, setResetSuccess] = useState(false)

  function completeLogin(token: string) {
    const payload = JSON.parse(atob(token.split('.')[1]))
    const name = payload.sub?.split('@')[0] ?? 'משתמש'
    const role = payload.role ?? 'TECHNICIAN'
    setAuth(token, name, role)
    navigate(role === 'TECHNICIAN' ? '/tech' : '/')
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoginError('')
    setLoginLoading(true)
    try {
      const result = await login(email, password)
      if (result.mfa_required) {
        setPendingToken(result.pending_token)
        setTotpCode('')
        setTotpError('')
        setScreen('totp')
      } else {
        completeLogin(result.access_token)
      }
    } catch {
      setLoginError('פרטי התחברות שגויים. אנא נסה שנית.')
    } finally {
      setLoginLoading(false)
    }
  }

  async function handleTotpVerify(e: React.FormEvent) {
    e.preventDefault()
    setTotpError('')
    setTotpLoading(true)
    try {
      const token = await verifyTotp(pendingToken, totpCode)
      completeLogin(token)
    } catch {
      setTotpError('קוד שגוי — בדוק את האפליקציה ונסה שנית.')
      setTotpCode('')
    } finally {
      setTotpLoading(false)
    }
  }

  async function handleForgot(e: React.FormEvent) {
    e.preventDefault()
    setForgotError('')
    setForgotLoading(true)
    try {
      await forgotPassword(phone)
      setScreen('reset')
    } catch {
      setForgotError('שגיאה בשליחת הקוד. אנא נסה שנית.')
    } finally {
      setForgotLoading(false)
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setResetError('')
    setResetLoading(true)
    try {
      await resetPassword(phone, otp, newPassword)
      setResetSuccess(true)
      setTimeout(() => {
        setScreen('login')
        setResetSuccess(false)
        setOtp('')
        setNewPassword('')
        setPhone('')
      }, 2500)
    } catch (err: any) {
      setResetError(err?.response?.data?.detail ?? 'הקוד שגוי או פג תוקף.')
    } finally {
      setResetLoading(false)
    }
  }

  return (
    <Center h="100vh" bg="gray.0">
      <Paper shadow="md" p="xl" w={380} radius="md" withBorder>
        <Stack gap="lg">
          <Stack gap={4} align="center">
            <Text size="3rem">{companyIcon}</Text>
            <Title order={2} ta="center">{companyName}</Title>
            <Text c="dimmed" size="sm" ta="center">מערכת ניהול שירות</Text>
          </Stack>

          {/* ── Login ── */}
          {screen === 'login' && (
            <>
              {loginError && <Alert color="red" variant="light">{loginError}</Alert>}
              <form onSubmit={handleLogin}>
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
                  <Button type="submit" fullWidth loading={loginLoading} mt="xs">
                    התחבר
                  </Button>
                  <Text ta="center" size="sm">
                    <Anchor component="button" type="button" onClick={() => { setScreen('forgot'); setForgotError('') }}>
                      שכחתי סיסמה
                    </Anchor>
                  </Text>
                </Stack>
              </form>
            </>
          )}

          {/* ── TOTP MFA step ── */}
          {screen === 'totp' && (
            <>
              <Stack gap={4} align="center">
                <Text size="2rem">🔐</Text>
                <Text fw={600} ta="center">אימות דו-שלבי</Text>
                <Text size="sm" c="dimmed" ta="center">
                  פתח את Google Authenticator והזן את הקוד בן 6 הספרות
                </Text>
              </Stack>
              {totpError && <Alert color="red" variant="light">{totpError}</Alert>}
              <form onSubmit={handleTotpVerify}>
                <Stack gap="sm">
                  <Group justify="center">
                    <PinInput
                      length={6}
                      type="number"
                      value={totpCode}
                      onChange={setTotpCode}
                      dir="ltr"
                      autoFocus
                    />
                  </Group>
                  <Button type="submit" fullWidth loading={totpLoading} disabled={totpCode.length < 6}>
                    אמת
                  </Button>
                  <Text ta="center" size="sm">
                    <Anchor component="button" type="button" onClick={() => { setScreen('login'); setTotpCode('') }}>
                      חזרה להתחברות
                    </Anchor>
                  </Text>
                </Stack>
              </form>
            </>
          )}

          {/* ── Forgot password — enter phone ── */}
          {screen === 'forgot' && (
            <>
              <Text ta="center" size="sm" c="dimmed">
                הזן את מספר הוואטסאפ שלך ונשלח קוד לאיפוס סיסמה
              </Text>
              {forgotError && <Alert color="red" variant="light">{forgotError}</Alert>}
              <form onSubmit={handleForgot}>
                <Stack gap="sm">
                  <TextInput
                    label="מספר וואטסאפ"
                    placeholder="05X-XXXXXXX"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    required
                    dir="ltr"
                  />
                  <Button type="submit" fullWidth loading={forgotLoading}>
                    שלח קוד
                  </Button>
                  <Text ta="center" size="sm">
                    <Anchor component="button" type="button" onClick={() => setScreen('login')}>
                      חזרה להתחברות
                    </Anchor>
                  </Text>
                </Stack>
              </form>
            </>
          )}

          {/* ── Reset password — enter OTP + new password ── */}
          {screen === 'reset' && (
            <>
              {resetSuccess ? (
                <Alert color="green" variant="light" ta="center">
                  ✅ הסיסמה עודכנה בהצלחה! מועבר להתחברות...
                </Alert>
              ) : (
                <>
                  <Text ta="center" size="sm" c="dimmed">
                    הזן את הקוד שקיבלת בוואטסאפ וסיסמה חדשה
                  </Text>
                  {resetError && <Alert color="red" variant="light">{resetError}</Alert>}
                  <form onSubmit={handleReset}>
                    <Stack gap="sm">
                      <Stack gap={4}>
                        <Text size="sm" fw={500}>קוד אימות</Text>
                        <Group justify="center">
                          <PinInput
                            length={6}
                            type="number"
                            value={otp}
                            onChange={setOtp}
                            dir="ltr"
                          />
                        </Group>
                      </Stack>
                      <PasswordInput
                        label="סיסמה חדשה"
                        placeholder="לפחות 6 תווים"
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        required
                        minLength={6}
                        dir="ltr"
                      />
                      <Button type="submit" fullWidth loading={resetLoading}>
                        עדכן סיסמה
                      </Button>
                      <Text ta="center" size="sm">
                        <Anchor component="button" type="button" onClick={() => setScreen('forgot')}>
                          שלח קוד מחדש
                        </Anchor>
                      </Text>
                    </Stack>
                  </form>
                </>
              )}
            </>
          )}
        </Stack>
      </Paper>
    </Center>
  )
}
