# פקודות שרת — Lift Agent

## דיפלוי

### אפליקציה ראשית
```bash
~/deploy.sh
```

### אדמין קונסול (backend בלבד)
```bash
~/deploy-admin.sh
```

---

## לוגים

### אפליקציה ראשית
```bash
sudo docker compose logs app -f
```

### אדמין קונסול backend
```bash
sudo docker compose -f ~/elevator-service-api/lift-agent-admin-docker-compose.yml logs backend -f
```

### שגיאות אחרונות בלבד (50 שורות)
```bash
sudo docker compose logs app --tail=50
```

---

## סטטוס שירותים

```bash
sudo docker compose ps
```

### בדוק שהכל רץ
```bash
sudo docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

---

## הפעלה מחדש

### רק ה-app (ללא build)
```bash
sudo docker compose restart app
```

### כל השירותים
```bash
sudo docker compose down && sudo docker compose up -d
```

---

## DB

### כניסה ל-psql
```bash
sudo docker compose exec db psql -U user -d elevator_db
```

### גיבוי
```bash
sudo docker compose exec db pg_dump -U user elevator_db > ~/backup_$(date +%Y%m%d).sql
```

---

## קבצים בשרת

| קובץ | תיאור |
|------|--------|
| `~/deploy.sh` | דיפלוי אפליקציה ראשית |
| `~/deploy-admin.sh` | דיפלוי אדמין קונסול |
| `~/elevator-service-api/.env` | משתני סביבה |
| `~/elevator-service-api/nginx/conf.d/` | הגדרות Nginx |

---

## SSH לשרת

```bash
ssh dtsehtik@lift-agent.com
```
