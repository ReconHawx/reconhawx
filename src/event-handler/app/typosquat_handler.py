#!/usr/bin/env python3
"""
Typosquat domain finding handler

This module provides specialized handling for typosquat domain findings,
including validation, enrichment, and workflow triggering.
"""

import logging
from typing import Any, Dict, List

from .event_handlers import (
    EventHandler,
    Condition,
    Action,
    ActionResult,
    registry
)

logger = logging.getLogger(__name__)


class TyposquatValidationCondition(Condition):
    """Validate typosquat findings have required attributes"""

    def __init__(self, required_fields: List[str]):
        self.required_fields = required_fields

    def _get_nested_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get nested value using dot notation"""
        keys = field_path.split('.')
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current


class TyposquatEnrichmentAction(Action):
    """Enrich typosquat findings with additional data"""

    async def execute(self, event_data: Dict[str, Any]) -> ActionResult:
        try:
            # Extract domain information
            domain = event_data.get("asset", {}).get("name", "")
            if not domain:
                return ActionResult(
                    success=False,
                    message="No domain found in event data"
                )

            # Add enrichment data
            enrichment = {
                "domain_length": len(domain),
                "has_numbers": any(c.isdigit() for c in domain),
                "has_hyphens": "-" in domain,
                "tld": domain.split(".")[-1] if "." in domain else "",
                "subdomain_count": len(domain.split(".")) - 2 if domain.count(".") > 1 else 0
            }

            # Add enrichment to event data for subsequent actions
            if "enrichment" not in event_data:
                event_data["enrichment"] = {}
            event_data["enrichment"].update(enrichment)

            logger.info(f"Enriched typosquat data for {domain}: {enrichment}")

            return ActionResult(
                success=True,
                message=f"Successfully enriched typosquat data for {domain}",
                data=enrichment
            )

        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Exception during enrichment: {str(e)}"
            )


class TyposquatWorkflowTriggerAction(Action):
    """Trigger workflow for typosquat investigation"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.workflow_name = config.get("workflow_name", "typosquat-investigation")
        self.api_url = config.get("api_url", "http://api:8000")
        self.api_key = config.get("api_key", "")

    async def execute(self, event_data: Dict[str, Any]) -> ActionResult:
        try:
            # Extract domain and other relevant data
            domain = event_data.get("asset", {}).get("name", "")
            severity = event_data.get("severity", "unknown")
            program_name = event_data.get("program_name", "unknown")

            if not domain:
                return ActionResult(
                    success=False,
                    message="No domain found in event data for workflow trigger"
                )

            # Prepare workflow parameters
            workflow_params = {
                "domain": domain,
                "severity": severity,
                "program_name": program_name,
                "template_id": event_data.get("template_id", ""),
                "url": event_data.get("url", ""),
                "timestamp": event_data.get("timestamp", ""),
                "enrichment": event_data.get("enrichment", {})
            }

            # Add any additional parameters from config
            config_params = self.config.get("parameters", {})
            workflow_params.update(config_params)

            # Trigger workflow via API
            import requests

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "workflow_name": self.workflow_name,
                "triggered_by": "typosquat_handler",
                "event_data": event_data,
                "parameters": workflow_params
            }

            response = requests.post(
                f"{self.api_url}/workflows/{self.workflow_name}/trigger",
                json=payload,
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                result_data = response.json()
                job_id = result_data.get("job_id", "unknown")

                return ActionResult(
                    success=True,
                    message=f"Typosquat investigation workflow triggered for {domain} (job: {job_id})",
                    data={
                        "workflow_name": self.workflow_name,
                        "job_id": job_id,
                        "domain": domain,
                        "parameters": workflow_params
                    }
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"Workflow trigger failed with status {response.status_code}: {response.text}"
                )

        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Exception during workflow trigger: {str(e)}"
            )


class TyposquatDiscordNotificationAction(Action):
    """Send Discord notification specifically formatted for typosquat findings"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        # Import here to avoid circular imports
        from .discord import DiscordClient
        self.discord = DiscordClient(config)

    async def execute(self, event_data: Dict[str, Any]) -> ActionResult:
        try:
            webhook_url = self.config.get("webhook_url")
            if not webhook_url:
                return ActionResult(
                    success=False,
                    message="No webhook URL configured for typosquat notifications"
                )

            # Extract domain information
            domain = event_data.get("asset", {}).get("name", "")
            severity = event_data.get("severity", "unknown").upper()
            template_id = event_data.get("template_id", "unknown")
            url = event_data.get("url", "")

            if not domain:
                return ActionResult(
                    success=False,
                    message="No domain found in event data"
                )

            # Create rich embed for typosquat
            title = f"🚨 TYPOSQUAT ALERT: {domain}"
            description = f"**Severity:** {severity}\n**Template:** {template_id}\n**URL:** {url}"

            # Add enrichment data if available
            enrichment = event_data.get("enrichment", {})
            if enrichment:
                enrichment_lines = []
                if enrichment.get("domain_length"):
                    enrichment_lines.append(f"Length: {enrichment['domain_length']}")
                if enrichment.get("tld"):
                    enrichment_lines.append(f"TLD: {enrichment['tld']}")
                if enrichment.get("subdomain_count", 0) > 0:
                    enrichment_lines.append(f"Subdomains: {enrichment['subdomain_count']}")

                if enrichment_lines:
                    description += "\n\n**Domain Analysis:**\n" + "\n".join(f"• {line}" for line in enrichment_lines)

            embed = {
                "title": title,
                "description": description,
                "color": 15158332,  # Red color for alerts
                "fields": [
                    {
                        "name": "Recommended Actions",
                        "value": "• Verify domain ownership\n• Check for malicious activity\n• Update security policies\n• Monitor for similar domains",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": f"Program: {event_data.get('program_name', 'unknown')}"
                }
            }

            success = self.discord.send(webhook_url, embeds=[embed])

            return ActionResult(
                success=success,
                message=f"Typosquat Discord notification {'sent' if success else 'failed'} for {domain}",
                data={"embed": embed, "domain": domain}
            )

        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Exception during Discord notification: {str(e)}"
            )


class TyposquatAIAnalysisAction(Action):
    """Trigger AI analysis for a newly ingested typosquat finding via the API."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_url = config.get("api_url", "http://api:8000")
        self.api_key = config.get("api_key", "")

    async def execute(self, event_data: Dict[str, Any]) -> ActionResult:
        try:
            finding_id = event_data.get("finding_id", "")
            if not finding_id:
                return ActionResult(
                    success=False,
                    message="No finding_id in event data for AI analysis"
                )

            import httpx
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.api_url}/findings/typosquat/ai-analyze/{finding_id}",
                    headers=headers,
                )

            if resp.status_code in (200, 202):
                return ActionResult(
                    success=True,
                    message=f"AI analysis triggered for finding {finding_id}",
                    data=resp.json(),
                )
            else:
                return ActionResult(
                    success=False,
                    message=f"AI analysis trigger returned HTTP {resp.status_code}",
                )
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Exception triggering AI analysis: {str(e)}",
            )


def create_typosquat_handler() -> EventHandler:
    """Create a pre-configured typosquat handler"""

    # Conditions for typosquat handling
    conditions = [
        TyposquatValidationCondition([
            "asset.name",  # Domain name
            "severity",    # Finding severity
            "program_name" # Program context
        ])
    ]

    # Actions for typosquat handling
    actions = [
        TyposquatEnrichmentAction({}),
        TyposquatDiscordNotificationAction({
            "webhook_url": "{program_settings.discord_webhook_url}"
        }),
        TyposquatWorkflowTriggerAction({
            "workflow_name": "typosquat-investigation",
            "api_url": "{api_base_url}",
            "api_key": "{internal_api_key}",
            "parameters": {
                "priority": "high",
                "investigation_type": "typosquat_domain"
            }
        }),
        TyposquatAIAnalysisAction({
            "api_url": "{api_base_url}",
            "api_key": "{internal_api_key}",
        }),
    ]

    return EventHandler("findings.nuclei.typosquat", conditions, actions)


def register_typosquat_handler():
    """Register the typosquat handler with the global registry"""
    handler = create_typosquat_handler()
    registry.register_handler(handler)
    logger.info("Registered typosquat domain finding handler")


# Auto-register the handler when module is imported
register_typosquat_handler()
