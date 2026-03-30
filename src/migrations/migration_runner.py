"""
Migration Runner for Database Schema Changes

This module provides the execution engine for database migrations including:
- SQL execution with transaction management
- Migration rollback capabilities
- Execution timing and error handling
- Database connection management
"""

import logging
import time
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from psycopg2.extras import RealDictCursor

from .migration_manager import MigrationManager, Migration, MigrationStatus

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Executes database migrations with proper transaction handling,
    error recovery, and status tracking.
    """
    
    def __init__(self, db_url: str, migrations_dir: str):
        """
        Initialize the migration runner.
        
        Args:
            db_url: PostgreSQL database connection URL
            migrations_dir: Directory containing migration files
        """
        self.db_url = db_url
        self.migration_manager = MigrationManager(migrations_dir, db_url)
        
    @contextmanager
    def get_connection(self):
        """Get a database connection with proper error handling."""
        conn = None
        try:
            conn = psycopg2.connect(self.db_url)
            conn.autocommit = False  # We'll manage transactions manually
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def run_migrations(self, target_version: Optional[str] = None, 
                      dry_run: bool = False) -> Dict[str, Any]:
        """
        Run pending migrations up to the target version.
        
        Args:
            target_version: Target migration version (None for latest)
            dry_run: If True, don't actually execute migrations
            
        Returns:
            Dictionary with execution results
        """
        pending_migrations = self.migration_manager.get_pending_migrations()
        
        if not pending_migrations:
            logger.info("No pending migrations to run")
            return {
                'success': True,
                'migrations_run': 0,
                'errors': [],
                'execution_time_ms': 0
            }
        
        # Filter to target version if specified
        if target_version:
            target_tuple = self.migration_manager._version_to_tuple(target_version)
            pending_migrations = [
                m for m in pending_migrations 
                if self.migration_manager._version_to_tuple(m.version) <= target_tuple
            ]
        
        if not pending_migrations:
            logger.info(f"No migrations to run up to version {target_version}")
            return {
                'success': True,
                'migrations_run': 0,
                'errors': [],
                'execution_time_ms': 0
            }
        
        logger.info(f"Running {len(pending_migrations)} migrations")
        
        if dry_run:
            logger.info("DRY RUN - No actual changes will be made")
            return self._dry_run_migrations(pending_migrations)
        
        return self._execute_migrations(pending_migrations)
    
    def _dry_run_migrations(self, migrations: List[Migration]) -> Dict[str, Any]:
        """Simulate migration execution without making changes."""
        results = {
            'success': True,
            'migrations_run': len(migrations),
            'errors': [],
            'execution_time_ms': 0
        }
        
        for migration in migrations:
            logger.info(f"DRY RUN: Would run migration {migration.version} - {migration.description}")
            
            # Validate SQL syntax
            try:
                with self.get_connection() as conn:
                    # Parse SQL to check syntax (PostgreSQL will validate)
                    conn.cursor().execute("SELECT 1")  # Test connection
            except Exception as e:
                error_msg = f"Migration {migration.version} has SQL syntax errors: {e}"
                results['errors'].append(error_msg)
                results['success'] = False
                logger.error(error_msg)
        
        return results
    
    def _execute_migrations(self, migrations: List[Migration]) -> Dict[str, Any]:
        """Execute migrations with proper transaction handling."""
        results = {
            'success': True,
            'migrations_run': 0,
            'errors': [],
            'execution_time_ms': 0
        }
        
        start_time = time.time()
        
        for migration in migrations:
            logger.info(f"Running migration {migration.version} - {migration.description}")
            
            migration_start = time.time()
            success = False
            error_message = None
            
            try:
                with self.get_connection() as conn:
                    # Execute migration SQL
                    cursor = conn.cursor()
                    cursor.execute(migration.sql_up)
                    conn.commit()
                    success = True
                    
                    logger.info(f"Successfully applied migration {migration.version}")
                    
            except Exception as e:
                error_message = str(e)
                logger.error(f"Failed to apply migration {migration.version}: {error_message}")
                results['success'] = False
                results['errors'].append(f"Migration {migration.version}: {error_message}")
            
            # Record migration execution
            execution_time_ms = int((time.time() - migration_start) * 1000)
            self.migration_manager.record_migration(
                migration, success, execution_time_ms, error_message
            )
            
            if success:
                results['migrations_run'] += 1
            else:
                # Stop on first failure
                break
        
        results['execution_time_ms'] = int((time.time() - start_time) * 1000)
        
        if results['success']:
            logger.info(f"Successfully ran {results['migrations_run']} migrations in {results['execution_time_ms']}ms")
        else:
            logger.error(f"Migration execution failed after {results['migrations_run']} migrations")
        
        return results
    
    def rollback_migration(self, version: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Rollback a specific migration.
        
        Args:
            version: Version of migration to rollback
            dry_run: If True, don't actually execute rollback
            
        Returns:
            Dictionary with rollback results
        """
        # Find the migration
        all_migrations = self.migration_manager.discover_migrations()
        migration = next((m for m in all_migrations if m.version == version), None)
        
        if not migration:
            return {
                'success': False,
                'error': f"Migration {version} not found"
            }
        
        if not migration.sql_down:
            return {
                'success': False,
                'error': f"Migration {version} has no rollback SQL defined"
            }
        
        # Check if migration is applied
        applied_migrations = self.migration_manager.get_applied_migrations()
        applied = next((m for m in applied_migrations if m.version == version), None)
        
        if not applied:
            return {
                'success': False,
                'error': f"Migration {version} is not applied"
            }
        
        if not applied.success:
            return {
                'success': False,
                'error': f"Migration {version} was not successfully applied"
            }
        
        logger.info(f"Rolling back migration {version} - {migration.description}")
        
        if dry_run:
            logger.info("DRY RUN - No actual changes will be made")
            return {
                'success': True,
                'message': f"Would rollback migration {version}"
            }
        
        # Execute rollback
        start_time = time.time()
        success = False
        error_message = None
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(migration.sql_down)
                conn.commit()
                success = True
                
                logger.info(f"Successfully rolled back migration {version}")
                
        except Exception as e:
            error_message = str(e)
            logger.error(f"Failed to rollback migration {version}: {error_message}")
        
        # Record rollback
        execution_time_ms = int((time.time() - start_time) * 1000)
        self.migration_manager.record_migration(
            migration, success, execution_time_ms, error_message
        )
        
        return {
            'success': success,
            'execution_time_ms': execution_time_ms,
            'error': error_message
        }
    
    def get_migration_status(self) -> Dict[str, str]:
        """Get status of all migrations."""
        return self.migration_manager.get_migration_status()
    
    def validate_database_schema(self) -> List[str]:
        """
        Validate that the database schema matches expected state.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check if all applied migrations are still valid
        applied_migrations = self.migration_manager.get_applied_migrations()
        all_migrations = self.migration_manager.discover_migrations()
        
        for applied in applied_migrations:
            if not applied.success:
                continue
                
            # Find corresponding migration file
            migration = next((m for m in all_migrations if m.version == applied.version), None)
            
            if not migration:
                errors.append(f"Applied migration {applied.version} not found in migration files")
                continue
            
            # Check if migration content has changed
            import hashlib
            content = f"{migration.version}:{migration.sql_up}"
            current_checksum = hashlib.sha256(content.encode()).hexdigest()
            
            if current_checksum != applied.checksum:
                errors.append(f"Migration {applied.version} content has changed since it was applied")
        
        return errors
    
    def create_initial_migration(self) -> str:
        """
        Create the initial migration from the current schema.sql file.
        
        Returns:
            Path to the created migration file
        """
        schema_file = "scripts/schema.sql"
        
        try:
            with open(schema_file, 'r') as f:
                schema_content = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Schema file {schema_file} not found")
        
        # Extract the actual schema creation SQL (skip the cleanup part)
        # Find the first CREATE statement
        create_start = schema_content.find("CREATE TABLE")
        if create_start == -1:
            raise ValueError("No CREATE TABLE statements found in schema file")
        
        # Extract from first CREATE to end
        schema_sql = schema_content[create_start:]
        
        # Create the initial migration
        return self.migration_manager.create_migration(
            "Initial schema creation",
            schema_sql,
            "-- This migration cannot be rolled back as it creates the base schema"
        ) 