from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from .settings import get_database_url


metadata = MetaData()

sessions_table = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True),
    Column("model", String, nullable=False),
    Column("tool_version", String, nullable=False),
    Column("system_prompt_suffix", Text, nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
    Column("updated_at", DateTime(timezone=False), nullable=False),
)

messages_table = Table(
    "messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("session_id", String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    Column("role", String, nullable=False),
    Column("content", JSON, nullable=False),
    Column("created_at", DateTime(timezone=False), nullable=False),
)

Index("idx_messages_session", messages_table.c.session_id, messages_table.c.created_at)


async_engine: AsyncEngine | None = None
AsyncSessionLocal: sessionmaker | None = None


async def init_engine() -> None:
    global async_engine, AsyncSessionLocal
    if async_engine is not None:
        return
    url = get_database_url()
    async_engine = create_async_engine(url, future=True, echo=False)
    AsyncSessionLocal = sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    # Create tables
    async with async_engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def create_session(session_id: str, model: str, tool_version: str, system_suffix: str) -> None:
    assert AsyncSessionLocal is not None
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        await session.execute(
            sessions_table.insert().values(
                id=session_id,
                model=model,
                tool_version=tool_version,
                system_prompt_suffix=system_suffix,
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()


async def upsert_message(message_id: str, session_id: str, role: str, content: dict) -> None:
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        await session.execute(
            messages_table.insert().values(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                created_at=datetime.utcnow(),
            )
        )
        await session.execute(
            update(sessions_table)
            .where(sessions_table.c.id == session_id)
            .values(updated_at=datetime.utcnow())
        )
        await session.commit()


async def list_sessions() -> Iterable[dict]:
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(
                sessions_table.c.id,
                sessions_table.c.model,
                sessions_table.c.created_at,
                sessions_table.c.updated_at,
            ).order_by(sessions_table.c.updated_at.desc())
        )
        return [dict(r._mapping) for r in res]


async def get_session(session_id: str) -> dict | None:
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(sessions_table).where(sessions_table.c.id == session_id)
        )
        row = res.first()
        return dict(row._mapping) if row else None


async def get_messages(session_id: str) -> list[dict]:
    assert AsyncSessionLocal is not None
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(messages_table).where(messages_table.c.session_id == session_id).order_by(messages_table.c.created_at.asc())
        )
        return [dict(r._mapping) for r in res]


