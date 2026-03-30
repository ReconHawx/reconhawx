#!/usr/bin/env python3
"""
Script to update nuclei templates repository
This can be run as a cron job to keep templates up to date
"""

import asyncio
import sys
import os
import logging
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def update_nuclei_templates():
    """Update the nuclei templates repository"""
    try:
        from app.routes.nuclei_templates import _update_nuclei_repo, _get_repo_last_commit_date
        
        logger.info("Starting nuclei templates repository update...")
        
        # Update the repository
        success = await _update_nuclei_repo()
        
        if success:
            last_updated = await _get_repo_last_commit_date()
            logger.info(f"Nuclei templates repository updated successfully. Last commit: {last_updated}")
            return True
        else:
            logger.error("Failed to update nuclei templates repository")
            return False
            
    except Exception as e:
        logger.error(f"Error updating nuclei templates: {str(e)}")
        return False

def main():
    """Main function"""
    print(f"🔄 Nuclei Templates Update - {datetime.now().isoformat()}")
    print("=" * 60)
    
    success = asyncio.run(update_nuclei_templates())
    
    if success:
        print("✅ Update completed successfully")
        sys.exit(0)
    else:
        print("❌ Update failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 