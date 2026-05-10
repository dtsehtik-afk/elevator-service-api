import client from './client'

export const aiApi = {
  refineText: (text: string) =>
    client.post<{ refined: string }>('/ai/refine-text', { text }).then(r => r.data),
}
