from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer


def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
    """Serialize datetime to ISO format string."""
    if dt is None:
        return None
    return dt.isoformat()


def utcnow() -> datetime:
    """Naive UTC 'now' replacement for the deprecated datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


SerializedDatetime = Annotated[
    datetime,
    PlainSerializer(serialize_datetime, return_type=str, when_used="json"),
]
