/**
 * AIRefineButton — adds "refine with AI" + voice input to any textarea.
 *
 * Text mode: takes current value → POST /ai/refine-text → replaces with formal Hebrew
 * Voice mode: Web Speech API → transcription → POST /ai/refine-text → replaces value
 *
 * Usage:
 *   <AIRefineButton value={notes} onChange={setNotes} />
 */

import { useState, useCallback } from 'react'
import { ActionIcon, Group, Tooltip, Loader } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface AIRefineButtonProps {
  value: string
  onChange: (value: string) => void
  size?: 'sm' | 'md'
}

export function AIRefineButton({ value, onChange, size = 'sm' }: AIRefineButtonProps) {
  const [refining, setRefining] = useState(false)
  const [listening, setListening] = useState(false)

  const refine = useCallback(async (text: string) => {
    if (!text.trim()) {
      notifications.show({ message: 'אין טקסט לעיבוד', color: 'orange' })
      return
    }
    setRefining(true)
    try {
      const { data } = await client.post<{ refined: string }>('/ai/refine-text', { text })
      onChange(data.refined)
      notifications.show({ message: '✨ הטקסט עובד בהצלחה', color: 'teal' })
    } catch {
      notifications.show({ message: 'שגיאה בעיבוד AI — נסה שוב', color: 'red' })
    } finally {
      setRefining(false)
    }
  }, [onChange])

  const startVoice = useCallback(() => {
    const SR = (window as any).webkitSpeechRecognition || (window as any).SpeechRecognition
    if (!SR) {
      notifications.show({ message: 'הדפדפן לא תומך בתמלול קולי', color: 'orange' })
      return
    }
    const r = new SR()
    r.lang = 'he-IL'
    r.continuous = false
    r.interimResults = false
    r.onstart = () => setListening(true)
    r.onend = () => setListening(false)
    r.onerror = () => {
      setListening(false)
      notifications.show({ message: 'שגיאה בזיהוי קול', color: 'red' })
    }
    r.onresult = (e: any) => {
      const transcript: string = e.results[0][0].transcript
      refine(transcript)
    }
    r.start()
  }, [refine])

  const iconSize = size === 'sm' ? 12 : 16

  return (
    <Group gap={4}>
      <Tooltip label="שפר עם AI (עברית מקצועית)" position="top">
        <ActionIcon
          size={size}
          variant="light"
          color="violet"
          onClick={() => refine(value)}
          disabled={refining || listening}
          aria-label="שפר טקסט עם AI"
        >
          {refining ? <Loader size={iconSize} /> : <>✨</>}
        </ActionIcon>
      </Tooltip>
      <Tooltip label={listening ? 'מאזין... דבר עכשיו' : 'הקלט קול ושפר עם AI'} position="top">
        <ActionIcon
          size={size}
          variant={listening ? 'filled' : 'light'}
          color={listening ? 'red' : 'blue'}
          onClick={startVoice}
          disabled={refining || listening}
          aria-label="הקלט קול ושפר"
        >
          {listening ? <>🔴</> : <>🎤</>}
        </ActionIcon>
      </Tooltip>
    </Group>
  )
}
