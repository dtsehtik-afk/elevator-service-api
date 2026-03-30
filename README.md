# Elevator Service API

REST API מלא לניהול שירות מעליות — 500 מעליות, עד 10 טכנאים.

## טכנולוגיה

| רכיב | טכנולוגיה |
|---|---|
| שפה | Python 3.11+ |
| Framework | FastAPI |
| DB | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Auth | JWT + bcrypt |
| Container | Docker + Compose |
| Tests | Pytest |

---

## הרצה מהירה עם Docker

```bash
# 1. העתק קובץ הגדרות
cp .env.example .env

# 2. ערוך SECRET_KEY ב-.env לערך ייחודי
# 3. הפעל
docker-compose up --build

# API יהיה זמין ב:
# http://localhost:8000/docs  — Swagger UI
# http://localhost:8000/redoc — ReDoc
```

---

## הרצה מקומית (ללא Docker)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# הגדר משתני סביבה (ראה .env.example)
export DATABASE_URL=postgresql://user:password@localhost:5432/elevator_db
export SECRET_KEY=my-secret-key

# הרץ Migrations
alembic upgrade head

# הפעל שרת
uvicorn app.main:app --reload
```

---

## מבנה הפרויקט

```
elevator-service-api/
├── app/
│   ├── main.py              # נקודת כניסה + middleware
│   ├── config.py            # הגדרות מסביבה
│   ├── database.py          # חיבור DB + session
│   ├── models/              # SQLAlchemy models
│   │   ├── elevator.py
│   │   ├── service_call.py
│   │   ├── technician.py
│   │   ├── assignment.py    # Assignment + AuditLog
│   │   └── maintenance.py
│   ├── schemas/             # Pydantic validation
│   ├── routers/             # API endpoints
│   ├── services/            # Business logic
│   │   ├── elevator_service.py
│   │   ├── service_call_service.py
│   │   ├── technician_service.py
│   │   ├── assignment_service.py   # Smart assignment (Haversine)
│   │   ├── schedule_service.py     # Daily schedule algorithm
│   │   ├── maintenance_service.py
│   │   ├── analytics_service.py
│   │   └── scheduler.py            # APScheduler background jobs
│   └── auth/
│       ├── security.py      # JWT + bcrypt
│       ├── dependencies.py  # FastAPI dependencies + RBAC
│       └── router.py        # /auth/login
├── migrations/              # Alembic
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_elevators.py
│   ├── test_service_calls.py
│   └── test_schedule.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## משתני סביבה (.env)

| משתנה | תיאור | ברירת מחדל |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:password@db:5432/elevator_db` |
| `SECRET_KEY` | מפתח סיוד JWT — **שנה בייצור!** | `changeme` |
| `ALGORITHM` | אלגוריתם JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | תפוגת טוקן | `30` |
| `CORS_ORIGINS` | דומיינים מורשים (פסיק) | `http://localhost:3000` |
| `REDIS_URL` | Redis connection | `redis://redis:6379` |

---

## Endpoints — תיאור מלא

### Authentication
| Method | Path | תיאור | Auth |
|---|---|---|---|
| POST | `/auth/login` | קבל JWT token | פומבי |

### Elevators
| Method | Path | תיאור | Role |
|---|---|---|---|
| GET | `/elevators` | רשימה + פילטרים | כל משתמש |
| POST | `/elevators` | הוסף מעלית | ADMIN/DISPATCHER |
| GET | `/elevators/{id}` | פרטים | כל משתמש |
| PUT | `/elevators/{id}` | עדכון | ADMIN/DISPATCHER |
| GET | `/elevators/{id}/analytics` | ניתוח תקלות | כל משתמש |
| GET | `/elevators/{id}/calls` | היסטוריית קריאות | כל משתמש |

### Service Calls
| Method | Path | תיאור | Role |
|---|---|---|---|
| GET | `/calls` | רשימה + פילטרים | כל משתמש |
| POST | `/calls` | פתח קריאה | כל משתמש |
| GET | `/calls/{id}` | פרטים | כל משתמש |
| PATCH | `/calls/{id}` | עדכון | בעל הקריאה / ADMIN |
| GET | `/calls/{id}/audit` | לוג שינויים | כל משתמש |
| POST | `/calls/{id}/assign` | שיבוץ ידני | ADMIN/DISPATCHER |
| POST | `/calls/{id}/auto-assign` | שיבוץ אוטומטי | ADMIN/DISPATCHER |

### Technicians
| Method | Path | תיאור | Role |
|---|---|---|---|
| GET | `/technicians` | רשימה | כל משתמש |
| POST | `/technicians` | יצירה | ADMIN |
| GET | `/technicians/{id}` | פרטים | כל משתמש |
| PUT | `/technicians/{id}` | עדכון | ADMIN / עצמי |
| POST | `/technicians/location` | עדכון מיקום | כל משתמש |
| GET | `/technicians/{id}/stats` | סטטיסטיקות | כל משתמש |
| GET | `/technicians/{id}/schedule` | לוז יומי | כל משתמש |

### Schedule
| Method | Path | תיאור | Role |
|---|---|---|---|
| GET | `/schedule/{technician_id}?date=YYYY-MM-DD` | לוז יומי מיטובי | כל משתמש |

### Maintenance
| Method | Path | תיאור | Role |
|---|---|---|---|
| GET | `/maintenance` | רשימה | כל משתמש |
| POST | `/maintenance` | תזמון | ADMIN/DISPATCHER |
| GET | `/maintenance/{id}` | פרטים | כל משתמש |
| PATCH | `/maintenance/{id}` | עדכון | ADMIN/DISPATCHER |

### Analytics (ADMIN only)
| Method | Path | תיאור |
|---|---|---|
| GET | `/analytics/recurring-faults` | מעליות עם 3+ תקלות ב-90 יום |
| GET | `/analytics/technician-performance` | ממוצע זמן טיפול לטכנאי |
| GET | `/analytics/monthly-summary?year=2024&month=1` | סיכום חודשי |
| GET | `/analytics/risk-elevators?threshold=70` | מעליות בסיכון גבוה |

---

## דוגמאות API

### Login
```bash
curl -X POST http://localhost:8000/auth/login \
  -F "username=admin@example.com" \
  -F "password=changeme123"
```

### Create Elevator
```bash
curl -X POST http://localhost:8000/elevators \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "address": "1 Rothschild Blvd",
    "city": "Tel Aviv",
    "floor_count": 15,
    "model": "Otis Gen2",
    "manufacturer": "Otis",
    "status": "ACTIVE"
  }'
```

### Open Service Call (Auto-detects recurring, auto-assigns CRITICAL)
```bash
curl -X POST http://localhost:8000/calls \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "elevator_id": "uuid-here",
    "reported_by": "Building Manager",
    "description": "Elevator stuck between floors 3 and 4",
    "priority": "CRITICAL",
    "fault_type": "STUCK"
  }'
```

### Get Daily Schedule
```bash
curl "http://localhost:8000/schedule/<technician-id>?date=2024-01-15" \
  -H "Authorization: Bearer <token>"
```

Response:
```json
{
  "technician": {"id": "...", "name": "Yossi Cohen", "email": "yossi@..."},
  "date": "2024-01-15",
  "total_stops": 4,
  "estimated_end_time": "16:30",
  "stops": [
    {
      "order": 1,
      "type": "SERVICE_CALL",
      "elevator": {"address": "1 Herzl St", "city": "Tel Aviv"},
      "priority": "CRITICAL",
      "fault_type": "STUCK",
      "estimated_arrival": "08:00",
      "estimated_duration_minutes": 30
    }
  ]
}
```

---

## הרצת בדיקות

```bash
# התקן תלויות
pip install -r requirements.txt

# הרץ את כל הבדיקות
pytest tests/ -v

# עם coverage
pytest tests/ -v --cov=app
```

---

## אבטחה

- **JWT** על כל endpoint מלבד `/health` ו-`/docs`
- **bcrypt** עם 12 salt rounds
- **RBAC**: ADMIN | TECHNICIAN | DISPATCHER
- **Rate Limiting**: 100 בקשות לדקה per IP (slowapi)
- **CORS**: רשימת domains מוגדרת ב-`.env`
- **SQL Injection**: SQLAlchemy parameterized queries בלבד
- **Audit Log**: כל שינוי סטטוס קריאה נרשם עם timestamp + user
- **Secrets**: כל הגדרות רגישות דרך environment variables בלבד

---

## אלגוריתם שיבוץ חכם

1. סנן טכנאים פעילים וזמינים עם פחות מ-`max_daily_calls` ביום
2. התאם `specialization` ל-`fault_type`
3. חשב מרחק גיאוגרפי (Haversine formula)
4. ציון משוקלל: **60% מרחק + 40% עומס**
5. בחר הטכנאי עם הציון הנמוך ביותר

## אלגוריתם לוז יומי

1. אסוף קריאות שירות + תחזוקות מתוכננות ליום
2. מיין לפי priority: CRITICAL → HIGH → MEDIUM → LOW
3. בתוך כל priority — Nearest Neighbor (גיאוגרפי)
4. הוסף 20 דקות נסיעה בין עצירות
5. הוסף זמן טיפול לפי `fault_type`
6. החזר רשימה עם `estimated_arrival` לכל עצירה
