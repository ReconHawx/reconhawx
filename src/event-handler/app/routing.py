#!/usr/bin/env python3
"""
Simplified routing logic for event parsing

This replaces the complex routing.py with a much simpler approach.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def parse_event_type(subject: str, payload: Dict[str, Any] = None) -> str:
    """
    Parse subject to extract event type in a simple, predictable way.
    
    Expected formats:
    - events.assets.subdomain.created -> assets.subdomain.created
    - events.assets.subdomain.resolved -> assets.subdomain.resolved  
    - events.findings.typosquat.created -> findings.typosquat.created
    - events.test.workflow.trigger -> test.workflow.trigger
    
    For batch events, the subject remains the same but payload contains batch data.
    
    Returns the event type or empty string if parsing fails.
    """
    parts = subject.split('.')
    
    # Remove 'events' prefix if present
    if parts and parts[0] == 'events':
        parts = parts[1:]
    
    # Note: No longer removing 'batch' suffix since API doesn't add it anymore
    # Batch events are identified by payload.event == 'batch'
    
    if len(parts) < 2:
        logger.debug(f"Cannot parse event type from subject: {subject}")
        return ""
    
    # Handle special cases
    if len(parts) >= 3:
        category = parts[0]  # assets, findings, test, etc.
        
        if category == 'assets':
            # assets.subdomain.created, assets.typosquat.created, etc.
            asset_type = parts[1]
            action = parts[2] if len(parts) > 2 else 'unknown'
            return f"assets.{asset_type}.{action}"
        
        elif category == 'findings':
            # findings.nuclei.created, findings.typosquat.created, etc.
            finding_type = parts[1]
            action = parts[2] if len(parts) > 2 else 'created'
            
            # Handle nuclei severity
            if finding_type == 'nuclei' and payload:
                severity = payload.get('severity', '').lower()
                if severity:
                    return f"findings.nuclei.{severity}"
                else:
                    return "findings.nuclei.created"
            
            return f"findings.{finding_type}.{action}"
        
        elif category == 'test':
            # test.workflow.trigger, etc.
            return '.'.join(parts)
    
    # Fallback: join remaining parts
    event_type = '.'.join(parts)
    logger.debug(f"Parsed event type '{event_type}' from subject '{subject}'")
    return event_type


def is_batch_event(subject: str) -> bool:
    """Check if this is a batch event"""
    return subject.endswith('.batch')


def extract_program_name(payload: Dict[str, Any]) -> str:
    """Extract program name from payload"""
    return payload.get('program_name', 'unknown')


def normalize_event_data(subject: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize event data into a consistent format for handlers.
    
    Returns a dict with all necessary fields for template substitution.
    """
    event_type = parse_event_type(subject, payload)
    program_name = extract_program_name(payload)
    
    # Create normalized event data
    normalized = {
        'subject': subject,
        'event_type': event_type,
        'event_family': event_type,  # Alias for backward compatibility
        'program_name': program_name,
        'timestamp': payload.get('timestamp'),
        
        # API configuration (will be set by main app)
        'api_base_url': 'http://api:8000',
        'internal_api_key': '',
        
        # Include all payload fields at root level for easy template access
        **payload
    }
    
    # Handle special asset cases
    # EXTENSIBILITY: To add support for new asset types (e.g., 'assets.url', 'assets.certificate'),
    # add new elif branches following the same pattern as subdomain and IP assets below.
    # Each asset type should create variables like: {asset_type}_list, {asset_type}_list_array, {asset_type}_count
    if event_type.startswith('assets.'):
        # For asset events, promote common fields
        if 'name' in payload:
            normalized['name'] = payload['name']

        # Handle batch asset events (multiple assets in 'assets' field)
        if 'assets' in payload:
            normalized['assets'] = payload['assets']
            if isinstance(payload['assets'], list):
                # Create domain variables for subdomain assets
                if event_type.startswith('assets.subdomain'):
                    domain_names = [asset.get('name', 'unknown') for asset in payload['assets'] if asset.get('name')]
                    normalized['domain_list'] = ', '.join(domain_names)
                    normalized['domain_list_array'] = domain_names
                    normalized['domain_count'] = len(domain_names)

                # Create IP variables for IP assets
                elif event_type.startswith('assets.ip'):
                    ip_addresses = []
                    for asset in payload['assets']:
                        if asset.get('ip_address'):
                            ip_addresses.append(asset['ip_address'])
                        elif asset.get('ip'):
                            ip_addresses.append(asset['ip'])

                    normalized['ip_list'] = ', '.join(ip_addresses)
                    normalized['ip_list_array'] = ip_addresses
                    normalized['ip_count'] = len(ip_addresses)

                # Create URL variables for URL assets
                elif event_type.startswith('assets.url'):
                    urls = []
                    for asset in payload['assets']:
                        if asset.get('url'):
                            urls.append(asset['url'])
                        elif asset.get('name'):
                            urls.append(asset['name'])

                    normalized['url_list'] = ', '.join(urls)
                    normalized['url_list_array'] = urls
                    normalized['url_count'] = len(urls)

        # Handle single asset events
        else:
            # Handle single subdomain events
            if event_type.startswith('assets.subdomain') and 'name' in payload:
                domain_names = [payload['name']]
                normalized['domain_list'] = payload['name']
                normalized['domain_list_array'] = domain_names
                normalized['domain_count'] = 1

            # Handle single IP events
            elif event_type.startswith('assets.ip'):
                ip_addresses = []
                if payload.get('ip_address'):
                    ip_addresses.append(payload['ip_address'])
                elif payload.get('ip'):
                    ip_addresses.append(payload['ip'])

                if ip_addresses:
                    normalized['ip_list'] = ip_addresses[0]
                    normalized['ip_list_array'] = ip_addresses
                    normalized['ip_count'] = 1

            # Handle single URL events
            elif event_type.startswith('assets.url'):
                urls = []
                if payload.get('url'):
                    urls.append(payload['url'])
                elif payload.get('name'):
                    urls.append(payload['name'])

                if urls:
                    normalized['url_list'] = urls[0]
                    normalized['url_list_array'] = urls
                    normalized['url_count'] = 1
    
    # Handle special finding cases  
    elif event_type.startswith('findings.'):
        if event_type.startswith('findings.typosquat'):
            # Promote typosquat-specific fields
            if 'typo_domain' in payload:
                normalized['typo_domain'] = payload['typo_domain']
            if 'domain_registered' in payload:
                normalized['domain_registered'] = payload['domain_registered']
            if 'whois_registrar' in payload:
                normalized['whois_registrar'] = payload['whois_registrar']
    
    return normalized


def should_skip_event(event_data: Dict[str, Any]) -> bool:
    """
    Simple check if event should be skipped entirely.
    
    This replaces complex permission checking with simple rules.
    """
    # Skip if no program name
    if not event_data.get('program_name'):
        logger.debug("Skipping event without program_name")
        return True
    
    # Skip if event type couldn't be parsed
    if not event_data.get('event_type'):
        logger.debug("Skipping event with unparseable event_type")
        return True
    
    return False