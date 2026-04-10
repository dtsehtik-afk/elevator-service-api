import client from './client'

export interface WhatsAppMessage {
  id: string
  direction: 'in' | 'out'
  msg_type: string
  text: string | null
  transcription: string | null
  timestamp: string
}

export interface Conversation {
  phone: string
  technician_name: string | null
  messages: WhatsAppMessage[]
}

export async function listConversations(): Promise<Conversation[]> {
  const { data } = await client.get<Conversation[]>('/conversations')
  return data
}
