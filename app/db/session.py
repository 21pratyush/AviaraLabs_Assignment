from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL,pool_pre_ping=True,echo=False,future=True)

SessionLocal = sessionmaker(bind=engine,autoflush=False,autocommit=False)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
