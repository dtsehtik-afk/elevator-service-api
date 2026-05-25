from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.technician import Technician
import os

db_url = os.environ.get("DATABASE_URL", "postgresql://admin:password@db:5432/lift_agent_db")
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)
session = Session()

techs = session.query(Technician).all()
for t in techs:
    print(f"Name: {t.name}")
    print(f"Phone: {t.phone}")
    print(f"Coords: {t.current_latitude}, {t.current_longitude}")
    print(f"Base Coords: {t.base_latitude}, {t.base_longitude}")
    print(f"Last updated: {t.last_location_at}")
    print(f"Active: {t.is_active}, Available: {t.is_available}")
    print("---")
