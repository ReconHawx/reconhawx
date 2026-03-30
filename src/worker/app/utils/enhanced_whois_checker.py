"""Enhanced WHOIS lookup: python-whois, direct port-43, then RDAP via whoisit.

Order: python-whois → TCP/43 (when a server is known for the TLD) → `whoisit` (RDAP)
for TLDs such as ``.dev`` that are often missing from static WHOIS server maps.
Bootstrap runs once per process (lazy, locked). No per-domain in-memory cache.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import logging
import re
import socket
import threading
import time
from typing import Any, List, Optional, Tuple

import tldextract
import whois as python_whois
import whoisit
from dateutil import parser as date_parser
from whoisit import errors as whoisit_errors

WHOIS_RATE_LIMIT = 1.0
WHOIS_TIMEOUT = 10

WHOIS_SERVERS = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "info": "whois.afilias.net",
    "biz": "whois.biz",
    "us": "whois.nic.us",
    "io": "whois.nic.io",
    "ai": "whois.nic.ai",
    "co": "whois.nic.co",
    "me": "whois.nic.me",
    "tv": "whois.nic.tv",
    "cc": "whois.nic.cc",
    "uk": "whois.nic.uk",
    "de": "whois.denic.de",
    "fr": "whois.afnic.fr",
    "it": "whois.nic.it",
    "ca": "whois.cira.ca",
    "au": "whois.auda.org.au",
    "jp": "whois.jprs.jp",
    "kr": "whois.kr",
    "cn": "whois.cnnic.cn",
    "in": "whois.registry.in",
    "br": "whois.registro.br",
    "mx": "whois.mx",
    "pl": "whois.dns.pl",
    "ru": "whois.tcinet.ru",
    "nl": "whois.domain-registry.nl",
    "be": "whois.dns.be",
    "ch": "whois.nic.ch",
    "se": "whois.iis.se",
    "no": "whois.norid.no",
    "dk": "whois.dk-hostmaster.dk",
    "fi": "whois.fi",
    "es": "whois.nic.es",
    "pt": "whois.dns.pt",
}

TLD_RATE_LIMITS = {
    "com": 1.0,
    "net": 1.0,
    "org": 0.8,
    "io": 1.5,
    "ai": 2.0,
    "uk": 1.2,
    "de": 1.5,
    "cn": 2.5,
    "jp": 2.0,
    "kr": 1.8,
    "in": 1.5,
    "br": 1.3,
    "au": 1.4,
    "ca": 1.1,
    "mx": 1.6,
}

class DomainStatus(Enum):
    AVAILABLE = "Available"
    REGISTERED = "Registered"
    RESERVED = "Reserved"
    PREMIUM = "Premium"
    ERROR = "Error"
    UNKNOWN = "Unknown"

@dataclass
class WhoisInfo:
    status: DomainStatus
    registrar: Optional[str] = None
    creation_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    updated_date: Optional[datetime] = None
    name_servers: List[str] = field(default_factory=list)
    registrant_name: Optional[str] = None
    registrant_org: Optional[str] = None
    registrant_country: Optional[str] = None
    admin_email: Optional[str] = None
    tech_email: Optional[str] = None
    dnssec: Optional[str] = None
    whois_server: Optional[str] = None
    raw_response: Optional[str] = None
    response_source: str = "unknown"


class EnhancedWhoisChecker:
    """WHOIS via python-whois, optional TCP/43, then RDAP (whoisit); per-TLD rate limiting."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self.rate_limiter: dict[str, float] = {}
        self.lock = threading.Lock()
        self._whoisit_bootstrap_ok = False
        self._whoisit_bootstrap_failed = False

    def _apply_rate_limit(self, tld: str) -> None:
        with self.lock:
            rate_limit = TLD_RATE_LIMITS.get(tld, WHOIS_RATE_LIMIT)
            current_time = time.time()
            last_check = self.rate_limiter.get(tld, 0)

            if current_time - last_check < rate_limit:
                sleep_time = rate_limit - (current_time - last_check)
                self.logger.debug("Rate limiting .%s: sleeping %.2fs", tld, sleep_time)
                time.sleep(sleep_time)

            self.rate_limiter[tld] = time.time()

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str or date_str.lower() in ["none", "null", "n/a", ""]:
            return None

        date_str = str(date_str).strip()

        try:
            return date_parser.parse(date_str)
        except (ValueError, TypeError):
            pass

        for pattern in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%d-%b-%Y",
            "%d.%m.%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
        ):
            try:
                return datetime.strptime(date_str, pattern)
            except ValueError:
                continue

        self.logger.debug("Could not parse date: %s", date_str)
        return None

    def _coerce_whois_date_value(self, date_value: Any) -> Optional[datetime]:
        if date_value is None:
            return None
        if isinstance(date_value, list):
            date_value = date_value[0] if date_value else None
        if date_value is None:
            return None
        if isinstance(date_value, datetime):
            return date_value
        if isinstance(date_value, str):
            return self._parse_date(date_value)
        return None

    def _dates_from_whois_json_blob(
        self, blob: str
    ) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
        blob = blob.strip()
        if not blob.startswith("{"):
            return None, None, None
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            return None, None, None

        def pick(key: str) -> Optional[datetime]:
            v = data.get(key)
            return self._coerce_whois_date_value(v)

        return pick("creation_date"), pick("expiration_date"), pick("updated_date")

    def _extract_emails(self, text: str) -> List[str]:
        email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        return re.findall(email_pattern, text, re.IGNORECASE)

    def _parse_python_whois_response(self, whois_data: Any, domain: str) -> WhoisInfo:
        self.logger.debug("Parsing python-whois response for %s", domain)

        domain_names = getattr(whois_data, "domain_name", None)
        if domain_names:
            if isinstance(domain_names, list):
                domain_names = [d.lower() if d else "" for d in domain_names]
            else:
                domain_names = [str(domain_names).lower()]

        is_registered = bool(
            domain_names and any(domain.lower() in dn for dn in domain_names if dn)
        )

        if not is_registered:
            return WhoisInfo(
                status=DomainStatus.AVAILABLE,
                response_source="python-whois",
                raw_response=str(whois_data)[:1000],
            )

        registrar = getattr(whois_data, "registrar", None)
        if isinstance(registrar, list):
            registrar = registrar[0] if registrar else None

        creation_date = self._coerce_whois_date_value(getattr(whois_data, "creation_date", None))
        expiration_date = self._coerce_whois_date_value(getattr(whois_data, "expiration_date", None))
        updated_date = self._coerce_whois_date_value(getattr(whois_data, "updated_date", None))
        raw_text = str(whois_data)
        if creation_date is None and expiration_date is None and updated_date is None:
            jc, je, ju = self._dates_from_whois_json_blob(raw_text)
            creation_date = creation_date or jc
            expiration_date = expiration_date or je
            updated_date = updated_date or ju

        name_servers = getattr(whois_data, "name_servers", [])
        if name_servers and not isinstance(name_servers, list):
            name_servers = [name_servers]
        name_servers = [ns.lower().strip() for ns in name_servers if ns]

        registrant_name = getattr(whois_data, "registrant_name", None)
        registrant_org = getattr(whois_data, "org", None)
        registrant_country = getattr(whois_data, "country", None)

        emails = self._extract_emails(raw_text)
        admin_email = None
        tech_email = None

        if emails:
            for email in emails:
                if "admin" in email.lower():
                    admin_email = email
                elif "tech" in email.lower():
                    tech_email = email

            if not admin_email and emails:
                admin_email = emails[0]

        dnssec = getattr(whois_data, "dnssec", None)
        if isinstance(dnssec, list):
            dnssec = ", ".join(str(d) for d in dnssec if d)

        return WhoisInfo(
            status=DomainStatus.REGISTERED,
            registrar=str(registrar) if registrar else None,
            creation_date=creation_date,
            expiration_date=expiration_date,
            updated_date=updated_date,
            name_servers=name_servers,
            registrant_name=str(registrant_name) if registrant_name else None,
            registrant_org=str(registrant_org) if registrant_org else None,
            registrant_country=str(registrant_country) if registrant_country else None,
            admin_email=admin_email,
            tech_email=tech_email,
            dnssec=str(dnssec) if dnssec else None,
            response_source="python-whois",
            raw_response=raw_text[:1000],
        )

    def _direct_whois_query(self, domain: str) -> Optional[str]:
        tld = tldextract.extract(domain).suffix
        whois_server = WHOIS_SERVERS.get(tld)

        if not whois_server:
            self.logger.debug("No WHOIS server known for .%s", tld)
            return None

        try:
            self.logger.debug("Direct WHOIS query to %s for %s", whois_server, domain)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(WHOIS_TIMEOUT)
                sock.connect((whois_server, 43))

                query = f"{domain}\r\n"
                sock.send(query.encode())

                response = b""
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    response += data

                return response.decode("utf-8", errors="ignore")

        except Exception as e:
            self.logger.debug("Direct WHOIS query failed for %s: %s", domain, e)
            return None

    def _parse_direct_whois_response(self, response: str, domain: str) -> WhoisInfo:
        if not response:
            return WhoisInfo(status=DomainStatus.ERROR, response_source="direct")

        response_lower = response.lower()

        availability_patterns = [
            r"no match",
            r"not found",
            r"no entries found",
            r"available",
            r"no data found",
            r"no object found",
            r"not registered",
            r"no information available",
            r"domain status:\s*available",
            r"status:\s*free",
        ]

        for pattern in availability_patterns:
            if re.search(pattern, response_lower):
                return WhoisInfo(
                    status=DomainStatus.AVAILABLE,
                    response_source="direct",
                    raw_response=response[:1000],
                )

        if len(response.strip()) < 50:
            return WhoisInfo(
                status=DomainStatus.UNKNOWN,
                response_source="direct",
                raw_response=response,
            )

        registrar = None
        creation_date = None
        expiration_date = None
        updated_date = None
        name_servers: List[str] = []

        registrar_patterns = [
            r"registrar:\s*(.+)",
            r"registrar name:\s*(.+)",
            r"sponsoring registrar:\s*(.+)",
        ]

        for pattern in registrar_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                registrar = match.group(1).strip()
                break

        date_patterns = {
            "creation_date": [
                r"creation date:\s*(.+)",
                r"created:\s*(.+)",
                r"registered:\s*(.+)",
                r"domain_dateregistered:\s*(.+)",
            ],
            "expiration_date": [
                r"expir(?:y|ation) date:\s*(.+)",
                r"expires:\s*(.+)",
                r"expiry:\s*(.+)",
                r"domain_datebilleduntil:\s*(.+)",
            ],
            "updated_date": [
                r"updated date:\s*(.+)",
                r"last updated:\s*(.+)",
                r"modified:\s*(.+)",
                r"domain_datelastmodified:\s*(.+)",
            ],
        }

        for pattern in date_patterns["creation_date"]:
            match = re.search(pattern, response, re.IGNORECASE)
            if not match:
                continue
            creation_date = self._parse_date(match.group(1).strip())
            if creation_date:
                break
        for pattern in date_patterns["expiration_date"]:
            match = re.search(pattern, response, re.IGNORECASE)
            if not match:
                continue
            expiration_date = self._parse_date(match.group(1).strip())
            if expiration_date:
                break
        for pattern in date_patterns["updated_date"]:
            match = re.search(pattern, response, re.IGNORECASE)
            if not match:
                continue
            updated_date = self._parse_date(match.group(1).strip())
            if updated_date:
                break

        ns_patterns = [
            r"name server:\s*(.+)",
            r"nameserver:\s*(.+)",
            r"nserver:\s*(.+)",
            r"dns:\s*(.+)",
        ]

        for pattern in ns_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            for match in matches:
                ns = match.strip().lower()
                if ns and ns not in name_servers:
                    name_servers.append(ns)

        emails = self._extract_emails(response)
        admin_email = None
        tech_email = None

        for email in emails:
            ctx = response[max(0, response.find(email) - 50) : response.find(email) + 50].lower()
            if "admin" in ctx:
                admin_email = email
            elif "tech" in ctx:
                tech_email = email

        return WhoisInfo(
            status=DomainStatus.REGISTERED,
            registrar=registrar,
            creation_date=creation_date,
            expiration_date=expiration_date,
            updated_date=updated_date,
            name_servers=name_servers,
            admin_email=admin_email,
            tech_email=tech_email,
            response_source="direct",
            raw_response=response[:1000],
        )

    def _ensure_whoisit_bootstrap(self) -> bool:
        if self._whoisit_bootstrap_ok:
            return True
        if self._whoisit_bootstrap_failed:
            return False
        with self.lock:
            if self._whoisit_bootstrap_ok:
                return True
            if self._whoisit_bootstrap_failed:
                return False
            try:
                whoisit.bootstrap(overrides=True)
                self._whoisit_bootstrap_ok = True
                self.logger.debug("whoisit bootstrap completed")
                return True
            except Exception as e:
                self.logger.warning("whoisit bootstrap failed: %s", e)
                self._whoisit_bootstrap_failed = True
                return False

    @staticmethod
    def _first_entity(entities: Any, role: str) -> Optional[dict]:
        if not isinstance(entities, dict):
            return None
        lst = entities.get(role)
        if not lst or not isinstance(lst, list) or not isinstance(lst[0], dict):
            return None
        return lst[0]

    def _parse_whoisit_domain(self, data: dict, domain: str) -> WhoisInfo:
        """Map whoisit `domain()` summary dict to WhoisInfo."""
        dom = domain.lower().strip(".")
        name = (data.get("name") or "").lower().strip(".")
        unicode_name = (data.get("unicode_name") or "").lower().rstrip(".")
        if name and name != dom and unicode_name != dom:
            self.logger.debug("whoisit name mismatch for %s (got %s)", domain, data.get("name"))

        entities = data.get("entities") or {}
        registrar_ent = self._first_entity(entities, "registrar")
        registrant_ent = self._first_entity(entities, "registrant")
        admin_ent = self._first_entity(entities, "administrative")

        registrar = (registrar_ent or {}).get("name")
        if registrar:
            registrar = str(registrar)

        registrant_name = (registrant_ent or {}).get("name")
        if registrant_name:
            registrant_name = str(registrant_name)

        registrant_org = registrant_name
        registrant_country = None
        addr = (registrant_ent or {}).get("address") if registrant_ent else None
        if isinstance(addr, dict):
            c = addr.get("country")
            if c and isinstance(c, str) and "REDACTED" not in c.upper():
                registrant_country = c

        admin_email = (registrant_ent or {}).get("email") if registrant_ent else None
        if isinstance(admin_email, str) and "REDACTED" in admin_email.upper():
            admin_email = None
        if not admin_email and admin_ent:
            ae = admin_ent.get("email")
            if isinstance(ae, str) and "REDACTED" not in ae.upper():
                admin_email = ae

        tech_ent = self._first_entity(entities, "technical")
        tech_email = (tech_ent or {}).get("email") if tech_ent else None
        if isinstance(tech_email, str) and "REDACTED" in tech_email.upper():
            tech_email = None

        name_servers = data.get("nameservers") or []
        if not isinstance(name_servers, list):
            name_servers = [name_servers]
        name_servers = [str(ns).lower().strip() for ns in name_servers if ns]

        creation_date = data.get("registration_date")
        if creation_date is not None and not isinstance(creation_date, datetime):
            creation_date = self._coerce_whois_date_value(creation_date)

        expiration_date = data.get("expiration_date")
        if expiration_date is not None and not isinstance(expiration_date, datetime):
            expiration_date = self._coerce_whois_date_value(expiration_date)

        updated_date = data.get("last_changed_date")
        if updated_date is not None and not isinstance(updated_date, datetime):
            updated_date = self._coerce_whois_date_value(updated_date)

        dnssec_val = data.get("dnssec")
        dnssec_s: Optional[str]
        if dnssec_val is True:
            dnssec_s = "true"
        elif dnssec_val is False:
            dnssec_s = None
        elif dnssec_val is None:
            dnssec_s = None
        else:
            dnssec_s = str(dnssec_val)

        whois_server = data.get("whois_server")
        if whois_server:
            whois_server = str(whois_server)

        return WhoisInfo(
            status=DomainStatus.REGISTERED,
            registrar=registrar,
            creation_date=creation_date if isinstance(creation_date, datetime) else None,
            expiration_date=expiration_date if isinstance(expiration_date, datetime) else None,
            updated_date=updated_date if isinstance(updated_date, datetime) else None,
            name_servers=name_servers,
            registrant_name=registrant_name,
            registrant_org=registrant_org,
            registrant_country=registrant_country,
            admin_email=admin_email if isinstance(admin_email, str) else None,
            tech_email=tech_email if isinstance(tech_email, str) else None,
            dnssec=dnssec_s,
            whois_server=whois_server,
            raw_response=None,
            response_source="whoisit",
        )

    def _whoisit_lookup(self, domain: str) -> Optional[WhoisInfo]:
        if not self._ensure_whoisit_bootstrap():
            return None
        try:
            self.logger.debug("Trying whoisit (RDAP) for %s", domain)
            data = whoisit.domain(domain)
            if not isinstance(data, dict):
                return None
            return self._parse_whoisit_domain(data, domain)
        except whoisit_errors.UnsupportedError:
            self.logger.debug("whoisit unsupported for %s", domain)
            return None
        except whoisit_errors.QueryError as e:
            self.logger.debug("whoisit query failed for %s: %s", domain, e)
            return None
        except Exception as e:
            self.logger.debug("whoisit error for %s: %s", domain, e)
            return None

    def check_whois(self, domain: str) -> WhoisInfo:
        tld = tldextract.extract(domain).suffix
        self._apply_rate_limit(tld)

        whois_info: Optional[WhoisInfo] = None
        last_error: Optional[BaseException] = None

        try:
            self.logger.debug("Trying python-whois for %s", domain)
            whois_data = python_whois.whois(domain)
            whois_info = self._parse_python_whois_response(whois_data, domain)

            if whois_info.status == DomainStatus.UNKNOWN:
                pass
            elif whois_info.status == DomainStatus.AVAILABLE:
                if tld not in WHOIS_SERVERS:
                    rdap = self._whoisit_lookup(domain)
                    if rdap is not None:
                        return rdap
                return whois_info
            else:
                return whois_info

        except Exception as e:
            last_error = e
            error_msg = str(e).lower()

            if any(
                indicator in error_msg
                for indicator in [
                    "no match",
                    "not found",
                    "no entries",
                    "available",
                    "no data",
                    "no object",
                ]
            ):
                if tld not in WHOIS_SERVERS:
                    rdap = self._whoisit_lookup(domain)
                    if rdap is not None:
                        return rdap
                return WhoisInfo(
                    status=DomainStatus.AVAILABLE,
                    response_source="python-whois-error",
                    raw_response=error_msg,
                )

            self.logger.debug("python-whois failed for %s: %s", domain, e)

        try:
            self.logger.debug("Trying direct WHOIS for %s", domain)
            response = self._direct_whois_query(domain)
            if response:
                whois_info = self._parse_direct_whois_response(response, domain)
                if whois_info.status != DomainStatus.UNKNOWN:
                    return whois_info

        except Exception as e:
            last_error = e
            self.logger.debug("Direct WHOIS failed for %s: %s", domain, e)

        rdap = self._whoisit_lookup(domain)
        if rdap is not None:
            return rdap

        error_msg = str(last_error) if last_error else "All WHOIS methods failed"
        return WhoisInfo(
            status=DomainStatus.ERROR,
            response_source="error",
            raw_response=error_msg[:1000],
        )
