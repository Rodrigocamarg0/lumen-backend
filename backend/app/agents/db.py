"""
Shared PostgresDb singleton for all Agno agents.
Agno auto-creates the `lumen_sessions` table on first use.
"""

from __future__ import annotations

from agno.db.postgres import PostgresDb

from app.config import settings

_db: PostgresDb | None = None


def get_db() -> PostgresDb:
    global _db
    if _db is None:
        _db = PostgresDb(
            db_url=settings.DATABASE_URL,
            session_table="lumen_sessions",
            memory_table="lumen_memories",
            metrics_table="lumen_metrics",
            eval_table="lumen_evals",
        )
    return _db
