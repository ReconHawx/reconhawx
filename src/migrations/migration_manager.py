"""
Migration Manager for Database Schema Versioning

This module provides the core migration management functionality including:
- Migration version tracking
- Migration file discovery and validation
- Migration dependency resolution
- Migration status tracking
"""

import os
import re
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Represents a database migration"""
    version: str
    filename: str
    description: str
    sql_up: str
    sql_down: Optional[str] = None
    dependencies: List[str] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class MigrationStatus:
    """Represents the status of a migration"""
    version: str
    applied_at: datetime
    checksum: str
    execution_time_ms: int
    success: bool
    error_message: Optional[str] = None


class MigrationManager:
    """
    Manages database migrations including version tracking, file discovery,
    and migration execution coordination.
    """
    
    def __init__(self, migrations_dir: str, db_url: str):
        """
        Initialize the migration manager.
        
        Args:
            migrations_dir: Directory containing migration files
            db_url: Database connection URL
        """
        self.migrations_dir = Path(migrations_dir)
        self.db_url = db_url
        self.migrations_table = "schema_migrations"
        
        # Ensure migrations directory exists
        self.migrations_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize migration tracking table
        self._init_migration_table()
    
    def _init_migration_table(self):
        """Initialize the migration tracking table if it doesn't exist."""
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.migrations_table} (
            version VARCHAR(50) PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL,
            checksum VARCHAR(64) NOT NULL,
            execution_time_ms INTEGER NOT NULL,
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(create_table_sql)
                conn.commit()
                logger.info(f"Migration tracking table '{self.migrations_table}' initialized")
        except Exception as e:
            logger.error(f"Failed to initialize migration table: {e}")
            raise
    
    def discover_migrations(self) -> List[Migration]:
        """
        Discover all migration files in the migrations directory.
        
        Returns:
            List of Migration objects sorted by version
        """
        migrations = []
        
        if not self.migrations_dir.exists():
            logger.warning(f"Migrations directory {self.migrations_dir} does not exist")
            return migrations
        
        # Look for migration files (format: V{version}__{description}.sql)
        migration_pattern = re.compile(r'^V(\d+\.\d+\.\d+)__(.+)\.sql$')
        
        for file_path in self.migrations_dir.glob("*.sql"):
            match = migration_pattern.match(file_path.name)
            if match:
                version, description = match.groups()
                description = description.replace('_', ' ')
                
                # Read migration SQL
                sql_content = file_path.read_text(encoding='utf-8')
                sql_up, sql_down = self._parse_migration_sql(sql_content)
                
                migration = Migration(
                    version=version,
                    filename=file_path.name,
                    description=description,
                    sql_up=sql_up,
                    sql_down=sql_down
                )
                migrations.append(migration)
        
        # Sort by version
        migrations.sort(key=lambda m: self._version_to_tuple(m.version))
        
        logger.info(f"Discovered {len(migrations)} migration files")
        return migrations
    
    def _parse_migration_sql(self, sql_content: str) -> Tuple[str, Optional[str]]:
        """
        Parse migration SQL content to extract up and down migrations.
        
        Args:
            sql_content: Raw SQL content from migration file
            
        Returns:
            Tuple of (up_sql, down_sql)
        """
        # Split on -- DOWN MIGRATION marker
        parts = sql_content.split('-- DOWN MIGRATION')
        
        sql_up = parts[0].strip()
        sql_down = parts[1].strip() if len(parts) > 1 else None
        
        return sql_up, sql_down
    
    def _version_to_tuple(self, version: str) -> Tuple[int, int, int]:
        """Convert version string to tuple for sorting."""
        return tuple(map(int, version.split('.')))
    
    def get_applied_migrations(self) -> List[MigrationStatus]:
        """
        Get list of migrations that have been applied to the database.
        
        Returns:
            List of MigrationStatus objects
        """
        query = f"""
        SELECT version, applied_at, checksum, execution_time_ms, success, error_message
        FROM {self.migrations_table}
        ORDER BY version
        """
        
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    
                    migrations = []
                    for row in rows:
                        status = MigrationStatus(
                            version=row[0],
                            applied_at=row[1],  # PostgreSQL returns datetime object directly
                            checksum=row[2],
                            execution_time_ms=row[3],
                            success=bool(row[4]),
                            error_message=row[5]
                        )
                        migrations.append(status)
                    
                    return migrations
        except Exception as e:
            logger.error(f"Failed to get applied migrations: {e}")
            raise
    
    def get_pending_migrations(self) -> List[Migration]:
        """
        Get list of migrations that haven't been applied yet.
        
        Returns:
            List of pending Migration objects
        """
        all_migrations = self.discover_migrations()
        # Only successful runs count as applied; failed rows stay rerunnable after SQL/fixes
        applied_versions = {m.version for m in self.get_applied_migrations() if m.success}
        
        pending = [m for m in all_migrations if m.version not in applied_versions]
        
        logger.info(f"Found {len(pending)} pending migrations")
        return pending
    
    def record_migration(self, migration: Migration, success: bool, 
                        execution_time_ms: int, error_message: Optional[str] = None):
        """
        Record a migration execution in the tracking table.
        
        Args:
            migration: The migration that was executed
            success: Whether the migration was successful
            execution_time_ms: Execution time in milliseconds
            error_message: Error message if migration failed
        """
        import hashlib
        
        # Calculate checksum of migration content
        content = f"{migration.version}:{migration.sql_up}"
        checksum = hashlib.sha256(content.encode()).hexdigest()
        
        insert_sql = f"""
        INSERT INTO {self.migrations_table}
        (version, applied_at, checksum, execution_time_ms, success, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (version) DO UPDATE SET
            applied_at = EXCLUDED.applied_at,
            checksum = EXCLUDED.checksum,
            execution_time_ms = EXCLUDED.execution_time_ms,
            success = EXCLUDED.success,
            error_message = EXCLUDED.error_message
        """
        
        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_sql, (
                        migration.version,
                        datetime.utcnow(),
                        checksum,
                        execution_time_ms,
                        success,
                        error_message
                    ))
                conn.commit()
                
                status = "successful" if success else "failed"
                logger.info(f"Recorded {status} migration {migration.version}")
        except Exception as e:
            logger.error(f"Failed to record migration {migration.version}: {e}")
            raise
    
    def get_migration_status(self) -> Dict[str, str]:
        """
        Get status of all migrations.
        
        Returns:
            Dictionary mapping version to status ('applied', 'pending', 'failed')
        """
        all_migrations = self.discover_migrations()
        applied_migrations = self.get_applied_migrations()
        
        status_map = {}
        
        # Mark all discovered migrations as pending initially
        for migration in all_migrations:
            status_map[migration.version] = 'pending'
        
        # Update with actual status
        for applied in applied_migrations:
            if applied.success:
                status_map[applied.version] = 'applied'
            else:
                status_map[applied.version] = 'failed'
        
        return status_map
    
    def validate_migrations(self) -> List[str]:
        """
        Validate migration files for common issues.
        
        Returns:
            List of validation error messages
        """
        errors = []
        migrations = self.discover_migrations()
        
        # Check for duplicate versions
        versions = [m.version for m in migrations]
        duplicates = [v for v in set(versions) if versions.count(v) > 1]
        if duplicates:
            errors.append(f"Duplicate migration versions found: {duplicates}")
        
        # Check for gaps in version numbers
        if migrations:
            expected_versions = []
            for i in range(len(migrations)):
                expected_versions.append(f"{i+1}.0.0")
            
            actual_versions = [m.version for m in migrations]
            missing_versions = set(expected_versions) - set(actual_versions)
            if missing_versions:
                errors.append(f"Missing migration versions: {missing_versions}")
        
        # Check for empty SQL
        for migration in migrations:
            if not migration.sql_up.strip():
                errors.append(f"Migration {migration.version} has empty UP SQL")
        
        return errors
    
    def create_migration(self, description: str, sql_up: str, sql_down: Optional[str] = None) -> str:
        """
        Create a new migration file.
        
        Args:
            description: Migration description
            sql_up: SQL to apply the migration
            sql_down: SQL to rollback the migration (optional)
            
        Returns:
            Path to the created migration file
        """
        # Get next version number
        existing_migrations = self.discover_migrations()
        next_version = len(existing_migrations) + 1
        
        version = f"{next_version}.0.0"
        filename = f"V{version}__{description.replace(' ', '_')}.sql"
        file_path = self.migrations_dir / filename
        
        # Create migration content
        content = f"""-- Migration: {description}
-- Version: {version}
-- Created: {datetime.utcnow().isoformat()}

-- UP MIGRATION
{sql_up}

"""
        
        if sql_down:
            content += f"""
-- DOWN MIGRATION
{sql_down}
"""
        
        # Write migration file
        file_path.write_text(content, encoding='utf-8')
        
        logger.info(f"Created migration file: {file_path}")
        return str(file_path) 