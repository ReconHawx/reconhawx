"""Notification handler templates for program-specific Discord notifications.

When program managers enable notifications, handlers are generated from these templates.
Webhook URL is resolved from notification_settings (event-specific or global fallback).
"""

from typing import Any, Dict, List

# Handler IDs that are Discord-only and should be removed from global when syncing
DISCORD_HANDLER_IDS = {
    "ct_typosquat_alert_notification",
    "subdomain_created_resolved_notification",
    "subdomain_resolved_notification_updated",
}

# Prefix for generated notification handlers (used when merging)
NOTIFY_HANDLER_PREFIX = "notify_"




def _get_webhook_for_handler(
    notification_settings: Dict[str, Any], handler_key: str
) -> str:
    """Get resolved webhook for a handler. Used to check if webhook is configured before adding handler."""
    global_wh = (notification_settings.get("discord_webhook_url") or "").strip()

    # Map handler keys to notification_settings paths
    webhook_paths = {
        "ct_alert": ("events", "ct_alerts"),
        "subdomain_created_resolved": ("events", "assets", "created", "subdomain"),
        "subdomain_resolved": ("events", "assets", "updated", "subdomain"),
        "nuclei": ("events", "findings"),
    }

    def get_from_path(*path_parts):
        obj = notification_settings
        for p in path_parts:
            obj = (obj or {}).get(p)
            if obj is None:
                return ""
        if isinstance(obj, str) and obj.strip():
            return obj.strip()
        if isinstance(obj, dict):
            return (obj.get("webhook_url") or "").strip()
        return ""

    if handler_key in webhook_paths:
        path = webhook_paths[handler_key]
        obj = notification_settings
        for p in path:
            obj = (obj or {}).get(p)
            if obj is None:
                return global_wh
        if isinstance(obj, str) and obj.strip():
            return obj.strip()
        if isinstance(obj, dict):
            wh = (obj.get("nuclei_webhook_url") or obj.get("webhook_url") or "").strip()
            if wh:
                return wh
        return global_wh

    # Generic asset: url_created -> events.assets.created.url
    if "_created" in handler_key or "_updated" in handler_key:
        parts = handler_key.split("_")
        if len(parts) >= 2:
            asset_type, action = parts[0], parts[1]
            wh = get_from_path("events", "assets", action, asset_type)
            if wh:
                return wh
    return global_wh


def _build_webhook_template(handler_key: str) -> str:
    """Build template path for webhook - event-handler will resolve with fallback to global."""
    # ProgramSettingsProvider will precompute notify_webhook_{key} = resolved URL
    return "{program_settings.notify_webhook_" + handler_key + "}"


def get_notification_handler_templates() -> Dict[str, Dict[str, Any]]:
    """Return handler templates keyed by handler_key (e.g. ct_alert, subdomain_created_resolved)."""
    return {
        "ct_alert": {
            "id": "notify_ct_alert",
            "event_type": "typosquat.ct_alert",
            "description": "Discord notification for CT monitor alerts (critical/high)",
            "conditions": [
                {"type": "field_value", "field": "priority", "operator": "in", "expected_value": ["critical", "high"]}
            ],
            "action": {
                "type": "discord_notification",
                "title_template": "🚨 CT Alert: Suspicious Certificate Detected",
                "description_template": (
                    "**Detected Domain:** `{detected_domain}`\n"
                    "**Protected Domain:** `{protected_domain}`\n"
                    "**Match Type:** {match_type}\n"
                    "**Similarity:** {similarity_score}\n"
                    "**Priority:** {priority}\n"
                    "**Certificate Issuer:** {certificate.issuer}\n"
                    "**Program:** {program_name}"
                ),
                "batch_title_template": "🚨 CT Alert: {event_count} Suspicious Certificates",
                "batch_description_template": (
                    "**{event_count} suspicious certificates** detected by CT Monitor\n\n"
                    "**Domains:**\n{detected_domain_list}\n\n"
                    "**Programs:** {program_list}"
                ),
                "color": 15158332,
                "batch_color": 15105570,
                "batching": {"max_events": 10, "max_delay_seconds": 60},
            },
        },
        "subdomain_created_resolved": {
            "id": "notify_subdomain_created_resolved",
            "event_type": "assets.subdomain.created",
            "description": "Discord notification for subdomains created with IPs",
            "conditions": [
                {"type": "field_exists", "field": "ip"},
                {"type": "field_value", "field": "ip", "operator": "not_empty"},
                {"type": "field_value", "field": "resolution_status", "operator": "equals", "expected_value": "created_resolved"},
            ],
            "action": {
                "type": "discord_notification",
                "title_template": "🎯 Subdomain Created (Resolved): {name}",
                "description_template": "**Subdomain:** {name}\n**Program:** {program_name}\n**IPs:** {ip}\n**Apex Domain:** {apex_domain}",
                "batch_title_template": "🎯 Subdomains Created (Resolved) ({domain_count})",
                "batch_description_template": "**{domain_count} subdomains** created with IP addresses for program `{program_name}`\n\n**Domains:** {domain_list}",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "subdomain_resolved": {
            "id": "notify_subdomain_resolved",
            "event_type": "assets.subdomain.updated",
            "description": "Discord notification for subdomains resolved via update",
            "conditions": [
                {"type": "field_value", "field": "new_ip_count", "operator": "greater_than", "expected_value": 0},
                {"type": "field_value", "field": "previous_ip_count", "operator": "equals", "expected_value": 0},
            ],
            "action": {
                "type": "discord_notification",
                "title_template": "🎯 Subdomain Resolved: {name}",
                "description_template": "**Subdomain:** {name}\n**Program:** {program_name}",
                "batch_title_template": "🎯 Subdomains Resolved ({domain_count})",
                "batch_description_template": "**{domain_count} subdomains** resolved for program `{program_name}`\n\n**Domains:** {domain_list}\n\n**Summary:** {domain_count} subdomains now resolves to an IP address.",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "url_created": {
            "id": "notify_url_created",
            "event_type": "assets.url.created",
            "description": "Discord notification for new URLs",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🔗 URL Created: {name}",
                "description_template": "**URL:** {name}\n**Program:** {program_name}",
                "batch_title_template": "🔗 URLs Created ({url_count})",
                "batch_description_template": "**{url_count} URLs** created for program `{program_name}`\n\n**URLs:** {url_list}",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "url_updated": {
            "id": "notify_url_updated",
            "event_type": "assets.url.updated",
            "description": "Discord notification for updated URLs",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🔗 URL Updated: {name}",
                "description_template": "**URL:** {name}\n**Program:** {program_name}",
                "batch_title_template": "🔗 URLs Updated ({url_count})",
                "batch_description_template": "**{url_count} URLs** updated for program `{program_name}`\n\n**URLs:** {url_list}",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "ip_created": {
            "id": "notify_ip_created",
            "event_type": "assets.ip.created",
            "description": "Discord notification for new IPs",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🌐 IP Created: {ip_address}",
                "description_template": "**IP:** {ip_address}\n**Program:** {program_name}",
                "batch_title_template": "🌐 IPs Created ({ip_count})",
                "batch_description_template": "**{ip_count} IPs** created for program `{program_name}`\n\n**IPs:** {ip_list}",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "ip_updated": {
            "id": "notify_ip_updated",
            "event_type": "assets.ip.updated",
            "description": "Discord notification for updated IPs",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🌐 IP Updated: {ip_address}",
                "description_template": "**IP:** {ip_address}\n**Program:** {program_name}",
                "batch_title_template": "🌐 IPs Updated ({ip_count})",
                "batch_description_template": "**{ip_count} IPs** updated for program `{program_name}`\n\n**IPs:** {ip_list}",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "service_created": {
            "id": "notify_service_created",
            "event_type": "assets.service.created",
            "description": "Discord notification for new services",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "⚙️ Service Created: {ip}:{port}",
                "description_template": "**Service:** {ip}:{port}\n**Program:** {program_name}",
                "batch_title_template": "⚙️ Services Created ({event_count})",
                "batch_description_template": "**{event_count} services** created for program `{program_name}`",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "service_updated": {
            "id": "notify_service_updated",
            "event_type": "assets.service.updated",
            "description": "Discord notification for updated services",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "⚙️ Service Updated: {ip}:{port}",
                "description_template": "**Service:** {ip}:{port}\n**Program:** {program_name}",
                "batch_title_template": "⚙️ Services Updated ({event_count})",
                "batch_description_template": "**{event_count} services** updated for program `{program_name}`",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "certificate_created": {
            "id": "notify_certificate_created",
            "event_type": "assets.certificate.created",
            "description": "Discord notification for new certificates",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🔒 Certificate Created",
                "description_template": "**Program:** {program_name}\n**Subject:** {subject_dn}",
                "batch_title_template": "🔒 Certificates Created ({event_count})",
                "batch_description_template": "**{event_count} certificates** created for program `{program_name}`",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
        "certificate_updated": {
            "id": "notify_certificate_updated",
            "event_type": "assets.certificate.updated",
            "description": "Discord notification for updated certificates",
            "conditions": [],
            "action": {
                "type": "discord_notification",
                "title_template": "🔒 Certificate Updated",
                "description_template": "**Program:** {program_name}\n**Subject:** {subject_dn}",
                "batch_title_template": "🔒 Certificates Updated ({event_count})",
                "batch_description_template": "**{event_count} certificates** updated for program `{program_name}`",
                "color": 5763719,
                "batch_color": 3066993,
                "batching": {"max_events": 15, "max_delay_seconds": 60},
            },
        },
    }


def _get_asset_event_key(asset_type: str, action: str) -> str:
    """Map asset type + action to handler key."""
    return f"{asset_type}_{action}"


def _normalize_event_value(val: Any) -> bool:
    """Support both old (bool) and new ({enabled, webhook_url}) format."""
    if isinstance(val, bool):
        return val
    if isinstance(val, dict):
        return val.get("enabled", False)
    return False


def _is_event_enabled(notification_settings: Dict[str, Any], handler_key: str) -> bool:
    """Check if the event type is enabled in notification_settings."""
    if not notification_settings.get("enabled"):
        return False
    events = notification_settings.get("events") or {}

    # ct_alert
    if handler_key == "ct_alert":
        ct = events.get("ct_alerts") or {}
        if isinstance(ct, dict):
            return ct.get("enabled", False)
        return bool(ct)

    # subdomain created/updated (specific handlers)
    if handler_key == "subdomain_created_resolved":
        created = (events.get("assets") or {}).get("created") or {}
        sub = created.get("subdomain") if isinstance(created, dict) else None
        return _normalize_event_value(sub)
    if handler_key == "subdomain_resolved":
        updated = (events.get("assets") or {}).get("updated") or {}
        sub = updated.get("subdomain") if isinstance(updated, dict) else None
        return _normalize_event_value(sub)

    # generic asset types: url, ip, service, certificate
    asset_keys = ["url_created", "url_updated", "ip_created", "ip_updated", "service_created", "service_updated", "certificate_created", "certificate_updated"]
    if handler_key in asset_keys:
        parts = handler_key.split("_")
        if len(parts) >= 2:
            asset_type, action = parts[0], parts[1]
            assets = (events.get("assets") or {}).get(action) or {}
            ev = assets.get(asset_type) if isinstance(assets, dict) else None
            return _normalize_event_value(ev)

    # nuclei - each severity gets its own handler
    if handler_key.startswith("nuclei_"):
        sev = handler_key.replace("nuclei_", "")
        severities = (events.get("findings") or {}).get("nuclei_severities") or []
        return sev in severities

    return False


def generate_handlers_from_notification_settings(
    notification_settings: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Generate notification handlers from notification_settings.

    Returns list of handler configs for enabled events.
    Webhook URL uses template {program_settings.notify_webhook_<key>} for runtime resolution.
    """
    handlers = []
    templates = get_notification_handler_templates()
    global_webhook = (notification_settings.get("discord_webhook_url") or "").strip()

    # CT alert
    if _is_event_enabled(notification_settings, "ct_alert"):
        t = templates["ct_alert"]
        wh = _get_webhook_for_handler(notification_settings, "ct_alert")
        if wh:
            h = {
                "id": t["id"],
                "event_type": t["event_type"],
                "description": t["description"],
                "conditions": t["conditions"],
                "actions": [{**t["action"], "webhook_url": _build_webhook_template("ct_alert")}],
            }
            handlers.append(h)

    # Subdomain specific
    if _is_event_enabled(notification_settings, "subdomain_created_resolved"):
        t = templates["subdomain_created_resolved"]
        if _get_webhook_for_handler(notification_settings, "subdomain_created_resolved"):
            h = {
                "id": t["id"],
                "event_type": t["event_type"],
                "description": t["description"],
                "conditions": t["conditions"],
                "actions": [{**t["action"], "webhook_url": _build_webhook_template("subdomain_created_resolved")}],
            }
            handlers.append(h)

    if _is_event_enabled(notification_settings, "subdomain_resolved"):
        t = templates["subdomain_resolved"]
        if _get_webhook_for_handler(notification_settings, "subdomain_resolved"):
            h = {
                "id": t["id"],
                "event_type": t["event_type"],
                "description": t["description"],
                "conditions": t["conditions"],
                "actions": [{**t["action"], "webhook_url": _build_webhook_template("subdomain_resolved")}],
            }
            handlers.append(h)

    # Generic asset types
    for key in ["url_created", "url_updated", "ip_created", "ip_updated", "service_created", "service_updated", "certificate_created", "certificate_updated"]:
        if _is_event_enabled(notification_settings, key):
            t = templates.get(key)
            if t:
                # Use global or asset-specific webhook
                wh = _get_webhook_for_handler(notification_settings, key)
                if not wh:
                    wh = global_webhook
                if wh:
                    h = {
                        "id": t["id"],
                        "event_type": t["event_type"],
                        "description": t["description"],
                        "conditions": t["conditions"],
                        "actions": [{**t["action"], "webhook_url": _build_webhook_template(key)}],
                    }
                    handlers.append(h)

    # Nuclei - one handler per enabled severity, all use nuclei_webhook_url
    nuclei_severities = (notification_settings.get("events") or {}).get("findings") or {}
    severities = nuclei_severities.get("nuclei_severities") or []
    if isinstance(severities, list) and severities:
        wh = (nuclei_severities.get("nuclei_webhook_url") or "").strip() or global_webhook
        if wh:
            for sev in severities:
                if isinstance(sev, str):
                    key = f"nuclei_{sev}"
                    h = {
                        "id": f"notify_nuclei_{sev}",
                        "event_type": f"findings.nuclei.{sev}",
                        "description": f"Discord notification for Nuclei {sev} findings",
                        "conditions": [],
                        "actions": [{
                            "type": "discord_notification",
                            "title_template": f"🔍 Nuclei {sev.capitalize()}: {{template_id}}",
                            "description_template": "**Finding:** {template_id}\n**Program:** {program_name}\n**Host:** {host}",
                            "batch_title_template": f"🔍 Nuclei {sev.capitalize()} Findings ({{event_count}})",
                            "batch_description_template": "**{event_count} findings** for program `{program_name}`",
                            "webhook_url": _build_webhook_template("nuclei"),
                            "color": 15158332 if sev in ("critical", "high") else 5763719,
                            "batch_color": 3066993,
                            "batching": {"max_events": 15, "max_delay_seconds": 60},
                        }],
                    }
                    handlers.append(h)

    return handlers


def filter_discord_handlers(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove Discord-only handlers from the list."""
    return [h for h in handlers if h.get("id") not in DISCORD_HANDLER_IDS]


def filter_notification_handlers(handlers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove generated notification handlers (id starts with notify_)."""
    return [h for h in handlers if not (h.get("id") or "").startswith(NOTIFY_HANDLER_PREFIX)]


def merge_handlers(
    base_handlers: List[Dict[str, Any]],
    notification_handlers: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge: base (with discord removed) + notification handlers."""
    filtered = filter_discord_handlers(base_handlers)
    notify_ids = {h.get("id") for h in notification_handlers}
    filtered = [h for h in filtered if h.get("id") not in notify_ids]
    return filtered + notification_handlers


async def sync_notification_handlers_for_program(
    program_id: str,
    program_name: str,
    notification_settings: Dict[str, Any],
) -> None:
    """Strip persisted ``notify_*`` handlers from program rows.

    Notification handlers are merged at effective-config read time from ``notification_settings``;
    they must not remain in ``event_handler_configs``.
    """
    from repository import EventHandlerConfigRepository

    program_config = await EventHandlerConfigRepository.get_program_config(program_id)
    if not program_config:
        return

    handlers = program_config.get("handlers") or []
    base_filtered = filter_discord_handlers(filter_notification_handlers(handlers))
    if base_filtered == handlers:
        return

    addon_mode = await EventHandlerConfigRepository.get_program_addon_mode(program_id)
    if not base_filtered:
        await EventHandlerConfigRepository.delete_program_config(program_id)
        return
    await EventHandlerConfigRepository.set_program_config(
        program_id, base_filtered, addon_mode=addon_mode
    )
