#!/usr/bin/env python3
import logging
import json
from typing import Any, Dict

import redis

from .config import NotifierConfig
import requests

logger = logging.getLogger(__name__)


class ProgramSettingsProvider:
    """API-based program settings provider.

    Fetches program notification settings directly from the API.
    """

    def __init__(self, cfg: NotifierConfig, redis_client: redis.Redis):
        self.cfg = cfg
        self.redis = redis_client
        self.cache_ttl = 300  # seconds

    def get_program_settings(self, program_name: str) -> Dict[str, Any]:
        cache_key = f"notify:settings:{program_name}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                settings = json.loads(cached.decode("utf-8"))
                logger.info("Using cached program settings for '%s' (enabled=%s, webhook=%s)", program_name, bool(settings.get("enabled")), bool(settings.get("discord_webhook_url")))
                return settings
        except Exception as e:
            logger.debug("Redis read error for %s: %s", cache_key, e)

        # Fetch from API
        settings: Dict[str, Any] = {}
        logger.info("Fetching program settings from API for '%s'", program_name)

        if not self.cfg.api_url:
            logger.error("Data API URL not configured, cannot fetch program settings")
            return self._get_default_settings()

        try:
            import time
            start_time = time.time()
            headers = {"Content-Type": "application/json"}
            if self.cfg.internal_service_api_key:
                headers["Authorization"] = f"Bearer {self.cfg.internal_service_api_key}"

            #logger.debug("Making API request to %s/programs/%s", self.cfg.api_url, program_name)
            resp = requests.get(
                f"{self.cfg.api_url}/programs/{program_name}",
                timeout=self.cfg.api_request_timeout,
                headers=headers
            )

            request_time = time.time() - start_time
            #logger.debug("API request completed in %.2f seconds", request_time)

            if resp.status_code == 200:
                data = resp.json() or {}
                settings = data.get("notification_settings") or {}
                logger.info("Fetched program settings from API for '%s' (enabled=%s, webhook=%s) in %.2fs",
                          program_name, bool(settings.get("enabled")), bool(settings.get("discord_webhook_url")), request_time)
            elif resp.status_code == 404:
                logger.warning("Program '%s' not found in API, using default disabled settings", program_name)
                settings = self._get_default_settings()
            else:
                logger.error("API returned %s when fetching program '%s' settings: %s",
                           resp.status_code, program_name, resp.text)
                settings = self._get_default_settings()

        except requests.exceptions.Timeout:
            logger.error("Timeout fetching program settings for '%s' from API", program_name)
            settings = self._get_default_settings()
        except requests.exceptions.ConnectionError:
            logger.error("Connection error fetching program settings for '%s' from API", program_name)
            settings = self._get_default_settings()
        except Exception as e:
            logger.error("Unexpected error fetching program settings for '%s': %s", program_name, str(e))
            settings = self._get_default_settings()

        # Precompute notify_webhook_* for handler template resolution
        settings = self._precompute_notify_webhooks(settings)

        # Cache the settings (including default disabled settings)
        try:
            self.redis.setex(cache_key, self.cache_ttl, json.dumps(settings))
            #logger.debug("Cached settings for '%s' (ttl=%ds)", program_name, self.cache_ttl)
        except Exception as e:
            logger.debug("Redis write error for %s: %s", cache_key, e)

        return settings

    def _get_default_settings(self) -> Dict[str, Any]:
        """Get default disabled settings when API is unavailable or program not found"""
        return {
            "enabled": False,
            "discord_webhook_url": None,
            "events": {}
        }

    def _precompute_notify_webhooks(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """Precompute notify_webhook_X for each handler type (event-specific or global fallback)."""
        global_wh = (settings.get("discord_webhook_url") or "").strip()

        def get_wh(*path, key="webhook_url"):
            obj = settings
            for p in path:
                obj = (obj or {}).get(p)
                if obj is None:
                    return global_wh
            if isinstance(obj, str) and obj.strip():
                return obj.strip()
            if isinstance(obj, dict):
                wh = (obj.get(key) or obj.get("webhook_url") or "").strip()
                return wh or global_wh
            return global_wh

        out = dict(settings)
        out["notify_webhook_ct_alert"] = get_wh("events", "ct_alerts")
        out["notify_webhook_subdomain_created_resolved"] = get_wh("events", "assets", "created", "subdomain")
        out["notify_webhook_subdomain_resolved"] = get_wh("events", "assets", "updated", "subdomain")
        out["notify_webhook_nuclei"] = get_wh("events", "findings", key="nuclei_webhook_url")
        for asset in ["url", "ip", "service", "certificate"]:
            for action in ["created", "updated"]:
                out[f"notify_webhook_{asset}_{action}"] = get_wh("events", "assets", action, asset)
        return out
