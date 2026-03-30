import logging
from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # API settings
    API_V1_STR: str = ""
    PROJECT_NAME: str = "Workflow API"

    # Kubernetes settings
    RUNNER_IMAGE: str = "runner:latest"
    RUNNER_SERVICE_ACCOUNT: str = "runner-service-account"
    JOB_TTL_SECONDS: int = 86400  # 24 hours

    # Asset Processing Configuration
    ASSET_BATCH_THRESHOLD: int = 100  # Queue batches larger than this
    ASSET_QUEUE_MAX_SIZE: int = 1000  # Max items in processing queue
    ASSET_PROCESSING_TIMEOUT: int = 300  # 5 minutes timeout for background processing
    ASSET_BATCH_SIZE: int = 50  # Database batch size for inserts
    ASSET_QUEUE_RETRY_ATTEMPTS: int = 3  # Retry attempts for failed processing
    
    # Database Optimization Configuration (Phase 2)
    DB_BULK_PROCESSING_THRESHOLD: int = 50  # Use bulk processing for batches >= this size
    DB_CHUNK_SIZE: int = 100  # Process assets in chunks of this size
    DB_BATCH_TIMEOUT: int = 600  # 10 minutes timeout for batch operations
    DB_CONNECTION_POOL_SIZE: int = 20  # Increased pool size for batch operations
    DB_MAX_OVERFLOW: int = 40  # Increased overflow for batch operations

    # Logging
    LOG_LEVEL: str = "INFO"

    # Event Publisher Configuration
    EVENT_BATCH_SIZE: int = int(os.getenv("EVENT_BATCH_SIZE", "50"))
    EVENT_BATCH_TIMEOUT: float = float(os.getenv("EVENT_BATCH_TIMEOUT", "2.0"))
    NATS_URL: str = os.getenv("NATS_URL", "nats://nats:4222")
    EVENTS_STREAM: str = os.getenv("EVENTS_STREAM", "EVENTS")

    class Config:
        case_sensitive = True

settings = Settings()

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
) 