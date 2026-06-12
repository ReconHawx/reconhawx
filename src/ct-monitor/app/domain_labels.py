"""
Registrable hostname labels via tldextract.

Keep in sync with runner ``utils.utils.hostname_without_public_suffix`` /
``extract_apex_domain`` and API ``utils.domain_utils.extract_apex_domain``.

Uses a module-level extractor pinned to the bundled public-suffix snapshot
(no live PSL fetch) and LRU caches: CT streams repeat hostnames heavily
(precert + cert pairs, www/apex SAN pairs), so cached lookups dominate.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

import tldextract

logger = logging.getLogger(__name__)

_extractor = tldextract.TLDExtract(suffix_list_urls=())

_LRU_MAXSIZE = 65536


@lru_cache(maxsize=_LRU_MAXSIZE)
def _hostname_without_public_suffix_cached(hostname: str) -> Optional[str]:
    try:
        extracted = _extractor(hostname)
        if not extracted.suffix:
            return None
        if extracted.subdomain:
            return f"{extracted.subdomain}.{extracted.domain}"
        if extracted.domain:
            return extracted.domain
        return None
    except Exception as e:
        logger.debug("hostname_without_public_suffix failed for '%s': %s", hostname, e)
        return None


def hostname_without_public_suffix(hostname: str) -> Optional[str]:
    """
    Return the hostname with the public suffix removed (via tldextract).

    Examples:
    - d0main.com -> d0main
    - d0main.example.com -> d0main.example
    - d0main.domain.co.uk -> d0main.domain

    Returns None when no public suffix is detected.
    """
    if not hostname or not isinstance(hostname, str):
        return None

    hostname = hostname.strip().lower()
    if not hostname:
        return None

    return _hostname_without_public_suffix_cached(hostname)


@lru_cache(maxsize=_LRU_MAXSIZE)
def _extract_apex_domain_cached(domain_name: str) -> str:
    try:
        extracted = _extractor(domain_name)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
        # Public-suffix-only strings (e.g. go.id, com.br) are common in CT SAN lists.
        if extracted.suffix and not extracted.domain:
            return domain_name
        logger.debug(
            "Could not extract apex domain from '%s', returning original",
            domain_name,
        )
        return domain_name
    except Exception as e:
        logger.error("Error extracting apex domain from '%s': %s", domain_name, e)
        return domain_name


def extract_apex_domain(domain_name: str) -> str:
    """
    Return the registrable apex (domain + public suffix) for similarity scoring.
    """
    if not domain_name or not isinstance(domain_name, str):
        return ""

    domain_name = domain_name.strip().lower()
    if not domain_name:
        return ""

    return _extract_apex_domain_cached(domain_name)
