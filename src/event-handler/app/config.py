#!/usr/bin/env python3
import os
from dataclasses import dataclass


@dataclass
class NotifierConfig:
    # NATS Configuration
    nats_url: str = os.getenv("NATS_URL", "nats://nats:4222")
    nats_stream: str = os.getenv("EVENTS_STREAM", "EVENTS")
    nats_subject_pattern: str = os.getenv("EVENTS_SUBJECT", "events.>")
    
    # Redis Configuration
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    # Logging Configuration
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
        
    # Settings Configuration - API-based, no file needed
    # settings_file is kept for backward compatibility but not used
    api_url: str = os.getenv("API_URL", "http://api:8000")
    internal_service_api_key: str = os.getenv("INTERNAL_SERVICE_API_KEY", "")
    api_request_timeout: int = int(os.getenv("EVENTHANDLER_API_TIMEOUT_SECONDS", "15"))
    
    # Batching Configuration
    default_max_items: int = int(os.getenv("EVENTHANDLER_MAX_ITEMS", "100"))
    default_max_delay_seconds: int = int(os.getenv("EVENTHANDLER_MAX_DELAY_SECONDS", "300"))
    default_dedup_window_seconds: int = int(os.getenv("EVENTHANDLER_DEDUP_WINDOW_SECONDS", "900"))
    include_samples: int = int(os.getenv("EVENTHANDLER_INCLUDE_SAMPLES", "10"))
    
    # Batch Event Handling Configuration
    enable_batch_processing: bool = os.getenv("EVENTHANDLER_ENABLE_BATCH_PROCESSING", "true").lower() == "true"
    batch_logging_verbose: bool = os.getenv("EVENTHANDLER_BATCH_LOGGING_VERBOSE", "false").lower() == "true"
    max_batch_size: int = int(os.getenv("EVENTHANDLER_MAX_BATCH_SIZE", "1000"))  # Max events per batch to process

    # Event Handler Configuration (definitions from API only: GET /internal/event-handler-configs)
    enable_event_handlers: bool = os.getenv("EVENTHANDLER_ENABLE_EVENT_HANDLERS", "true").lower() == "true"
    fallback_to_legacy: bool = os.getenv("EVENTHANDLER_FALLBACK_TO_LEGACY", "true").lower() == "true"  # Fallback to old Discord system if no handlers match
    api_config_cache_ttl: int = int(os.getenv("EVENTHANDLER_API_CONFIG_CACHE_TTL", "60"))  # Seconds to cache API config per program

    # Concurrency: max messages processed concurrently per fetch batch (0 = sequential)
    max_concurrent_messages: int = int(os.getenv("EVENTHANDLER_MAX_CONCURRENT_MESSAGES", "25"))


