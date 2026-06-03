"""
Registrable hostname labels via tldextract.

Keep in sync with runner ``utils.utils.hostname_without_public_suffix`` /
``extract_apex_domain`` and API ``utils.domain_utils.extract_apex_domain``.
"""

from __future__ import annotations

import logging
from typing import Optional

import tldextract

logger = logging.getLogger(__name__)


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

    try:
        extracted = tldextract.extract(hostname)
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


def extract_apex_domain(domain_name: str) -> str:
    """
    Return the registrable apex (domain + public suffix) for similarity scoring.
    """
    if not domain_name or not isinstance(domain_name, str):
        return ""

    domain_name = domain_name.strip().lower()
    if not domain_name:
        return ""

    try:
        extracted = tldextract.extract(domain_name)
        if extracted.domain and extracted.suffix:
            return f"{extracted.domain}.{extracted.suffix}"
        logger.warning(
            "Could not extract apex domain from '%s', returning original",
            domain_name,
        )
        return domain_name
    except Exception as e:
        logger.error("Error extracting apex domain from '%s': %s", domain_name, e)
        return domain_name
