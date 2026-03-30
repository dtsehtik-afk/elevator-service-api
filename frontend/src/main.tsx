import React from 'react'
import ReactDOM from 'react-dom/client'
import { MantineProvider, createTheme, DirectionProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { ModalsProvider } from '@mantine/modals'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import '@mantine/dates/styles.css'
import App from './App'

document.documentElement.setAttribute('dir', 'rtl')
document.documentElement.setAttribute('lang', 'he')

const theme = createTheme({
  fontFamily: 'Heebo, Arial, sans-serif',
  primaryColor: 'blue',
  defaultRadius: 'md',
  components: {
    Table: { defaultProps: { highlightOnHover: true, withTableBorder: true, withColumnBorders: false } },
  },
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <DirectionProvider initialDirection="rtl">
      <MantineProvider theme={theme}>
        <ModalsProvider>
          <Notifications position="top-right" />
          <QueryClientProvider client={queryClient}>
            <App />
          </QueryClientProvider>
        </ModalsProvider>
      </MantineProvider>
    </DirectionProvider>
  </React.StrictMode>
)
