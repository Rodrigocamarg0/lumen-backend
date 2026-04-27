from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


engine: Engine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False, expire_on_commit=False)


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
        SessionLocal.configure(bind=engine)
    return engine


def init_db() -> None:
    import app.models.conversation  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def get_db_session() -> Generator[Session]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
