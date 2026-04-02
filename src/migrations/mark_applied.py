#!/usr/bin/env python3
"""
Utility script to mark migrations as applied without running them.
This is useful when setting up migrations for an existing database.
"""

import sys
import os
import logging
from datetime import datetime

# Add the parent directory to the path so we can import the migrations module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.migration_manager import MigrationManager

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

def get_db_url():
    """Get database URL from environment or default."""
    return os.getenv('DATABASE_URL', 'postgresql://admin:password@localhost:5432/recon_db')

def get_migrations_dir():
    """Get migrations directory path."""
    return os.getenv('MIGRATIONS_DIR', os.path.dirname(os.path.abspath(__file__)))

def mark_migration_applied(version: str, description: str = None):
    """Mark a specific migration as applied."""
    manager = MigrationManager(get_migrations_dir(), get_db_url())
    
    # Find the migration
    all_migrations = manager.discover_migrations()
    migration = next((m for m in all_migrations if m.version == version), None)
    
    if not migration:
        print(f"❌ Migration {version} not found")
        return False
    
    # Check if already applied
    applied_migrations = manager.get_applied_migrations()
    already_applied = next((m for m in applied_migrations if m.version == version), None)
    
    if already_applied:
        print(f"⚠️  Migration {version} is already marked as applied")
        return True
    
    # Mark as applied
    import hashlib
    content = f"{migration.version}:{migration.sql_up}"
    checksum = hashlib.sha256(content.encode()).hexdigest()
    
    # Record the migration as successful
    manager.record_migration(
        migration=migration,
        success=True,
        execution_time_ms=0,
        error_message=None
    )
    
    print(f"✅ Marked migration {version} as applied")
    print(f"   Description: {migration.description}")
    print(f"   Checksum: {checksum[:16]}...")
    
    return True

def mark_all_pending_applied(yes: bool = False):
    """Mark all pending migrations as applied."""
    manager = MigrationManager(get_migrations_dir(), get_db_url())
    
    pending_migrations = manager.get_pending_migrations()
    
    if not pending_migrations:
        print("ℹ️  No pending migrations to mark")
        return
    
    print(f"Found {len(pending_migrations)} pending migrations:")
    for migration in pending_migrations:
        print(f"  - {migration.version}: {migration.description}")
    
    if not yes:
        response = input("\nMark all these migrations as applied? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return
    
    for migration in pending_migrations:
        mark_migration_applied(migration.version)

def main():
    """Main function."""
    setup_logging()
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python mark_applied.py <version>     # Mark specific migration as applied")
        print("  python mark_applied.py --all         # Mark all pending migrations as applied")
        print("  python mark_applied.py --all --yes   # Same, non-interactive (CI / scripts)")
        print("  python mark_applied.py --list        # List all migrations and their status")
        return
    
    command = sys.argv[1]
    
    if command == "--all":
        non_interactive = len(sys.argv) > 2 and sys.argv[2] == "--yes"
        mark_all_pending_applied(yes=non_interactive)
    elif command == "--list":
        manager = MigrationManager(get_migrations_dir(), get_db_url())
        all_migrations = manager.discover_migrations()
        applied_migrations = manager.get_applied_migrations()
        applied_versions = {m.version for m in applied_migrations}
        
        print("Migration Status:")
        print("=" * 50)
        for migration in all_migrations:
            status = "✅ Applied" if migration.version in applied_versions else "⏳ Pending"
            print(f"{status} {migration.version} - {migration.description}")
    else:
        # Treat as version
        version = command
        mark_migration_applied(version)

if __name__ == '__main__':
    main() 