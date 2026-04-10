import { Accordion, Badge, Center, Loader, Paper, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { listConversations, WhatsAppMessage } from '../api/conversations'
import { formatDate } from '../utils/dates'

function MessageBubble({ msg }: { msg: WhatsAppMessage }) {
  const isIncoming = msg.direction === 'in'
  const isAudio = msg.msg_type === 'audioMessage'

  return (
    <Paper
      p="xs"
      radius="md"
      withBorder={false}
      style={{
        alignSelf: isIncoming ? 'flex-end' : 'flex-start',
        maxWidth: '75%',
        background: isIncoming ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-gray-2)',
      }}
    >
      {isAudio ? (
        <Stack gap={2}>
          <Text size="sm" c={isIncoming ? 'white' : 'dark'}>🎤 הודעה קולית</Text>
          {msg.transcription && (
            <Text size="xs" c={isIncoming ? 'blue.1' : 'dimmed'} fs="italic">
              {msg.transcription}
            </Text>
          )}
        </Stack>
      ) : (
        <Text size="sm" c={isIncoming ? 'white' : 'dark'}>{msg.text ?? ''}</Text>
      )}
      <Text size="xs" c={isIncoming ? 'blue.1' : 'dimmed'} ta="right" mt={2}>
        {formatDate(msg.timestamp)}
      </Text>
    </Paper>
  )
}

export default function ConversationsPage() {
  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ['conversations'],
    queryFn: listConversations,
  })

  if (isLoading) {
    return <Center h={300}><Loader /></Center>
  }

  return (
    <Stack gap="lg">
      <Title order={2}>💬 שיחות WhatsApp</Title>

      {conversations.length === 0 ? (
        <Center h={200}><Text c="dimmed">אין שיחות להצגה</Text></Center>
      ) : (
        <Accordion variant="separated" radius="md">
          {conversations.map((conv) => {
            const displayName = conv.technician_name ?? conv.phone
            const lastMsg = conv.messages[conv.messages.length - 1]
            return (
              <Accordion.Item key={conv.phone} value={conv.phone}>
                <Accordion.Control>
                  <Stack gap={2}>
                    <Text fw={600}>{displayName}</Text>
                    <Text size="xs" c="dimmed" dir="ltr">{conv.phone}</Text>
                    {lastMsg && (
                      <Text size="xs" c="dimmed" lineClamp={1}>
                        {lastMsg.msg_type === 'audioMessage'
                          ? '🎤 הודעה קולית'
                          : (lastMsg.text ?? '')}
                      </Text>
                    )}
                  </Stack>
                  <Badge size="sm" color="blue" ml="xs">{conv.messages.length}</Badge>
                </Accordion.Control>
                <Accordion.Panel>
                  <Stack gap="xs" style={{ display: 'flex', flexDirection: 'column' }}>
                    {conv.messages.map((msg) => (
                      <MessageBubble key={msg.id} msg={msg} />
                    ))}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            )
          })}
        </Accordion>
      )}
    </Stack>
  )
}
