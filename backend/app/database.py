from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import get_settings

class Base(DeclarativeBase):
    pass

def build_engine():
    url = get_settings().database_url
    if not url:
        return None
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)

engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) if engine else None

def get_db():
    if SessionLocal is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Database is not configured. Set DATABASE_URL in backend/.env.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
