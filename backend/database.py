"""SQLAlchemy database engine and session management (SQLite)."""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import ROOT_DIR, settings


def _resolve_db_url(raw_url: str) -> str:
    if raw_url.startswith("sqlite:///./"):
        rel = raw_url.replace("sqlite:///./", "")
        full_path = ROOT_DIR / rel
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{full_path}"
    if raw_url.startswith("sqlite:///"):
        p = Path(raw_url.replace("sqlite:///", ""))
        p.parent.mkdir(parents=True, exist_ok=True)
    return raw_url


DB_URL = _resolve_db_url(settings.database_url)
engine = create_engine(DB_URL, connect_args={"check_same_thread": False}, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
