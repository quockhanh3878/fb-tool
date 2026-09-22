"""Bounded, database-backed leases shared by all browser entry points."""
from contextlib import asynccontextmanager
from contextvars import ContextVar
import asyncio
from datetime import timedelta

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import get_session_factory
from app.models.base import new_uuid, utcnow
from app.models.operations import ResourceLease


class LeaseBusy(RuntimeError):
    pass


_held = ContextVar("browser_leases", default=())


@asynccontextmanager
async def resource_lease(resource: str):
    identity = (resource, id(asyncio.current_task()))
    if identity in _held.get():
        yield
        return
    owner = new_uuid()
    expires = utcnow() + timedelta(seconds=get_settings().job_lease_seconds)
    async with get_session_factory()() as db:
        result = await db.execute(update(ResourceLease).where(
            ResourceLease.resource == resource, ResourceLease.expires_at <= utcnow(),
        ).values(owner=owner, expires_at=expires))
        if result.rowcount != 1:
            db.add(ResourceLease(resource=resource, owner=owner, expires_at=expires))
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                raise LeaseBusy("Browser resource is busy") from None
        await db.commit()
    context_token = _held.set((*_held.get(), identity))
    try:
        yield
    finally:
        _held.reset(context_token)
        async with get_session_factory()() as db:
            await db.execute(delete(ResourceLease).where(
                ResourceLease.resource == resource, ResourceLease.owner == owner,
            ))
            await db.commit()