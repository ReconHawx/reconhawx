"""
API-based event handler config provider.
Fetches effective config from API and caches in Redis.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from .config import NotifierConfig

logger = logging.getLogger(__name__)

CACHE_KEY_PREFIX = "event_handler:config:"


class ApiConfigProvider:
    """Fetches event handler config from API with Redis cache."""

    def __init__(self, cfg: NotifierConfig, redis_client):
        self.cfg = cfg
        self.redis = redis_client
        self.cache_ttl = cfg.api_config_cache_ttl

    def get_handlers(self, program_name: str) -> List[Dict[str, Any]]:
        """Get effective handlers for a program. Uses Redis cache, then API."""
        cache_key = f"{CACHE_KEY_PREFIX}{program_name or '__global__'}"
        try:
            cached = self.redis.get(cache_key)
            if cached:
                handlers = json.loads(cached.decode("utf-8"))
                logger.debug(f"Using cached handler config for '{program_name or 'global'}' ({len(handlers)} handlers)")
                return handlers
        except Exception as e:
            logger.debug(f"Redis read error for {cache_key}: {e}")

        handlers = self._fetch_from_api(program_name)
        if handlers is not None:
            try:
                self.redis.setex(cache_key, self.cache_ttl, json.dumps(handlers))
            except Exception as e:
                logger.debug(f"Redis write error for {cache_key}: {e}")
            return handlers

        logger.warning(
            "No handler config from API for program '%s'; returning empty handler list",
            program_name or "global",
        )
        return []

    def _fetch_from_api(self, program_name: Optional[str]) -> Optional[List[Dict[str, Any]]]:
        """Fetch effective config from API. Returns None on failure."""
        if not self.cfg.api_url or not self.cfg.internal_service_api_key:
            logger.debug("API URL or internal key not configured, skipping API fetch")
            return None

        url = f"{self.cfg.api_url}/internal/event-handler-configs"
        if program_name:
            url += f"?program_name={program_name}"
        headers = {"Content-Type": "application/json"}
        headers["Authorization"] = f"Bearer {self.cfg.internal_service_api_key}"

        try:
            resp = requests.get(url, timeout=self.cfg.api_request_timeout, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                handlers = data.get("handlers", [])
                logger.info(f"Fetched {len(handlers)} handlers from API for program '{program_name or 'global'}'")
                return handlers
            logger.warning(f"API returned {resp.status_code} for event-handler-configs")
        except requests.exceptions.Timeout:
            logger.warning("Timeout fetching event handler config from API")
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error fetching event handler config from API")
        except Exception as e:
            logger.warning(f"Error fetching event handler config from API: {e}")
        return None

    def invalidate_cache(self, program_name: Optional[str] = None):
        """Invalidate cache for a program or all programs (program_name=None deletes all config keys)."""
        try:
            if program_name is not None:
                key = f"{CACHE_KEY_PREFIX}{program_name}"
                self.redis.delete(key)
                logger.debug(f"Invalidated cache for {program_name}")
            else:
                for key in self.redis.scan_iter(match=f"{CACHE_KEY_PREFIX}*"):
                    self.redis.delete(key)
                logger.debug("Invalidated all event handler config cache")
        except Exception as e:
            logger.warning(f"Error invalidating cache: {e}")
