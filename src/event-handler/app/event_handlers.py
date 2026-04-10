#!/usr/bin/env python3
"""
Simplified Event Handler System for Notifier

This replaces the complex event_handlers.py with a much simpler approach.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json
import re

import httpx

logger = logging.getLogger(__name__)

# Shared async HTTP client for workflow/PhishLabs actions (reused to limit connections)
_http_client: Optional[httpx.AsyncClient] = None


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared async HTTP client, creating it on first use."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def close_http_client() -> None:
    """Close the shared HTTP client (call on app shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


@dataclass
class ActionResult:
    """Result of an action execution"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class SimpleEventHandler:
    """Simplified event handler that processes events based on conditions and actions"""
    
    def __init__(self, handler_id: str, config: Dict[str, Any]):
        self.handler_id = handler_id
        self.event_type = config.get('event_type', '')
        self.conditions = config.get('conditions', [])
        self.actions = config.get('actions', [])
        self.description = config.get('description', '')
        
        # Extract batching config from actions
        self.batch_config = None
        for action in self.actions:
            if 'batching' in action:
                self.batch_config = action['batching']
                break
    
    def check_conditions(self, event_data: Dict[str, Any]) -> bool:
        """Check if all conditions are met"""
        for condition in self.conditions:
            if not self._evaluate_condition(condition, event_data):
                return False
        return True
    
    def _evaluate_condition(self, condition: Dict[str, Any], event_data: Dict[str, Any]) -> bool:
        """Evaluate a single condition"""
        condition_type = condition.get('type')
        
        if condition_type == 'field_exists':
            field = condition.get('field')
            return self._get_nested_value(event_data, field) is not None
        
        elif condition_type == 'field_value':
            field = condition.get('field')
            expected = condition.get('expected_value')
            operator = condition.get('operator', 'equals')
            actual = self._get_nested_value(event_data, field)
            
            if operator == 'equals':
                return actual == expected
            elif operator == 'not_equals':
                return actual != expected
            elif operator == 'null_or_empty':
                return actual is None or actual == "" or (isinstance(actual, list) and len(actual) == 0)
            elif operator == 'not_exists':
                return actual is None or actual == "" or (isinstance(actual, list) and len(actual) == 0)
            elif operator == 'exists':
                return actual is not None and actual != "" and (not isinstance(actual, list) or len(actual) > 0)
            elif operator == 'greater_than':
                return actual is not None and actual != "" and (not isinstance(actual, list) or len(actual) > 0) and actual > expected
            elif operator == 'less_than':
                return actual is not None and actual != "" and (not isinstance(actual, list) or len(actual) > 0) and actual < expected
            elif operator == 'not_empty':
                return actual is not None and actual != "" and (not isinstance(actual, list) or len(actual) > 0)
            elif operator == 'in':
                if isinstance(expected, list):
                    return actual in expected
                else:
                    return actual == expected
        
        elif condition_type == 'asset_filter':
            # For asset filtering, check if the event itself matches the filter
            asset_field = condition.get('asset_field', 'assets')
            filter_field = condition.get('filter_field')
            filter_operator = condition.get('filter_operator')
            
            if not filter_field or not filter_operator:
                return True
            
            # For single asset events, check the event directly
            if asset_field == 'assets' and 'assets' not in event_data:
                # Single asset event - check the event itself as the asset
                asset = event_data
                return self._asset_matches_filter(asset, condition)
            elif asset_field in event_data:
                # Check if any asset in the assets array matches the filter
                assets = event_data.get(asset_field, [])
                if not isinstance(assets, list):
                    assets = [assets]
                
                for asset in assets:
                    if self._asset_matches_filter(asset, condition):
                        return True
                return False
            
            return True
        
        return False
    
    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get nested value using dot notation (e.g., 'asset.name')"""
        if not field_path:
            return None
            
        keys = field_path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        
        return current
    
    async def handle_event(self, event_data: Dict[str, Any], batch_manager: Optional['SimpleBatchManager'] = None) -> List[ActionResult]:
        """Handle an event by checking conditions and executing actions"""
        if not self.check_conditions(event_data):
            return []

        results = []

        # Check if batching is configured and available
        if self.batch_config and batch_manager:
            result = batch_manager.add_to_batch(self.handler_id, event_data, self.batch_config)
            logger.debug(f"Batch result: {result}")
            if result.get('should_flush'):
                # Execute batch
                batched_events = batch_manager.get_and_clear_batch(self.handler_id, event_data.get('program_name', 'unknown'))
                batch_results = await self._execute_batch_actions(batched_events, event_data)
                results.extend(batch_results)
            else:
                # Just queued for batching
                results.append(ActionResult(
                    success=True,
                    message=f"Event queued for batching ({result.get('count', 0)} events in batch)"
                ))
        else:
            # No batching configured, execute immediately
            action_results = await self._execute_actions(event_data)
            results.extend(action_results)

        return results
    
    async def _execute_actions(self, event_data: Dict[str, Any]) -> List[ActionResult]:
        """Execute all actions for a single event"""
        results = []
        
        for action in self.actions:
            try:
                result = await self._execute_single_action(action, event_data)
                results.append(result)
            except Exception as e:
                logger.error(f"Error executing action: {e}")
                results.append(ActionResult(
                    success=False,
                    message=f"Action execution error: {str(e)}"
                ))
        
        return results
    
    async def _execute_batch_actions(self, batched_events: List[Dict[str, Any]], trigger_event: Dict[str, Any]) -> List[ActionResult]:
        """Execute all actions for a batch of events"""
        results = []

        # Create batch context
        batch_context = self._create_batch_context(batched_events, trigger_event)
        logger.debug(f"Created batch context with {len(batched_events)} events, ip_count: {batch_context.get('ip_count', 0)}")

        for action in self.actions:
            logger.debug(f"Executing batch action: {action.get('type')}")
            try:
                result = await self._execute_batch_action(action, batch_context)
                results.append(result)
                logger.debug(f"Batch action result: success={result.success}, message='{result.message}'")
            except Exception as e:
                logger.error(f"Error executing batch action: {e}")
                import traceback
                logger.error(f"Batch action traceback: {traceback.format_exc()}")
                results.append(ActionResult(
                    success=False,
                    message=f"Batch action execution error: {str(e)}"
                ))

        return results
    
    def _create_batch_context(self, batched_events: List[Dict[str, Any]], trigger_event: Dict[str, Any]) -> Dict[str, Any]:
        """Create context for batch template substitution with asset filtering support"""
        event_count = len(batched_events)
        
        # Check if we have asset filter conditions (either at handler level or action level)
        asset_filter_condition = None
        
        # First check handler-level conditions
        for condition in self.conditions:
            if condition.get('type') == 'asset_filter':
                asset_filter_condition = condition
                break
        
        # If not found, check action-level conditions
        if not asset_filter_condition:
            for action in self.actions:
                logger.debug(f"Checking action {action.get('type')} for asset filter conditions")
                if 'conditions' in action:
                    logger.debug(f"Action has {len(action['conditions'])} conditions")
                    for condition in action['conditions']:
                        logger.debug(f"Checking condition: {condition}")
                        if condition.get('type') == 'asset_filter':
                            asset_filter_condition = condition
                            logger.debug(f"Found asset filter condition: {asset_filter_condition}")
                            break
                if asset_filter_condition:
                    break
        
        # Extract asset names from events, applying asset filters if present
        # EXTENSIBILITY: To add support for new asset types, add new lists here
        # and extract them in the loop below following the same pattern as domain_names and ip_addresses
        domain_names = []
        ip_addresses = []
        urls = []
        filtered_assets = []

        for event in batched_events:
            payload = event.get('payload', event)

            # Handle asset events with assets array
            if 'assets' in payload and isinstance(payload['assets'], list):
                for asset in payload['assets']:
                    # Apply asset filter if present
                    if asset_filter_condition:
                        if self._asset_matches_filter(asset, asset_filter_condition):
                            # Handle subdomain assets
                            domain_name = asset.get('name')
                            if domain_name and domain_name not in domain_names:
                                domain_names.append(domain_name)
                                filtered_assets.append(asset)

                            # Handle IP assets
                            ip_address = asset.get('ip_address') or asset.get('ip')
                            if ip_address:
                                # Handle both single IP strings and lists of IPs
                                if isinstance(ip_address, list):
                                    for ip in ip_address:
                                        if ip and ip not in ip_addresses:
                                            ip_addresses.append(ip)
                                elif ip_address not in ip_addresses:
                                    ip_addresses.append(ip_address)

                            # Handle URL assets
                            url = asset.get('url') or asset.get('name')
                            if url and url not in urls:
                                urls.append(url)
                                filtered_assets.append(asset)
                    else:
                        # No filter, include all assets
                        # Handle subdomain assets
                        domain_name = asset.get('name')
                        if domain_name and domain_name not in domain_names:
                            domain_names.append(domain_name)
                            filtered_assets.append(asset)

                        # Handle IP assets
                        ip_address = asset.get('ip_address') or asset.get('ip')
                        if ip_address:
                            # Handle both single IP strings and lists of IPs
                            if isinstance(ip_address, list):
                                for ip in ip_address:
                                    if ip and ip not in ip_addresses:
                                        ip_addresses.append(ip)
                            elif ip_address not in ip_addresses:
                                ip_addresses.append(ip_address)

                        # Handle URL assets
                        url = asset.get('url') or asset.get('name')
                        if url and url not in urls:
                            urls.append(url)
                            filtered_assets.append(asset)
            else:
                # Handle single asset events or other event types
                # Handle subdomain events
                domain_name = (
                    payload.get('name') or
                    payload.get('typo_domain') or
                    payload.get('domain') or
                    event.get('name')
                )
                if domain_name and domain_name not in domain_names:
                    domain_names.append(domain_name)

                # Handle IP events
                ip_address = payload.get('ip_address') or payload.get('ip')
                if ip_address:
                    # Handle both single IP strings and lists of IPs
                    if isinstance(ip_address, list):
                        for ip in ip_address:
                            if ip and ip not in ip_addresses:
                                ip_addresses.append(ip)
                    elif ip_address not in ip_addresses:
                        ip_addresses.append(ip_address)

                # Handle URL events
                url = payload.get('url') or payload.get('name')
                if url and url not in urls:
                    urls.append(url)
        
        # Create batch variables
        # EXTENSIBILITY: Add new asset type variables here following the pattern:
        # '{asset_type}_count': len(asset_list), '{asset_type}_list': ', '.join(asset_list), '{asset_type}_list_array': asset_list
        batch_context = dict(trigger_event)
        batch_context.update({
            'event_count': event_count,
            'domain_count': len(domain_names),
            'domain_list': ', '.join(domain_names),
            'domain_list_array': domain_names,
            'ip_count': len(ip_addresses),
            'ip_list': ', '.join(ip_addresses),
            'ip_list_array': ip_addresses,
            'url_count': len(urls),
            'url_list': ', '.join(urls),
            'url_list_array': urls,
            'batched_events': batched_events,
            'filtered_assets': filtered_assets
        })
        
        return batch_context
    
    def _asset_matches_filter(self, asset: Dict[str, Any], filter_condition: Dict[str, Any]) -> bool:
        """Check if an asset matches the filter condition"""
        filter_field = filter_condition.get('filter_field')
        filter_operator = filter_condition.get('filter_operator')

        if not filter_field or not filter_operator:
            return True

        # Handle IP-specific filter fields
        if filter_field == 'ip':
            # Try both 'ip_address' and 'ip' fields for IP assets
            field_value = asset.get('ip_address') or asset.get('ip')
        else:
            field_value = asset.get(filter_field)

        if filter_operator == 'not_exists':
            return field_value is None or field_value == "" or (isinstance(field_value, list) and len(field_value) == 0)
        elif filter_operator == 'exists':
            return field_value is not None and field_value != "" and (not isinstance(field_value, list) or len(field_value) > 0)
        elif filter_operator == 'equals':
            expected_value = filter_condition.get('filter_value')
            return field_value == expected_value
        elif filter_operator == 'not_equals':
            expected_value = filter_condition.get('filter_value')
            return field_value != expected_value

        return True

    async def _execute_single_action(self, action: Dict[str, Any], event_data: Dict[str, Any]) -> ActionResult:
        """Execute a single action"""
        action_type = action.get('type')
        
        if action_type == 'log':
            return await self._execute_log_action(action, event_data)
        elif action_type == 'discord_notification':
            return await self._execute_discord_action(action, event_data)
        elif action_type == 'workflow_trigger':
            return await self._execute_workflow_action(action, event_data)
        elif action_type == 'phishlabs_batch_trigger':
            return await self._execute_phishlabs_batch_action(action, event_data)
        elif action_type == 'ai_analysis_batch_trigger':
            return await self._execute_ai_analysis_batch_action(action, event_data)
        else:
            return ActionResult(
                success=False,
                message=f"Unknown action type: {action_type}"
            )
    
    async def _execute_batch_action(self, action: Dict[str, Any], batch_context: Dict[str, Any]) -> ActionResult:
        """Execute a batch action"""
        action_type = action.get('type')
        logger.debug(f"Called _execute_batch_action with action_type: {action_type}")
        if action_type == 'log':
            return await self._execute_log_action(action, batch_context, is_batch=True)
        elif action_type == 'discord_notification':
            # For batch actions, we need to check if notifications are enabled for the batch
            # Use the original event type from the batch context
            return await self._execute_discord_batch_action(action, batch_context)
        elif action_type == 'workflow_trigger':
            return await self._execute_workflow_action(action, batch_context, is_batch=True)
        elif action_type == 'phishlabs_batch_trigger':
            return await self._execute_phishlabs_batch_action(action, batch_context, is_batch=True)
        elif action_type == 'ai_analysis_batch_trigger':
            return await self._execute_ai_analysis_batch_action(action, batch_context, is_batch=True)
        else:
            return ActionResult(
                success=False,
                message=f"Unknown batch action type: {action_type}"
            )
    
    async def _execute_log_action(self, action: Dict[str, Any], event_data: Dict[str, Any], is_batch: bool = False) -> ActionResult:
        """Execute a log action"""
        level = action.get('level', 'info').upper()
        template = action.get('batch_message_template' if is_batch else 'message_template', 
                             'Batch event processed' if is_batch else 'Event processed')
        
        try:
            message = self._substitute_template(template, event_data)
            
            if level == 'DEBUG':
                logger.debug(message)
            elif level == 'INFO':
                logger.info(message)
            elif level == 'WARNING':
                logger.warning(message)
            elif level == 'ERROR':
                logger.error(message)
            else:
                logger.info(message)
            
            return ActionResult(
                success=True,
                message=f"{'Batch' if is_batch else 'Event'} logged successfully",
                data={'level': level, 'message': message}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Log action failed: {str(e)}"
            )
    
    async def _execute_discord_action(self, action: Dict[str, Any], event_data: Dict[str, Any], is_batch: bool = False) -> ActionResult:
        """Execute a Discord notification action"""
        try:
            from .discord import DiscordClient

            program_settings = event_data.get('program_settings', {})

            # Get webhook URL (template may use program_settings.notify_webhook_X with fallback to discord_webhook_url)
            webhook_url = self._substitute_template(action.get('webhook_url', ''), event_data)
            if not webhook_url:
                webhook_url = (program_settings.get('discord_webhook_url') or '').strip()
            if not webhook_url:
                return ActionResult(
                    success=False,
                    message="No webhook URL configured"
                )
            
            # Create embed
            title_template = action.get('batch_title_template' if is_batch else 'title_template', 
                                     'Batch Notification' if is_batch else 'Event Notification')
            desc_template = action.get('batch_description_template' if is_batch else 'description_template', '')
            
            title = self._substitute_template(title_template, event_data)
            description = self._substitute_template(desc_template, event_data)
            
            embed = {
                'title': title,
                'description': description,
                'color': action.get('batch_color' if is_batch else 'color', 3447003)
            }
            
            # Send notification
            discord = DiscordClient(None)
            success = discord.send(webhook_url, embeds=[embed])
            
            return ActionResult(
                success=success,
                message=f"Discord notification {'sent' if success else 'failed'}",
                data={'embed': embed}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Discord action failed: {str(e)}"
            )

    async def _execute_discord_batch_action(self, action: Dict[str, Any], batch_context: Dict[str, Any]) -> ActionResult:
        """Execute a Discord notification action for batches"""
        try:
            from .discord import DiscordClient

            program_settings = batch_context.get('program_settings', {})

            # Get webhook URL (template may use program_settings.notify_webhook_X with fallback to discord_webhook_url)
            webhook_url = self._substitute_template(action.get('webhook_url', ''), batch_context)
            if not webhook_url:
                webhook_url = (program_settings.get('discord_webhook_url') or '').strip()
            if not webhook_url:
                return ActionResult(
                    success=False,
                    message="No webhook URL configured"
                )

            # Create embed for batch
            title_template = action.get('batch_title_template', 'Batch Notification')
            desc_template = action.get('batch_description_template', '')

            title = self._substitute_template(title_template, batch_context)
            description = self._substitute_template(desc_template, batch_context)

            embed = {
                'title': title,
                'description': description,
                'color': action.get('batch_color', 3447003)
            }

            # Send notification
            discord = DiscordClient(None)
            success = discord.send(webhook_url, embeds=[embed])

            return ActionResult(
                success=success,
                message=f"Discord batch notification {'sent' if success else 'failed'}",
                data={'embed': embed}
            )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Discord batch action failed: {str(e)}"
            )

    async def _execute_workflow_action(self, action: Dict[str, Any], event_data: Dict[str, Any], is_batch: bool = False) -> ActionResult:
        """Execute a workflow trigger action (async HTTP, non-blocking)."""
        try:
            logger.debug(f"Executing workflow action: is_batch={is_batch}")

            # Get configuration
            workflow_name = action.get('parameters', {}).get('workflow_name')
            if not workflow_name:
                logger.error("No workflow name configured")
                return ActionResult(
                    success=False,
                    message="No workflow name configured"
                )

            api_url = self._substitute_template(action.get('api_url', '{api_base_url}'), event_data)
            api_key = self._substitute_template(action.get('api_key', '{internal_api_key}'), event_data)
            logger.debug(f"Workflow: {workflow_name}, API URL: {api_url}")

            # Build payload
            #if action.get('use_custom_payload', False):
            payload = self._substitute_template_object(action.get('parameters', {}), event_data)
            logger.debug(f"Using custom payload with {len(payload)} parameters")
            # else:
            #     payload = {
            #         'workflow_name': workflow_name,
            #         'program_name': event_data.get('program_name'),
            #         'description': f"{'Batch' if is_batch else 'Event'} triggered workflow",
            #         'parameters': self._substitute_template_object(action.get('parameters', {}), event_data)
            #     }
            #     logger.debug(f"Using standard payload format")

            logger.debug(f"Payload keys: {list(payload.keys())}")
            if 'parameters' in payload:
                logger.debug(f"Parameters keys: {list(payload['parameters'].keys())}")

            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'

            url = f"{api_url}/workflows/run"
            logger.debug(f"Making POST request to: {url}")
            logger.debug(f"Payload: {json.dumps(payload, indent=4)}")
            client = await _get_http_client()
            response = await client.post(url, json=payload, headers=headers)

            logger.debug(f"Response status: {response.status_code}")
            if response.status_code == 200:
                result_data = response.json()
                workflow_id = result_data.get('workflow_id', result_data.get('id', 'unknown'))
                logger.info(f"Workflow '{workflow_name}' triggered successfully (ID: {workflow_id})")
                return ActionResult(
                    success=True,
                    message=f"Workflow '{workflow_name}' triggered successfully (ID: {workflow_id})",
                    data={'workflow_id': workflow_id}
                )
            else:
                logger.error(f"Workflow trigger failed: {response.status_code} - {response.text}")
                return ActionResult(
                    success=False,
                    message=f"Workflow trigger failed: {response.status_code} - {response.text}"
                )

        except httpx.HTTPError as e:
            logger.error(f"Workflow action HTTP error: {e}")
            return ActionResult(
                success=False,
                message=f"Workflow action failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Workflow action failed: {str(e)}")
            import traceback
            logger.error(f"Workflow action traceback: {traceback.format_exc()}")
            return ActionResult(
                success=False,
                message=f"Workflow action failed: {str(e)}"
            )

    async def _execute_phishlabs_batch_action(self, action: Dict[str, Any], event_data: Dict[str, Any], is_batch: bool = False) -> ActionResult:
        """Execute a phishlabs batch trigger action (async HTTP, non-blocking)."""
        try:
            logger.info(f"PhishLabs batch action started - is_batch: {is_batch}")

            # Get configuration
            finding_ids = action.get('finding_ids', [])
            logger.debug(f"Initial finding_ids from config: {finding_ids}")

            if not finding_ids:
                if is_batch:
                    # For batched events, extract finding IDs from all batched events
                    batched_events = event_data.get('batched_events', [])
                    finding_id_template = action.get('finding_id_template', '{id}')
                    logger.info(f"Processing {len(batched_events)} batched events with template: {finding_id_template}")

                    finding_ids = []
                    for i, event in enumerate(batched_events):
                        # Extract finding ID from each batched event
                        finding_id = self._substitute_template(finding_id_template, event)
                        logger.debug(f"Event {i}: extracted finding_id '{finding_id}' from event data: {event}")
                        if finding_id and finding_id not in finding_ids:
                            finding_ids.append(finding_id)
                    logger.info(f"Extracted {len(finding_ids)} unique finding IDs from batch: {finding_ids}")
                else:
                    # For single events, extract finding ID from the single event
                    finding_id_template = action.get('finding_id_template', '{id}')
                    finding_id = self._substitute_template(finding_id_template, event_data)
                    logger.debug(f"Single event: extracted finding_id '{finding_id}' using template '{finding_id_template}' from event: {event_data}")
                    if finding_id:
                        finding_ids = [finding_id]
                        logger.info(f"Single finding ID extracted: {finding_ids}")

            if not finding_ids:
                logger.warning("No finding IDs found in event data")
                return ActionResult(
                    success=False,
                    message="No finding IDs configured or found in event data"
                )

            # If finding_ids is a template string, expand it
            if isinstance(finding_ids, str):
                finding_ids = self._substitute_template(finding_ids, event_data)
                if isinstance(finding_ids, str):
                    # If it's still a string, try to parse as JSON or split by comma
                    try:
                        finding_ids = json.loads(finding_ids)
                    except:
                        finding_ids = [fid.strip() for fid in finding_ids.split(',') if fid.strip()]

            # Ensure finding_ids is a list
            if not isinstance(finding_ids, list):
                finding_ids = [str(finding_ids)]

            # Filter out empty strings
            finding_ids = [fid for fid in finding_ids if fid]

            if not finding_ids:
                return ActionResult(
                    success=False,
                    message="No valid finding IDs found"
                )

            api_url = self._substitute_template(action.get('api_url', '{api_base_url}'), event_data)
            api_key = self._substitute_template(action.get('api_key', '{internal_api_key}'), event_data)
            logger.debug(f"API URL: {api_url}")
            logger.debug(f"API Key configured: {'Yes' if api_key else 'No'}")

            # Build payload
            payload = {
                'finding_ids': finding_ids
            }

            # Add optional catcode if provided
            catcode = action.get('catcode')
            if catcode:
                catcode = self._substitute_template(catcode, event_data)
                if catcode:
                    payload['catcode'] = catcode
                    logger.debug(f"Added catcode: {catcode}")

            logger.info(f"Sending PhishLabs batch request with {len(finding_ids)} finding IDs")
            logger.debug(f"Request payload: {payload}")

            # Make request
            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'

            url = f"{api_url}/findings/typosquat/phishlabs/batch"
            logger.info(f"Making POST request to: {url}")

            client = await _get_http_client()
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {dict(response.headers)}")
            logger.debug(f"Response body: {response.text}")

            if response.status_code == 200:
                try:
                    result_data = response.json()
                    job_id = result_data.get('job_id', 'unknown')
                    logger.info(f"PhishLabs batch job triggered successfully with job ID: {job_id}")
                    return ActionResult(
                        success=True,
                        message=f"PhishLabs batch job triggered successfully (Job ID: {job_id})",
                        data={'job_id': job_id, 'finding_count': len(finding_ids)}
                    )
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    return ActionResult(
                        success=False,
                        message=f"PhishLabs batch trigger succeeded but response parsing failed: {str(e)}"
                    )
            else:
                logger.warning(f"PhishLabs batch trigger failed with status {response.status_code}: {response.text}")
                return ActionResult(
                    success=False,
                    message=f"PhishLabs batch trigger failed: {response.status_code} - {response.text}"
                )

        except httpx.HTTPError as e:
            logger.error(f"PhishLabs batch action HTTP error: {e}")
            return ActionResult(
                success=False,
                message=f"HTTP request failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"PhishLabs batch action failed with exception: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return ActionResult(
                success=False,
                message=f"PhishLabs batch action failed: {str(e)}"
            )

    async def _execute_ai_analysis_batch_action(self, action: Dict[str, Any], event_data: Dict[str, Any], is_batch: bool = False) -> ActionResult:
        """Execute an AI analysis batch trigger action."""
        try:
            finding_ids = action.get('finding_ids', [])

            if not finding_ids:
                if is_batch:
                    batched_events = event_data.get('batched_events', [])
                    finding_id_template = action.get('finding_id_template', '{record_id}')
                    finding_ids = []
                    for event in batched_events:
                        finding_id = self._substitute_template(finding_id_template, event)
                        if finding_id and finding_id not in finding_ids:
                            finding_ids.append(finding_id)
                else:
                    finding_id_template = action.get('finding_id_template', '{record_id}')
                    finding_id = self._substitute_template(finding_id_template, event_data)
                    if finding_id:
                        finding_ids = [finding_id]

            if not finding_ids:
                return ActionResult(
                    success=False,
                    message="No finding IDs found in event data"
                )

            if isinstance(finding_ids, str):
                finding_ids = [finding_ids]
            finding_ids = [fid for fid in finding_ids if fid]

            api_url = self._substitute_template(action.get('api_url', '{api_base_url}'), event_data)
            api_key = self._substitute_template(action.get('api_key', '{internal_api_key}'), event_data)

            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'

            url = f"{api_url}/findings/typosquat/ai-analysis/batch"
            payload = {"finding_ids": finding_ids}

            client = await _get_http_client()
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                result_data = response.json()
                job_id = result_data.get('job_id', 'unknown')
                return ActionResult(
                    success=True,
                    message=f"AI analysis batch job triggered (Job ID: {job_id})",
                    data={'job_id': job_id, 'finding_count': len(finding_ids)}
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"AI analysis batch trigger failed: {response.status_code} - {response.text}"
                )
        except Exception as e:
            logger.error(f"AI analysis batch action failed: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return ActionResult(
                success=False,
                message=f"AI analysis batch action failed: {str(e)}"
            )

    def _substitute_template(self, template: str, data: Dict[str, Any]) -> Any:
        """Simple template substitution using {key} format, with array support"""
        if not isinstance(template, str):
            return str(template)
        
        # Check if this is a pure template that should return the original value type
        if self._is_array_template(template):
            return self._expand_array_template(template, data)
        
        def replace_match(match):
            path = match.group(1)
            value = self._get_nested_value(data, path)
            return str(value) if value is not None else match.group(0)
        
        return re.sub(r'\{([^}]+)\}', replace_match, template)
    
    def _substitute_template_object(self, obj: Any, data: Dict[str, Any]) -> Any:
        """Recursively substitute templates in an object with special array expansion support"""
        if isinstance(obj, str):
            return self._substitute_template(obj, data)
        elif isinstance(obj, dict):
            return {k: self._substitute_template_object(v, data) for k, v in obj.items()}
        elif isinstance(obj, list):
            # Special handling for array expansion in lists
            result = []
            for item in obj:
                substituted_item = self._substitute_template_object(item, data)
                if isinstance(item, str) and self._is_array_template(item) and isinstance(substituted_item, list):
                    # This template expanded to an array, extend rather than append
                    result.extend(substituted_item)
                else:
                    result.append(substituted_item)
            return result
        else:
            return obj
    
    def _is_array_template(self, template: str) -> bool:
        """Check if this is a template that should expand to an array"""
        # Check if it's a simple template like "{domain_list_array}"
        import re
        match = re.match(r'^\{([^}]+)\}$', template.strip())
        return match is not None
    
    def _expand_array_template(self, template: str, data: Dict[str, Any]) -> Any:
        """Expand a template that should return an array"""
        import re
        match = re.match(r'^\{([^}]+)\}$', template.strip())
        if match:
            path = match.group(1)
            value = self._get_nested_value(data, path)
            return value if value is not None else []
        return template


class SimpleBatchManager:
    """Simplified batch manager using Redis"""
    
    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config
        self.handler_timeouts = {}  # Store handler-specific timeouts
    
    def add_to_batch(self, handler_id: str, event_data: Dict[str, Any], batch_config: Dict[str, Any]) -> Dict[str, Any]:
        """Add event to batch and return batch status"""
        program_name = event_data.get('program_name', 'unknown')
        batch_key = f"batch:{handler_id}:{program_name}"
        
        now = int(time.time())
        max_events = batch_config.get('max_events', 10)
        max_delay = batch_config.get('max_delay_seconds', 300)
        
        # Store handler timeout for expiration checking
        self.handler_timeouts[handler_id] = max_delay
        
        logger.debug(f"Adding to batch: {batch_key}, event: {event_data.get('name', 'unknown')}")
        
        # Check current batch state before adding
        meta_key = f"notify:{batch_key}:meta"
        try:
            current_count = self.redis.llen(f"notify:{batch_key}:items")
            current_meta = self.redis.hget(meta_key, "first_ts")
            logger.debug(f"Batch state before add: count={current_count}, first_ts={current_meta}")
        except Exception as e:
            logger.warning(f"Error checking batch state: {e}")

        # Add to batch with better atomicity
        # Store first_ts and timeout in a meta hash (data, not TTL)
        try:
            pipe = self.redis.pipeline(transaction=True)
            pipe.rpush(f"notify:{batch_key}:items", json.dumps(event_data))
            pipe.hsetnx(meta_key, "first_ts", str(now))
            pipe.hset(meta_key, "timeout", str(max_delay))
            pipe.expire(f"notify:{batch_key}:items", max_delay * 2)
            pipe.expire(meta_key, max_delay * 2)
            pipe.llen(f"notify:{batch_key}:items")
            pipe.hget(meta_key, "first_ts")
            results = pipe.execute()

            count = results[5] or 0
            first_ts_raw = results[6] or b"0"
            try:
                first_ts = int(first_ts_raw.decode('utf-8') if isinstance(first_ts_raw, bytes) else str(first_ts_raw))
            except Exception:
                first_ts = now
            
            should_flush = count >= max_events or (now - first_ts) >= max_delay
            
            logger.debug(f"Batch {batch_key}: count={count}, age={now-first_ts}s, should_flush={should_flush}")
            logger.debug(f"Pipeline results: {results}")
            
            return {
                'count': count,
                'should_flush': should_flush,
                'age_seconds': now - first_ts
            }
        except Exception as e:
            logger.error(f"Error adding to batch {batch_key}: {e}")
            return {
                'count': 0,
                'should_flush': False,
                'age_seconds': 0
            }
    
    def get_and_clear_batch(self, handler_id: str, program_name: str) -> List[Dict[str, Any]]:
        """Get and clear a batch"""
        batch_key = f"batch:{handler_id}:{program_name}"
        meta_key = f"notify:{batch_key}:meta"

        pipe = self.redis.pipeline()
        pipe.lrange(f"notify:{batch_key}:items", 0, -1)
        pipe.delete(f"notify:{batch_key}:items")
        pipe.delete(meta_key)
        results = pipe.execute()
        
        items = []
        for raw_item in (results[0] or []):
            try:
                if isinstance(raw_item, bytes):
                    raw_item = raw_item.decode('utf-8')
                items.append(json.loads(raw_item))
            except Exception as e:
                logger.error(f"Error parsing batch item: {e}")
        
        logger.info(f"Retrieved and cleared batch {batch_key}: {len(items)} events")
        return items
    
    def get_expired_batches(self) -> List[tuple]:
        """Get list of expired batches that need to be flushed"""
        expired = []
        current_time = int(time.time())

        try:
            for key in self.redis.scan_iter(match="notify:batch:*:meta"):
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key

                    # Extract batch info from key: notify:batch:handler_id:program:meta
                    parts = key_str.split(':')
                    if len(parts) < 5:
                        continue

                    handler_id = parts[2]
                    program_name = ':'.join(parts[3:-1])

                    meta = self.redis.hgetall(key)
                    if not meta:
                        continue

                    first_ts_raw = meta.get(b'first_ts', meta.get('first_ts'))
                    if not first_ts_raw:
                        continue

                    first_ts = int(first_ts_raw.decode('utf-8') if isinstance(first_ts_raw, bytes) else first_ts_raw)
                    age = current_time - first_ts

                    # Use timeout from meta (stored as data), fallback to handler_timeouts
                    timeout_raw = meta.get(b'timeout', meta.get('timeout'))
                    if timeout_raw is not None:
                        timeout = int(timeout_raw.decode('utf-8') if isinstance(timeout_raw, bytes) else timeout_raw)
                    else:
                        timeout = self.handler_timeouts.get(handler_id, 60)

                    items_key = f"notify:batch:{handler_id}:{program_name}:items"
                    item_count = self.redis.llen(items_key)

                    if item_count and item_count > 0:
                        logger.debug(f"Checking batch: {handler_id}:{program_name} (age: {age}s, items: {item_count}, timeout: {timeout}s)")

                        if age >= timeout:
                            expired.append((handler_id, program_name, age))
                            logger.debug(f"Found expired batch: {handler_id}:{program_name} (age: {age}s, items: {item_count}, timeout: {timeout}s)")

                except Exception as e:
                    logger.debug(f"Error processing batch key {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scanning for expired batches: {e}")

        return expired

    def list_pending_batches_with_items(self) -> List[tuple]:
        """Batches with at least one queued item: (handler_id, program_name, age_seconds).

        Used for admin-triggered flush (not limited by max_delay expiry).
        """
        pending: List[tuple] = []
        current_time = int(time.time())

        try:
            for key in self.redis.scan_iter(match="notify:batch:*:meta"):
                try:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key

                    parts = key_str.split(":")
                    if len(parts) < 5:
                        continue

                    handler_id = parts[2]
                    program_name = ":".join(parts[3:-1])

                    meta = self.redis.hgetall(key)
                    if not meta:
                        continue

                    first_ts_raw = meta.get(b"first_ts", meta.get("first_ts"))
                    if not first_ts_raw:
                        continue

                    first_ts = int(
                        first_ts_raw.decode("utf-8")
                        if isinstance(first_ts_raw, bytes)
                        else first_ts_raw
                    )
                    age = current_time - first_ts

                    items_key = f"notify:batch:{handler_id}:{program_name}:items"
                    item_count = self.redis.llen(items_key)

                    if item_count and item_count > 0:
                        pending.append((handler_id, program_name, age))

                except Exception as e:
                    logger.debug(f"Error processing batch key {key}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scanning for pending batches: {e}")

        return pending

    def delete_all_pending_batches(self) -> Dict[str, Any]:
        """Remove all queued batch data from Redis without running handler actions."""
        batches_cleared = 0
        events_discarded = 0
        errors: List[Dict[str, Any]] = []

        try:
            for meta_key in self.redis.scan_iter(match="notify:batch:*:meta"):
                try:
                    key_str = meta_key.decode("utf-8") if isinstance(meta_key, bytes) else meta_key

                    parts = key_str.split(":")
                    if len(parts) < 5:
                        continue

                    handler_id = parts[2]
                    program_name = ":".join(parts[3:-1])
                    items_key = f"notify:batch:{handler_id}:{program_name}:items"
                    n = int(self.redis.llen(items_key))
                    if n <= 0:
                        continue

                    pipe = self.redis.pipeline(transaction=True)
                    pipe.delete(items_key)
                    pipe.delete(key_str)
                    pipe.execute()
                    batches_cleared += 1
                    events_discarded += n
                    logger.warning(
                        "Admin clear: dropped batch %s:%s (%s events)",
                        handler_id,
                        program_name,
                        n,
                    )
                except Exception as e:
                    logger.error("Error clearing batch key %s: %s", meta_key, e)
                    errors.append({"key": repr(meta_key), "error": str(e)})

        except Exception as e:
            logger.error(f"Error scanning batches for delete: {e}")
            return {
                "status": "error",
                "detail": str(e),
                "batches_cleared": batches_cleared,
                "events_discarded": events_discarded,
                "errors": errors,
            }

        return {
            "status": "ok",
            "batches_cleared": batches_cleared,
            "events_discarded": events_discarded,
            "errors": errors,
        }


class SimpleHandlerRegistry:
    """Simple registry for event handlers"""
    
    def __init__(self):
        self.handlers: Dict[str, List[SimpleEventHandler]] = {}
        self.batch_manager: Optional[SimpleBatchManager] = None
    
    def register_handler(self, handler: SimpleEventHandler):
        """Register a handler"""
        if handler.event_type not in self.handlers:
            self.handlers[handler.event_type] = []
        self.handlers[handler.event_type].append(handler)
        logger.info(f"Registered handler '{handler.handler_id}' for event type '{handler.event_type}'")
    
    def set_batch_manager(self, batch_manager: SimpleBatchManager):
        """Set the batch manager"""
        self.batch_manager = batch_manager
        
        # Update batch manager with handler timeout info
        if not hasattr(batch_manager, '_handler_timeouts'):
            batch_manager._handler_timeouts = {}
        
        # Store timeout info from all handlers
        for handlers_list in self.handlers.values():
            for handler in handlers_list:
                if handler.batch_config and 'max_delay_seconds' in handler.batch_config:
                    timeout = handler.batch_config['max_delay_seconds']
                    batch_manager._handler_timeouts[handler.handler_id] = timeout
                    logger.debug(f"Set timeout for handler {handler.handler_id}: {timeout}s")
    
    def get_handlers(self, event_type: str) -> List[SimpleEventHandler]:
        """Get handlers for an event type"""
        return self.handlers.get(event_type, [])

    def get_handler_by_id(self, handler_id: str) -> Optional['SimpleEventHandler']:
        """Get handler by id (for batch recovery)."""
        for handlers_list in self.handlers.values():
            for h in handlers_list:
                if h.handler_id == handler_id:
                    return h
        return None
    
    async def handle_event(self, event_type: str, event_data: Dict[str, Any]) -> List[ActionResult]:
        """Handle an event with all matching handlers"""
        all_results = []
        handlers = self.get_handlers(event_type)
        
        logger.debug(f"Handling event '{event_type}' with {len(handlers)} handlers")
        logger.debug(f"Event data: {event_data}")
        
        for handler in handlers:
            try:
                results = await handler.handle_event(event_data, self.batch_manager)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Error in handler '{handler.handler_id}': {e}")
                all_results.append(ActionResult(
                    success=False,
                    message=f"Handler error: {str(e)}"
                ))
        
        return all_results
    
    async def process_expired_batches(self) -> int:
        """Process expired batches"""
        if not self.batch_manager:
            return 0
        
        processed = 0
        expired_batches = self.batch_manager.get_expired_batches()
        
        #logger.debug(f"Found {len(expired_batches)} expired batches to process")
        
        for handler_id, program_name, age in expired_batches:
            try:
                # Find the handler
                handler = None
                for handlers_list in self.handlers.values():
                    for h in handlers_list:
                        if h.handler_id == handler_id:
                            handler = h
                            break
                    if handler:
                        break
                
                if not handler:
                    logger.warning(f"Handler not found for expired batch: {handler_id}")
                    continue
                
                # Get batched events
                batched_events = self.batch_manager.get_and_clear_batch(handler_id, program_name)
                if not batched_events:
                    logger.debug(f"No events found in expired batch: {handler_id}:{program_name}")
                    continue
                
                logger.info(f"Processing expired batch: {handler_id}:{program_name} with {len(batched_events)} events (age: {age}s)")
                logger.debug(f"Batched events: {batched_events}")
                # Create trigger event with proper context
                first_event = batched_events[0] if batched_events else {}
                trigger_event = {
                    'program_name': program_name,
                    'expired_batch': True,
                    'batch_age': age,
                    'event_type': handler.event_type,
                    'event_family': handler.event_type,
                    'api_base_url': first_event.get('api_base_url', 'http://api:8000'),
                    'internal_api_key': first_event.get('internal_api_key', ''),
                    'program_settings': first_event.get('program_settings', {}),
                    # Add fields from the first event for template substitution
                    **first_event
                }
                
                # Execute batch actions
                results = await handler._execute_batch_actions(batched_events, trigger_event)
                successful = [r for r in results if r.success]
                
                logger.info(f"Processed expired batch {handler_id}:{program_name} - {len(batched_events)} events, {len(successful)}/{len(results)} successful actions")
                
                # Log individual results for debugging
                for i, result in enumerate(results):
                    if result.success:
                        logger.debug(f"  Action {i+1}: SUCCESS - {result.message}")
                    else:
                        logger.warning(f"  Action {i+1}: FAILED - {result.message}")
                
                processed += 1
                
            except Exception as e:
                logger.error(f"Error processing expired batch {handler_id}:{program_name}: {e}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
        
        return processed


# Global registry instance
registry = SimpleHandlerRegistry()