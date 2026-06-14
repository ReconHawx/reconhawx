from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


CtMonitorEventType = Literal[
    "typosquat_alert",
    "typosquat_skip",
    "asset_match",
    "asset_submission",
]

CtMonitorOutcome = Literal[
    "published",
    "skipped_existing",
    "publish_failed",
    "matched",
    "skipped_legitimate_subdomain",
    "skipped_protected_domain",
    "skipped_similarity_length_gate",
    "skipped_similarity_threshold",
    "queued",
    "dedup_skipped",
    "submitted",
    "submit_failed",
]


class CtMonitorLogIngestItem(BaseModel):
    program_id: str = Field(..., description="Program UUID")
    program_name: Optional[str] = Field(None, description="Program display name")
    event_type: CtMonitorEventType
    outcome: CtMonitorOutcome
    occurred_at: Optional[datetime] = None
    domain: Optional[str] = Field(None, description="Detected or matched domain")
    protected_domain: Optional[str] = None
    match_type: Optional[str] = None
    similarity_score: Optional[float] = None
    priority: Optional[str] = None
    cert_fingerprint: Optional[str] = None
    cert_issuer: Optional[str] = None
    cert_source: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class CtMonitorLogIngestRequest(BaseModel):
    logs: List[CtMonitorLogIngestItem] = Field(..., min_length=1, max_length=1000)


class CtMonitorLogSearchRequest(BaseModel):
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program name(s)")
    event_type: Optional[Union[CtMonitorEventType, List[CtMonitorEventType]]] = None
    outcome: Optional[Union[CtMonitorOutcome, List[CtMonitorOutcome]]] = None
    search: Optional[str] = Field(None, description="Search domain, protected domain, fingerprint, or issuer")
    match_type: Optional[str] = None
    priority: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    sort_by: Literal[
        "occurred_at",
        "created_at",
        "program_name",
        "event_type",
        "outcome",
        "domain",
        "similarity_score",
    ] = "occurred_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=250)
