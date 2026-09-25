import time

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.deps import get_db
from src.db.models import IngestFailure
from src.ingest import bulk
from src.ingest.tracker import tracker

router = APIRouter()


class PipelineJobOut(BaseModel):
    id: int
    source: str
    label: str
    stage: str
    seconds_in_stage: int


class PipelineOut(BaseModel):
    jobs: list[PipelineJobOut]


class IngestFailureOut(BaseModel):
    id: int
    created_at: str
    source: str
    label: str
    video_id: str | None
    status: str
    reason: str
    detail: str | None
    title: str | None
    artist: str | None
    song_id: str | None


class BulkRequest(BaseModel):
    queries: list[str]


@router.get("/ingest/pipeline", response_model=PipelineOut)
def ingest_pipeline() -> PipelineOut:
    """Every song that is queued, downloading, waiting or being analysed."""
    now = time.time()
    return PipelineOut(jobs=[
        PipelineJobOut(
            id=j.id, source=j.source, label=j.label, stage=j.stage.value,
            seconds_in_stage=int(now - j.stage_since),
        )
        for j in tracker.snapshot()
    ])


@router.get("/ingest/failures", response_model=list[IngestFailureOut])
def ingest_failures(
    limit: int = Query(200, ge=1, le=2000),
    reason: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[IngestFailureOut]:
    """Songs that did not make it into the library, newest first."""
    q = db.query(IngestFailure)
    if reason:
        q = q.filter(IngestFailure.reason == reason)
    rows = q.order_by(IngestFailure.id.desc()).limit(limit).all()
    return [
        IngestFailureOut(
            id=r.id, created_at=r.created_at.isoformat(), source=r.source, label=r.label,
            video_id=r.video_id, status=r.status, reason=r.reason, detail=r.detail,
            title=r.title, artist=r.artist, song_id=r.song_id,
        )
        for r in rows
    ]


# Under /admin/ so nginx keeps them off the internet (they start hours of work).
@router.post("/admin/bulk")
def bulk_enqueue(req: BulkRequest) -> dict:
    """Queue "Artist - Title" search queries for download and analysis."""
    return {"queued": bulk.enqueue(req.queries)}


@router.delete("/admin/bulk")
def bulk_cancel() -> dict:
    """Drop every queued song that has not started yet."""
    return {"cancelled": bulk.cancel_pending()}
