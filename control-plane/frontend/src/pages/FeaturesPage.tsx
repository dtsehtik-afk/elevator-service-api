import { useState } from 'react'
import { Title, Paper, Group, Text, Badge, Stack, Collapse, SimpleGrid } from '@mantine/core'

interface FeatureNode {
  label: string
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
          { label: 'שיוך לבניין, לקוח וחברת ניהול' },
          { label: 'היסטוריית קריאות ותחזוקה' },
          { label: 'ניקוד סיכון אוטומטי (risk score)' },
          { label: 'קואורדינטות GPS מכתובת' },
          { label: 'ייבוא נתונים מ-Excel / PDF', badge: 'ייבוא', badgeColor: 'teal' },
        ],
      },
      {
        label: 'בניינים וחברות ניהול', icon: '🏗️',
        children: [
          { label: 'ניהול נכסים ובניינים' },
          { label: 'חברות ניהול ואנשי קשר' },
          { label: 'שיוך טלפונים לניתוב קריאות' },
        ],
      },
    ],
  },
  {
    label: 'קריאות שירות', icon: '🔧', badge: 'ליבה', badgeColor: 'blue',
    children: [
      {
        label: 'מקורות קריאה', icon: '📥',
        children: [
          { label: 'פתיחה ידנית מהפורטל' },
          { label: 'מאימייל (beepertalk)', badge: 'אוטומטי', badgeColor: 'teal' },
          { label: 'מ-WhatsApp (מנהל)', badge: 'WhatsApp', badgeColor: 'green' },
          { label: 'מדוח ביקורת (ליקוי חמור)', badge: 'אוטומטי', badgeColor: 'teal' },
          { label: 'מתזמון תחזוקה מתקרב', badge: 'אוטומטי', badgeColor: 'teal' },
        ],
      },
      {
        label: 'מחזור חיים', icon: '🔄',
        children: [
          { label: 'OPEN → ASSIGNED → IN_PROGRESS → RESOLVED → CLOSED' },
          { label: 'עדיפות: CRITICAL / HIGH / MEDIUM / LOW' },
          { label: 'סוגי תקלה: תקיעה, דלת, חשמל, מכני, תוכנה, תחזוקה' },
          { label: 'רישום אירועים (Audit Log)' },
        ],
      },
      {
        label: 'שיוך טכנאי', icon: '👷',
        children: [
          { label: 'ניתוב AI חכם לפי מיקום, עומס, התמחות', badge: 'AI', badgeColor: 'violet' },
          { label: 'שידור לכל הטכנאים המתאימים (Broadcast)' },
          { label: 'מודל ראשון שעונה לוקח — מענה "1"' },
          { label: 'טיפול בדחייה — העברה למועמד הבא' },
          { label: 'שיוך ידני ע"י מנהל' },
          { label: 'הזרקת הקשר: ביקורות פתוחות + תחזוקה קרובה' },
        ],
      },
    ],
  },
  {
    label: 'ניהול טכנאים', icon: '👷', badge: 'ליבה', badgeColor: 'blue',
    children: [
      { label: 'פרופיל: שם, טלפון, WhatsApp, אימייל' },
      { label: 'התמחויות ואזורי עבודה' },
      { label: 'מצב: פעיל / זמין / כוננות' },
      { label: 'GPS בזמן אמת (מיקום חי)', badge: 'GPS', badgeColor: 'orange' },
      { label: 'מגבלת קריאות יומית (max_daily_calls)' },
      { label: 'מעקב עומס עבודה' },
      {
        label: 'אפליקציית טכנאי', icon: '📱', badge: 'Mobile', badgeColor: 'orange',
        children: [
          { label: 'פורטל ייעודי ללא login (URL עם tech_id)' },
          { label: 'פרטי קריאה פעילה + כתובת + ניווט' },
          { label: 'עדכון מיקום GPS' },
          { label: 'השלמת קריאה עם הקלטה קולית' },
          { label: 'תמלול קולי אוטומטי (Whisper)', badge: 'AI', badgeColor: 'violet' },
          { label: 'רשימת תחזוקה וביקורות למעלית' },
        ],
      },
    ],
  },
  {
    label: 'AI ועיבוד חכם', icon: '🤖', badge: 'AI', badgeColor: 'violet',
    children: [
      {
        label: 'Google Gemini (ראשי)', icon: '✨',
        children: [
          { label: 'סוכן שאלות ותשובות בעברית ב-WhatsApp', badge: 'Chat', badgeColor: 'grape' },
          { label: 'פרשנות פקודות מנהל (WhatsApp)', badge: 'NLP', badgeColor: 'violet' },
          { label: 'ניתוח דוחות ביקורת PDF/תמונה (Gemini Vision)' },
          { label: 'סיווג קריאות נכנסות מאימייל' },
        ],
      },
      {
        label: 'Anthropic Claude (גיבוי)', icon: '🛡️',
        children: [
          { label: 'Fallback כשGemini לא זמין' },
        ],
      },
      {
        label: 'OpenAI Whisper', icon: '🎙️',
        children: [
          { label: 'תמלול הודעות קוליות מWhatsApp' },
          { label: 'שפה: עברית' },
        ],
      },
      {
        label: 'ניתוב חכם', icon: '🧭',
        children: [
          { label: 'ניקוד טכנאים: מרחק, עומס, התמחות, עדיפות' },
          { label: 'קריאה CRITICAL — 75% משקל למרחק' },
          { label: 'קריאה LOW — 40% משקל למרחק' },
        ],
      },
    ],
  },
  {
    label: 'אינטגרציות', icon: '🔌', badge: 'מודולרי', badgeColor: 'grape',
    children: [
      {
        label: 'WhatsApp (Green API)', icon: '💬', badge: 'מודול', badgeColor: 'green',
        children: [
          { label: 'שליחת משימות לטכנאים' },
          { label: 'אישור/דחיית קריאה' },
          { label: 'התראות תחזוקה דחופה' },
          { label: 'פקודות מנהל (סגור, שייך, דוחות)' },
          { label: 'צ\'אט חופשי עברית עם סוכן AI' },
          { label: 'תזכורות GPS לטכנאים' },
        ],
      },
      {
        label: 'Gmail / IMAP', icon: '📧', badge: 'מודול', badgeColor: 'red',
        children: [
          { label: 'פולינג קריאות שירות מ-beepertalk' },
          { label: 'זיהוי מעלית לפי כתובת + טלפון (fuzzy match)' },
          { label: 'פולינג דוחות ביקורת מהמייל' },
          { label: 'שליחת דוחות ביקורת ללקוח' },
        ],
      },
      {
        label: 'מיפוי (Nominatim/OSM)', icon: '🗺️', badge: 'מודול', badgeColor: 'blue',
        children: [
          { label: 'גיאוקודינג כתובות → GPS (חינמי)' },
          { label: 'חישוב זמן נסיעה (Haversine)' },
          { label: 'ניווט לטכנאים לשטח' },
          { label: '47 ערים עם קואורדינטות מובנות' },
        ],
      },
      {
        label: 'Google Drive', icon: '💾', badge: 'מודול', badgeColor: 'yellow',
        children: [
          { label: 'העלאת דוחות ביקורת אוטומטית' },
          { label: 'יצירת תיקיות לפי שנה ומעלית' },
          { label: 'סריקת קבצים חדשים (כל 15 דקות)' },
          { label: 'לינקים לצפייה ציבורית' },
        ],
      },
      {
        label: 'Make.com (Webhook)', icon: '⚡', badge: 'אוטומציה', badgeColor: 'teal',
        children: [
          { label: 'קבלת אימיילים ועיבוד ליצירת קריאות' },
        ],
      },
    ],
  },
  {
    label: 'תחזוקה וביקורות', icon: '🔍', badge: 'מודולרי', badgeColor: 'grape',
    children: [
      {
        label: 'תחזוקה מתוזמנת', icon: '📅',
        children: [
          { label: '15+ ימים לפני — LOW (שקט)' },
          { label: '10+ ימים לפני — MEDIUM (שקט)' },
          { label: '5+ ימים לפני — HIGH + התראה WhatsApp' },
          { label: 'באיחור — CRITICAL + דחוף WhatsApp (פעם אחת)' },
          { label: 'ריצה אוטומטית כל לילה' },
        ],
      },
      {
        label: 'ביקורות', icon: '📋',
        children: [
          { label: 'העלאת דוח PDF/תמונה' },
          { label: 'ניתוח Gemini Vision — ליקויים, תוצאה, תאריך' },
          { label: 'מעקב ליקויים: OPEN / PARTIAL / CLOSED' },
          { label: 'פתיחת קריאה אוטומטית לליקוי חמור' },
          { label: 'שמירה ב-Google Drive' },
          { label: 'שיוך טכנאי לטיפול' },
        ],
      },
    ],
  },
  {
    label: 'אנליטיקס ודוחות', icon: '📊',
    children: [
      { label: 'מעליות עם תקלות חוזרות (3+ קריאות ב-90 יום)' },
      { label: 'ביצועי טכנאים — זמן תגובה, יעילות' },
      { label: 'סיכום חודשי — קריאות, פתרונות, סטטיסטיקות' },
      { label: 'זיהוי מעליות בסיכון גבוה' },
      { label: 'היסטוריית קריאות לכל מעלית' },
      { label: 'ייצוא Excel עם כל המטה-דאטה' },
    ],
  },
  {
    label: 'SaaS Control Plane', icon: '☁️', badge: 'מנהל מערכת', badgeColor: 'dark',
    children: [
      {
        label: 'ניהול דיירים', icon: '🏢',
        children: [
          { label: 'יצירת לקוח + API key אוטומטי' },
          { label: 'סטטוסים: PENDING → DEPLOYING → ACTIVE' },
          { label: 'תוכניות: TRIAL / BASIC / PRO / ENTERPRISE' },
        ],
      },
      {
        label: '1-Click Deploy', icon: '🚀', badge: 'אוטומטי', badgeColor: 'teal',
        children: [
          { label: 'יצירת VPS על Hetzner Cloud' },
          { label: 'התקנת Docker + האפליקציה' },
          { label: 'DNS אוטומטי (Cloudflare) — subdomain.lift-agent.com' },
          { label: 'SSL אוטומטי (Let\'s Encrypt / certbot)' },
        ],
      },
      {
        label: 'ניטור בריאות', icon: '📡',
        children: [
          { label: 'פולינג כל 5 דקות לכל דייר' },
          { label: 'היסטוריית snapshots' },
          { label: 'סטטיסטיקות בזמן אמת (מעליות, קריאות, טכנאים, uptime)' },
        ],
      },
      {
        label: 'מודולים', icon: '🔧',
        children: [
          { label: 'הפעלה/כיבוי לכל לקוח בנפרד' },
          { label: 'WhatsApp, Gmail, Maps, Drive, OpenAI, תזכורות' },
          { label: 'סנכרון בזמן אמת לשרת הלקוח' },
        ],
      },
      {
        label: 'חיוב (Stripe)', icon: '💳', badge: 'Stripe', badgeColor: 'indigo',
        children: [
          { label: 'מנויים חודשיים אוטומטיים' },
          { label: 'שדרוג/שנמוג תוכנית עם חיוב יחסי' },
          { label: 'ניהול אמצעי תשלום' },
        ],
      },
    ],
  },
]

function FeatureTree({ nodes, depth = 0 }: { nodes: FeatureNode[]; depth?: number }) {
  return (
    <Stack gap={2} pl={depth > 0 ? 16 : 0}>
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
          padding: '3px 6px',
          borderRadius: 6,
          background: depth === 0 ? 'var(--mantine-color-dark-6)' : undefined,
        }}
        onClick={() => hasChildren && setOpen((o) => !o)}
      >
        <Text size="xs" c="dimmed" style={{ userSelect: 'none', width: 10, flexShrink: 0 }}>
          {hasChildren ? (open ? '▾' : '▸') : '•'}
        </Text>
        {node.icon && <Text size="sm">{node.icon}</Text>}
        <Text size="sm" fw={depth <= 1 ? 600 : 400} style={{ flex: 1 }}>
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
          <div style={{ borderRight: '2px solid var(--mantine-color-dark-4)', marginTop: 2, marginBottom: 2 }}>
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
          <Text size="sm" c="dimmed">לחץ על קטגוריה להרחבה / כיווץ</Text>
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
