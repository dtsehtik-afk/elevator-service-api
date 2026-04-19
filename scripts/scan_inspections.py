from app.database import SessionLocal
from app.services.inspection_email_poller import poll_inspection_emails
from datetime import date, timedelta

db = SessionLocal()
r = poll_inspection_emails(db, since_date=date.today() - timedelta(days=90))
print(f"דוחות שעובדו: {r}")
db.close()
