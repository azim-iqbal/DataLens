import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime

os.makedirs("data", exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/datalens.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class AuditHistory(Base):
    __tablename__ = "audit_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    filename = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    compliance_status = Column(String)  # Compliant / Non-Compliant
    clause_count = Column(Integer)

Base.metadata.create_all(bind=engine)

with engine.begin() as connection:
    columns = connection.execute(text("PRAGMA table_info(audit_history)")).fetchall()
    existing_column_names = {row[1] for row in columns}
    if "session_id" not in existing_column_names:
        connection.execute(text("ALTER TABLE audit_history ADD COLUMN session_id VARCHAR"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
