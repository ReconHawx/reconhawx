from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class NucleiTemplate(BaseModel):
    """Nuclei template model"""
    id: str = Field(..., description="Unique identifier for the template")
    name: str = Field(..., description="Name of the template")
    author: Optional[str] = Field(None, description="Author of the template")
    severity: Optional[str] = Field(None, description="Severity level (low, medium, high, critical)")
    description: Optional[str] = Field(None, description="Description of what the template detects")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    content: str = Field(..., description="YAML content of the nuclei template")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    is_active: bool = Field(default=True, description="Whether the template is active")

class NucleiTemplateCreate(BaseModel):
    """Model for creating a new nuclei template - only requires YAML content"""
    content: str = Field(..., description="YAML content of the nuclei template")

class NucleiTemplateUpdate(BaseModel):
    """Model for updating a nuclei template"""
    content: Optional[str] = Field(None, description="YAML content of the nuclei template")
    is_active: Optional[bool] = Field(None, description="Whether the template is active")

class NucleiTemplateResponse(BaseModel):
    """Response model for nuclei template"""
    id: str
    name: str
    author: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True

class NucleiTemplateListResponse(BaseModel):
    """Response model for listing nuclei templates"""
    templates: List[NucleiTemplateResponse]
    total: int
    page: int
    limit: int

class NucleiTemplateCreateResponse(BaseModel):
    """Response model for template creation"""
    id: str
    name: str
    author: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    status: str
    message: str

class NucleiTemplateUpdateResponse(BaseModel):
    """Response model for template update"""
    id: str
    name: str
    author: Optional[str] = None
    severity: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []
    status: str
    message: str 