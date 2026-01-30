from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class APIMessage(BaseModel):
    message: str = Field(..., description="Human-readable message.")


# -----------------------
# Projects
# -----------------------
class ProjectCreate(BaseModel):
    name: str = Field(..., description="Project name.")
    description: Optional[str] = Field(None, description="Optional description.")
    width: int = Field(1920, ge=1, description="Video width in pixels.")
    height: int = Field(1080, ge=1, description="Video height in pixels.")
    fps: Decimal = Field(Decimal("30.000"), ge=Decimal("1.000"), description="Frames per second.")


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Project name.")
    description: Optional[str] = Field(None, description="Optional description.")
    width: Optional[int] = Field(None, ge=1, description="Video width in pixels.")
    height: Optional[int] = Field(None, ge=1, description="Video height in pixels.")
    fps: Optional[Decimal] = Field(None, ge=Decimal("1.000"), description="Frames per second.")
    duration_ms: Optional[int] = Field(None, ge=0, description="Project duration in milliseconds.")


class Project(ProjectCreate):
    id: UUID = Field(..., description="Project UUID.")
    duration_ms: int = Field(..., ge=0, description="Project duration in milliseconds.")
    created_at: datetime = Field(..., description="Created timestamp.")
    updated_at: datetime = Field(..., description="Updated timestamp.")


# -----------------------
# Media Assets
# -----------------------
MediaKind = Literal["video", "audio", "image"]


class MediaAssetCreate(BaseModel):
    project_id: UUID = Field(..., description="Owning project UUID.")
    kind: MediaKind = Field(..., description="Media kind.")
    source_uri: str = Field(..., description="Where the media is stored (URL or local path).")
    original_filename: Optional[str] = Field(None, description="Original filename if uploaded.")
    mime_type: Optional[str] = Field(None, description="Mime type, if known.")
    size_bytes: Optional[int] = Field(None, ge=0, description="File size in bytes.")
    duration_ms: Optional[int] = Field(None, ge=0, description="Duration in ms for audio/video.")
    width: Optional[int] = Field(None, ge=1, description="Width in pixels for images/video.")
    height: Optional[int] = Field(None, ge=1, description="Height in pixels for images/video.")
    fps: Optional[Decimal] = Field(None, ge=Decimal("0.000"), description="FPS for video, if known.")
    has_audio: bool = Field(False, description="Whether asset includes audio stream.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary JSON metadata.")


class MediaAsset(MediaAssetCreate):
    id: UUID = Field(..., description="Media asset UUID.")
    created_at: datetime = Field(..., description="Created timestamp.")


# -----------------------
# Timeline Tracks
# -----------------------
TrackType = Literal["video", "audio", "overlay"]


class TimelineTrackCreate(BaseModel):
    project_id: UUID = Field(..., description="Owning project UUID.")
    track_type: TrackType = Field(..., description="Track type.")
    name: str = Field(..., description="Track name.")
    sort_order: int = Field(0, description="Ordering within project.")
    muted: bool = Field(False, description="Mute track (audio).")
    locked: bool = Field(False, description="Lock track from edits.")


class TimelineTrackUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Track name.")
    sort_order: Optional[int] = Field(None, description="Ordering within project.")
    muted: Optional[bool] = Field(None, description="Mute track.")
    locked: Optional[bool] = Field(None, description="Lock track.")


class TimelineTrack(TimelineTrackCreate):
    id: UUID = Field(..., description="Track UUID.")
    created_at: datetime = Field(..., description="Created timestamp.")


# -----------------------
# Timeline Clips
# -----------------------
ClipType = Literal["media", "title", "color", "generator"]


class TimelineClipCreate(BaseModel):
    project_id: UUID = Field(..., description="Owning project UUID.")
    track_id: UUID = Field(..., description="Owning track UUID.")
    media_asset_id: Optional[UUID] = Field(None, description="Linked media asset (nullable).")
    clip_type: ClipType = Field(..., description="Clip type.")
    name: Optional[str] = Field(None, description="Optional clip name.")
    start_ms: int = Field(0, ge=0, description="Timeline start position in ms.")
    end_ms: int = Field(0, ge=0, description="Timeline end position in ms.")
    in_ms: int = Field(0, ge=0, description="Source in point in ms.")
    out_ms: int = Field(0, ge=0, description="Source out point in ms.")
    speed: Decimal = Field(Decimal("1.0"), ge=Decimal("0.001"), description="Playback speed multiplier.")
    opacity: Decimal = Field(Decimal("1.0"), ge=Decimal("0.0"), le=Decimal("1.0"), description="Opacity 0..1.")
    volume: Decimal = Field(Decimal("1.0"), ge=Decimal("0.0"), description="Volume multiplier.")
    transform: Dict[str, Any] = Field(default_factory=dict, description="Transform JSON payload.")


class TimelineClipUpdate(BaseModel):
    track_id: Optional[UUID] = Field(None, description="Move clip to another track.")
    media_asset_id: Optional[UUID] = Field(None, description="Change media binding (nullable).")
    name: Optional[str] = Field(None, description="Optional clip name.")
    start_ms: Optional[int] = Field(None, ge=0, description="Timeline start in ms.")
    end_ms: Optional[int] = Field(None, ge=0, description="Timeline end in ms.")
    in_ms: Optional[int] = Field(None, ge=0, description="Source in in ms.")
    out_ms: Optional[int] = Field(None, ge=0, description="Source out in ms.")
    speed: Optional[Decimal] = Field(None, ge=Decimal("0.001"), description="Playback speed.")
    opacity: Optional[Decimal] = Field(None, ge=Decimal("0.0"), le=Decimal("1.0"), description="Opacity 0..1.")
    volume: Optional[Decimal] = Field(None, ge=Decimal("0.0"), description="Volume multiplier.")
    transform: Optional[Dict[str, Any]] = Field(None, description="Transform JSON payload.")


class TimelineClip(TimelineClipCreate):
    id: UUID = Field(..., description="Clip UUID.")
    created_at: datetime = Field(..., description="Created timestamp.")


# -----------------------
# Clip Trims
# -----------------------
TrimKind = Literal["in", "out", "both"]


class ClipTrimCreate(BaseModel):
    clip_id: UUID = Field(..., description="Timeline clip UUID.")
    kind: TrimKind = Field(..., description="Trim kind: in/out/both.")
    trim_in_ms: Optional[int] = Field(None, ge=0, description="Trim in value in ms.")
    trim_out_ms: Optional[int] = Field(None, ge=0, description="Trim out value in ms.")


class ClipTrim(ClipTrimCreate):
    id: UUID = Field(..., description="Trim UUID.")
    created_at: datetime = Field(..., description="Created timestamp.")


# -----------------------
# Transitions
# -----------------------
class TransitionCreate(BaseModel):
    project_id: UUID = Field(..., description="Owning project UUID.")
    track_id: UUID = Field(..., description="Owning track UUID.")
    from_clip_id: UUID = Field(..., description="From clip UUID.")
    to_clip_id: UUID = Field(..., description="To clip UUID.")
    transition_type: str = Field("crossfade", description="Transition type.")
    duration_ms: int = Field(1000, ge=0, description="Transition duration in ms.")
    easing: str = Field("linear", description="Easing function name.")
    params: Dict[str, Any] = Field(default_factory=dict, description="Transition parameters JSON.")


class TransitionUpdate(BaseModel):
    transition_type: Optional[str] = Field(None, description="Transition type.")
    duration_ms: Optional[int] = Field(None, ge=0, description="Duration in ms.")
    easing: Optional[str] = Field(None, description="Easing function.")
    params: Optional[Dict[str, Any]] = Field(None, description="Parameters JSON.")


class Transition(TransitionCreate):
    id: UUID = Field(..., description="Transition UUID.")
    created_at: datetime = Field(..., description="Created timestamp.")


# -----------------------
# Export Jobs + Events
# -----------------------
ExportStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
ExportEventType = Literal["created", "queued", "started", "progress", "completed", "failed", "canceled"]


class ExportJobCreate(BaseModel):
    project_id: UUID = Field(..., description="Project to export.")
    preset: str = Field("mp4_h264", description="Export preset identifier.")


class ExportJobUpdate(BaseModel):
    status: Optional[ExportStatus] = Field(None, description="Export job status.")
    progress: Optional[Decimal] = Field(None, ge=Decimal("0.00"), le=Decimal("100.00"), description="Progress 0..100.")
    output_uri: Optional[str] = Field(None, description="Output file location/URL.")
    error_message: Optional[str] = Field(None, description="Error message if failed.")
    started_at: Optional[datetime] = Field(None, description="Started timestamp.")
    finished_at: Optional[datetime] = Field(None, description="Finished timestamp.")


class ExportJob(ExportJobCreate):
    id: UUID = Field(..., description="Export job UUID.")
    output_uri: Optional[str] = Field(None, description="Output URI, if completed.")
    status: ExportStatus = Field(..., description="Job status.")
    progress: Decimal = Field(..., description="Progress 0..100.")
    error_message: Optional[str] = Field(None, description="Error message if failed.")
    started_at: Optional[datetime] = Field(None, description="Started timestamp.")
    finished_at: Optional[datetime] = Field(None, description="Finished timestamp.")
    created_at: datetime = Field(..., description="Created timestamp.")
    updated_at: datetime = Field(..., description="Updated timestamp.")


class ExportJobEventCreate(BaseModel):
    export_job_id: UUID = Field(..., description="Export job UUID.")
    event_type: ExportEventType = Field(..., description="Event type.")
    message: Optional[str] = Field(None, description="Event message.")
    progress: Optional[Decimal] = Field(None, ge=Decimal("0.00"), le=Decimal("100.00"), description="Progress 0..100.")


class ExportJobEvent(ExportJobEventCreate):
    id: int = Field(..., description="Event id (sequence).")
    created_at: datetime = Field(..., description="Created timestamp.")


class ExportJobWithEvents(ExportJob):
    events: List[ExportJobEvent] = Field(default_factory=list, description="Events in chronological order.")
