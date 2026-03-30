from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"

class JobResult(BaseModel):
    success_count: int = 0
    error_count: int = 0
    errors: List[Dict[str, Any]] = []
    processed_findings: List[Dict[str, Any]] = []

class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    created_at: datetime
    updated_at: datetime
    results: Optional[JobResult] = None

class BatchPhishlabsRequest(BaseModel):
    finding_ids: List[str] = Field(..., description="List of typosquat finding IDs to enrich with PhishLabs data")
    catcode: Optional[str] = Field(None, description="PhishLabs category code for creating incidents")
    report_to_gsb: bool = Field(False, description="Whether to also report domains to Google Safe Browsing")

class AIAnalysisBatchRequest(BaseModel):
    finding_ids: List[str] = Field(..., description="List of typosquat finding IDs to analyze")
    model: Optional[str] = Field(None, description="Override Ollama model for this batch")
    force: bool = Field(False, description="Re-analyze even if already analyzed")

class DummyBatchRequest(BaseModel):
    items: List[str] = Field(..., description="List of items to process in the dummy batch job")

class TyposquatBatchRequest(BaseModel):
    domains: List[str] = Field(..., description="List of domains to analyze for typosquatting characteristics")

class GatherApiFindingsRequest(BaseModel):
    program_name: str = Field(..., description="Program name to gather findings for")
    api_vendor: str = Field(default="threatstream", description="API vendor to use (threatstream, etc.)")
    date_range_hours: Optional[int] = Field(None, description="Number of hours to limit data range (for supported vendors)")

class SyncRecordedFutureDataRequest(BaseModel):
    program_name: str = Field(..., description="Program name to sync RecordedFuture data for")
    batch_size: int = Field(default=50, ge=1, le=200, description="Number of findings to process per batch")
    max_age_days: int = Field(default=30, ge=0, le=365, description="Only sync findings newer than this many days (0 = all)")
    include_screenshots: bool = Field(default=True, description="Whether to include screenshot processing")

# New scheduling models
class ScheduleType(str, Enum):
    ONCE = "once"
    RECURRING = "recurring"
    CRON = "cron"

class JobType(str, Enum):
    DUMMY_BATCH = "dummy_batch"
    TYPOSQUAT_BATCH = "typosquat_batch"
    PHISHLABS_BATCH = "phishlabs_batch"
    AI_ANALYSIS_BATCH = "ai_analysis_batch"
    GATHER_API_FINDINGS = "gather_api_findings"
    SYNC_RECORDEDFUTURE_DATA = "sync_recordedfuture_data"
    WORKFLOW = "workflow"
    CUSTOM = "custom"

class CronSchedule(BaseModel):
    """Cron expression for job scheduling"""
    minute: str = Field(default="0", description="Minute (0-59, *, */n)")
    hour: str = Field(default="*", description="Hour (0-23, *, */n)")
    day_of_month: str = Field(default="*", description="Day of month (1-31, *, */n)")
    month: str = Field(default="*", description="Month (1-12, *, */n)")
    day_of_week: str = Field(default="*", description="Day of week (0-7, *, */n, where 0 and 7 are Sunday)")
    
    @validator('minute', 'hour', 'day_of_month', 'month', 'day_of_week')
    def validate_cron_field(cls, v):
        if v == "*":
            return v
        if v.startswith("*/"):
            try:
                int(v[2:])
                return v
            except ValueError:
                raise ValueError(f"Invalid cron expression: {v}")
        
        # Handle ranges like "1-5", "0-59", etc.
        if "-" in v:
            try:
                parts = v.split("-")
                if len(parts) == 2:
                    start, end = int(parts[0]), int(parts[1])
                    if start <= end:
                        return v
                    else:
                        raise ValueError(f"Invalid range in cron expression: {v}")
                else:
                    raise ValueError(f"Invalid range format in cron expression: {v}")
            except ValueError:
                raise ValueError(f"Invalid range in cron expression: {v}")
        
        # Handle lists like "1,2,3" or "1,3,5"
        if "," in v:
            try:
                parts = v.split(",")
                for part in parts:
                    int(part.strip())
                return v
            except ValueError:
                raise ValueError(f"Invalid list in cron expression: {v}")
        
        # Handle single numbers
        try:
            int(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid cron expression: {v}")
    
    def to_cron_string(self) -> str:
        """Convert to standard cron string format"""
        return f"{self.minute} {self.hour} {self.day_of_month} {self.month} {self.day_of_week}"

class RecurringSchedule(BaseModel):
    """Recurring schedule configuration"""
    interval_minutes: Optional[int] = Field(None, ge=1, description="Interval in minutes")
    interval_hours: Optional[int] = Field(None, ge=1, description="Interval in hours")
    interval_days: Optional[int] = Field(None, ge=1, description="Interval in days")
    max_executions: Optional[int] = Field(None, ge=1, description="Maximum number of executions")
    end_date: Optional[datetime] = Field(None, description="End date for recurring jobs")
    
    @validator('interval_minutes', 'interval_hours', 'interval_days')
    def validate_interval(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Interval must be greater than 0")
        return v
    
    def get_interval_seconds(self) -> int:
        """Get interval in seconds"""
        total_seconds = 0
        if self.interval_minutes:
            total_seconds += self.interval_minutes * 60
        if self.interval_hours:
            total_seconds += self.interval_hours * 3600
        if self.interval_days:
            total_seconds += self.interval_days * 86400
        return total_seconds if total_seconds > 0 else 3600  # Default to 1 hour

class JobSchedule(BaseModel):
    """Job scheduling configuration"""
    schedule_type: ScheduleType = Field(..., description="Type of schedule")
    start_time: Optional[datetime] = Field(None, description="Start time for the job")
    cron_schedule: Optional[CronSchedule] = Field(None, description="Cron schedule for recurring jobs")
    recurring_schedule: Optional[RecurringSchedule] = Field(None, description="Recurring schedule configuration")
    timezone: str = Field(default="UTC", description="Timezone for scheduling")
    enabled: bool = Field(default=True, description="Whether the schedule is enabled")
    
    @validator('cron_schedule')
    def validate_cron_schedule(cls, v, values):
        if values.get('schedule_type') == ScheduleType.CRON and not v:
            raise ValueError("Cron schedule is required for cron schedule type")
        return v
    
    @validator('recurring_schedule')
    def validate_recurring_schedule(cls, v, values):
        if values.get('schedule_type') == ScheduleType.RECURRING and not v:
            raise ValueError("Recurring schedule is required for recurring schedule type")
        return v

class ScheduledJobRequest(BaseModel):
    """Request model for creating scheduled jobs"""
    job_type: JobType = Field(..., description="Type of job to schedule")
    job_data: Dict[str, Any] = Field(..., description="Job-specific data")
    schedule: JobSchedule = Field(..., description="Schedule configuration")
    name: str = Field(..., description="Name for the scheduled job")
    description: Optional[str] = Field(None, description="Description of the scheduled job")
    program_name: str = Field(..., description="Program name for the scheduled job")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for the scheduled job")
    
    @validator('name')
    def validate_name(cls, v):
        if not v.strip():
            raise ValueError("Name cannot be empty")
        if len(v) > 100:
            raise ValueError("Name cannot exceed 100 characters")
        return v.strip()

class ScheduledJobResponse(BaseModel):
    """Response model for scheduled jobs"""
    schedule_id: str
    job_type: JobType
    name: str
    description: Optional[str]
    program_id: str
    program_name: Optional[str] = None
    job_data: Dict[str, Any] = Field(default_factory=dict, description="Job-specific data")
    schedule: JobSchedule
    status: JobStatus
    next_run: Optional[datetime]
    last_run: Optional[datetime]
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    created_at: datetime
    updated_at: datetime
    tags: List[str] = []

class ScheduledJobUpdateRequest(BaseModel):
    """Request model for updating scheduled jobs"""
    name: Optional[str] = Field(None, description="New name for the scheduled job")
    description: Optional[str] = Field(None, description="New description")
    schedule: Optional[JobSchedule] = Field(None, description="New schedule configuration")
    enabled: Optional[bool] = Field(None, description="Whether to enable/disable the schedule")
    tags: Optional[List[str]] = Field(None, description="New tags")
    job_data: Optional[Dict[str, Any]] = Field(None, description="Job-specific data updates")

class JobExecutionHistory(BaseModel):
    """Model for job execution history"""
    execution_id: str
    schedule_id: str
    job_id: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[int]
    error_message: Optional[str]
    results: Optional[Any] 