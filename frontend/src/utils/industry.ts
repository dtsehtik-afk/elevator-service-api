export const INDUSTRY_OPTIONS = [
  { value: 'elevators',   label: 'מעליות',       icon: '🛗' },
  { value: 'renovations', label: 'שיפוצים',      icon: '🔨' },
  { value: 'electrical',  label: 'חשמל',         icon: '⚡' },
  { value: 'plumbing',    label: 'אינסטלציה',    icon: '🚰' },
  { value: 'hvac',        label: 'מיזוג אוויר',  icon: '❄️' },
  { value: 'cleaning',    label: 'ניקיון',       icon: '🧹' },
  { value: 'security',    label: 'אבטחה',        icon: '🔒' },
  { value: 'landscaping', label: 'גינון',        icon: '🌿' },
  { value: 'other',       label: 'אחר',          icon: '🔧' },
]

export const INDUSTRY_ICON: Record<string, string> = Object.fromEntries(
  INDUSTRY_OPTIONS.map(o => [o.value, o.icon])
)

export function industryIcon(industry?: string | null, fallback = '⚡'): string {
  return (industry && INDUSTRY_ICON[industry]) ?? fallback
}
