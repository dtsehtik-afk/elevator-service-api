import { useState, useEffect } from 'react'
import { Title, Paper, Stack, Text, Badge, Group, Button, Alert, PinInput, Table } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { totpSetup, totpConfirm, totpDisable, totpStatus, loginHistory } from '../api/auth'
import api from '../api/client'

export default function SecurityPage() {
  const qc = useQueryClient()

  const { data: status } = useQuery({ queryKey: ['totp-status'], queryFn: totpStatus })
  const { data: history } = useQuery({ queryKey: ['login-history'], queryFn: loginHistory })

  const [setupData, setSetupData] = useState<{ secret: string } | null>(null)
  const [qrUrl, setQrUrl] = useState<string | null>(null)
  const [setupCode, setSetupCode] = useState('')
  const [setupLoading, setSetupLoading] = useState(false)
  const [disableCode, setDisableCode] = useState('')

  useEffect(() => {
    if (!setupData) { setQrUrl(null); return }
    api.get('/auth/totp/qr', { responseType: 'blob' }).then(r => {
      setQrUrl(URL.createObjectURL(r.data))
    }).catch(() => {})
  }, [setupData])
  const [disableLoading, setDisableLoading] = useState(false)
  const [showDisable, setShowDisable] = useState(false)

  async function handleSetup() {
    setSetupLoading(true)
    try {
      const data = await totpSetup()
      setSetupData(data)
      setSetupCode('')
    } catch {
      notifications.show({ message: 'Error setting up TOTP', color: 'red' })
    } finally {
      setSetupLoading(false)
    }
  }

  async function handleConfirm() {
    setSetupLoading(true)
    try {
      await totpConfirm(setupCode)
      notifications.show({ message: '✅ Two-factor authentication enabled', color: 'green' })
      setSetupData(null)
      setSetupCode('')
      qc.invalidateQueries({ queryKey: ['totp-status'] })
    } catch {
      notifications.show({ message: 'Invalid code — try again', color: 'red' })
    } finally {
      setSetupLoading(false)
    }
  }

  async function handleDisable() {
    setDisableLoading(true)
    try {
      await totpDisable(disableCode)
      notifications.show({ message: 'Two-factor authentication disabled', color: 'orange' })
      setShowDisable(false)
      setDisableCode('')
      qc.invalidateQueries({ queryKey: ['totp-status'] })
    } catch {
      notifications.show({ message: 'Invalid code', color: 'red' })
    } finally {
      setDisableLoading(false)
    }
  }

  const totpEnabled = status?.totp_enabled ?? false

  return (
    <Stack gap="md" maw={560}>
      <Title order={2}>🔐 Security</Title>

      <Paper withBorder radius="md" p="lg">
        <Group justify="space-between" mb="sm">
          <div>
            <Text fw={600}>Two-Factor Authentication (Google Authenticator)</Text>
            <Text size="sm" c="dimmed">Protect your account with a one-time code</Text>
          </div>
          <Badge color={totpEnabled ? 'green' : 'gray'} size="lg">{totpEnabled ? 'Enabled' : 'Disabled'}</Badge>
        </Group>

        {!totpEnabled && !setupData && (
          <Button onClick={handleSetup} loading={setupLoading}>Enable 2FA</Button>
        )}

        {setupData && (
          <Stack gap="md">
            <Alert color="blue" variant="light">
              Scan the QR code with Google Authenticator, then enter the 6-digit code shown in the app.
            </Alert>
            <Group justify="center">
              {qrUrl && (
                <img src={qrUrl} width={200} height={200} alt="TOTP QR Code" style={{ borderRadius: 8, border: '1px solid #dee2e6' }} />
              )}
            </Group>
            <Text size="xs" c="dimmed" ta="center" style={{ fontFamily: 'monospace' }}>
              {setupData.secret}
            </Text>
            <Stack gap="xs">
              <Text size="sm" fw={500}>Enter confirmation code:</Text>
              <Group justify="center">
                <PinInput length={6} type="number" value={setupCode} onChange={setSetupCode} dir="ltr" />
              </Group>
              <Group>
                <Button onClick={handleConfirm} loading={setupLoading} disabled={setupCode.length < 6}>
                  Confirm & Enable
                </Button>
                <Button variant="subtle" color="gray" onClick={() => setSetupData(null)}>Cancel</Button>
              </Group>
            </Stack>
          </Stack>
        )}

        {totpEnabled && !showDisable && (
          <Button color="red" variant="light" onClick={() => setShowDisable(true)}>Disable 2FA</Button>
        )}

        {totpEnabled && showDisable && (
          <Stack gap="xs">
            <Text size="sm">Enter a code from Google Authenticator to disable:</Text>
            <Group>
              <PinInput length={6} type="number" value={disableCode} onChange={setDisableCode} dir="ltr" />
              <Button color="red" onClick={handleDisable} loading={disableLoading} disabled={disableCode.length < 6}>Disable</Button>
              <Button variant="subtle" color="gray" onClick={() => { setShowDisable(false); setDisableCode('') }}>Cancel</Button>
            </Group>
          </Stack>
        )}
      </Paper>

      <Paper withBorder radius="md" p="lg">
        <Text fw={600} mb="sm">Recent Login History</Text>
        {!history || history.length === 0 ? (
          <Text size="sm" c="dimmed">No records</Text>
        ) : (
          <Table fz="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>IP</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Date</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {history.map((h, i) => (
                <Table.Tr key={i}>
                  <Table.Td style={{ fontFamily: 'monospace' }}>{h.ip_address}</Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={h.success ? 'green' : 'red'}>{h.success ? 'Success' : 'Failed'}</Badge>
                  </Table.Td>
                  <Table.Td>{new Date(h.created_at).toLocaleString()}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
    </Stack>
  )
}
