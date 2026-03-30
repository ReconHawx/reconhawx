#!/usr/bin/env python3
"""
Database Migration CLI Tool

This script provides a command-line interface for managing database migrations.
It can be run directly or imported as a module.

Usage:
    python migrate.py status
    python migrate.py run
    python migrate.py create "Add new table"
    python migrate.py rollback 1.0.0
"""

import sys
import os

# Add the parent directory to the path so we can import the migrations module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrations.cli import main

if __name__ == '__main__':
    main() 