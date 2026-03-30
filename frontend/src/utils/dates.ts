import dayjs from 'dayjs'
import 'dayjs/locale/he'

dayjs.locale('he')

export function formatDate(d: string | null | undefined): string {
  if (!d) return '—'
  return dayjs(d).format('DD/MM/YYYY')
}

export function formatDateTime(d: string | null | undefined): string {
  if (!d) return '—'
  return dayjs(d).format('DD/MM/YYYY HH:mm')
}

export function isOverdue(d: string | null | undefined): boolean {
  if (!d) return false
  return dayjs(d).isBefore(dayjs(), 'day')
}

export function isSoon(d: string | null | undefined, days = 14): boolean {
  if (!d) return false
  const diff = dayjs(d).diff(dayjs(), 'day')
  return diff >= 0 && diff <= days
}
