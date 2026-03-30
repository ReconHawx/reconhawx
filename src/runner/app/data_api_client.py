#!/usr/bin/env python3
"""
Enhanced Data API Client

This module provides an enhanced client for communicating with the Data API,
specifically for asset posting and job status tracking.
"""

import logging
import aiohttp
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")

class DataAPIClient:
    """
    Enhanced client for communicating with the Data API.
    
    This client handles asset posting and job status tracking for the
    Asset Processing Coordinator.
    """
    
    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.base_timeout = timeout  # Store base timeout
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.shutdown()
    
    async def initialize(self):
        """Initialize the HTTP session"""
        if self.session is None:
            timeout_config = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout_config,
                headers=self._headers
            )
            logger.debug(f"Initialized Data API client for {self.base_url}")

    async def shutdown(self):
        """Shutdown the HTTP session with proper cleanup"""
        if self.session:
            # First close the session gracefully
            await self.session.close()
            
            # Then wait for the underlying connector to finish cleanup
            connector = self.session.connector
            if connector and hasattr(connector, 'close'):
                await connector.close()
            
            # Wait for all connections to be properly closed
            import asyncio
            await asyncio.sleep(0.25)
            
            self.session = None
            logger.debug("Data API client session and connector closed")
    
    def _convert_asset_keys_to_strings(self, assets: Dict[Any, List[Any]]) -> Dict[str, List[Any]]:
        """
        Convert AssetType enum keys to string keys for API serialization.
        
        Args:
            assets: Dictionary with potentially AssetType enum keys
            
        Returns:
            Dictionary with string keys
        """
        converted_assets = {}
        for key, asset_list in assets.items():
            # Convert enum keys to strings, handle both AssetType enums and other types
            if hasattr(key, 'value'):
                # This is an enum, use its value
                string_key = key.value
            else:
                # This is already a string or other type, convert to string
                string_key = str(key)
            
            converted_assets[string_key] = asset_list
        
        return converted_assets
    
    def _convert_assets_to_dicts(self, assets: Dict[str, List[Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Convert asset objects to dictionaries for JSON serialization.
        
        Args:
            assets: Dictionary with asset lists
            
        Returns:
            Dictionary with asset lists converted to dictionaries
        """
        def convert_value_to_serializable(value):
            """Recursively convert values to JSON serializable format"""
            if hasattr(value, 'isoformat'):
                # Handle datetime objects
                return value.isoformat()
            elif isinstance(value, list):
                # Handle lists recursively
                return [convert_value_to_serializable(item) for item in value]
            elif isinstance(value, dict):
                # Handle dictionaries recursively
                return {k: convert_value_to_serializable(v) for k, v in value.items()}
            elif hasattr(value, 'to_dict'):
                # Use Pydantic model's to_dict method
                return convert_value_to_serializable(value.to_dict())
            elif hasattr(value, 'model_dump'):
                # Use Pydantic v2 model_dump method, excluding None values to prevent overwriting existing data
                return convert_value_to_serializable(value.model_dump(by_alias=True, exclude_none=True))
            elif hasattr(value, '__dict__'):
                # Convert object to dictionary recursively
                return convert_value_to_serializable(value.__dict__)
            else:
                # Primitive type, return as-is
                return value
        
        converted_assets = {}
        for asset_type, asset_list in assets.items():
            converted_list = []
            for asset in asset_list:
                if hasattr(asset, 'to_dict'):
                    # Use Pydantic model's to_dict method
                    asset_dict = asset.to_dict()
                    # Convert any remaining datetime objects
                    asset_dict = convert_value_to_serializable(asset_dict)
                    converted_list.append(asset_dict)
                elif hasattr(asset, 'model_dump'):
                    # Use Pydantic v2 model_dump method, excluding None values to prevent overwriting existing data
                    asset_dict = asset.model_dump(by_alias=True, exclude_none=True)
                    # Convert any remaining datetime objects
                    asset_dict = convert_value_to_serializable(asset_dict)
                    converted_list.append(asset_dict)
                elif hasattr(asset, '__dict__'):
                    # Fallback: convert object to dictionary
                    asset_dict = asset.__dict__.copy()
                    # Convert all values to serializable format
                    asset_dict = convert_value_to_serializable(asset_dict)
                    converted_list.append(asset_dict)
                elif isinstance(asset, dict):
                    # Asset is already a dictionary, but we need to ensure it's serializable
                    asset_dict = convert_value_to_serializable(asset)
                    converted_list.append(asset_dict)
                else:
                    # Already a dictionary or primitive type
                    converted_list.append(asset)
            
            converted_assets[asset_type] = converted_list
        
        # Final validation: ensure the entire structure is JSON serializable
        try:
            import json
            json.dumps(converted_assets)
        except (TypeError, ValueError) as e:
            logger.warning(f"JSON validation failed after conversion: {e}")
            # Try to fix any remaining serialization issues
            converted_assets = self._deep_clean_for_json(converted_assets)
        
        return converted_assets
    
    def _deep_clean_for_json(self, obj):
        """Deep clean object to ensure JSON serialization"""
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                try:
                    cleaned[str(k)] = self._deep_clean_for_json(v)
                except Exception as e:
                    logger.warning(f"Failed to serialize key {k}: {e}")
                    cleaned[str(k)] = str(v)
            return cleaned
        elif isinstance(obj, list):
            return [self._deep_clean_for_json(item) for item in obj]
        elif hasattr(obj, 'isoformat'):
            # Handle datetime objects
            try:
                iso_str = obj.isoformat()
                return iso_str
            except Exception as dt_e:
                logger.warning(f"Failed to convert datetime {obj} to ISO string: {dt_e}")
                return str(obj)
        elif hasattr(obj, '__dict__'):
            # Handle objects with __dict__
            return self._deep_clean_for_json(obj.__dict__)
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        elif isinstance(obj, datetime):
            # Handle datetime objects directly
            return obj.isoformat()
        else:
            # Convert anything else to string
            logger.debug(f"Converting unknown type {type(obj)} to string: {obj}")
            return str(obj)
    
    async def post_assets_unified(self, assets: Dict[Any, List[Any]], program_name: str,
                                 workflow_id: str = None, step_name: str = None) -> Dict[str, Any]:
        """
        Post assets using the new unified API endpoint.

        Args:
            assets: Dictionary of assets by type (keys can be AssetType enums)
            program_name: Name of the program for the assets
            workflow_id: Optional workflow ID for tracking
            step_name: Optional step name for tracking

        Returns:
            API response containing processing mode and job_id if background processing
        """
        await self.initialize()

        try:
            # Convert AssetType enum keys to strings for API serialization
            converted_assets = self._convert_asset_keys_to_strings(assets)

            # Convert asset objects to dictionaries for JSON serialization
            serializable_assets = self._convert_assets_to_dicts(converted_assets)

            # Prepare the unified request payload
            payload = {
                "program_name": program_name,
                "assets": serializable_assets
            }

            # Add optional metadata
            if workflow_id:
                payload["workflow_id"] = workflow_id
            if step_name:
                payload["step_name"] = step_name

            # Calculate total asset count for dynamic timeout
            total_asset_count = sum(len(asset_list) for asset_list in serializable_assets.values())
            dynamic_timeout = self._calculate_timeout_for_assets(total_asset_count)

            logger.debug(f"Posting {total_asset_count} assets to unified API for program: {program_name} with {dynamic_timeout}s timeout")

            # Create timeout config for this specific request
            timeout = aiohttp.ClientTimeout(total=dynamic_timeout)
            async with self.session.post(
                f"{self.base_url}/assets",
                json=payload,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Assets posted to unified API successfully: {result.get('processing_mode', 'unknown')} mode")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Unified API error {response.status}: {error_text}")
                    raise Exception(f"Unified API error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error posting assets to unified API: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error posting assets to unified API: {e}")
            raise
    
    async def post_wpscan_findings_unified(self, wpscan_findings: List[Any], program_name: str,
                                          workflow_id: str = None, step_name: str = None, execution_id: str = None) -> Dict[str, Any]:
        """
        Post WPScan findings using the dedicated WPScan findings API endpoint.

        Args:
            wpscan_findings: List of WPScan findings to post
            program_name: Name of the program for the findings
            workflow_id: Optional workflow ID for tracking
            step_name: Optional step name for tracking
            execution_id: Optional workflow execution ID for tracking

        Returns:
            API response containing processing mode and job_id if background processing
        """
        logger.info(f"🔄 WPSCAN API CLIENT: post_wpscan_findings_unified called with {len(wpscan_findings)} findings, program_name={program_name}")
        await self.initialize()

        try:
            # Convert findings objects to dictionaries for JSON serialization
            serializable_findings = []
            for finding in wpscan_findings:
                logger.debug(f"Processing WPScan finding type: {type(finding)}")
                if hasattr(finding, 'model_dump'):
                    # Pydantic model - model_dump() should handle datetime serialization
                    logger.debug("Using model_dump() for Pydantic model")
                    finding_dict = finding.model_dump()
                    logger.debug(f"model_dump() result type: {type(finding_dict)}, keys: {list(finding_dict.keys()) if isinstance(finding_dict, dict) else 'Not dict'}")
                    serializable_findings.append(finding_dict)
                elif hasattr(finding, '__dict__'):
                    # Regular object with __dict__
                    logger.debug("Using __dict__ for regular object")
                    serializable_findings.append(self._deep_clean_for_json(finding.__dict__))
                elif isinstance(finding, dict):
                    # Already a dictionary
                    logger.debug("Finding is already a dict, deep cleaning")
                    serializable_findings.append(self._deep_clean_for_json(finding))
                else:
                    # Convert to string as fallback
                    logger.warning(f"Unknown finding type {type(finding)}, converting to string")
                    continue

            # Prepare the WPScan findings request payload
            payload = {
                "program_name": program_name,
                "findings": {"wpscan": serializable_findings}
            }

            # Add optional metadata
            if workflow_id:
                payload["workflow_id"] = workflow_id
            if step_name:
                payload["step_name"] = step_name
            if execution_id:
                payload["execution_id"] = execution_id

            # Final validation: ensure the entire payload is JSON serializable
            payload = self._deep_clean_for_json(payload)

            try:
                import json
                json.dumps(payload)
                logger.debug("WPScan payload JSON validation passed")
            except (TypeError, ValueError) as e:
                logger.warning(f"JSON validation failed after cleaning: {e}")
                raise e

            # Calculate total finding count for dynamic timeout
            finding_count = len(serializable_findings)
            dynamic_timeout = self._calculate_timeout_for_assets(finding_count)

            logger.debug(f"Posting {finding_count} WPScan findings to dedicated API for program: {program_name} with {dynamic_timeout}s timeout")

            # Create timeout config for this specific request
            timeout = aiohttp.ClientTimeout(total=dynamic_timeout)
            async with self.session.post(
                f"{self.base_url}/findings/wpscan",
                json=payload,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"WPScan findings posted to dedicated API successfully: {result.get('processing_mode', 'unknown')} mode")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"WPScan API error {response.status}: {error_text}")
                    raise Exception(f"WPScan API error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error posting WPScan findings to dedicated API: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error posting WPScan findings to dedicated API: {e}")
            raise

    async def post_nuclei_findings_unified(self, nuclei_findings: List[Any], program_name: str,
                                          workflow_id: str = None, step_name: str = None, execution_id: str = None) -> Dict[str, Any]:
        """
        Post nuclei findings using the dedicated nuclei findings API endpoint.

        Args:
            nuclei_findings: List of nuclei findings to post
            program_name: Name of the program for the findings
            workflow_id: Optional workflow ID for tracking
            step_name: Optional step name for tracking
            execution_id: Optional workflow execution ID for tracking

        Returns:
            API response containing processing mode and job_id if background processing
        """
        logger.info(f"🔄 NUCLEI API CLIENT: post_nuclei_findings_unified called with {len(nuclei_findings)} findings, program_name={program_name}")
        await self.initialize()

        try:
            # Convert findings objects to dictionaries for JSON serialization
            serializable_findings = []
            for finding in nuclei_findings:
                if hasattr(finding, 'model_dump'):
                    # Pydantic model - model_dump() should handle datetime serialization
                    finding_dict = finding.model_dump()
                    # Don't double-process Pydantic models - model_dump() should handle serialization
                    serializable_findings.append(finding_dict)
                elif hasattr(finding, '__dict__'):
                    # Regular object with __dict__
                    logger.debug("Using __dict__ for regular object")
                    serializable_findings.append(self._deep_clean_for_json(finding.__dict__))
                elif isinstance(finding, dict):
                    # Already a dictionary
                    logger.debug("Finding is already a dict, deep cleaning")
                    serializable_findings.append(self._deep_clean_for_json(finding))
                else:
                    # Convert to string as fallback
                    logger.warning(f"Unknown finding type {type(finding)}, converting to string")
                    continue

            # Prepare the nuclei findings request payload
            payload = {
                "program_name": program_name,
                "findings": {"nuclei": serializable_findings}
            }

            logger.debug(f"Payload before deep cleaning - findings count: {len(serializable_findings)}")
            logger.debug(f"First finding keys: {list(serializable_findings[0].keys()) if serializable_findings else 'No findings'}")
            if serializable_findings:
                created_at = serializable_findings[0].get('created_at')
                updated_at = serializable_findings[0].get('updated_at')
                logger.debug(f"First finding created_at: {created_at} (type: {type(created_at)})")
                logger.debug(f"First finding updated_at: {updated_at} (type: {type(updated_at)})")

            # Add optional metadata
            if workflow_id:
                payload["workflow_id"] = workflow_id
            if step_name:
                payload["step_name"] = step_name
            if execution_id:
                payload["execution_id"] = execution_id

            # Final validation: ensure the entire payload is JSON serializable
            # First, apply deep cleaning to handle datetime objects and other non-serializable types
            payload = self._deep_clean_for_json(payload)

            try:
                import json
                json.dumps(payload)
                logger.debug("Nuclei payload JSON validation passed")
            except (TypeError, ValueError) as e:
                logger.warning(f"JSON validation still failed after cleaning: {e}")
                # Log the problematic payload structure for debugging
                logger.debug(f"Payload structure: {list(payload.keys())}")
                if 'findings' in payload:
                    logger.debug(f"Findings keys: {list(payload['findings'].keys())}")
                    if 'nuclei' in payload['findings'] and payload['findings']['nuclei']:
                        logger.debug(f"First nuclei finding keys: {list(payload['findings']['nuclei'][0].keys()) if isinstance(payload['findings']['nuclei'][0], dict) else 'Not a dict'}")
                        logger.debug(f"First nuclei finding sample: {str(payload['findings']['nuclei'][0])[:200]}")
                raise e

            # Calculate total finding count for dynamic timeout
            finding_count = len(serializable_findings)
            dynamic_timeout = self._calculate_timeout_for_assets(finding_count)

            logger.debug(f"Posting {finding_count} nuclei findings to dedicated API for program: {program_name} with {dynamic_timeout}s timeout")

            # Create timeout config for this specific request
            timeout = aiohttp.ClientTimeout(total=dynamic_timeout)
            async with self.session.post(
                f"{self.base_url}/findings/nuclei",
                json=payload,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Nuclei findings posted to dedicated API successfully: {result.get('processing_mode', 'unknown')} mode")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Nuclei API error {response.status}: {error_text}")
                    raise Exception(f"Nuclei API error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error posting nuclei findings to dedicated API: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error posting nuclei findings to dedicated API: {e}")
            raise

    async def post_typosquat_domain_findings(self, typosquat_findings: List[Any], program_name: str) -> Dict[str, Any]:
        """
        Post typosquat domain findings to /findings/typosquat endpoint.

        Args:
            typosquat_findings: List of typosquat domain findings to post
            program_name: Name of the program for the findings

        Returns:
            API response with job status or error information
        """
        if not typosquat_findings:
            logger.warning("No typosquat domain findings to post")
            return {"status": "error", "error": "No findings to post"}

        await self.initialize()

        try:
            # Convert findings objects to dictionaries for JSON serialization
            serializable_findings = []
            for finding in typosquat_findings:
                if hasattr(finding, 'model_dump'):
                    finding_dict = finding.model_dump(by_alias=True, exclude_none=True)
                    serializable_findings.append(self._deep_clean_for_json(finding_dict))
                elif hasattr(finding, 'to_dict'):
                    serializable_findings.append(self._deep_clean_for_json(finding.to_dict()))
                elif hasattr(finding, '__dict__'):
                    serializable_findings.append(self._deep_clean_for_json(finding.__dict__))
                else:
                    serializable_findings.append(self._deep_clean_for_json(finding))

            payload = {
                "program_name": program_name,
                "findings": {"typosquat_domain": serializable_findings}
            }

            finding_count = len(serializable_findings)
            dynamic_timeout = min(max(30, finding_count * 2), 300)

            logger.debug(f"Posting {finding_count} typosquat domain findings to /findings/typosquat for program: {program_name}")

            async with self.session.post(
                f"{self.base_url}/findings/typosquat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=dynamic_timeout)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Typosquat domain findings posted successfully: {result.get('processing_mode', 'unknown')} mode")
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"API error posting typosquat domain findings: {response.status} - {error_text}")
                    return {"status": "error", "error": f"API error {response.status}: {error_text}"}

        except aiohttp.ClientError as e:
            logger.error(f"Network error posting typosquat domain findings: {e}")
            return {"status": "error", "error": f"Network error: {e}"}
        except Exception as e:
            logger.exception(f"Unexpected error posting typosquat domain findings: {e}")
            return {"status": "error", "error": f"Unexpected error: {e}"}

    async def post_broken_link_findings(self, broken_link_findings: List[Any], program_name: str) -> bool:
        """
        Post broken link findings to /findings/broken-links endpoint.

        Args:
            broken_link_findings: List of broken link findings to post
            program_name: Name of the program for the findings

        Returns:
            True if successful, False otherwise
        """
        if not broken_link_findings:
            logger.warning("No broken link findings to post")
            return True

        await self.initialize()

        try:
            # Convert findings objects to dictionaries for JSON serialization
            serializable_findings = []
            for finding in broken_link_findings:
                if isinstance(finding, dict):
                    serializable_findings.append(self._deep_clean_for_json(finding))
                elif hasattr(finding, 'model_dump'):
                    finding_dict = finding.model_dump(by_alias=True, exclude_none=True)
                    serializable_findings.append(self._deep_clean_for_json(finding_dict))
                elif hasattr(finding, 'to_dict'):
                    serializable_findings.append(self._deep_clean_for_json(finding.to_dict()))
                elif hasattr(finding, '__dict__'):
                    serializable_findings.append(self._deep_clean_for_json(finding.__dict__))
                else:
                    serializable_findings.append(self._deep_clean_for_json(finding))

            finding_count = len(serializable_findings)
            dynamic_timeout = min(max(30, finding_count * 2), 300)

            logger.debug(f"Posting {finding_count} broken link findings to /findings/broken-links for program: {program_name}")

            # Post each finding individually
            success_count = 0
            for finding in serializable_findings:
                try:
                    finding['program_name'] = program_name
                    async with self.session.post(
                        f"{self.base_url}/findings/broken-links",
                        json=finding,
                        timeout=aiohttp.ClientTimeout(total=dynamic_timeout)
                    ) as response:
                        if response.status in [200, 201]:
                            success_count += 1
                        else:
                            error_text = await response.text()
                            logger.error(f"API error posting broken link finding: {response.status} - {error_text}")
                except Exception as e:
                    logger.error(f"Error posting broken link finding: {e}")

            if success_count == finding_count:
                logger.debug(f"All {finding_count} broken link findings posted successfully")
                return True
            else:
                logger.warning(f"Posted {success_count}/{finding_count} broken link findings")
                return False

        except aiohttp.ClientError as e:
            logger.error(f"Network error posting broken link findings: {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error posting broken link findings: {e}")
            return False

    async def post_typosquat_url_findings(self, typosquat_findings: List[Any], program_name: str) -> Dict[str, Any]:
        """
        Post typosquat URL findings to /findings/typosquat-url endpoint.
        This endpoint accepts one finding at a time, so we send each individually.

        Args:
            typosquat_findings: List of typosquat URL findings to post
            program_name: Name of the program for the findings

        Returns:
            API response with job status or error information (aggregated from all individual posts)
        """
        if not typosquat_findings:
            logger.warning("No typosquat URL findings to post")
            return {"status": "error", "error": "No findings to post"}

        await self.initialize()

        try:
            finding_count = len(typosquat_findings)
            logger.debug(f"Posting {finding_count} typosquat URL findings individually to /findings/typosquat-url for program: {program_name}")

            success_count = 0
            failed_count = 0
            errors = []

            # Post each finding individually
            for idx, finding in enumerate(typosquat_findings):
                try:
                    # Convert finding to dictionary
                    if hasattr(finding, 'model_dump'):
                        finding_dict = finding.model_dump(by_alias=True, exclude_none=True)
                        finding_dict = self._deep_clean_for_json(finding_dict)
                    elif hasattr(finding, 'to_dict'):
                        finding_dict = self._deep_clean_for_json(finding.to_dict())
                    elif hasattr(finding, '__dict__'):
                        finding_dict = self._deep_clean_for_json(finding.__dict__)
                    else:
                        finding_dict = self._deep_clean_for_json(finding)

                    # API requires typosquat_domain or typosquat_domain_id; runner model uses typo_domain / hostname
                    if not finding_dict.get('typosquat_domain') and not finding_dict.get('typosquat_domain_id'):
                        domain = finding_dict.get('typo_domain') or finding_dict.get('hostname')
                        if domain:
                            finding_dict['typosquat_domain'] = domain
                        else:
                            logger.warning(f"Typosquat URL finding {idx+1}/{finding_count} has no typosquat_domain/typosquat_domain_id/typo_domain/hostname, skipping")
                            failed_count += 1
                            errors.append(f"Finding {idx+1}: missing typosquat domain reference")
                            continue

                    # Add program_name to each finding
                    finding_dict['program_name'] = program_name

                    # Post individual finding
                    async with self.session.post(
                        f"{self.base_url}/findings/typosquat-url",
                        json=finding_dict,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            success_count += 1
                            logger.debug(f"Typosquat URL finding {idx+1}/{finding_count} posted successfully")
                        else:
                            error_text = await response.text()
                            failed_count += 1
                            errors.append(f"Finding {idx+1}: {response.status} - {error_text}")
                            logger.error(f"API error posting typosquat URL finding {idx+1}/{finding_count}: {response.status} - {error_text}")

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Finding {idx+1}: {str(e)}")
                    logger.error(f"Error posting typosquat URL finding {idx+1}/{finding_count}: {e}")

            # Return aggregated result
            if success_count > 0:
                logger.info(f"Posted {success_count}/{finding_count} typosquat URL findings successfully")
                return {
                    "status": "success" if failed_count == 0 else "partial",
                    "processing_mode": "sync",
                    "summary": {
                        "total": finding_count,
                        "successful": success_count,
                        "failed": failed_count,
                        "errors": errors if errors else []
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to post all {finding_count} findings",
                    "errors": errors
                }

        except Exception as e:
            logger.exception(f"Unexpected error posting typosquat URL findings: {e}")
            return {"status": "error", "error": f"Unexpected error: {e}"}

    async def post_typosquat_screenshot_findings(self, typosquat_findings: List[Any], program_name: str) -> Dict[str, Any]:
        """
        Post typosquat screenshot findings to /findings/typosquat-screenshot endpoint.
        This endpoint accepts one finding at a time, so we send each individually.

        Args:
            typosquat_findings: List of typosquat screenshot findings to post
            program_name: Name of the program for the findings

        Returns:
            API response with job status or error information (aggregated from all individual posts)
        """
        if not typosquat_findings:
            logger.warning("No typosquat screenshot findings to post")
            return {"status": "error", "error": "No findings to post"}

        await self.initialize()

        try:
            finding_count = len(typosquat_findings)
            logger.debug(f"Posting {finding_count} typosquat screenshot findings individually to /findings/typosquat-screenshot for program: {program_name}")

            success_count = 0
            failed_count = 0
            errors = []

            # Post each finding individually
            for idx, finding in enumerate(typosquat_findings):
                try:
                    # Convert finding to dictionary
                    if hasattr(finding, 'model_dump'):
                        finding_dict = finding.model_dump(by_alias=True, exclude_none=True)
                        finding_dict = self._deep_clean_for_json(finding_dict)
                    elif hasattr(finding, 'to_dict'):
                        finding_dict = self._deep_clean_for_json(finding.to_dict())
                    elif hasattr(finding, '__dict__'):
                        finding_dict = self._deep_clean_for_json(finding.__dict__)
                    else:
                        finding_dict = self._deep_clean_for_json(finding)

                    # Add program_name to each finding
                    finding_dict['program_name'] = program_name

                    # Post individual finding
                    async with self.session.post(
                        f"{self.base_url}/findings/typosquat-screenshot",
                        json=finding_dict,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            result = await response.json()
                            success_count += 1
                            logger.debug(f"Typosquat screenshot finding {idx+1}/{finding_count} posted successfully")
                        else:
                            error_text = await response.text()
                            failed_count += 1
                            errors.append(f"Finding {idx+1}: {response.status} - {error_text}")
                            logger.error(f"API error posting typosquat screenshot finding {idx+1}/{finding_count}: {response.status} - {error_text}")

                except Exception as e:
                    failed_count += 1
                    errors.append(f"Finding {idx+1}: {str(e)}")
                    logger.error(f"Error posting typosquat screenshot finding {idx+1}/{finding_count}: {e}")

            # Return aggregated result
            if success_count > 0:
                logger.info(f"Posted {success_count}/{finding_count} typosquat screenshot findings successfully")
                return {
                    "status": "success" if failed_count == 0 else "partial",
                    "processing_mode": "sync",
                    "summary": {
                        "total": finding_count,
                        "successful": success_count,
                        "failed": failed_count,
                        "errors": errors if errors else []
                    }
                }
            else:
                return {
                    "status": "error",
                    "error": f"Failed to post all {finding_count} findings",
                    "errors": errors
                }

        except Exception as e:
            logger.exception(f"Unexpected error posting typosquat screenshot findings: {e}")
            return {"status": "error", "error": f"Unexpected error: {e}"}
    
    async def _send_screenshot_assets(self, asset_list: List[Any], program_name: str,
                                    workflow_id: str, step_name: str) -> tuple[bool, List[Dict[str, Any]]]:
        """Send screenshot assets to the specific screenshot endpoint"""
        try:
            success = True
            api_responses = []

            for asset in asset_list:
                # Extract screenshot data
                url = asset.get('url', '')
                image_data = asset.get('image_data', '')
                filename = asset.get('filename', 'screenshot.png')
                extracted_text = asset.get('extracted_text')

                if not url or not image_data:
                    logger.warning("Invalid screenshot asset: missing url or image_data")
                    continue

                # Decode base64 image data
                import base64
                try:
                    # image_data is already base64 encoded as a string
                    image_bytes = base64.b64decode(image_data)
                except Exception as e:
                    logger.error(f"Failed to decode image data for {url}: {e}")
                    continue

                # Prepare form data for screenshot upload
                import aiohttp
                data = aiohttp.FormData()
                data.add_field('file', image_bytes, filename=filename, content_type='image/png')
                data.add_field('url', url)
                data.add_field('program_name', program_name)
                data.add_field('workflow_id', workflow_id)
                data.add_field('step_name', step_name)
                data.add_field('bucket_type', 'findings')
                if extracted_text:
                    data.add_field('extracted_text', extracted_text)
                
                # Send to screenshot endpoint using a separate session for form data
                # (the main session has JSON headers which conflict with multipart form data)
                import aiohttp
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                async with aiohttp.ClientSession(headers=headers) as upload_session:
                    async with upload_session.post(f"{self.base_url}/assets/screenshot", data=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            file_id = result.get('data', {}).get('file_id')

                            # Create a synthetic API response in the format expected by aggregation
                            # Since screenshot endpoint doesn't return detailed counts, we create them
                            synthetic_response = {
                                "summary": {
                                    "total_assets": 1,
                                    "created_assets": 1,
                                    "updated_assets": 0,
                                    "skipped_assets": 0,
                                    "failed_assets": 0,
                                    "detailed_counts": {
                                        "screenshot": {
                                            "total": 1,
                                            "created": 1,
                                            "updated": 0,
                                            "skipped": 0,
                                            "failed": 0,
                                            "created_assets": [{"url": url, "filename": filename}],
                                            "updated_assets": [],
                                            "skipped_assets": [],
                                            "failed_assets": [],
                                            "errors": []
                                        }
                                    }
                                },
                                "file_id": file_id
                            }
                            api_responses.append(synthetic_response)
                        else:
                            error_text = await response.text()
                            logger.error(f"Failed to upload screenshot for {url}: {response.status} - {error_text}")
                            success = False

            return success, api_responses

        except Exception as e:
            logger.error(f"Error sending screenshot assets: {e}")
            return False, []
    
    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a background asset processing job.

        Args:
            job_id: The job ID to check

        Returns:
            Job status information

        Raises:
            Exception: If API request fails
        """
        await self.initialize()

        try:
            logger.debug(f"Checking status for asset job {job_id}")

            async with self.session.get(
                f"{self.base_url}/assets/job/{job_id}"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Ensure consistent format for both unified and legacy jobs
                    if "job_id" not in result:
                        result["job_id"] = job_id
                    return result
                elif response.status == 404:
                    logger.warning(f"Asset job {job_id} not found")
                    return {"status": "not_found", "error": "Job not found", "job_id": job_id}
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status} getting asset job status: {error_text}")
                    raise Exception(f"API error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error getting asset job status for {job_id}: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting asset job status for {job_id}: {e}")
            raise

    async def get_findings_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get status of a background findings processing job.

        Args:
            job_id: The job ID to check

        Returns:
            Job status information

        Raises:
            Exception: If API request fails
        """
        await self.initialize()

        try:
            async with self.session.get(
                f"{self.base_url}/findings/job/{job_id}"
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.debug(f"Findings job {job_id} status: {result.get('status', 'unknown')}")
                    # Ensure consistent format for findings jobs
                    if "job_id" not in result:
                        result["job_id"] = job_id
                    return result
                elif response.status == 404:
                    logger.warning(f"Findings job {job_id} not found")
                    return {"status": "not_found", "error": "Job not found", "job_id": job_id}
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status} getting findings job status: {error_text}")
                    raise Exception(f"API error {response.status}: {error_text}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error getting findings job status for {job_id}: {e}")
            raise Exception(f"Network error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error getting findings job status for {job_id}: {e}")
            raise

        
    def _calculate_timeout_for_assets(self, asset_count: int) -> int:
        """Calculate timeout based on asset count for large volumes"""
        # Base timeout for small requests
        if asset_count <= 1000:
            return self.base_timeout
        
        # Dynamic timeout: 30s base + 15s per 1000 assets
        # 1000 assets = 30s, 2000 = 45s, 3000 = 60s, 4000 = 75s, 5000 = 90s
        extra_timeout = ((asset_count - 1000) // 1000 + 1) * 15
        calculated_timeout = self.base_timeout + extra_timeout
        
        # Cap at reasonable maximum (5 minutes)
        max_timeout = 300
        final_timeout = min(calculated_timeout, max_timeout)
        
        logger.info(f"Calculated timeout for {asset_count} assets: {final_timeout}s (base: {self.base_timeout}s)")
        return final_timeout
