#!/usr/bin/env python3
import logging
import time
from typing import Any, Dict, List

import requests

from .config import NotifierConfig

logger = logging.getLogger(__name__)


class DiscordClient:
    def __init__(self, cfg: NotifierConfig):
        self.cfg = cfg

    def send(self, webhook_url: str, content: str = None, embeds: List[Dict[str, Any]] = None, max_retries: int = 3) -> bool:
        payload: Dict[str, Any] = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds
        backoff = 1.0
        for attempt in range(max_retries + 1):
            try:
                logger.info("Sending Discord message: %s", payload)
                resp = requests.post(webhook_url, json=payload, timeout=10)
                if resp.status_code in (200, 204):
                    return True
                if resp.status_code == 429:
                    try:
                        retry_after = resp.json().get("retry_after", backoff)
                    except Exception:
                        retry_after = backoff
                    logger.warning("Discord rate limited, retrying in %ss", retry_after)
                    time.sleep(float(retry_after))
                else:
                    logger.warning("Discord error %s: %s", resp.status_code, resp.text[:200])
                    time.sleep(backoff)
            except Exception as e:
                logger.warning("Discord post failed (attempt %s/%s): %s", attempt + 1, max_retries + 1, e)
                time.sleep(backoff)
            backoff = min(backoff * 2, 30)
        return False


