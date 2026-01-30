from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.api.db import get_engine


async def _insert_event(
    engine: AsyncEngine,
    export_job_id: UUID,
    event_type: str,
    message: Optional[str] = None,
    progress: Optional[Decimal] = None,
) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO export_job_events (export_job_id, event_type, message, progress)
                VALUES (:export_job_id, :event_type, :message, :progress)
                """
            ),
            {
                "export_job_id": export_job_id,
                "event_type": event_type,
                "message": message,
                "progress": progress,
            },
        )


async def _update_job(
    engine: AsyncEngine,
    export_job_id: UUID,
    *,
    status: Optional[str] = None,
    progress: Optional[Decimal] = None,
    output_uri: Optional[str] = None,
    error_message: Optional[str] = None,
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    fields = []
    params = {"id": export_job_id}
    if status is not None:
        fields.append("status = :status")
        params["status"] = status
    if progress is not None:
        fields.append("progress = :progress")
        params["progress"] = progress
    if output_uri is not None:
        fields.append("output_uri = :output_uri")
        params["output_uri"] = output_uri
    if error_message is not None:
        fields.append("error_message = :error_message")
        params["error_message"] = error_message
    if started_at is not None:
        fields.append("started_at = :started_at")
        params["started_at"] = started_at
    if finished_at is not None:
        fields.append("finished_at = :finished_at")
        params["finished_at"] = finished_at

    if not fields:
        return

    async with engine.begin() as conn:
        await conn.execute(
            text(f"UPDATE export_jobs SET {', '.join(fields)} WHERE id = :id"),
            params,
        )


# PUBLIC_INTERFACE
async def run_export_job_stub(export_job_id: UUID) -> None:
    """Background export stub.

    This simulates an export pipeline:
    - status: queued -> running -> succeeded
    - progress: increments periodically
    - writes export_job_events records along the way

    Args:
        export_job_id: The export job UUID.

    Returns:
        None
    """
    engine = get_engine()
    now = datetime.now(timezone.utc)
    await _update_job(engine, export_job_id, status="queued", progress=Decimal("0.00"))
    await _insert_event(engine, export_job_id, "queued", "Export queued.", Decimal("0.00"))

    await asyncio.sleep(0.2)
    await _update_job(engine, export_job_id, status="running", started_at=now, progress=Decimal("0.00"))
    await _insert_event(engine, export_job_id, "started", "Export started.", Decimal("0.00"))

    for pct in (Decimal("10.00"), Decimal("25.00"), Decimal("50.00"), Decimal("75.00"), Decimal("100.00")):
        await asyncio.sleep(0.25)
        await _update_job(engine, export_job_id, progress=pct)
        await _insert_event(engine, export_job_id, "progress", f"Progress {pct}%", pct)

    finished = datetime.now(timezone.utc)
    output_uri = f"exports/{export_job_id}.mp4"  # stub path; real implementation would be a signed URL or storage URI.
    await _update_job(
        engine,
        export_job_id,
        status="succeeded",
        progress=Decimal("100.00"),
        output_uri=output_uri,
        finished_at=finished,
    )
    await _insert_event(engine, export_job_id, "completed", "Export completed.", Decimal("100.00"))
