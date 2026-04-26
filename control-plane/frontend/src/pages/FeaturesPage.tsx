import { useState } from 'react'
import { Title, Paper, Group, Text, Badge, Stack, Collapse, ActionIcon, SimpleGrid, ThemeIcon } from '@mantine/core'

interface FeatureNode {
  label: string
  description?: string
  badge?: string
  badgeColor?: string
  children?: FeatureNode[]
  icon?: string
}

const FEATURES: FeatureNode[] = [
  {
    label: 'ניהול נכסים', icon: '🏢', badge: 'ליבה', badgeColor: 'blue',
    children: [
      {
        label: 'מעליות', icon: '🛗',
        children: [
          { label: 'רישום מעלית עם פרטים מלאים' },
          { label: 'סטטוס פעיל / לא פעיל' },
          { label: 'שיוך לבניין ולקוח' },
          { label: 'היסטוריית תחזוקה וקריאות' },
          { label: 'מיקום גיאוגרפי (Google Maps)' },
        ],
      },
      {
        label: 'בניינים', icon: '🏗️',
        children: [
          { label: 'ניהול נכסים ובניינים' },
          { label: 'שיוך מעליות לבניין' },
          { label: 'פרטי כתובת ואיש קשר' },
        ],
      },
      {
        label: 'אנשי קשר', icon: '👤',
        children: [
          { label: 'ניהול לקוחות ואנשי קשר' },
          { label: 'שיוך לנכסים ומעליות' },
        ],
      },
    ],
  },
  {
    label: 'קריאות שירות', icon: '🔧', badge: 'ליבה', badgeColor: 'blue',
    children: [
      {
        label: 'מחזור חיים של קריאה', icon: '🔄',
        children: [
          { label: 'פתיחה → שיוך → בתהליך → הושלם', badge: 'אוטומטי', badgeColor: 'teal' },
          { label: 'עדיפות וחומרה' },
          { label: 'תיאור וצרופות' },
          { label: 'היסטוריית שינויים' },
        ],
      },
      {
        label: 'שיוך טכנאי', icon: '👷',
        children: [
          { label: 'ניתוב חכם מבוסס AI', badge: 'AI', badgeColor: 'violet' },
          { label: 'התחשבות בזמינות ומיקום' },
          { label: 'שיוך ידני או אוטומטי' },
        ],
      },
      {
        label: 'קריאות דחופות', icon: '🚨',
        children: [
          { label: 'זיהוי קריאות לילה/שבת' },
          { label: 'התראות WhatsApp מיידיות', badge: 'WhatsApp', badgeColor: 'green' },
          { label: 'טיפול בכוננות' },
        ],
      },
    ],
  },
  {
    label: 'ניהול טכנאים', icon: '👷', badge: 'ליבה', badgeColor: 'blue',
    children: [
      { label: 'פרופיל טכנאי — מיומנויות ואזור' },
      { label: 'ניהול זמינות וכוננות' },
      { label: 'מעקב עומס עבודה' },
      { label: 'דירוג לפי קירבה וביצועים' },
      { label: 'אפליקציית טכנאי ייעודית', badge: 'Mobile', badgeColor: 'orange' },
    ],
  },
  {
    label: 'אינטגרציות', icon: '🔌', badge: 'מודולרי', badgeColor: 'grape',
    children: [
      {
        label: 'WhatsApp (Green API)', icon: '💬', badge: 'מודול', badgeColor: 'green',
        children: [
          { label: 'פתיחת קריאות מWhatsApp' },
          { label: 'עדכון סטטוס בזמן אמת' },
          { label: 'תזכורות ביקורת אוטומטיות' },
          { label: 'התראות לטכנאים' },
        ],
      },
      {
        label: 'Gmail', icon: '📧', badge: 'מודול', badgeColor: 'red',
        children: [
          { label: 'קריאות שירות מאימייל אוטומטית' },
          { label: 'עיבוד AI לסיווג הקריאה', badge: 'AI', badgeColor: 'violet' },
          { label: 'שליחת דוחות ביקורת' },
        ],
      },
      {
        label: 'Google Maps', icon: '🗺️', badge: 'מודול', badgeColor: 'blue',
        children: [
          { label: 'ניווט לטכנאים לשטח' },
          { label: 'ניתוב לפי מרחק' },
          { label: 'תצוגת מפה של מעליות' },
        ],
      },
      {
        label: 'Google Drive', icon: '💾', badge: 'מודול', badgeColor: 'yellow',
        children: [
          { label: 'שמירת דוחות ביקורת אוטומטית' },
          { label: 'ארכיון מסמכים' },
        ],
      },
      {
        label: 'OpenAI', icon: '🤖', badge: 'מודול', badgeColor: 'violet',
        children: [
          { label: 'תמלול הקלטות קוליות' },
          { label: 'עיבוד וסיכום קריאות' },
        ],
      },
    ],
  },
  {
    label: 'ביקורות', icon: '🔍', badge: 'מודולרי', badgeColor: 'grape',
    children: [
      { label: 'תזמון ביקורות תקופתיות' },
      { label: 'רשימת תיוג לביקורת' },
      { label: 'דוחות ביקורת דיגיטליים' },
      { label: 'שליחה אוטומטית ללקוח', badge: 'אוטומטי', badgeColor: 'teal' },
      { label: 'ארכיון היסטוריית ביקורות' },
    ],
  },
  {
    label: 'אנליטיקס ודוחות', icon: '📊',
    children: [
      { label: 'כמות קריאות לפי תקופה' },
      { label: 'זמני תגובה וסיום' },
      { label: 'ביצועי טכנאים' },
      { label: 'מעליות עם הכי הרבה תקלות' },
      { label: 'עלויות תחזוקה' },
    ],
  },
  {
    label: 'SaaS Platform', icon: '☁️', badge: 'Control Plane', badgeColor: 'dark',
    children: [
      {
        label: 'ניהול דיירים', icon: '🏢',
        children: [
          { label: 'יצירת לקוח חדש בלחיצה' },
          { label: '1-Click Deploy על Hetzner', badge: 'אוטומטי', badgeColor: 'teal' },
          { label: 'DNS אוטומטי (Cloudflare)' },
          { label: 'SSL אוטומטי (Let\'s Encrypt)' },
        ],
      },
      {
        label: 'ניטור בריאות', icon: '📡',
        children: [
          { label: 'בדיקת זמינות כל 5 דקות' },
          { label: 'היסטוריית polls' },
          { label: 'סטטיסטיקות בזמן אמת' },
        ],
      },
      {
        label: 'מודולים', icon: '🔧',
        children: [
          { label: 'הפעלה/כיבוי מודולים לכל לקוח' },
          { label: 'WhatsApp, Gmail, Maps, Drive, OpenAI' },
        ],
      },
      {
        label: 'חיוב', icon: '💳',
        children: [
          { label: 'תוכניות: Trial / Basic / Pro / Enterprise' },
          { label: 'חיוב אוטומטי (Stripe)', badge: 'Stripe', badgeColor: 'indigo' },
          { label: 'ניהול מנויים' },
        ],
      },
    ],
  },
]

function FeatureTree({ nodes, depth = 0 }: { nodes: FeatureNode[]; depth?: number }) {
  return (
    <Stack gap={4} pl={depth > 0 ? 20 : 0}>
      {nodes.map((node, i) => (
        <FeatureItem key={i} node={node} depth={depth} />
      ))}
    </Stack>
  )
}

function FeatureItem({ node, depth }: { node: FeatureNode; depth: number }) {
  const [open, setOpen] = useState(depth === 0)
  const hasChildren = node.children && node.children.length > 0

  return (
    <div>
      <Group
        gap={6}
        style={{
          cursor: hasChildren ? 'pointer' : 'default',
          padding: '4px 8px',
          borderRadius: 6,
          background: depth === 0 ? 'var(--mantine-color-dark-6)' : undefined,
        }}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >
        {hasChildren && (
          <Text size="xs" c="dimmed" style={{ userSelect: 'none', width: 12 }}>
            {open ? '▾' : '▸'}
          </Text>
        )}
        {!hasChildren && <Text size="xs" c="dimmed" style={{ width: 12 }}>•</Text>}
        {node.icon && <Text size={depth === 0 ? 'md' : 'sm'}>{node.icon}</Text>}
        <Text size={depth === 0 ? 'sm' : 'sm'} fw={depth === 0 ? 600 : 400}>
          {node.label}
        </Text>
        {node.badge && (
          <Badge size="xs" color={node.badgeColor ?? 'gray'} variant="light">
            {node.badge}
          </Badge>
        )}
      </Group>

      {hasChildren && (
        <Collapse in={open}>
          <div style={{ borderRight: '2px solid var(--mantine-color-dark-4)', marginRight: 0, paddingRight: 0, marginTop: 2, marginBottom: 2 }}>
            <FeatureTree nodes={node.children!} depth={depth + 1} />
          </div>
        </Collapse>
      )}
    </div>
  )
}

export default function FeaturesPage() {
  return (
    <>
      <Group justify="space-between" mb="md">
        <div>
          <Title order={3}>🗺️ מפת יכולות המערכת</Title>
          <Text size="sm" c="dimmed">לחץ על קטגוריה להרחבה</Text>
        </div>
        <Badge size="lg" variant="dot" color="green">Lift-Agent v1.0</Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">
        {FEATURES.map((f, i) => (
          <Paper key={i} withBorder p="md" radius="md">
            <FeatureItem node={f} depth={0} />
          </Paper>
        ))}
      </SimpleGrid>
    </>
  )
}
