import json
import logging
from typing import Any, Dict, List, Optional

from utils.utils import extract_apex_domain, is_valid_domain

from .base import Task, AssetType, CommandSpec, parameter_manager

logger = logging.getLogger(__name__)

_RAW_RESPONSE_MAX = 16000


class WhoisDomainCheck(Task):
    name = "whois_domain_check"
    description = "WHOIS lookup on apex domains; structured WHOIS stored on apex_domain assets"
    input_type = AssetType.STRING
    output_types = [AssetType.APEX_DOMAIN]

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        import base64

        hash_dict = {"task": self.name, "target": target}
        return base64.b64encode(str(hash_dict).encode()).decode()

    def _collect_unique_apex_domains(self, input_data: Any) -> List[str]:
        items = input_data if isinstance(input_data, list) else [input_data]
        ordered: Dict[str, str] = {}
        for item in items:
            if not item or not isinstance(item, str):
                continue
            raw = item.strip().lower()
            if not raw:
                continue
            try:
                apex = extract_apex_domain(raw)
            except ValueError:
                logger.debug("Skipping invalid domain input: empty after extract")
                continue
            apex = apex.strip().lower()
            if not apex or not is_valid_domain(apex):
                continue
            if apex not in ordered:
                ordered[apex] = apex
        return list(ordered.values())

    async def generate_commands(
        self,
        input_data: List[Any],
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[CommandSpec]:
        unique_apex = self._collect_unique_apex_domains(input_data)
        if not unique_apex:
            logger.warning("whois_domain_check: no valid apex domains after extract/dedupe")
            return []

        chunk_size = params.get("chunk_size")
        if chunk_size is None:
            chunk_size = parameter_manager.get_chunk_size(self.name)
        try:
            chunk_size = max(1, int(chunk_size))
        except (TypeError, ValueError):
            chunk_size = 1

        commands: List[CommandSpec] = []
        for i in range(0, len(unique_apex), chunk_size):
            chunk = unique_apex[i : i + chunk_size]
            cmd = self.get_command(chunk, params)
            if cmd:
                commands.append(
                    CommandSpec(task_name=self.name, command=cmd, params=params)
                )
        logger.info(
            "whois_domain_check: %s unique apex domain(s) -> %s worker job(s)",
            len(unique_apex),
            len(commands),
        )
        return commands

    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        domains = input_data if isinstance(input_data, list) else [input_data]
        domains = [d for d in domains if d and isinstance(d, str)]
        if not domains:
            return "echo '{}'"
        text = "\n".join(domains)
        return f"cat << 'EOF' | python3 whois_domain_wrapper.py\n{text}\nEOF"

    def _worker_payload_to_apex_asset(self, name: str, data: dict) -> dict:
        """Map worker JSON keys to API apex_domain / DB whois_* columns (full row each run)."""
        raw = data.get("raw_response")
        if raw and isinstance(raw, str) and len(raw) > _RAW_RESPONSE_MAX:
            raw = raw[:_RAW_RESPONSE_MAX] + "..."

        ns = data.get("name_servers")
        if ns is not None and isinstance(ns, list) and len(ns) == 0:
            ns = None

        return {
            "name": name,
            "whois_status": data.get("status"),
            "whois_registrar": data.get("registrar"),
            "whois_creation_date": data.get("creation_date"),
            "whois_expiration_date": data.get("expiration_date"),
            "whois_updated_date": data.get("updated_date"),
            "whois_name_servers": ns,
            "whois_registrant_name": data.get("registrant_name"),
            "whois_registrant_org": data.get("registrant_org"),
            "whois_registrant_country": data.get("registrant_country"),
            "whois_admin_email": data.get("admin_email"),
            "whois_tech_email": data.get("tech_email"),
            "whois_dnssec": data.get("dnssec"),
            "whois_registry_server": data.get("whois_server"),
            "whois_response_source": data.get("response_source"),
            "whois_raw_response": raw,
            "whois_error": data.get("error"),
        }

    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        normalized = self.normalize_output_for_parsing(output)
        if not normalized or not normalized.strip():
            logger.warning("whois_domain_check: empty output")
            return {AssetType.APEX_DOMAIN: []}

        try:
            blob = json.loads(normalized)
        except json.JSONDecodeError as e:
            logger.error("whois_domain_check: invalid JSON: %s", e)
            return {AssetType.APEX_DOMAIN: []}

        if not isinstance(blob, dict):
            return {AssetType.APEX_DOMAIN: []}

        assets: List[dict] = []
        for domain, data in blob.items():
            if not domain or not isinstance(domain, str):
                continue
            name = domain.strip().lower()
            if not name:
                continue
            if isinstance(data, dict):
                assets.append(self._worker_payload_to_apex_asset(name, data))
            else:
                base = self._worker_payload_to_apex_asset(name, {})
                base["whois_status"] = "Error"
                base["whois_error"] = str(data)[:2000]
                base["whois_response_source"] = "parse"
                assets.append(base)

        logger.info("whois_domain_check: parsed %s apex_domain asset(s)", len(assets))
        return {AssetType.APEX_DOMAIN: assets}
