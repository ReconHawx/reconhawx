"""
Scale certstream-server Deployment replicas via the Kubernetes API (in-cluster).

Used when CT monitoring is enabled/disabled on programs so the aggregator
does not run while idle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

_SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
_SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
_SA_NAMESPACE_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"


def certstream_scale_enabled_from_env() -> bool:
    """True when ct-monitor should patch certstream-server scale (in-cluster default)."""
    raw = os.getenv("CT_CERTSTREAM_SCALE_ENABLED", "").strip().lower()
    if raw in ("false", "0", "no", "off"):
        return False
    if raw in ("true", "1", "yes", "on"):
        return True
    return os.path.isfile(_SA_TOKEN_PATH)


def _read_namespace() -> str:
    env_ns = (os.getenv("KUBERNETES_NAMESPACE") or "").strip()
    if env_ns:
        return env_ns
    try:
        with open(_SA_NAMESPACE_PATH, encoding="utf-8") as f:
            return f.read().strip() or "reconhawx"
    except OSError:
        return "reconhawx"


def _api_base() -> Optional[str]:
    host = (os.getenv("KUBERNETES_SERVICE_HOST") or "").strip()
    port = (os.getenv("KUBERNETES_SERVICE_PORT") or "443").strip()
    if not host:
        return None
    return f"https://{host}:{port}"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=_SA_CA_PATH)
    return ctx


async def _load_token() -> Optional[str]:
    try:
        with open(_SA_TOKEN_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


async def scale_certstream_deployment(
    replicas: int,
    *,
    deployment_name: Optional[str] = None,
    namespace: Optional[str] = None,
    enabled: Optional[bool] = None,
) -> bool:
    """
    Patch Deployment scale subresource. Returns True on success or when scaling is disabled.
    """
    if enabled is None:
        enabled = certstream_scale_enabled_from_env()
    if not enabled:
        logger.debug("certstream-server K8s scale disabled (not in cluster or CT_CERTSTREAM_SCALE_ENABLED=off)")
        return True

    deploy = deployment_name or os.getenv("CERTSTREAM_DEPLOYMENT_NAME", "certstream-server")
    ns = namespace or _read_namespace()
    api_base = _api_base()
    token = await _load_token()
    if not api_base or not token:
        logger.warning("Cannot scale certstream-server: missing in-cluster Kubernetes API config")
        return False

    url = f"{api_base}/apis/apps/v1/namespaces/{ns}/deployments/{deploy}/scale"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/merge-patch+json",
    }
    body = {"spec": {"replicas": int(replicas)}}

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=_ssl_context())
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            async with session.patch(url, json=body, headers=headers) as resp:
                if resp.status in (200, 201):
                    return True
                text = (await resp.text())[:500]
                logger.warning(
                    "certstream-server scale to %s failed: HTTP %s %s",
                    replicas,
                    resp.status,
                    text,
                )
                return False
    except aiohttp.ClientError as e:
        logger.warning("certstream-server scale to %s failed: %s", replicas, e)
        return False
    except Exception as e:
        logger.warning("certstream-server scale error: %s", e)
        return False


async def wait_for_certstream_http_ready(
    health_url: str,
    *,
    timeout_sec: float = 90.0,
    poll_interval_sec: float = 2.0,
) -> bool:
    """Poll certstream-server HTTP until example.json responds (after scale-up)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    while loop.time() < deadline:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(health_url) as resp:
                    if resp.status == 200:
                        return True
        except aiohttp.ClientError:
            pass
        except Exception:
            pass
        await asyncio.sleep(poll_interval_sec)
    logger.warning("certstream-server not ready at %s within %ss", health_url, timeout_sec)
    return False


def certstream_health_url_from_ws(certstream_url: str) -> str:
    """Map ws://certstream:4000/ to http://certstream:4000/example.json."""
    base = certstream_url.strip()
    if base.startswith("wss://"):
        base = "https://" + base[6:]
    elif base.startswith("ws://"):
        base = "http://" + base[5:]
    base = base.rstrip("/")
    return f"{base}/example.json"
