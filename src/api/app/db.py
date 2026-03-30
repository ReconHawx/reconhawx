import os
import logging
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from models.postgres import Base, ReconTaskParameters

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# PostgreSQL connection details
POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "password")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("DATABASE_NAME", "recon_db")

# Construct PostgreSQL connection URL
POSTGRES_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create SQLAlchemy engine with optimized settings
engine = create_engine(
    POSTGRES_URL,
    echo=bool(os.getenv("SQL_ECHO", "false").lower() == "true"),  # Log SQL queries if enabled
    pool_size=int(os.getenv("DB_POOL_SIZE", "20")),  # Increased from 10 to 20
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "40")),  # Increased from 20 to 40
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,   # Recycle connections every hour
    pool_timeout=30,     # Wait up to 30 seconds for available connection
    # Add timeout settings to prevent hanging queries
    connect_args={
        "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),  # Connection timeout in seconds
        "options": f"-c statement_timeout={os.getenv('DB_STATEMENT_TIMEOUT', '300000')}"  # Query timeout in milliseconds
    }
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a session factory for batch operations with optimized settings
BatchSessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False, 
    bind=engine,
    # Optimize for batch operations
    expire_on_commit=False  # Keep objects accessible after commit
)

def get_db() -> Session:
    """Get database session for synchronous operations"""
    try:
        db = SessionLocal()
        return db
    except Exception as e:
        logger.error(f"Error creating database session: {e}")
        raise

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[Session, None]:
    """Get database session for asynchronous operations"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@asynccontextmanager
async def get_batch_db_session() -> AsyncGenerator[Session, None]:
    """Get optimized database session for batch operations"""
    db = BatchSessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    """Initialize database tables and default data"""
    try:
        logger.debug("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        logger.debug("Database tables created successfully")
        
        # Initialize default data
        _initialize_default_recon_task_parameters()
        
        logger.debug("Database initialization completed")
        
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

def _initialize_default_recon_task_parameters():
    """Initialize default recon task parameters in the database if they don't exist"""
    try:
        db = SessionLocal()
        
        # Default parameters for all recon tasks
        default_parameters = {
            "resolve_domain": {
                "last_execution_threshold": 24,
                "timeout": 120,
                "max_retries": 3,
                "chunk_size": 10
            },
            "resolve_ip": {
                "last_execution_threshold": 24,
                "timeout": 120,
                "max_retries": 3,
                "chunk_size": 10
            },
            "port_scan": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 5
            },
            "nuclei_scan": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 10
            },
            "crawl_website": {
                "last_execution_threshold": 24,
                "timeout": 1800,
                "max_retries": 3,
                "chunk_size": 1
            },
            "screenshot_website": {
                "last_execution_threshold": 24,
                "timeout": 600,
                "max_retries": 3,
                "chunk_size": 10
            },
            "subdomain_finder": {
                "last_execution_threshold": 24,
                "timeout": 300,
                "max_retries": 3,
                "chunk_size": 10
            },
            "test_http": {
                "last_execution_threshold": 24,
                "timeout": 900,
                "max_retries": 3,
                "chunk_size": 10
            },
            "typosquat_detection": {
                "last_execution_threshold": 168,  # 7 days
                "timeout": 1800,
                "max_retries": 3,
                "chunk_size": 20
            },
            "resolve_ip_cidr": {
                "last_execution_threshold": 1,  # 1 hour
                "timeout": 300,  # 5 minutes
                "max_retries": 3,
                "chunk_size": 1
            },
            "shell_command": {
                "last_execution_threshold": 24,
                "timeout": 300,  # 5 minutes
                "max_retries": 3,
                "chunk_size": 10
            },
            "fuzz_website": {
                "last_execution_threshold": 24,
                "timeout": 300,  # 5 minutes
                "max_retries": 3,
                "chunk_size": 5
            },
            "whois_domain_check": {
                "last_execution_threshold": 24,
                "timeout": 600,
                "max_retries": 3,
                "chunk_size": 1,
            },
        }
        
        # Check which tasks already have parameters stored
        existing_tasks = set()
        for task in db.query(ReconTaskParameters).all():
            existing_tasks.add(task.recon_task)
        
        # Insert default parameters for tasks that don't have them
        inserted_count = 0
        for task_name, parameters in default_parameters.items():
            if task_name not in existing_tasks:
                task_params = ReconTaskParameters(
                    recon_task=task_name,
                    parameters=parameters
                )
                
                db.add(task_params)
                inserted_count += 1
                logger.debug(f"Initialized default parameters for recon task: {task_name}")
        
        if inserted_count > 0:
            db.commit()
            logger.debug(f"Initialized default parameters for {inserted_count} recon tasks")
        else:
            logger.debug("All recon task parameters already exist in database")
            
        db.close()
            
    except Exception as e:
        logger.error(f"Error initializing default recon task parameters: {str(e)}")
        raise

def test_connection():
    """Test database connection"""
    try:
        logger.debug(f"Testing database connection to: {POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        logger.debug("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        logger.error(f"Database URL: {POSTGRES_URL.replace(POSTGRES_PASSWORD, '***')}")
        return False

# Database utilities for migration
def execute_raw_sql(sql: str, params: dict = None):
    """Execute raw SQL for migration purposes"""
    db = SessionLocal()
    try:
        result = db.execute(text(sql), params or {})
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        logger.error(f"Error executing SQL: {str(e)}")
        raise
    finally:
        db.close()

def bulk_insert_data(model_class, data_list: list, batch_size: int = 1000):
    """Bulk insert data for migration efficiency"""
    db = SessionLocal()
    try:
        total_inserted = 0
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            db.bulk_insert_mappings(model_class, batch)
            db.commit()
            total_inserted += len(batch)
            logger.debug(f"Inserted batch {i//batch_size + 1}: {len(batch)} records ({total_inserted}/{len(data_list)} total)")
        
        return total_inserted
    except Exception as e:
        db.rollback()
        logger.error(f"Error during bulk insert: {str(e)}")
        raise
    finally:
        db.close()

# Setup logging for SQLAlchemy
def setup_db_logging():
    """Setup database query logging"""
    logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.dialects').setLevel(logging.INFO)
    logging.getLogger('sqlalchemy.pool').setLevel(logging.INFO)

# PostgreSQL specific optimizations
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set PostgreSQL connection parameters for performance"""
    if engine.dialect.name == 'postgresql':
        with dbapi_connection.cursor() as cursor:
            # Set reasonable work_mem for better sort/join performance
            cursor.execute("SET work_mem = '256MB'")
            # Set statement timeout to prevent long-running queries
            cursor.execute("SET statement_timeout = '300s'")
            # Use parallel queries when beneficial
            cursor.execute("SET max_parallel_workers_per_gather = 2")

if __name__ == "__main__":
    # Test database connection and initialization
    setup_db_logging()
    if test_connection():
        print("✅ Database connection successful")
        init_database()
        print("✅ Database initialization completed")
    else:
        print("❌ Database connection failed")
        exit(1) 