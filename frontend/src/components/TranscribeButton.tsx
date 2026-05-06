/**
 * TranscribeButton — microphone icon that records audio and returns transcribed Hebrew text.
 * Usage: <TranscribeButton onResult={text => setMyField(text)} />
 */
import { useState, useRef } from 'react'
import { ActionIcon, Tooltip, Loader } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import client from '../api/client'

interface Props {
  onResult: (text: string) => void
  size?: 'xs' | 'sm' | 'md' | 'lg'
  color?: string
}

export default function TranscribeButton({ onResult, size = 'sm', color = 'blue' }: Props) {
  const [recording, setRecording] = useState(false)
  const [loading, setLoading] = useState(false)
  const mediaRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mr = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      chunksRef.current = []
      mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setLoading(true)
        try {
          const fd = new FormData()
          fd.append('file', blob, 'recording.webm')
          const { data } = await client.post('/transcribe', fd, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          if (data.text) onResult(data.text)
        } catch {
          notifications.show({ message: 'שגיאה בתמלול — נסה שוב', color: 'red' })
        } finally {
          setLoading(false)
        }
      }
      mr.start()
      mediaRef.current = mr
      setRecording(true)
    } catch {
      notifications.show({ message: 'לא ניתן לגשת למיקרופון', color: 'red' })
    }
  }

  function stopRecording() {
    mediaRef.current?.stop()
    mediaRef.current = null
    setRecording(false)
  }

  if (loading) return <Loader size="xs" />

  return (
    <Tooltip label={recording ? 'לחץ לעצירה' : 'הקלט קול'} withArrow>
      <ActionIcon
        size={size}
        color={recording ? 'red' : color}
        variant={recording ? 'filled' : 'subtle'}
        onClick={recording ? stopRecording : startRecording}
        style={recording ? { animation: 'pulse 1s infinite' } : undefined}
      >
        🎤
      </ActionIcon>
    </Tooltip>
  )
}
