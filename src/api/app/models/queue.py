from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class QueueStatusResponse(BaseModel):
    queue_name: str
    status: Dict[str, Any]
    error: Optional[str] = None

class QueueMessagesResponse(BaseModel):
    queue_name: str
    messages: List[Dict[str, Any]]
    error: Optional[str] = None 