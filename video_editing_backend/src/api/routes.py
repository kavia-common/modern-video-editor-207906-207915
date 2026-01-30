from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.db import get_db_session
from src.api.exporter import run_export_job_stub
from src.api.schemas import (
    APIMessage,
    ClipTrim,
    ClipTrimCreate,
    ExportJob,
    ExportJobCreate,
    ExportJobEvent,
    ExportJobWithEvents,
    MediaAsset,
    MediaAssetCreate,
    Project,
    ProjectCreate,
    ProjectUpdate,
    TimelineClip,
    TimelineClipCreate,
    TimelineClipUpdate,
    TimelineTrack,
    TimelineTrackCreate,
    TimelineTrackUpdate,
    Transition,
    TransitionCreate,
    TransitionUpdate,
)
from src.api.settings import get_settings

router = APIRouter(prefix="/api", tags=["video-editor"])


def _row_to_dict(row: Any) -> Dict[str, Any]:
    """Convert SQLAlchemy Row to dict."""
    return dict(row._mapping)  # type: ignore[attr-defined]


async def _fetch_one(session: AsyncSession, stmt: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    res = await session.execute(text(stmt), params)
    row = res.fetchone()
    return _row_to_dict(row) if row else None


async def _fetch_all(session: AsyncSession, stmt: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    res = await session.execute(text(stmt), params)
    return [_row_to_dict(r) for r in res.fetchall()]


# -----------------------
# Health + Docs helpers
# -----------------------
@router.get("/health", response_model=APIMessage, summary="Health check", description="Basic health check.")
async def api_health() -> APIMessage:
    return APIMessage(message="Healthy")


@router.get(
    "/docs/websockets",
    response_model=APIMessage,
    summary="WebSocket usage note",
    description="This backend does not expose WebSocket endpoints in this iteration; export status is available via polling export job endpoints.",
)
async def websocket_usage_note() -> APIMessage:
    return APIMessage(message="No WebSocket endpoints. Poll /api/exports/{job_id} or /api/exports/{job_id}/events for status.")


# -----------------------
# Projects CRUD
# -----------------------
@router.post(
    "/projects",
    response_model=Project,
    summary="Create project",
    description="Create a new video editing project.",
)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_db_session)) -> Project:
    try:
        row = await _fetch_one(
            session,
            """
            INSERT INTO projects (name, description, width, height, fps)
            VALUES (:name, :description, :width, :height, :fps)
            RETURNING id, name, description, width, height, fps, duration_ms, created_at, updated_at
            """,
            payload.model_dump(),
        )
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {str(e.orig)}") from e

    assert row is not None
    return Project(**row)


@router.get(
    "/projects",
    response_model=List[Project],
    summary="List projects",
    description="List projects ordered by updated_at descending.",
)
async def list_projects(session: AsyncSession = Depends(get_db_session)) -> List[Project]:
    rows = await _fetch_all(
        session,
        """
        SELECT id, name, description, width, height, fps, duration_ms, created_at, updated_at
        FROM projects
        ORDER BY updated_at DESC
        """,
        {},
    )
    return [Project(**r) for r in rows]


@router.get(
    "/projects/{project_id}",
    response_model=Project,
    summary="Get project",
    description="Fetch a single project by id.",
)
async def get_project(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> Project:
    row = await _fetch_one(
        session,
        """
        SELECT id, name, description, width, height, fps, duration_ms, created_at, updated_at
        FROM projects
        WHERE id = :id
        """,
        {"id": project_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return Project(**row)


@router.patch(
    "/projects/{project_id}",
    response_model=Project,
    summary="Update project",
    description="Patch project fields.",
)
async def update_project(project_id: UUID, payload: ProjectUpdate, session: AsyncSession = Depends(get_db_session)) -> Project:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        return await get_project(project_id, session)

    set_sql = ", ".join([f"{k} = :{k}" for k in data.keys()])
    data["id"] = project_id

    row = await _fetch_one(
        session,
        f"""
        UPDATE projects
        SET {set_sql}
        WHERE id = :id
        RETURNING id, name, description, width, height, fps, duration_ms, created_at, updated_at
        """,
        data,
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Project not found")
    await session.commit()
    return Project(**row)


@router.delete(
    "/projects/{project_id}",
    response_model=APIMessage,
    summary="Delete project",
    description="Delete a project and all related records (cascade).",
)
async def delete_project(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> APIMessage:
    res = await session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Project not found")
    await session.commit()
    return APIMessage(message="Deleted")


# -----------------------
# Media assets
# -----------------------
@router.post(
    "/media",
    response_model=MediaAsset,
    summary="Register media asset",
    description="Register a media asset by providing source_uri and metadata (no file upload).",
)
async def register_media(payload: MediaAssetCreate, session: AsyncSession = Depends(get_db_session)) -> MediaAsset:
    row = await _fetch_one(
        session,
        """
        INSERT INTO media_assets (
            project_id, kind, source_uri, original_filename, mime_type, size_bytes,
            duration_ms, width, height, fps, has_audio, metadata
        )
        VALUES (
            :project_id, :kind, :source_uri, :original_filename, :mime_type, :size_bytes,
            :duration_ms, :width, :height, :fps, :has_audio, :metadata::jsonb
        )
        RETURNING
            id, project_id, kind, source_uri, original_filename, mime_type, size_bytes,
            duration_ms, width, height, fps, has_audio, metadata, created_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create media asset")
    await session.commit()
    return MediaAsset(**row)


@router.get(
    "/projects/{project_id}/media",
    response_model=List[MediaAsset],
    summary="List project media assets",
    description="List all media assets registered for a project.",
)
async def list_project_media(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[MediaAsset]:
    rows = await _fetch_all(
        session,
        """
        SELECT
            id, project_id, kind, source_uri, original_filename, mime_type, size_bytes,
            duration_ms, width, height, fps, has_audio, metadata, created_at
        FROM media_assets
        WHERE project_id = :project_id
        ORDER BY created_at DESC
        """,
        {"project_id": project_id},
    )
    return [MediaAsset(**r) for r in rows]


@router.post(
    "/projects/{project_id}/media/upload",
    response_model=MediaAsset,
    summary="Upload media file",
    description="Upload a file and create a media_assets record. This stores to local disk (uploads/) as a stub.",
)
async def upload_media_file(
    project_id: UUID,
    kind: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> MediaAsset:
    settings = get_settings()
    upload_root = Path(settings.upload_dir)
    upload_root.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "").suffix
    asset_id = uuid4()
    dest = upload_root / f"{asset_id}{ext}"

    content = await file.read()
    dest.write_bytes(content)

    mime_type = file.content_type
    size_bytes = len(content)
    source_uri = f"{settings.upload_dir}/{dest.name}"

    payload = MediaAssetCreate(
        project_id=project_id,
        kind=kind,  # validated by DB check constraint; frontend should send video/audio/image.
        source_uri=source_uri,
        original_filename=file.filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        duration_ms=None,
        width=None,
        height=None,
        fps=None,
        has_audio=False,
        metadata={"uploaded": True},
    )

    row = await _fetch_one(
        session,
        """
        INSERT INTO media_assets (
            id, project_id, kind, source_uri, original_filename, mime_type, size_bytes,
            duration_ms, width, height, fps, has_audio, metadata
        )
        VALUES (
            :id, :project_id, :kind, :source_uri, :original_filename, :mime_type, :size_bytes,
            :duration_ms, :width, :height, :fps, :has_audio, :metadata::jsonb
        )
        RETURNING
            id, project_id, kind, source_uri, original_filename, mime_type, size_bytes,
            duration_ms, width, height, fps, has_audio, metadata, created_at
        """,
        {**payload.model_dump(), "id": asset_id},
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create uploaded media asset")
    await session.commit()
    return MediaAsset(**row)


# -----------------------
# Timeline tracks
# -----------------------
@router.post(
    "/tracks",
    response_model=TimelineTrack,
    summary="Create timeline track",
    description="Create a track for a project.",
)
async def create_track(payload: TimelineTrackCreate, session: AsyncSession = Depends(get_db_session)) -> TimelineTrack:
    row = await _fetch_one(
        session,
        """
        INSERT INTO timeline_tracks (project_id, track_type, name, sort_order, muted, locked)
        VALUES (:project_id, :track_type, :name, :sort_order, :muted, :locked)
        RETURNING id, project_id, track_type, name, sort_order, muted, locked, created_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create track")
    await session.commit()
    return TimelineTrack(**row)


@router.get(
    "/projects/{project_id}/tracks",
    response_model=List[TimelineTrack],
    summary="List tracks",
    description="List tracks in a project.",
)
async def list_tracks(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[TimelineTrack]:
    rows = await _fetch_all(
        session,
        """
        SELECT id, project_id, track_type, name, sort_order, muted, locked, created_at
        FROM timeline_tracks
        WHERE project_id = :project_id
        ORDER BY sort_order ASC, created_at ASC
        """,
        {"project_id": project_id},
    )
    return [TimelineTrack(**r) for r in rows]


@router.patch(
    "/tracks/{track_id}",
    response_model=TimelineTrack,
    summary="Update track",
    description="Patch track fields.",
)
async def update_track(track_id: UUID, payload: TimelineTrackUpdate, session: AsyncSession = Depends(get_db_session)) -> TimelineTrack:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        row = await _fetch_one(
            session,
            """
            SELECT id, project_id, track_type, name, sort_order, muted, locked, created_at
            FROM timeline_tracks WHERE id = :id
            """,
            {"id": track_id},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Track not found")
        return TimelineTrack(**row)

    set_sql = ", ".join([f"{k} = :{k}" for k in data.keys()])
    data["id"] = track_id

    row = await _fetch_one(
        session,
        f"""
        UPDATE timeline_tracks
        SET {set_sql}
        WHERE id = :id
        RETURNING id, project_id, track_type, name, sort_order, muted, locked, created_at
        """,
        data,
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Track not found")
    await session.commit()
    return TimelineTrack(**row)


@router.delete(
    "/tracks/{track_id}",
    response_model=APIMessage,
    summary="Delete track",
    description="Delete a track (clips/transitions cascade).",
)
async def delete_track(track_id: UUID, session: AsyncSession = Depends(get_db_session)) -> APIMessage:
    res = await session.execute(text("DELETE FROM timeline_tracks WHERE id = :id"), {"id": track_id})
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Track not found")
    await session.commit()
    return APIMessage(message="Deleted")


# -----------------------
# Timeline clips
# -----------------------
@router.post(
    "/clips",
    response_model=TimelineClip,
    summary="Create clip",
    description="Create a timeline clip on a track.",
)
async def create_clip(payload: TimelineClipCreate, session: AsyncSession = Depends(get_db_session)) -> TimelineClip:
    row = await _fetch_one(
        session,
        """
        INSERT INTO timeline_clips (
            project_id, track_id, media_asset_id, clip_type, name,
            start_ms, end_ms, in_ms, out_ms, speed, opacity, volume, transform
        )
        VALUES (
            :project_id, :track_id, :media_asset_id, :clip_type, :name,
            :start_ms, :end_ms, :in_ms, :out_ms, :speed, :opacity, :volume, :transform::jsonb
        )
        RETURNING
            id, project_id, track_id, media_asset_id, clip_type, name,
            start_ms, end_ms, in_ms, out_ms, speed, opacity, volume, transform, created_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create clip")
    await session.commit()
    return TimelineClip(**row)


@router.get(
    "/projects/{project_id}/clips",
    response_model=List[TimelineClip],
    summary="List clips",
    description="List clips in a project ordered by start time.",
)
async def list_clips(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[TimelineClip]:
    rows = await _fetch_all(
        session,
        """
        SELECT
            id, project_id, track_id, media_asset_id, clip_type, name,
            start_ms, end_ms, in_ms, out_ms, speed, opacity, volume, transform, created_at
        FROM timeline_clips
        WHERE project_id = :project_id
        ORDER BY start_ms ASC, created_at ASC
        """,
        {"project_id": project_id},
    )
    return [TimelineClip(**r) for r in rows]


@router.patch(
    "/clips/{clip_id}",
    response_model=TimelineClip,
    summary="Update clip",
    description="Patch clip fields (move, trim, transform, etc.).",
)
async def update_clip(clip_id: UUID, payload: TimelineClipUpdate, session: AsyncSession = Depends(get_db_session)) -> TimelineClip:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        row = await _fetch_one(
            session,
            """
            SELECT
                id, project_id, track_id, media_asset_id, clip_type, name,
                start_ms, end_ms, in_ms, out_ms, speed, opacity, volume, transform, created_at
            FROM timeline_clips WHERE id = :id
            """,
            {"id": clip_id},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Clip not found")
        return TimelineClip(**row)

    if "transform" in data:
        # Keep jsonb cast explicit
        data["transform"] = data["transform"]

    set_parts = []
    for k in data.keys():
        if k == "transform":
            set_parts.append("transform = :transform::jsonb")
        else:
            set_parts.append(f"{k} = :{k}")
    set_sql = ", ".join(set_parts)
    data["id"] = clip_id

    row = await _fetch_one(
        session,
        f"""
        UPDATE timeline_clips
        SET {set_sql}
        WHERE id = :id
        RETURNING
            id, project_id, track_id, media_asset_id, clip_type, name,
            start_ms, end_ms, in_ms, out_ms, speed, opacity, volume, transform, created_at
        """,
        data,
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Clip not found")
    await session.commit()
    return TimelineClip(**row)


@router.delete(
    "/clips/{clip_id}",
    response_model=APIMessage,
    summary="Delete clip",
    description="Delete a clip (trims/transitions cascade).",
)
async def delete_clip(clip_id: UUID, session: AsyncSession = Depends(get_db_session)) -> APIMessage:
    res = await session.execute(text("DELETE FROM timeline_clips WHERE id = :id"), {"id": clip_id})
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Clip not found")
    await session.commit()
    return APIMessage(message="Deleted")


# -----------------------
# Trims
# -----------------------
@router.post(
    "/trims",
    response_model=ClipTrim,
    summary="Create clip trim",
    description="Create a trim record for a clip.",
)
async def create_trim(payload: ClipTrimCreate, session: AsyncSession = Depends(get_db_session)) -> ClipTrim:
    row = await _fetch_one(
        session,
        """
        INSERT INTO clip_trims (clip_id, kind, trim_in_ms, trim_out_ms)
        VALUES (:clip_id, :kind, :trim_in_ms, :trim_out_ms)
        RETURNING id, clip_id, kind, trim_in_ms, trim_out_ms, created_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create trim")
    await session.commit()
    return ClipTrim(**row)


@router.get(
    "/clips/{clip_id}/trims",
    response_model=List[ClipTrim],
    summary="List clip trims",
    description="List trim records for a clip.",
)
async def list_trims(clip_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[ClipTrim]:
    rows = await _fetch_all(
        session,
        """
        SELECT id, clip_id, kind, trim_in_ms, trim_out_ms, created_at
        FROM clip_trims
        WHERE clip_id = :clip_id
        ORDER BY created_at ASC
        """,
        {"clip_id": clip_id},
    )
    return [ClipTrim(**r) for r in rows]


@router.delete(
    "/trims/{trim_id}",
    response_model=APIMessage,
    summary="Delete trim",
    description="Delete a trim record.",
)
async def delete_trim(trim_id: UUID, session: AsyncSession = Depends(get_db_session)) -> APIMessage:
    res = await session.execute(text("DELETE FROM clip_trims WHERE id = :id"), {"id": trim_id})
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Trim not found")
    await session.commit()
    return APIMessage(message="Deleted")


# -----------------------
# Transitions
# -----------------------
@router.post(
    "/transitions",
    response_model=Transition,
    summary="Create transition",
    description="Create a transition between two clips on a track.",
)
async def create_transition(payload: TransitionCreate, session: AsyncSession = Depends(get_db_session)) -> Transition:
    row = await _fetch_one(
        session,
        """
        INSERT INTO transitions (
            project_id, track_id, from_clip_id, to_clip_id,
            transition_type, duration_ms, easing, params
        )
        VALUES (
            :project_id, :track_id, :from_clip_id, :to_clip_id,
            :transition_type, :duration_ms, :easing, :params::jsonb
        )
        RETURNING
            id, project_id, track_id, from_clip_id, to_clip_id,
            transition_type, duration_ms, easing, params, created_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create transition")
    await session.commit()
    return Transition(**row)


@router.get(
    "/projects/{project_id}/transitions",
    response_model=List[Transition],
    summary="List transitions",
    description="List transitions for a project.",
)
async def list_transitions(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[Transition]:
    rows = await _fetch_all(
        session,
        """
        SELECT
            id, project_id, track_id, from_clip_id, to_clip_id,
            transition_type, duration_ms, easing, params, created_at
        FROM transitions
        WHERE project_id = :project_id
        ORDER BY created_at ASC
        """,
        {"project_id": project_id},
    )
    return [Transition(**r) for r in rows]


@router.patch(
    "/transitions/{transition_id}",
    response_model=Transition,
    summary="Update transition",
    description="Patch transition fields.",
)
async def update_transition(
    transition_id: UUID, payload: TransitionUpdate, session: AsyncSession = Depends(get_db_session)
) -> Transition:
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not data:
        row = await _fetch_one(
            session,
            """
            SELECT
                id, project_id, track_id, from_clip_id, to_clip_id,
                transition_type, duration_ms, easing, params, created_at
            FROM transitions
            WHERE id = :id
            """,
            {"id": transition_id},
        )
        if not row:
            raise HTTPException(status_code=404, detail="Transition not found")
        return Transition(**row)

    set_parts = []
    for k in data.keys():
        if k == "params":
            set_parts.append("params = :params::jsonb")
        else:
            set_parts.append(f"{k} = :{k}")
    set_sql = ", ".join(set_parts)
    data["id"] = transition_id

    row = await _fetch_one(
        session,
        f"""
        UPDATE transitions
        SET {set_sql}
        WHERE id = :id
        RETURNING
            id, project_id, track_id, from_clip_id, to_clip_id,
            transition_type, duration_ms, easing, params, created_at
        """,
        data,
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Transition not found")
    await session.commit()
    return Transition(**row)


@router.delete(
    "/transitions/{transition_id}",
    response_model=APIMessage,
    summary="Delete transition",
    description="Delete a transition.",
)
async def delete_transition(transition_id: UUID, session: AsyncSession = Depends(get_db_session)) -> APIMessage:
    res = await session.execute(text("DELETE FROM transitions WHERE id = :id"), {"id": transition_id})
    if res.rowcount == 0:
        await session.rollback()
        raise HTTPException(status_code=404, detail="Transition not found")
    await session.commit()
    return APIMessage(message="Deleted")


# -----------------------
# Exports
# -----------------------
@router.post(
    "/exports",
    response_model=ExportJob,
    summary="Create export job",
    description="Create an export job for a project and start a background stub worker that updates status and events.",
)
async def create_export_job(
    payload: ExportJobCreate,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db_session),
) -> ExportJob:
    row = await _fetch_one(
        session,
        """
        INSERT INTO export_jobs (project_id, preset, status, progress)
        VALUES (:project_id, :preset, 'queued', 0.00)
        RETURNING
            id, project_id, preset, output_uri, status, progress, error_message,
            started_at, finished_at, created_at, updated_at
        """,
        payload.model_dump(),
    )
    if not row:
        await session.rollback()
        raise HTTPException(status_code=400, detail="Unable to create export job")

    # Create an initial event (matches allowed enum values)
    await session.execute(
        text(
            """
            INSERT INTO export_job_events (export_job_id, event_type, message, progress)
            VALUES (:export_job_id, 'created', 'Export job created.', 0.00)
            """
        ),
        {"export_job_id": row["id"]},
    )
    await session.commit()

    # Fire-and-forget stub
    background_tasks.add_task(run_export_job_stub, row["id"])
    return ExportJob(**row)


@router.get(
    "/projects/{project_id}/exports",
    response_model=List[ExportJob],
    summary="List export jobs",
    description="List export jobs for a project (newest first).",
)
async def list_export_jobs(project_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[ExportJob]:
    rows = await _fetch_all(
        session,
        """
        SELECT
            id, project_id, preset, output_uri, status, progress, error_message,
            started_at, finished_at, created_at, updated_at
        FROM export_jobs
        WHERE project_id = :project_id
        ORDER BY created_at DESC
        """,
        {"project_id": project_id},
    )
    return [ExportJob(**r) for r in rows]


@router.get(
    "/exports/{export_job_id}",
    response_model=ExportJob,
    summary="Get export job",
    description="Fetch a single export job.",
)
async def get_export_job(export_job_id: UUID, session: AsyncSession = Depends(get_db_session)) -> ExportJob:
    row = await _fetch_one(
        session,
        """
        SELECT
            id, project_id, preset, output_uri, status, progress, error_message,
            started_at, finished_at, created_at, updated_at
        FROM export_jobs
        WHERE id = :id
        """,
        {"id": export_job_id},
    )
    if not row:
        raise HTTPException(status_code=404, detail="Export job not found")
    return ExportJob(**row)


@router.get(
    "/exports/{export_job_id}/events",
    response_model=List[ExportJobEvent],
    summary="List export job events",
    description="List events for an export job ordered chronologically.",
)
async def list_export_job_events(export_job_id: UUID, session: AsyncSession = Depends(get_db_session)) -> List[ExportJobEvent]:
    rows = await _fetch_all(
        session,
        """
        SELECT id, export_job_id, event_type, message, progress, created_at
        FROM export_job_events
        WHERE export_job_id = :id
        ORDER BY created_at ASC, id ASC
        """,
        {"id": export_job_id},
    )
    return [ExportJobEvent(**r) for r in rows]


@router.get(
    "/exports/{export_job_id}/with-events",
    response_model=ExportJobWithEvents,
    summary="Get export job with events",
    description="Convenience endpoint: export job plus events.",
)
async def get_export_job_with_events(export_job_id: UUID, session: AsyncSession = Depends(get_db_session)) -> ExportJobWithEvents:
    job = await get_export_job(export_job_id, session)
    events = await list_export_job_events(export_job_id, session)
    return ExportJobWithEvents(**job.model_dump(), events=events)
