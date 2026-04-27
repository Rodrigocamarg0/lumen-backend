from __future__ import annotations

from collections.abc import Generator
import logging

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False, expire_on_commit=False)

# Lightweight migrations for columns added after initial table creation.
# create_all() only creates NEW tables; it cannot ALTER existing ones.
# Format: (SQL with IF NOT EXISTS so each entry is idempotent)
_COLUMN_MIGRATIONS: list[str] = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_accepted_version VARCHAR(32)",
]


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        SessionLocal.configure(bind=engine)
    return engine


def init_db() -> None:
    import app.models.conversation  # noqa: F401

    eng = get_engine()
    Base.metadata.create_all(bind=eng)

    with eng.begin() as conn:
        for sql in _COLUMN_MIGRATIONS:
            try:
                conn.execute(text(sql))
            except Exception:
                logger.warning("Migration skipped (may already exist): %s", sql)


def get_db_session() -> Generator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
