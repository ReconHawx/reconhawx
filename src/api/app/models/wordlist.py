from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DynamicWordlistType(str, Enum):
    """Supported dynamic wordlist types"""
    SUBDOMAIN_PREFIXES = "subdomain_prefixes"
    # Future types can be added here:
    # APEX_DOMAINS = "apex_domains"
    # URL_PATHS = "url_paths"
    # TECHNOLOGY_NAMES = "technology_names"


class Wordlist(BaseModel):
    """Wordlist model"""
    id: str = Field(..., description="Unique identifier for the wordlist")
    name: str = Field(..., description="Name of the wordlist")
    description: Optional[str] = Field(None, description="Description of the wordlist")
    filename: Optional[str] = Field(None, description="Original filename (None for dynamic wordlists)")
    content_type: Optional[str] = Field(None, description="Content type of the file (None for dynamic wordlists)")
    file_size: Optional[int] = Field(None, description="Size of the file in bytes (None for dynamic wordlists)")
    word_count: int = Field(..., description="Number of words in the wordlist")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    program_name: Optional[str] = Field(None, description="Program this wordlist belongs to")
    created_by: Optional[str] = Field(None, description="Username who created the wordlist")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    is_active: bool = Field(default=True, description="Whether the wordlist is active")
    # Dynamic wordlist fields
    is_dynamic: bool = Field(default=False, description="Whether this is a dynamic wordlist")
    dynamic_type: Optional[str] = Field(None, description="Type of dynamic generation (e.g., 'subdomain_prefixes')")
    dynamic_config: Optional[Dict[str, Any]] = Field(None, description="Configuration for dynamic generation")


class WordlistCreate(BaseModel):
    """Model for creating a new static wordlist (uploaded file)"""
    name: str = Field(..., description="Name of the wordlist")
    description: Optional[str] = Field(None, description="Description of the wordlist")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    program_name: Optional[str] = Field(None, description="Program this wordlist belongs to (optional)")


class DynamicWordlistCreate(BaseModel):
    """Model for creating a new dynamic wordlist"""
    name: str = Field(..., description="Name of the wordlist")
    description: Optional[str] = Field(None, description="Description of the wordlist")
    dynamic_type: DynamicWordlistType = Field(..., description="Type of dynamic generation")
    program_name: str = Field(..., description="Program to generate wordlist from (required for dynamic)")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")


class WordlistUpdate(BaseModel):
    """Model for updating a wordlist"""
    name: Optional[str] = Field(None, description="Name of the wordlist")
    description: Optional[str] = Field(None, description="Description of the wordlist")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    program_name: Optional[str] = Field(None, description="Program this wordlist belongs to (optional)")
    is_active: Optional[bool] = Field(None, description="Whether the wordlist is active")


class WordlistResponse(BaseModel):
    """Response model for wordlist"""
    id: str
    name: str
    description: Optional[str] = None
    filename: Optional[str] = None  # Optional for dynamic wordlists
    content_type: Optional[str] = None  # Optional for dynamic wordlists
    file_size: Optional[int] = None  # Optional for dynamic wordlists
    word_count: int
    tags: List[str] = []
    download_uri: Optional[str] = None
    program_name: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_active: bool = True
    # Dynamic wordlist fields
    is_dynamic: bool = False
    dynamic_type: Optional[str] = None
    dynamic_config: Optional[Dict[str, Any]] = None


class WordlistListResponse(BaseModel):
    """Response model for listing wordlists"""
    wordlists: List[WordlistResponse]
    total: int
    page: int
    limit: int


class WordlistCreateResponse(BaseModel):
    """Response model for static wordlist creation"""
    id: str
    name: str
    filename: str
    file_size: int
    word_count: int
    status: str
    message: str


class DynamicWordlistCreateResponse(BaseModel):
    """Response model for dynamic wordlist creation"""
    id: str
    name: str
    dynamic_type: str
    program_name: str
    word_count: int
    status: str
    message: str


class WordlistUpdateResponse(BaseModel):
    """Response model for wordlist update"""
    id: str
    name: str
    status: str
    message: str
