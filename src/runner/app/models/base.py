from datetime import datetime

def serialize_datetime(dt: datetime) -> str:
    """Serialize datetime to ISO format string"""
    if dt is None:
        return None
    return dt.isoformat()