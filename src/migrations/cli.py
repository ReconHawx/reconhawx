#!/usr/bin/env python
"""
Command Line Interface for Database Migrations

This module provides a CLI for managing database migrations including:
- Running migrations
- Checking migration status
- Creating new migrations
- Rolling back migrations
- Validation and dry-run capabilities
"""

import argparse
import logging
import sys
import os
from typing import Optional
from pathlib import Path

from .migration_runner import MigrationRunner
from .migration_manager import MigrationManager


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def get_db_url(port: Optional[int] = None) -> str:
    """Get database URL from environment or default, optionally overriding the port."""
    base_url = os.getenv('DATABASE_URL', 'postgresql://admin:password@localhost:5432/reconhawx')
    
    # If a custom port is provided, replace the port in the URL
    if port is not None:
        # Parse the URL and replace the port
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(base_url)
        
        # Replace the netloc (hostname:port) with the new port
        if '@' in parsed.netloc:
            # Format: user:pass@host:port
            auth_part, host_part = parsed.netloc.rsplit('@', 1)
            host = host_part.split(':')[0] if ':' in host_part else host_part
            new_netloc = f"{auth_part}@{host}:{port}"
        else:
            # Format: host:port
            host = parsed.netloc.split(':')[0] if ':' in parsed.netloc else parsed.netloc
            new_netloc = f"{host}:{port}"
        
        base_url = urlunparse((
            parsed.scheme,
            new_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
    
    return base_url


def get_migrations_dir() -> str:
    """Get migrations directory path."""
    return os.getenv('MIGRATIONS_DIR', 'src/migrations')


def status_command(args):
    """Show migration status."""
    runner = MigrationRunner(get_db_url(args.port), get_migrations_dir())
    
    print("Migration Status:")
    print("=" * 50)
    
    status_map = runner.get_migration_status()
    all_migrations = runner.migration_manager.discover_migrations()
    
    if not all_migrations:
        print("No migration files found.")
        return
    
    for migration in all_migrations:
        status = status_map.get(migration.version, 'unknown')
        status_icon = {
            'applied': '✓',
            'pending': '⏳',
            'failed': '✗',
            'unknown': '?'
        }.get(status, '?')
        
        print(f"{status_icon} {migration.version} - {migration.description}")
    
    # Show applied migrations details
    applied_migrations = runner.migration_manager.get_applied_migrations()
    if applied_migrations:
        print(f"\nApplied Migrations ({len(applied_migrations)}):")
        print("-" * 30)
        for applied in applied_migrations:
            print(f"  {applied.version} - {applied.applied_at.strftime('%Y-%m-%d %H:%M:%S')}")
            if not applied.success:
                print(f"    ERROR: {applied.error_message}")


def run_command(args):
    """Run pending migrations."""
    runner = MigrationRunner(get_db_url(args.port), get_migrations_dir())
    
    if args.dry_run:
        print("DRY RUN - No actual changes will be made")
    
    result = runner.run_migrations(
        target_version=args.target_version,
        dry_run=args.dry_run
    )
    
    if result['success']:
        print(f"✓ Successfully ran {result['migrations_run']} migrations")
        if result['execution_time_ms'] > 0:
            print(f"  Execution time: {result['execution_time_ms']}ms")
    else:
        print("✗ Migration execution failed")
        for error in result['errors']:
            print(f"  ERROR: {error}")
        sys.exit(1)


def rollback_command(args):
    """Rollback a specific migration."""
    runner = MigrationRunner(get_db_url(args.port), get_migrations_dir())
    
    if args.dry_run:
        print("DRY RUN - No actual changes will be made")
    
    result = runner.rollback_migration(args.version, dry_run=args.dry_run)
    
    if result['success']:
        print(f"✓ Successfully rolled back migration {args.version}")
        if 'execution_time_ms' in result and result['execution_time_ms'] > 0:
            print(f"  Execution time: {result['execution_time_ms']}ms")
    else:
        print(f"✗ Failed to rollback migration {args.version}")
        print(f"  ERROR: {result.get('error', 'Unknown error')}")
        sys.exit(1)


def create_command(args):
    """Create a new migration file."""
    manager = MigrationManager(get_migrations_dir(), get_db_url(args.port))
    
    # Read SQL from file if provided
    sql_up = ""
    sql_down = None
    
    if args.sql_file:
        with open(args.sql_file, 'r') as f:
            sql_up = f.read()
    else:
        # Create a template migration
        sql_up = f"""-- Migration: {args.description}
-- Add your SQL here

-- Example:
-- CREATE TABLE example_table (
--     id SERIAL PRIMARY KEY,
--     name VARCHAR(255) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );
"""
    
    if args.rollback_file:
        with open(args.rollback_file, 'r') as f:
            sql_down = f.read()
    
    file_path = manager.create_migration(args.description, sql_up, sql_down)
    print(f"✓ Created migration file: {file_path}")


def validate_command(args):
    """Validate migration files and database schema."""
    runner = MigrationRunner(get_db_url(args.port), get_migrations_dir())
    
    print("Validating migrations...")
    
    # Validate migration files
    validation_errors = runner.migration_manager.validate_migrations()
    if validation_errors:
        print("✗ Migration validation errors:")
        for error in validation_errors:
            print(f"  ERROR: {error}")
    else:
        print("✓ Migration files are valid")
    
    # Validate database schema
    schema_errors = runner.validate_database_schema()
    if schema_errors:
        print("✗ Database schema validation errors:")
        for error in schema_errors:
            print(f"  ERROR: {error}")
    else:
        print("✓ Database schema is valid")
    
    if validation_errors or schema_errors:
        sys.exit(1)


def init_command(args):
    """Initialize migration system with current schema."""
    runner = MigrationRunner(get_db_url(args.port), get_migrations_dir())
    
    print("Creating initial migration from current schema...")
    
    try:
        file_path = runner.create_initial_migration()
        print(f"✓ Created initial migration: {file_path}")
        print("\nNext steps:")
        print("1. Review the generated migration file")
        print("2. Run 'migrate run' to apply the migration")
    except Exception as e:
        print(f"✗ Failed to create initial migration: {e}")
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Database Migration Management Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  migrate status                    # Show migration status
  migrate run                      # Run all pending migrations
  migrate run --dry-run            # Preview pending migrations
  migrate --port 5433 run          # Run on custom port
  migrate run --target-version 2.0.0  # Run up to specific version
  migrate create "Add user table"   # Create new migration
  migrate rollback 1.0.0           # Rollback specific migration
  migrate --port 5433 validate     # Validate on custom port
  migrate init                      # Initialize with current schema
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--port', type=int, default=None,
                       help='PostgreSQL port (overrides port in DATABASE_URL)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show migration status')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run pending migrations')
    run_parser.add_argument('--target-version', help='Target migration version')
    run_parser.add_argument('--dry-run', action='store_true',
                           help='Preview changes without applying them')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback a migration')
    rollback_parser.add_argument('version', help='Migration version to rollback')
    rollback_parser.add_argument('--dry-run', action='store_true',
                                help='Preview rollback without applying it')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new migration')
    create_parser.add_argument('description', help='Migration description')
    create_parser.add_argument('--sql-file', help='SQL file for migration')
    create_parser.add_argument('--rollback-file', help='SQL file for rollback')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate migrations')
    
    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize migration system')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Execute command
    command_handlers = {
        'status': status_command,
        'run': run_command,
        'rollback': rollback_command,
        'create': create_command,
        'validate': validate_command,
        'init': init_command
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == '__main__':
    main() 