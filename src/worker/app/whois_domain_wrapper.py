#!/usr/bin/env python3
"""Read apex domains from stdin (one per line), run WHOIS, print one JSON object to stdout."""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional

from utils.enhanced_whois_checker import DomainStatus, EnhancedWhoisChecker, WhoisInfo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

_RAW_MAX = 500


def _dt(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def whois_info_to_dict(info: WhoisInfo) -> Dict[str, Any]:
    status = info.status
    if isinstance(status, DomainStatus):
        status_str = status.value
    else:
        status_str = str(status)

    raw = info.raw_response
    if raw and len(raw) > _RAW_MAX:
        raw = raw[:_RAW_MAX] + "..."

    return {
        "status": status_str,
        "registrar": info.registrar,
        "creation_date": _dt(info.creation_date),
        "expiration_date": _dt(info.expiration_date),
        "updated_date": _dt(info.updated_date),
        "name_servers": list(info.name_servers) if info.name_servers else [],
        "registrant_name": info.registrant_name,
        "registrant_org": info.registrant_org,
        "registrant_country": info.registrant_country,
        "admin_email": info.admin_email,
        "tech_email": info.tech_email,
        "dnssec": info.dnssec,
        "whois_server": info.whois_server,
        "response_source": info.response_source,
        "raw_response": raw,
    }


def main() -> None:
    lines = [ln.strip().lower() for ln in sys.stdin if ln.strip()]
    checker = EnhancedWhoisChecker()
    out: Dict[str, Any] = {}
    for domain in lines:
        try:
            info = checker.check_whois(domain)
            out[domain] = whois_info_to_dict(info)
        except Exception as e:
            logger.exception("WHOIS failed for %s", domain)
            out[domain] = {
                "status": DomainStatus.ERROR.value,
                "error": str(e)[:500],
                "response_source": "exception",
            }
    print(json.dumps(out))


if __name__ == "__main__":
    main()
