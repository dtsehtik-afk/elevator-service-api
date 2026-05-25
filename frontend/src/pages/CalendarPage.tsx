import React, { useState, useEffect } from 'react';
import { Title, Container, Paper, Box, Group, Badge, Text, ActionIcon, Button, Modal, Stack } from '@mantine/core';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import timeGridPlugin from '@fullcalendar/timegrid';
import interactionPlugin from '@fullcalendar/interaction';
import { useNavigate } from 'react-router-dom';
import { IconExternalLink, IconCalendarEvent } from '@tabler/icons-react';
import client from '../api/client';

// Map our backend types to FullCalendar colors
const TYPE_COLORS: Record<string, string> = {
  maintenance: '#40c057', // green
  inspection: '#fd7e14',  // orange
  finance: '#228be6',     // blue
  contract: '#7950f2',    // purple
  service_call: '#fa5252', // red
  meeting: '#fab005',     // yellow
};

const TYPE_LABELS: Record<string, string> = {
  maintenance: 'תחזוקה מתוכננת',
  inspection: 'בדיקת מהנדס',
  finance: 'כספים',
  contract: 'חוזה',
  service_call: 'קריאת שירות',
  meeting: 'פגישה / ליד',
};

export default function CalendarPage() {
  const navigate = useNavigate();
  const [events, setEvents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);

  useEffect(() => {
    fetchEvents();
  }, []);

  const fetchEvents = async () => {
    setLoading(true);
    try {
      // Fetch -1 month to +2 months roughly
      const d = new Date();
      const start = new Date(d.getFullYear(), d.getMonth() - 1, 1).toISOString().split('T')[0];
      const end = new Date(d.getFullYear(), d.getMonth() + 3, 0).toISOString().split('T')[0];
      
      const res = await client.get(`/api/v1/calendar/events?start=${start}&end=${end}`);
      const mapped = res.data.events.map((e: any) => ({
        id: e.id,
        title: e.title,
        start: e.date,
        allDay: e.allDay,
        extendedProps: {
          type: e.type,
          url: e.url,
          status: e.status
        },
        backgroundColor: TYPE_COLORS[e.type] || '#868e96',
        borderColor: TYPE_COLORS[e.type] || '#868e96',
      }));
      setEvents(mapped);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleEventClick = (info: any) => {
    setSelectedEvent(info.event);
  };

  return (
    <Container size="xl" py="md" style={{ display: 'flex', flexDirection: 'column', height: '100vh', paddingBottom: '30px' }}>
      <Group justify="space-between" mb="md">
        <Title order={2}>יומן מרכזי</Title>
        <Button 
          variant="light" 
          leftSection={<IconCalendarEvent size={18} />}
          component="a"
          href="/api/v1/calendar/feed.ics?token=lift1234"
          target="_blank"
        >
          סנכרון יומן חיצוני (Google/Apple)
        </Button>
      </Group>

      <Paper withBorder shadow="sm" p="md" radius="md" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <Box style={{ flexGrow: 1, minHeight: 0, overflow: 'auto' }}>
          <FullCalendar
            plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            locale="he"
            direction="rtl"
            headerToolbar={{
              right: 'prev,next today',
              center: 'title',
              left: 'dayGridMonth,timeGridWeek,timeGridDay'
            }}
            events={events}
            eventClick={handleEventClick}
            height="100%"
            dayMaxEvents={3}
          />
        </Box>
      </Paper>

      {/* Quick Legend */}
      <Group mt="md" justify="center">
        {Object.entries(TYPE_LABELS).map(([key, label]) => (
          <Badge key={key} color={TYPE_COLORS[key]} variant="light" size="lg">
            {label}
          </Badge>
        ))}
      </Group>

      {/* Modal for event details */}
      <Modal 
        opened={!!selectedEvent} 
        onClose={() => setSelectedEvent(null)} 
        title={selectedEvent?.title}
        centered
      >
        {selectedEvent && (
          <Stack>
            <Group justify="space-between">
              <Text fw={500}>סוג אירוע:</Text>
              <Badge color={TYPE_COLORS[selectedEvent.extendedProps.type]}>
                {TYPE_LABELS[selectedEvent.extendedProps.type]}
              </Badge>
            </Group>
            <Group justify="space-between">
              <Text fw={500}>תאריך:</Text>
              <Text>{selectedEvent.start?.toLocaleDateString('he-IL')}</Text>
            </Group>
            {selectedEvent.extendedProps.status && (
              <Group justify="space-between">
                <Text fw={500}>סטטוס / רמת דחיפות:</Text>
                <Text>{selectedEvent.extendedProps.status}</Text>
              </Group>
            )}
            <Button 
              fullWidth 
              mt="md" 
              rightSection={<IconExternalLink size={18} />}
              onClick={() => {
                navigate(selectedEvent.extendedProps.url);
                setSelectedEvent(null);
              }}
            >
              מעבר לדף הרלוונטי
            </Button>
          </Stack>
        )}
      </Modal>
    </Container>
  );
}
