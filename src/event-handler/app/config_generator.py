#!/usr/bin/env python3
"""
Configuration generator for event handlers

This script helps generate handler configuration files with sensible defaults
and examples for different types of event handlers.
"""

import argparse
import logging
import os
import yaml
from typing import Dict, Any

from .recon_log_format import apply_service_logging, parse_log_level

logger = logging.getLogger(__name__)


def generate_typosquat_config() -> Dict[str, Any]:
    """Generate configuration for typosquat domain findings handler"""
    return {
        "handlers": [
            {
                "event_type": ["findings.nuclei.typosquat"],
                "description": "Handle typosquat domain findings with workflow trigger and Discord notifications",
                "conditions": [
                    {
                        "type": "field_exists",
                        "field": "asset.name"
                    },
                    {
                        "type": "field_exists",
                        "field": "severity"
                    },
                    {
                        "type": "field_exists",
                        "field": "program_name"
                    }
                ],
                "actions": [
                    {
                        "type": "discord_notification",
                        "title_template": "🚨 TYPOSQUAT ALERT: {asset.name}",
                        "description_template": "**Severity:** {severity}\n**Template:** {template_id}\n**URL:** {url}\n\n**Domain Analysis:**\n• Length: {enrichment.domain_length}\n• TLD: {enrichment.tld}",
                        "webhook_url": "{program_settings.discord_webhook_url}",
                        "color": 15158332
                    },
                    {
                        "type": "workflow_trigger",
                        "workflow_name": "typosquat-investigation",
                        "api_url": "{api_base_url}",
                        "api_key": "{internal_api_key}",
                        "parameters": {
                            "domain": "{asset.name}",
                            "severity": "{severity}",
                            "template_id": "{template_id}",
                            "url": "{url}",
                            "priority": "high",
                            "investigation_type": "typosquat_domain"
                        }
                    },
                    {
                        "type": "log",
                        "level": "info",
                        "message_template": "Typosquat finding processed: {asset.name} (severity: {severity}, program: {program_name})"
                    }
                ]
            }
        ]
    }


def generate_critical_findings_config() -> Dict[str, Any]:
    """Generate configuration for critical nuclei findings"""
    return {
        "handlers": [
            {
                "event_type": ["findings.nuclei.critical"],
                "description": "Handle critical severity nuclei findings",
                "conditions": [
                    {
                        "type": "field_value",
                        "field": "severity",
                        "expected_value": "critical",
                        "operator": "equals"
                    }
                ],
                "actions": [
                    {
                        "type": "discord_notification",
                        "title_template": "🔴 CRITICAL FINDING: {template_id}",
                        "description_template": "**Target:** {url}\n**Severity:** {severity}\n**Program:** {program_name}",
                        "webhook_url": "{program_settings.discord_webhook_url}",
                        "color": 15158332
                    },
                    {
                        "type": "workflow_trigger",
                        "workflow_name": "critical-finding-response",
                        "parameters": {
                            "url": "{url}",
                            "template_id": "{template_id}",
                            "severity": "{severity}"
                        }
                    }
                ]
            }
        ]
    }


def generate_asset_discovery_config() -> Dict[str, Any]:
    """Generate configuration for new asset discoveries"""
    return {
        "handlers": [
            {
                "event_type": ["assets.subdomain.created"],
                "description": "Log new subdomain discoveries",
                "conditions": [
                    {
                        "type": "field_exists",
                        "field": "name"
                    }
                ],
                "actions": [
                    {
                        "type": "log",
                        "level": "info",
                        "message_template": "New subdomain discovered: {name} (program: {program_name})"
                    }
                ]
            },
            {
                "event_type": ["assets.domain.created"],
                "description": "Handle new domain discoveries with optional notifications",
                "conditions": [
                    {
                        "type": "field_exists",
                        "field": "name"
                    }
                ],
                "actions": [
                    {
                        "type": "discord_notification",
                        "title_template": "🌐 New Domain: {name}",
                        "description_template": "New domain discovered in program {program_name}",
                        "webhook_url": "{program_settings.discord_webhook_url}",
                        "color": 3447003
                    },
                    {
                        "type": "log",
                        "level": "info",
                        "message_template": "New domain discovered: {name} (program: {program_name})"
                    }
                ]
            }
        ]
    }


def generate_comprehensive_config(include_examples: bool = True) -> Dict[str, Any]:
    """Generate a comprehensive configuration with multiple handlers"""

    config = {
        "handlers": []
    }

    # Add typosquat handler
    config["handlers"].extend(generate_typosquat_config()["handlers"])

    # Add critical findings handler
    config["handlers"].extend(generate_critical_findings_config()["handlers"])

    # Add asset discovery handlers
    config["handlers"].extend(generate_asset_discovery_config()["handlers"])

    if include_examples:
        # Add example handlers with comments
        config["handlers"].extend([
            {
                "event_type": ["findings.nuclei.high"],
                "description": "Example: Handle high severity nuclei findings",
                "conditions": [
                    {
                        "type": "field_value",
                        "field": "severity",
                        "expected_value": "high",
                        "operator": "equals"
                    }
                ],
                "actions": [
                    {
                        "type": "discord_notification",
                        "title_template": "🟡 HIGH SEVERITY: {template_id}",
                        "description_template": "**Target:** {url}\n**Severity:** {severity}",
                        "webhook_url": "{program_settings.discord_webhook_url}",
                        "color": 16776960  # Yellow
                    }
                ]
            },
            {
                "event_type": ["assets.ip.created"],
                "description": "Example: Handle new IP address discoveries",
                "conditions": [
                    {
                        "type": "field_exists",
                        "field": "name"
                    }
                ],
                "actions": [
                    {
                        "type": "log",
                        "level": "debug",
                        "message_template": "New IP discovered: {name}"
                    }
                ]
            }
        ])

    return config


def save_config(config: Dict[str, Any], filepath: str, overwrite: bool = False):
    """Save configuration to file"""

    if os.path.exists(filepath) and not overwrite:
        logger.warning("File %s already exists. Use --overwrite to replace it.", filepath)
        return False

    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2, sort_keys=False)

        logger.info("Configuration saved to %s", filepath)
        return True

    except Exception as e:
        logger.error("Error saving configuration: %s", e)
        return False


def main():
    apply_service_logging(
        service="event-handler",
        include_uvicorn=False,
        log_format=os.getenv("LOG_FORMAT", "text"),
        root_level=parse_log_level(os.getenv("LOG_LEVEL"), logging.INFO),
        text_format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Generate event handler configuration files")
    parser.add_argument("output", help="Output configuration file path")
    parser.add_argument(
        "--type",
        choices=["typosquat", "critical", "assets", "comprehensive"],
        default="comprehensive",
        help="Type of configuration to generate"
    )
    parser.add_argument(
        "--include-examples",
        action="store_true",
        help="Include example handlers (only for comprehensive type)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing configuration file"
    )

    args = parser.parse_args()

    # Generate configuration based on type
    if args.type == "typosquat":
        config = generate_typosquat_config()
    elif args.type == "critical":
        config = generate_critical_findings_config()
    elif args.type == "assets":
        config = generate_asset_discovery_config()
    elif args.type == "comprehensive":
        config = generate_comprehensive_config(args.include_examples)
    else:
        logger.error("Unknown configuration type: %s", args.type)
        return

    # Save configuration
    success = save_config(config, args.output, args.overwrite)

    if success:
        logger.info(
            "Generated %s configuration with %d handlers",
            args.type,
            len(config["handlers"]),
        )
        for handler in config["handlers"]:
            et = handler["event_type"]
            et_display = ", ".join(et) if isinstance(et, list) else str(et)
            logger.info("  - %s: %s", et_display, handler["description"])


if __name__ == "__main__":
    main()
