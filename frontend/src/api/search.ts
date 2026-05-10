import client from './client'

export interface SearchResult {
  id: string
  type: 'elevator' | 'customer' | 'call' | 'technician'
  title: string
  subtitle: string
  url: string
}

export const searchApi = {
  search: (q: string) =>
    client.get<SearchResult[]>('/search', { params: { q } }).then(r => r.data),
}
