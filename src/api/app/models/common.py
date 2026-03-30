from pydantic import BaseModel
from typing import Optional, Any, Dict

class StatsQueryFilter(BaseModel):
    filter: Optional[Dict[str, Any]] = {}
