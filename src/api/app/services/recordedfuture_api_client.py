"""
RecordedFuture API Client

This module provides a client for interacting with the RecordedFuture API,
specifically for managing playbook alert status changes.
"""

import aiohttp
import logging
from typing import Dict, Any, Optional, List
from repository.program_repo import ProgramRepository

logger = logging.getLogger(__name__)


class RecordedFutureAPIClient:
    """Client for RecordedFuture API operations"""
    
    def __init__(self):
        self.base_url = "https://api.recordedfuture.com"
        self.session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()
    
    async def initialize(self):
        """Initialize the HTTP session with connection pooling"""
        if self.session is None or self.session.closed:
            if self._connector is None or self._connector.closed:
                self._connector = aiohttp.TCPConnector(
                    limit=10,  # Total connection pool size
                    limit_per_host=5,  # Max connections per host
                    keepalive_timeout=30,
                    enable_cleanup_closed=True
                )
            
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(
                connector=self._connector,
                timeout=timeout
            )
            logger.debug("Initialized RecordedFuture API client session")
    
    async def shutdown(self):
        """Shutdown the HTTP session and connector"""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        
        if self._connector and not self._connector.closed:
            await self._connector.close()
            self._connector = None
        
        logger.debug("RecordedFuture API client session closed")
    
    async def change_playbook_alert_status(
        self, 
        program_name: str, 
        playbook_alert_id: str, 
        new_status: str,
        user_rf_uhash: Optional[str] = None,
        log_entry: Optional[str] = None,
        added_actions_taken: Optional[List[str]] = None,
        unassign: bool = False
    ) -> Dict[str, Any]:
        """
        Change the status of a RecordedFuture playbook alert
        
        Args:
            program_name: Name of the program to get API key from
            playbook_alert_id: ID of the playbook alert to update
            new_status: New status to set for the alert
            user_rf_uhash: User RF Uhash (optional, for assignment)
            log_entry: Log entry
            added_actions_taken: Added actions taken
            unassign: If True, explicitly unassign the alert (set assignee to null)
        Returns:
            Dict containing the API response
            
        Raises:
            ValueError: If program not found or API key missing
            aiohttp.ClientError: If API request fails
        """
        if not program_name:
            raise ValueError("program_name is required")
        
        if not playbook_alert_id:
            raise ValueError("playbook_alert_id is required")
        
        if not new_status:
            raise ValueError("new_status is required")
        
        # Get program settings to retrieve API key
        program_data = await ProgramRepository.get_program_by_name(program_name)
        if not program_data:
            raise ValueError(f"Program '{program_name}' not found")
        
        rf_token = program_data.get('recordedfuture_api_key')
        if not rf_token:
            raise ValueError(f"RecordedFuture API key not configured for program '{program_name}'")
        
        # Ensure session is initialized
        await self.initialize()
        
        # Prepare request
        url = f"{self.base_url}/playbook-alert/common/{playbook_alert_id}"
        headers = {
            "Accept": "application/json",
            "X-RFToken": rf_token,
            "Content-Type": "application/json"
        }
        
        payload = {
            "status": new_status
        }
        logger.info(f"Changing RecordedFuture playbook alert {playbook_alert_id} status to '{new_status}' for program '{program_name}'")
        
        # Handle assignment/unassignment
        if unassign:
            payload["assignee"] = None
            logger.info(f"Unassigning playbook alert {playbook_alert_id}")
        elif user_rf_uhash:
            payload["assignee"] = "uhash:" + user_rf_uhash
            logger.info(f"Assigning playbook alert {playbook_alert_id} to user {user_rf_uhash}")
        
        if log_entry:
            payload["log_entry"] = log_entry
            logger.info(f"Adding log entry to playbook alert {playbook_alert_id}: {log_entry}")
        if added_actions_taken:
            payload["added_actions_taken"] = added_actions_taken
            logger.info(f"Adding added actions taken to playbook alert {playbook_alert_id}: {added_actions_taken}")
        
        try:
            async with self.session.put(url, json=payload, headers=headers) as response:
                response_data = await response.json()
                
                if response.status == 200:
                    logger.info(f"Successfully changed playbook alert {playbook_alert_id} status to '{new_status}'")
                    return {
                        "success": True,
                        "status_code": response.status,
                        "data": response_data,
                        "message": f"Playbook alert status changed to '{new_status}'"
                    }
                else:
                    error_msg = f"Failed to change playbook alert status: {response.status} - {response_data}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "status_code": response.status,
                        "error": response_data,
                        "message": f"API request failed with status {response.status}"
                    }
                    
        except aiohttp.ClientError as e:
            error_msg = f"HTTP client error changing playbook alert status: {str(e)}"
            logger.error(error_msg)
            raise aiohttp.ClientError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error changing playbook alert status: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e
    
    async def get_playbook_alert_status(
        self, 
        program_name: str, 
        playbook_alert_id: str
    ) -> Dict[str, Any]:
        """
        Get the current status of a RecordedFuture playbook alert
        
        Args:
            program_name: Name of the program to get API key from
            playbook_alert_id: ID of the playbook alert to query
            
        Returns:
            Dict containing the alert status information
            
        Raises:
            ValueError: If program not found or API key missing
            aiohttp.ClientError: If API request fails
        """
        if not program_name:
            raise ValueError("program_name is required")
        
        if not playbook_alert_id:
            raise ValueError("playbook_alert_id is required")
        
        # Get program settings to retrieve API key
        program_data = await ProgramRepository.get_program_by_name(program_name)
        if not program_data:
            raise ValueError(f"Program '{program_name}' not found")
        
        rf_token = program_data.get('recordedfuture_api_key')
        if not rf_token:
            raise ValueError(f"RecordedFuture API key not configured for program '{program_name}'")
        
        # Ensure session is initialized
        await self.initialize()
        
        # Prepare request
        url = f"{self.base_url}/playbook-alert/common/{playbook_alert_id}"
        headers = {
            "Accept": "application/json",
            "X-RFToken": rf_token,
            "Content-Type": "application/json"
        }
        
        logger.info(f"Getting RecordedFuture playbook alert {playbook_alert_id} status for program '{program_name}'")
        
        try:
            async with self.session.get(url, headers=headers) as response:
                response_data = await response.json()
                
                if response.status == 200:
                    logger.info(f"Successfully retrieved playbook alert {playbook_alert_id} status")
                    return {
                        "success": True,
                        "status_code": response.status,
                        "data": response_data,
                        "message": "Playbook alert status retrieved successfully"
                    }
                else:
                    error_msg = f"Failed to get playbook alert status: {response.status} - {response_data}"
                    logger.error(error_msg)
                    return {
                        "success": False,
                        "status_code": response.status,
                        "error": response_data,
                        "message": f"API request failed with status {response.status}"
                    }
                    
        except aiohttp.ClientError as e:
            error_msg = f"HTTP client error getting playbook alert status: {str(e)}"
            logger.error(error_msg)
            raise aiohttp.ClientError(error_msg) from e
        except Exception as e:
            error_msg = f"Unexpected error getting playbook alert status: {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg) from e


# Convenience function for easy usage
async def change_playbook_alert_status(
    program_name: str, 
    alert_id: str, 
    new_status: str,
    user_rf_uhash: Optional[str] = None,
    log_entry: Optional[str] = None,
    added_actions_taken: Optional[List[str]] = None,
    unassign: bool = False
) -> Dict[str, Any]:
    """
    Convenience function to change a playbook alert status
    
    Args:
        program_name: Name of the program to get API key from
        alert_id: ID of the playbook alert to update
        new_status: New status to set for the alert
        user_rf_uhash: User RF Uhash (optional, for assignment)
        log_entry: Log entry
        added_actions_taken: Added actions taken
        unassign: If True, explicitly unassign the alert (set assignee to null)
    Returns:
        Dict containing the API response
    """
    # Map alert_id to playbook_alert_id for the client method
    client_payload = {
        "program_name": program_name,
        "playbook_alert_id": alert_id,  # Map alert_id to playbook_alert_id
        "new_status": new_status,
        "unassign": unassign
    }
    if user_rf_uhash:
        client_payload["user_rf_uhash"] = user_rf_uhash
    if log_entry:
        client_payload["log_entry"] = log_entry
    if added_actions_taken:
        client_payload["added_actions_taken"] = added_actions_taken
    async with RecordedFutureAPIClient() as client:
        return await client.change_playbook_alert_status(
            **client_payload
        )


async def get_playbook_alert_status(
    program_name: str, 
    alert_id: str
) -> Dict[str, Any]:
    """
    Convenience function to get a playbook alert status
    
    Args:
        program_name: Name of the program to get API key from
        alert_id: ID of the playbook alert to query
        
    Returns:
        Dict containing the alert status information
    """
    async with RecordedFutureAPIClient() as client:
        return await client.get_playbook_alert_status(
            program_name, 
            alert_id
        )
