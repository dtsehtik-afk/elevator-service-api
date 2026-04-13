import { MantineColor } from '@mantine/core'

export const PRIORITY_LABELS: Record<string, string> = {
  CRITICAL: 'קריטי',
  HIGH: 'גבוה',
  MEDIUM: 'בינוני',
  LOW: 'נמוך',
}

export const PRIORITY_COLORS: Record<string, MantineColor> = {
  CRITICAL: 'red',
  HIGH: 'orange',
  MEDIUM: 'yellow',
  LOW: 'green',
}

export const CALL_STATUS_LABELS: Record<string, string> = {
  OPEN: 'פתוחה',
  ASSIGNED: 'שובצה',
  IN_PROGRESS: 'בטיפול',
  RESOLVED: 'נפתרה',
  CLOSED: 'סגורה',
  MONITORING: 'במעקב',
}

export const CALL_STATUS_COLORS: Record<string, MantineColor> = {
  OPEN: 'red',
  ASSIGNED: 'orange',
  IN_PROGRESS: 'blue',
  RESOLVED: 'green',
  CLOSED: 'gray',
  MONITORING: 'teal',
}

export const ELEVATOR_STATUS_LABELS: Record<string, string> = {
  ACTIVE: 'פעילה',
  INACTIVE: 'לא פעילה',
  UNDER_REPAIR: 'בתיקון',
}

export const ELEVATOR_STATUS_COLORS: Record<string, MantineColor> = {
  ACTIVE: 'green',
  INACTIVE: 'gray',
  UNDER_REPAIR: 'orange',
}

export const FAULT_TYPE_LABELS: Record<string, string> = {
  MECHANICAL: 'מכאני',
  ELECTRICAL: 'חשמלי',
  SOFTWARE: 'תוכנה',
  STUCK: 'תקועה',
  DOOR: 'דלת',
  OTHER: 'אחר',
}

export const MAINTENANCE_TYPE_LABELS: Record<string, string> = {
  ROUTINE: 'שגרתי',
  INSPECTION: 'בדיקה',
  EMERGENCY: 'חירום',
  ANNUAL: 'שנתי',
}

export const MAINTENANCE_STATUS_LABELS: Record<string, string> = {
  SCHEDULED: 'מתוזמן',
  IN_PROGRESS: 'בביצוע',
  COMPLETED: 'הושלם',
  CANCELLED: 'בוטל',
}

export const MAINTENANCE_STATUS_COLORS: Record<string, MantineColor> = {
  SCHEDULED: 'blue',
  IN_PROGRESS: 'orange',
  COMPLETED: 'green',
  CANCELLED: 'gray',
}
