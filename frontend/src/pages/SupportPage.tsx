import { useState } from 'react'
import {
  Stack, Title, Paper, Text, Group, Accordion, Textarea, TextInput,
  Button, Badge, SimpleGrid, Card, ThemeIcon, Anchor, Divider, Box,
} from '@mantine/core'
import { notifications } from '@mantine/notifications'

const FAQ_ITEMS = [
  {
    q: 'איך מוסיפים מעלית חדשה למערכת?',
    a: 'עוברים לעמוד "מעליות" → לוחצים על כפתור "הוסף מעלית" בפינה העליונה → ממלאים כתובת, עיר, ופרטי חוזה שירות.',
  },
  {
    q: 'איך פותחים קריאת שירות ידנית?',
    a: 'עמוד "קריאות שירות" → "קריאה חדשה". אפשר גם מעמוד פרטי מעלית. קריאות נכנסות מהטלפון מתקבלות אוטומטית דרך הווב-הוק.',
  },
  {
    q: 'איך משייכים קריאה ממתינה למעלית?',
    a: 'עמוד "קריאות ממתינות" → לוחצים על הקריאה → מחפשים מעלית בתיבת החיפוש → לוחצים "שייך". אפשר גם להוסיף מעלית חדשה מאותה חלון.',
  },
  {
    q: 'הסוכן לא מגיב בווצאפ — מה לעשות?',
    a: 'בדוק שה-Green API instance פעיל. עבור ל"סוכן ווצאפ" → בדוק שיש שיחות אחרונות. אם ה-instance לא מחובר יש לחבר מחדש דרך ממשק Green API.',
  },
  {
    q: 'איך מגדירים שעות עבודה?',
    a: 'עמוד "הגדרות" → "שעות עבודה". ניתן לכבות/להדליק ימים ולשנות שעות תחילה וסיום. השינוי נכנס לתוקף מיידית.',
  },
  {
    q: 'איך מייצאים דוח לאקסל?',
    a: 'עמוד "דוחות" → בוחרים ישות ועמודות → לוחצים "ייצוא Excel" בסרגל העליון. הקובץ מורד אוטומטית.',
  },
  {
    q: 'טכנאי לא מקבל הודעות ווצאפ — מה בודקים?',
    a: 'בדוק שמספר הווצאפ של הטכנאי מוגדר נכון (כולל קידומת 972). בדוק שה-Green API instance פעיל. בדוק את יומן האירועים בעמוד "ניהול מערכת".',
  },
  {
    q: 'איך מגדירים תדירות תחזוקה למעלית?',
    a: 'עמוד פרטי מעלית → לשונית "תחזוקה" → שדה "תדירות תחזוקה בשנה". ערכים: 2, 4, 6 (ברירת מחדל), או 12 פעמים בשנה.',
  },
]

interface SupportForm {
  subject: string
  description: string
  contact: string
}

export default function SupportPage() {
  const [form, setForm] = useState<SupportForm>({ subject: '', description: '', contact: '' })
  const [sending, setSending] = useState(false)

  async function handleSend() {
    if (!form.subject || !form.description) {
      notifications.show({ message: 'נא למלא נושא ותיאור', color: 'red' })
      return
    }
    setSending(true)
    try {
      // Opens email client with pre-filled support request
      const body = encodeURIComponent(
        `נושא: ${form.subject}\n\nתיאור:\n${form.description}\n\nיצירת קשר: ${form.contact || 'לא הוזן'}`
      )
      window.location.href = `mailto:dtsehtik@gmail.com?subject=${encodeURIComponent(`[Lift Agent Support] ${form.subject}`)}&body=${body}`
      setForm({ subject: '', description: '', contact: '' })
      notifications.show({ message: 'נפתח לקוח דוא"ל לשליחת הפנייה', color: 'green' })
    } finally {
      setSending(false)
    }
  }

  return (
    <Stack gap="lg" dir="rtl">
      <Group gap="xs">
        <Text size="2rem">🛠️</Text>
        <Title order={2}>מרכז תמיכה</Title>
      </Group>

      {/* Quick links */}
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        {[
          { icon: '📖', label: 'תיעוד מערכת', desc: 'מדריכי שימוש', href: null },
          { icon: '🐛', label: 'דיווח על באג', desc: 'משהו לא עובד?', href: null },
          { icon: '💡', label: 'בקשת פיצ׳ר', desc: 'רעיון לשיפור', href: null },
          { icon: '📞', label: 'יצירת קשר ישיר', desc: 'dtsehtik@gmail.com', href: 'mailto:dtsehtik@gmail.com' },
        ].map(item => (
          <Card
            key={item.label}
            withBorder
            radius="md"
            p="md"
            style={{ cursor: item.href ? 'pointer' : 'default' }}
            onClick={() => item.href && window.open(item.href)}
          >
            <Group gap="sm">
              <ThemeIcon size={40} radius="md" variant="light" color="blue">
                <Text size="xl">{item.icon}</Text>
              </ThemeIcon>
              <Stack gap={0}>
                <Text size="sm" fw={600}>{item.label}</Text>
                <Text size="xs" c="dimmed">{item.desc}</Text>
              </Stack>
            </Group>
          </Card>
        ))}
      </SimpleGrid>

      <Group align="flex-start" gap="lg" wrap="nowrap" style={{ alignItems: 'stretch' }}>
        {/* FAQ */}
        <Paper withBorder radius="md" p="md" style={{ flex: 1.5 }}>
          <Text fw={700} size="lg" mb="md">❓ שאלות נפוצות</Text>
          <Accordion variant="separated" chevronPosition="right">
            {FAQ_ITEMS.map((item, i) => (
              <Accordion.Item key={i} value={String(i)}>
                <Accordion.Control>
                  <Text size="sm" fw={500}>{item.q}</Text>
                </Accordion.Control>
                <Accordion.Panel>
                  <Text size="sm" c="dimmed" style={{ direction: 'rtl' }}>{item.a}</Text>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Paper>

        {/* Contact form */}
        <Paper withBorder radius="md" p="md" style={{ flex: 1, minWidth: 280 }}>
          <Text fw={700} size="lg" mb="xs">✉️ פתיחת פנייה</Text>
          <Text size="xs" c="dimmed" mb="md">
            הפנייה תישלח ל-<Anchor href="mailto:dtsehtik@gmail.com" size="xs">dtsehtik@gmail.com</Anchor>
          </Text>
          <Stack gap="sm">
            <TextInput
              label="נושא"
              placeholder="תיאור קצר של הבעיה"
              value={form.subject}
              onChange={e => setForm(p => ({ ...p, subject: e.target.value }))}
              required
            />
            <Textarea
              label="תיאור מפורט"
              placeholder="פרט מה קרה, מה ניסית לעשות, ומה הציפייה שלך..."
              rows={5}
              value={form.description}
              onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
              required
            />
            <TextInput
              label="טלפון / ווצאפ ליצירת קשר (אופציונלי)"
              placeholder="050-0000000"
              value={form.contact}
              onChange={e => setForm(p => ({ ...p, contact: e.target.value }))}
            />
            <Button onClick={handleSend} loading={sending} fullWidth>
              שלח פנייה
            </Button>
          </Stack>

          <Divider my="md" />

          <Box>
            <Text size="xs" fw={600} mb="xs">⚙️ גישת מנהל מערכת</Text>
            <Text size="xs" c="dimmed" mb="xs">לוגים ומידע טכני מפורט:</Text>
            <Button
              variant="light"
              size="xs"
              fullWidth
              onClick={() => window.open('/admin-console', '_self')}
            >
              פתח Admin Console
            </Button>
          </Box>
        </Paper>
      </Group>
    </Stack>
  )
}
