"""Fire-and-forget CT monitor control for API-side triggers (program settings)."""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CT_MONITOR_URL = os.getenv("CT_MONITOR_URL", "http://ct-monitor:8002")

# Single-flight coalesced background sync (program save path).
_ct_sync_task: Optional[asyncio.Task] = None
_ct_sync_rerun_requested = False


async def ensure_ct_monitor_started() -> None:
    """
    Ask ct-monitor to start. Idempotent: treats 'already running' as success.
    Logs warnings on failure; does not raise (program save should still succeed).
    """
    base = CT_MONITOR_URL.rstrip("/")
    url = f"{base}/start"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url)
            if response.status_code == 200:
                logger.info("CT monitor start acknowledged (%s)", url)
                return
            if response.status_code == 400:
                try:
                    body = response.json()
                    msg = (body.get("message") or "").lower()
                except Exception:
                    msg = response.text.lower()
                if "already running" in msg:
                    return
            logger.warning(
                "CT monitor POST /start returned %s: %s",
                response.status_code,
                (response.text or "")[:500],
            )
    except httpx.ConnectError as e:
        logger.warning("Could not connect to CT monitor at %s: %s", base, e)
    except httpx.TimeoutException:
        logger.warning("Timeout starting CT monitor at %s", base)
    except Exception as e:
        logger.warning("Error starting CT monitor: %s", e)


async def notify_ct_monitor_reload_runtime_settings() -> None:
    """
    Ask ct-monitor to reload global runtime settings from the API.
    Fire-and-forget; logs warnings on failure.
    """
    base = CT_MONITOR_URL.rstrip("/")
    url = f"{base}/reload-runtime-settings"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url)
            if response.status_code == 200:
                logger.info("CT monitor runtime reload acknowledged (%s)", url)
                return
            logger.warning(
                "CT monitor POST %s returned %s: %s",
                url,
                response.status_code,
                (response.text or "")[:500],
            )
    except httpx.ConnectError as e:
        logger.warning("Could not connect to CT monitor at %s: %s", base, e)
    except httpx.TimeoutException:
        logger.warning("Timeout reloading CT monitor runtime at %s", base)
    except Exception as e:
        logger.warning("Error notifying CT monitor runtime reload: %s", e)


async def sync_ct_monitor_program_config() -> None:
    """
    Ensure ct-monitor is running, then reload program CT config from the API.
    Call after ct_monitoring_enabled (or related program) changes so matchers update.
    """
    await ensure_ct_monitor_started()
    base = CT_MONITOR_URL.rstrip("/")
    url = f"{base}/refresh-domains"
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url)
                if response.status_code in (200, 202):
                    logger.info("CT monitor config reload acknowledged (%s)", url)
                    return
                if response.status_code == 503 and attempt < 2:
                    logger.info(
                        "CT monitor refresh returned 503; retrying after start settles (%s/3)",
                        attempt + 1,
                    )
                    await asyncio.sleep(1.0)
                    continue
                logger.warning(
                    "CT monitor POST /refresh-domains returned %s: %s",
                    response.status_code,
                    (response.text or "")[:500],
                )
                return
        except httpx.ConnectError as e:
            logger.warning("Could not connect to CT monitor at %s: %s", base, e)
            return
        except httpx.TimeoutException:
            logger.warning("Timeout reloading CT monitor config at %s", base)
            return
        except Exception as e:
            logger.warning("Error reloading CT monitor config: %s", e)
            return


async def _coalesced_sync_worker(initial_reason: str) -> None:
    """Run CT config sync; coalesce rapid triggers into one follow-up refresh."""
    global _ct_sync_task, _ct_sync_rerun_requested

    reason = initial_reason
    while True:
        _ct_sync_rerun_requested = False
        try:
            if reason:
                logger.info("CT monitor config sync scheduled (%s)", reason)
            await sync_ct_monitor_program_config()
        except Exception:
            logger.exception("Background CT monitor config sync failed")
        reason = ""
        if _ct_sync_rerun_requested:
            logger.info("CT monitor config sync rerun requested; refreshing again")
            continue
        break

    _ct_sync_task = None


def schedule_ct_monitor_program_config_sync(reason: str = "") -> None:
    """
    Schedule a background CT config reload without blocking the caller.
    Multiple calls while a sync is in flight coalesce into at most one follow-up run.
    """
    global _ct_sync_task, _ct_sync_rerun_requested

    _ct_sync_rerun_requested = True
    if _ct_sync_task is not None and not _ct_sync_task.done():
        logger.debug("CT monitor config sync already in progress; coalescing request")
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "Cannot schedule CT monitor config sync without a running event loop (%s)",
            reason or "no reason",
        )
        return

    _ct_sync_task = loop.create_task(_coalesced_sync_worker(reason))
