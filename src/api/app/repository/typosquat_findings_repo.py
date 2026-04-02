from sqlalchemy import and_, or_, func, desc, asc, Integer, String, select, literal, text, case, exists
from sqlalchemy.orm import joinedload
from typing import Dict, Any, Optional, List
import logging
import os
from datetime import datetime, timezone
import uuid
import json
from utils import normalize_url_for_storage
from utils.domain_utils import extract_apex_domain
import tldextract
import asyncio
from services.kubernetes import KubernetesService
import redis
try:
    from dateutil import parser
except ImportError:
    parser = None
from models.postgres import (
    TyposquatApexDomain,
    TyposquatDomain,
    Program,
    TyposquatURL,
    TyposquatScreenshot,
    TyposquatScreenshotFile,
    TyposquatCertificate,
    User,
)
from db import get_db_session
# Direct import to avoid circular import
from repository.program_repo import ProgramRepository
from repository.apexdomain_assets_repo import ApexDomainAssetsRepository
from utils.query_filters import QueryFilterUtils, ProgramAccessMixin
from services.recordedfuture_api_client import change_playbook_alert_status
from services.protected_domain_similarity_service import ProtectedDomainSimilarityService
from services.typosquat_auto_resolve_service import TyposquatAutoResolveService, _compute_auto_resolve
from services.typosquat_filtering_service import TyposquatFilteringService
from services.ai_analysis_service import resolve_typosquat_prompts

logger = logging.getLogger(__name__)

_WHOIS_PAYLOAD_KEYS = (
    "whois_registrar",
    "whois_creation_date",
    "whois_expiration_date",
    "whois_registrant_name",
    "whois_registrant_country",
    "whois_admin_email",
)

_TERMINAL_CLOSURE_STATUSES = frozenset(("resolved", "dismissed"))


def _last_closure_summary(
    closure_events: Any,
    last_closure_at_column: Any = None,
) -> Dict[str, Any]:
    """Derive list-friendly fields; prefer persisted last_closure_at for the date."""
    out: Dict[str, Any] = {
        "last_closure_at": None,
        "last_closure_to_status": None,
        "last_closed_by_user_id": None,
    }
    if last_closure_at_column is not None:
        if isinstance(last_closure_at_column, datetime):
            out["last_closure_at"] = last_closure_at_column.isoformat() + "Z"
        else:
            out["last_closure_at"] = str(last_closure_at_column)
    if not closure_events or not isinstance(closure_events, list):
        return out
    last = closure_events[-1]
    if not isinstance(last, dict):
        return out
    if out["last_closure_at"] is None:
        out["last_closure_at"] = last.get("closed_at")
    out["last_closure_to_status"] = last.get("to_status")
    out["last_closed_by_user_id"] = last.get("closed_by_user_id")
    return out


def _closure_events_for_api(db, events: Any) -> List[Dict[str, Any]]:
    """Copy closure event dicts and attach closed_by_username when user exists."""
    if not events or not isinstance(events, list):
        return []
    user_ids_set = set()
    for e in events:
        if isinstance(e, dict) and e.get("closed_by_user_id"):
            user_ids_set.add(str(e["closed_by_user_id"]))
    id_to_name: Dict[str, Optional[str]] = {}
    if user_ids_set:
        try:
            uid_cast = [uuid.UUID(u) for u in user_ids_set]
        except ValueError:
            uid_cast = []
        if uid_cast:
            for row in db.query(User.id, User.username).filter(User.id.in_(uid_cast)).all():
                id_to_name[str(row.id)] = row.username
    out: List[Dict[str, Any]] = []
    for e in events:
        if not isinstance(e, dict):
            continue
        row = dict(e)
        cid = row.get("closed_by_user_id")
        row["closed_by_username"] = id_to_name.get(str(cid)) if cid else None
        out.append(row)
    return out


class TyposquatFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for findings operations"""

    # Redis connection for batch processing
    _redis_client = None
    _batch_size = 25  # Process 25 domains per workflow
    _queue_expiry = 3600  # 1 hour expiry for queued domains
    
    @staticmethod
    def _serialize_jsonb_data(data: Dict) -> Dict:
        """Ensure JSONB data is properly serializable by converting datetime objects to ISO strings"""
        if not data:
            return data
        
        # Use JSON dumps/loads to handle datetime serialization
        try:
            # This will convert datetime objects to strings and back to dict
            serialized_data = json.loads(json.dumps(data, default=str))
            return serialized_data
        except Exception as e:
            logger.warning(f"Failed to serialize JSONB data: {e}")
            return data

    # In-memory fallback queue when Redis is not available
    _memory_queues = {}  # {program_id: {domain: timestamp}}

    @classmethod
    def get_redis_client(cls):
        """Get or create Redis client"""
        if cls._redis_client is None:
            try:
                # Try to get Redis URL from environment (preferred method)
                redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

                # Use Redis.from_url() to properly parse the URL
                cls._redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )

                # Test connection
                cls._redis_client.ping()
                logger.info(f"Successfully connected to Redis at {redis_url}")

            except Exception as e:
                logger.warning(f"Failed to connect to Redis at {redis_url}: {str(e)}. Using in-memory fallback.")
                cls._redis_client = None

        return cls._redis_client

    @staticmethod
    def _coerce_whois_datetime(val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, str) and parser:
            try:
                return parser.parse(val)
            except (ValueError, TypeError):
                return None
        return None

    @staticmethod
    def _whois_subset_from_typosquat_data(typosquat_data: Dict[str, Any]) -> Dict[str, Any]:
        return {k: typosquat_data[k] for k in _WHOIS_PAYLOAD_KEYS if k in typosquat_data}

    @staticmethod
    def _apply_whois_payload_to_apex(apex: TyposquatApexDomain, data: Dict[str, Any]) -> None:
        if "whois_registrar" in data:
            apex.whois_registrar = data.get("whois_registrar")
        if "whois_registrant_name" in data:
            apex.whois_registrant_name = data.get("whois_registrant_name")
        if "whois_registrant_country" in data:
            apex.whois_registrant_country = data.get("whois_registrant_country")
        if "whois_admin_email" in data:
            apex.whois_admin_email = data.get("whois_admin_email")
        if "whois_creation_date" in data:
            apex.whois_creation_date = TyposquatFindingsRepository._coerce_whois_datetime(
                data.get("whois_creation_date")
            )
        if "whois_expiration_date" in data:
            apex.whois_expiration_date = TyposquatFindingsRepository._coerce_whois_datetime(
                data.get("whois_expiration_date")
            )

    @staticmethod
    def find_or_create_typosquat_apex_in_session(
        db,
        apex_domain_name: str,
        program_id,
        typosquat_data: Optional[Dict[str, Any]] = None,
    ) -> TyposquatApexDomain:
        """Return typosquat_apex_domains row for (program, apex), optionally merging WHOIS from payload."""
        pid = program_id if isinstance(program_id, uuid.UUID) else uuid.UUID(str(program_id))
        apex = (
            db.query(TyposquatApexDomain)
            .filter(
                TyposquatApexDomain.program_id == pid,
                TyposquatApexDomain.apex_domain == apex_domain_name,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        whois_payload = TyposquatFindingsRepository._whois_subset_from_typosquat_data(typosquat_data or {})
        if apex:
            if whois_payload:
                TyposquatFindingsRepository._apply_whois_payload_to_apex(apex, whois_payload)
                apex.updated_at = now
            return apex
        apex = TyposquatApexDomain(
            program_id=pid,
            apex_domain=apex_domain_name,
            created_at=now,
            updated_at=now,
        )
        if whois_payload:
            TyposquatFindingsRepository._apply_whois_payload_to_apex(apex, whois_payload)
        db.add(apex)
        db.flush()
        return apex

    @staticmethod
    def _whois_public_fields_from_apex(typosquat: TyposquatDomain) -> Dict[str, Any]:
        a = typosquat.typosquat_apex
        if not a:
            return {
                "whois_registrar": None,
                "whois_creation_date": None,
                "whois_expiration_date": None,
                "whois_registrant_name": None,
                "whois_registrant_country": None,
                "whois_admin_email": None,
            }
        return {
            "whois_registrar": a.whois_registrar,
            "whois_creation_date": a.whois_creation_date.isoformat() if a.whois_creation_date else None,
            "whois_expiration_date": a.whois_expiration_date.isoformat() if a.whois_expiration_date else None,
            "whois_registrant_name": a.whois_registrant_name,
            "whois_registrant_country": a.whois_registrant_country,
            "whois_admin_email": a.whois_admin_email,
        }
    
    # Typosquat Domain Methods
    @staticmethod
    async def find_or_create_apex_domain(apex_domain_name: str, program_id: str, source: Optional[str] = None) -> str:
        """
        Find or create a typosquat_apex_domains row and return its ID.

        ``source`` is retained for API compatibility and is unused.
        """
        try:
            async with get_db_session() as db:
                apex = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                    db, apex_domain_name, program_id, None
                )
                db.commit()
                return str(apex.id)
        except Exception as e:
            logger.error(f"Error creating apex domain {apex_domain_name}: {str(e)}")
            raise

    @staticmethod
    async def _process_apex_domain_batch(program_id: str):
        """Process a batch of queued apex domains"""
        try:
            redis_client = TyposquatFindingsRepository.get_redis_client()

            if redis_client is None:
                logger.warning("Redis not available, cannot process apex domain batch")
                return

            queue_key = f"apex_domains_queue:{program_id}"

            # Get batch of domains (up to batch size)
            # Use ZPOPMIN for Redis 6.2+ or ZRANGE + ZREM for older versions
            try:
                # Try Redis 6.2+ ZPOPMIN first
                domains_with_scores = redis_client.zpopmin(queue_key, TyposquatFindingsRepository._batch_size)
                domains = [domain for domain, score in domains_with_scores]
            except Exception:
                # Fallback for older Redis versions
                domains = redis_client.zrange(queue_key, 0, TyposquatFindingsRepository._batch_size - 1)
                if domains:
                    redis_client.zrem(queue_key, *domains)

            if not domains:
                logger.info(f"No domains to process for program {program_id}")
                return

            logger.info(f"Processing batch of {len(domains)} apex domains for program {program_id}")

            # Get program name
            async with get_db_session() as db:
                from models.postgres import Program
                program = db.query(Program).filter(Program.id == program_id).first()
                if not program:
                    logger.error(f"Program not found for ID {program_id}")
                    return
                program_name = program.name

            # Create batch workflow
            execution_id = str(uuid.uuid4())
            {
                "workflow_id": None,
                "execution_id": execution_id,
                "program_name": program_name,
                "name": f"Batch_Typosquat_Analysis_{len(domains)}_domains",
                "description": f"Batch analysis of {len(domains)} apex domains from Threatstream",
                "variables": {},
                "inputs": {
                    "input_1": {
                        "type": "direct",
                        "values": domains,  # Multiple domains in batch!
                        "value_type": "domains"
                    }
                },
                "steps": [
                    {
                        "name": "step_1",
                        "tasks": [
                            {
                                "name": "typosquat_detection",
                                "force": True,
                                "params": {
                                    "include_subdomains": False,
                                    "analyze_input_as_variations": True
                                },
                                "task_type": "typosquat_detection",
                                "input_mapping": {
                                    "domains": "inputs.input_1"
                                }
                            }
                        ]
                    }
                ]
            }

            # Create Kubernetes service and trigger batch workflow
            KubernetesService()
            #job = k8s_service.create_runner_job(workflow_data)
            logger.info(f"Successfully triggered batch workflow for {len(domains)} apex domains with execution ID: {execution_id}")

        except Exception as e:
            logger.error(f"Failed to process apex domain batch for program {program_id}: {str(e)}")

    @staticmethod
    async def _process_apex_domain_batch_memory(program_id: str):
        """Process a batch of queued apex domains using in-memory storage"""
        try:
            if program_id not in TyposquatFindingsRepository._memory_queues:
                logger.info(f"No in-memory queue found for program {program_id}")
                return

            # Get all domains from memory queue
            domains_dict = TyposquatFindingsRepository._memory_queues[program_id]
            if not domains_dict:
                logger.info(f"No domains in in-memory queue for program {program_id}")
                return

            # Sort by timestamp and take up to batch size
            sorted_domains = sorted(domains_dict.items(), key=lambda x: x[1])
            domains = [domain for domain, timestamp in sorted_domains[:TyposquatFindingsRepository._batch_size]]

            if not domains:
                logger.info(f"No domains to process for program {program_id}")
                return

            # Remove processed domains from memory queue
            for domain in domains:
                del TyposquatFindingsRepository._memory_queues[program_id][domain]

            # Clean up empty queues
            if not TyposquatFindingsRepository._memory_queues[program_id]:
                del TyposquatFindingsRepository._memory_queues[program_id]

            logger.info(f"Processing batch of {len(domains)} apex domains for program {program_id} (in-memory)")

            # Get program name
            async with get_db_session() as db:
                from models.postgres import Program
                program = db.query(Program).filter(Program.id == program_id).first()
                if not program:
                    logger.error(f"Program not found for ID {program_id}")
                    return
                program_name = program.name

            # Create batch workflow (same as Redis version)
            execution_id = str(uuid.uuid4())
            {
                "workflow_id": None,
                "execution_id": execution_id,
                "program_name": program_name,
                "name": f"Batch_Typosquat_Analysis_{len(domains)}_domains_memory",
                "description": f"Batch analysis of {len(domains)} apex domains from Threatstream (in-memory)",
                "variables": {},
                "inputs": {
                    "input_1": {
                        "type": "direct",
                        "values": domains,
                        "value_type": "domains"
                    }
                },
                "steps": [
                    {
                        "name": "step_1",
                        "tasks": [
                            {
                                "name": "typosquat_detection",
                                "force": True,
                                "params": {
                                    "include_subdomains": False,
                                    "analyze_input_as_variations": True
                                },
                                "task_type": "typosquat_detection",
                                "input_mapping": {
                                    "domains": "inputs.input_1"
                                }
                            }
                        ]
                    }
                ]
            }

            # Create Kubernetes service and trigger batch workflow
            KubernetesService()
            #job = k8s_service.create_runner_job(workflow_data)
            logger.info(f"Successfully triggered batch workflow for {len(domains)} apex domains with execution ID: {execution_id} (in-memory)")

        except Exception as e:
            logger.error(f"Failed to process apex domain batch for program {program_id} (in-memory): {str(e)}")

    @staticmethod
    async def process_all_queued_domains():
        """Process all queued domains across all programs (for periodic cleanup)"""
        try:
            processed_count = 0

            # Process Redis queues if available
            redis_client = TyposquatFindingsRepository.get_redis_client()
            if redis_client is not None:
                # Find all Redis queue keys
                queue_pattern = "apex_domains_queue:*"
                queue_keys = redis_client.scan_iter(queue_pattern)

                for queue_key in queue_keys:
                    program_id = queue_key.split(":")[1]

                    # Check if queue has domains
                    queue_size = redis_client.zcard(queue_key)
                    if queue_size > 0:
                        logger.info(f"Processing {queue_size} remaining domains for program {program_id} (Redis)")
                        await TyposquatFindingsRepository._process_apex_domain_batch(program_id)
                        processed_count += 1

            # Process in-memory queues
            for program_id in list(TyposquatFindingsRepository._memory_queues.keys()):
                if program_id in TyposquatFindingsRepository._memory_queues:
                    queue_size = len(TyposquatFindingsRepository._memory_queues[program_id])
                    if queue_size > 0:
                        logger.info(f"Processing {queue_size} remaining domains for program {program_id} (in-memory)")
                        await TyposquatFindingsRepository._process_apex_domain_batch_memory(program_id)
                        processed_count += 1

            if processed_count > 0:
                logger.info(f"Processed queued domains for {processed_count} programs")
            else:
                logger.debug("No queued domains to process")

        except Exception as e:
            logger.error(f"Failed to process all queued domains: {str(e)}")

    @staticmethod
    async def create_or_update_typosquat_finding(typosquat_data: Dict[str, Any]) -> tuple[str, str, Optional[Dict[str, Any]]]:
        """Create or update a typosquat domain. Returns (record_id, action, event_data) where event_data contains rich payload data."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == typosquat_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{typosquat_data.get('program_name')}' not found")
                
                # Check if typosquat domain already exists (filter by both domain and program for accuracy)
                existing = db.query(TyposquatDomain).filter(
                    TyposquatDomain.typo_domain == typosquat_data.get('typo_domain'),
                    TyposquatDomain.program_id == program.id
                ).first()
                
                if existing:
                    # Update existing with new schema fields - only if provided
                    if 'fuzzers' in typosquat_data:
                        existing.fuzzer_types = typosquat_data.get('fuzzers', [])
                    if 'risk_analysis_total_score' in typosquat_data:
                        existing.risk_score = typosquat_data.get('risk_analysis_total_score')
                    if 'notes' in typosquat_data:
                        existing.notes = typosquat_data.get('notes')
                    existing.updated_at = datetime.utcnow()
                    
                    expected_apex = extract_apex_domain(existing.typo_domain)
                    apex_row = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                        db, expected_apex, program.id, typosquat_data
                    )
                    if existing.apex_typosquat_domain_id != apex_row.id:
                        existing.apex_typosquat_domain_id = apex_row.id

                    # Update new schema fields if provided
                    if 'domain_registered' in typosquat_data:
                        existing.domain_registered = typosquat_data.get('domain_registered')
                    if 'dns_a_records' in typosquat_data:
                        existing.dns_a_records = typosquat_data.get('dns_a_records')
                    if 'dns_mx_records' in typosquat_data:
                        existing.dns_mx_records = typosquat_data.get('dns_mx_records')
                    if 'dns_ns_records' in typosquat_data:
                        existing.dns_ns_records = typosquat_data.get('dns_ns_records')
                    if 'is_wildcard' in typosquat_data:
                        existing.is_wildcard = typosquat_data.get('is_wildcard')
                    if 'wildcard_types' in typosquat_data:
                        existing.wildcard_types = typosquat_data.get('wildcard_types')

                    # Update GeoIP fields
                    if 'geoip_country' in typosquat_data:
                        existing.geoip_country = typosquat_data.get('geoip_country')
                    if 'geoip_city' in typosquat_data:
                        existing.geoip_city = typosquat_data.get('geoip_city')
                    if 'geoip_organization' in typosquat_data:
                        existing.geoip_organization = typosquat_data.get('geoip_organization')
                    
                    # Update risk analysis fields
                    if 'risk_analysis_total_score' in typosquat_data:
                        existing.risk_analysis_total_score = typosquat_data.get('risk_analysis_total_score')
                    if 'risk_analysis_risk_level' in typosquat_data:
                        existing.risk_analysis_risk_level = typosquat_data.get('risk_analysis_risk_level')
                    if 'risk_analysis_version' in typosquat_data:
                        existing.risk_analysis_version = typosquat_data.get('risk_analysis_version')
                    if 'risk_analysis_timestamp' in typosquat_data:
                        existing.risk_analysis_timestamp = typosquat_data.get('risk_analysis_timestamp')
                    if 'risk_analysis_category_scores' in typosquat_data:
                        existing.risk_analysis_category_scores = typosquat_data.get('risk_analysis_category_scores')
                    if 'risk_analysis_risk_factors' in typosquat_data:
                        existing.risk_analysis_risk_factors = typosquat_data.get('risk_analysis_risk_factors')
                    
                    # Update PhishLabs data (consolidated into JSONB)
                    # Handle both old individual fields and new consolidated phishlabs_data field
                    if 'phishlabs_data' in typosquat_data and typosquat_data.get('phishlabs_data') is not None and typosquat_data.get('phishlabs_data') != "null":
                        # Direct phishlabs_data JSONB field provided
                        new_phishlabs_data = TyposquatFindingsRepository._serialize_jsonb_data(typosquat_data.get('phishlabs_data'))
                        if existing.phishlabs_data:
                            # Create a new dict to avoid SQLAlchemy JSONB update issues
                            merged_data = dict(existing.phishlabs_data)
                            merged_data.update(new_phishlabs_data)
                            existing.phishlabs_data = TyposquatFindingsRepository._serialize_jsonb_data(merged_data)
                        else:
                            existing.phishlabs_data = new_phishlabs_data
                    elif any(key.startswith('phishlabs_') for key in typosquat_data.keys()):
                        # Build phishlabs_data JSONB from individual phishlabs fields
                        phishlabs_data = {}
                        if 'phishlabs_incident_id' in typosquat_data:
                            incident_id = typosquat_data.get('phishlabs_incident_id')
                            phishlabs_data['incident_id'] = int(incident_id) if incident_id is not None else None
                        if 'phishlabs_url' in typosquat_data:
                            phishlabs_data['url'] = typosquat_data.get('phishlabs_url')
                        if 'phishlabs_category_code' in typosquat_data:
                            category_code = typosquat_data.get('phishlabs_category_code')
                            phishlabs_data['category_code'] = int(category_code) if category_code is not None else None
                        if 'phishlabs_category_name' in typosquat_data:
                            phishlabs_data['category_name'] = typosquat_data.get('phishlabs_category_name')
                        if 'phishlabs_status' in typosquat_data:
                            phishlabs_data['status'] = typosquat_data.get('phishlabs_status')
                        if 'phishlabs_comment' in typosquat_data:
                            phishlabs_data['comment'] = typosquat_data.get('phishlabs_comment')
                        if 'phishlabs_product' in typosquat_data:
                            phishlabs_data['product'] = typosquat_data.get('phishlabs_product')
                        if 'phishlabs_create_date' in typosquat_data:
                            phishlabs_data['create_date'] = typosquat_data.get('phishlabs_create_date')
                        if 'phishlabs_assignee' in typosquat_data:
                            phishlabs_data['assignee'] = typosquat_data.get('phishlabs_assignee')
                        if 'phishlabs_last_comment' in typosquat_data:
                            phishlabs_data['last_comment'] = typosquat_data.get('phishlabs_last_comment')
                        if 'phishlabs_group_category_name' in typosquat_data:
                            phishlabs_data['group_category_name'] = typosquat_data.get('phishlabs_group_category_name')
                        if 'phishlabs_action_description' in typosquat_data:
                            phishlabs_data['action_description'] = typosquat_data.get('phishlabs_action_description')
                        if 'phishlabs_status_description' in typosquat_data:
                            phishlabs_data['status_description'] = typosquat_data.get('phishlabs_status_description')
                        if 'phishlabs_mitigation_start' in typosquat_data:
                            phishlabs_data['mitigation_start'] = typosquat_data.get('phishlabs_mitigation_start')
                        if 'phishlabs_date_resolved' in typosquat_data:
                            phishlabs_data['date_resolved'] = typosquat_data.get('phishlabs_date_resolved')
                        if 'phishlabs_severity_name' in typosquat_data:
                            phishlabs_data['severity_name'] = typosquat_data.get('phishlabs_severity_name')
                        if 'phishlabs_mx_record' in typosquat_data:
                            phishlabs_data['mx_record'] = typosquat_data.get('phishlabs_mx_record')
                        if 'phishlabs_ticket_status' in typosquat_data:
                            phishlabs_data['ticket_status'] = typosquat_data.get('phishlabs_ticket_status')
                        if 'phishlabs_resolution_status' in typosquat_data:
                            phishlabs_data['resolution_status'] = typosquat_data.get('phishlabs_resolution_status')
                        if 'phishlabs_incident_status' in typosquat_data:
                            phishlabs_data['incident_status'] = typosquat_data.get('phishlabs_incident_status')
                        if 'phishlabs_last_updated' in typosquat_data:
                            phishlabs_data['last_updated'] = typosquat_data.get('phishlabs_last_updated')

                        # Merge with existing phishlabs_data if it exists
                        if existing.phishlabs_data:
                            # Create a new dict to avoid SQLAlchemy JSONB update issues
                            merged_data = dict(existing.phishlabs_data)
                            merged_data.update(phishlabs_data)
                            existing.phishlabs_data = TyposquatFindingsRepository._serialize_jsonb_data(merged_data)
                        else:
                            existing.phishlabs_data = TyposquatFindingsRepository._serialize_jsonb_data(phishlabs_data)

                    # Update Threatstream data - only if explicitly provided, not None, and not string "null"
                    if ('threatstream_data' in typosquat_data and 
                        typosquat_data.get('threatstream_data') is not None and 
                        typosquat_data.get('threatstream_data') != "null"):
                        existing.threatstream_data = typosquat_data.get('threatstream_data')

                    # Update RecordedFuture data - only if explicitly provided, not None, and not string "null"
                    if ('recordedfuture_data' in typosquat_data and 
                        typosquat_data.get('recordedfuture_data') is not None and 
                        typosquat_data.get('recordedfuture_data') != "null"):
                        existing.recordedfuture_data = typosquat_data.get('recordedfuture_data')

                    # Source is never overwritten when domain already exists - preserve original attribution

                    # Update parked domain detection fields
                    if 'is_parked' in typosquat_data:
                        existing.is_parked = typosquat_data.get('is_parked')
                    if 'parked_detection_timestamp' in typosquat_data:
                        existing.parked_detection_timestamp = typosquat_data.get('parked_detection_timestamp')
                    if 'parked_detection_reasons' in typosquat_data:
                        existing.parked_detection_reasons = typosquat_data.get('parked_detection_reasons')
                    if 'parked_confidence' in typosquat_data:
                        existing.parked_confidence = typosquat_data.get('parked_confidence')

                    # Update auto_resolve based on program settings
                    settings = getattr(program, 'typosquat_auto_resolve_settings', None) or {}
                    min_parked = settings.get('min_parked_confidence_percent')
                    min_similarity = settings.get('min_similarity_percent')
                    existing.auto_resolve = _compute_auto_resolve(
                        existing.parked_confidence,
                        existing.protected_domain_similarities,
                        min_parked,
                        min_similarity,
                    )

                    db.commit()
                    db.refresh(existing)

                    # Trigger async protected domain similarity calculation (non-blocking)
                    protected_domains = program.protected_domains or []
                    if protected_domains:
                        asyncio.create_task(
                            ProtectedDomainSimilarityService.calculate_and_update_for_domain(
                                str(existing.id),
                                typosquat_data.get('typo_domain'),
                                protected_domains
                            )
                        )

                    # Prepare rich event data for unified processor
                    event_data = {
                        "event": "finding.updated",
                        "finding_type": "typosquat",
                        "record_id": str(existing.id),
                        "name": typosquat_data.get('typo_domain'),
                        "program_name": typosquat_data.get('program_name'),
                        "apex_domain": extract_apex_domain(typosquat_data.get('typo_domain')),
                        "fuzzer_types": typosquat_data.get('fuzzers', []),
                        "risk_score": typosquat_data.get('risk_analysis_total_score'),
                        "domain_registered": typosquat_data.get('domain_registered'),
                        "phishlabs_incident_id": typosquat_data.get('phishlabs_incident_id')
                    }

                    logger.info(f"Typosquat domain {typosquat_data.get('typo_domain')} was updated")

                    return str(existing.id), "updated", event_data
                else:
                    # --- Pre-insertion filtering gate ---
                    typo_domain_name = typosquat_data.get('typo_domain')
                    protected_domains = getattr(program, 'protected_domains', None) or []
                    protected_prefixes = getattr(program, 'protected_subdomain_prefixes', None) or []
                    filtering_settings = getattr(program, 'typosquat_filtering_settings', None) or {}
                    asset_apex_domains = await ApexDomainAssetsRepository.get_apex_domain_names_for_program(
                        program.name
                    )

                    passes_filter, filter_reason = TyposquatFilteringService.should_insert_domain(
                        typo_domain_name, protected_domains, protected_prefixes, filtering_settings,
                        asset_apex_domains=asset_apex_domains,
                    )
                    if not passes_filter:
                        logger.info(
                            f"Typosquat domain {typo_domain_name} FILTERED OUT: {filter_reason}"
                        )
                        filter_event_data = {
                            "event": "finding.filtered",
                            "finding_type": "typosquat",
                            "typo_domain": typo_domain_name,
                            "program_name": typosquat_data.get('program_name'),
                            "source": typosquat_data.get('source'),
                            "filter_reason": filter_reason,
                        }
                        rf_data = typosquat_data.get('recordedfuture_data')
                        if rf_data:
                            filter_event_data["recordedfuture_data"] = rf_data
                        return None, "filtered", filter_event_data

                    apex_domain_name = extract_apex_domain(typo_domain_name)
                    apex_row = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                        db, apex_domain_name, program.id, typosquat_data
                    )
                    logger.info(
                        f"Using typosquat_apex_domains row {apex_row.id} for new domain {typo_domain_name}"
                    )

                    # Create new with all fields - build parameters conditionally to avoid overwriting with None
                    typosquat_params = {
                        "typo_domain": typosquat_data.get('typo_domain'),
                        "fuzzer_types": typosquat_data.get('fuzzers', []),
                        "risk_score": typosquat_data.get('risk_analysis_total_score'),
                        "program_id": program.id,
                        "detected_at": typosquat_data.get('detected_at') or datetime.utcnow(),
                        "notes": typosquat_data.get('notes'),
                        "status": typosquat_data.get('status'),
                        "assigned_to": typosquat_data.get('assigned_to'),
                        "apex_typosquat_domain_id": apex_row.id,
                        # Domain information
                        "domain_registered": typosquat_data.get('domain_registered'),
                        "dns_a_records": typosquat_data.get('dns_a_records'),
                        "dns_mx_records": typosquat_data.get('dns_mx_records'),
                        "dns_ns_records": typosquat_data.get('dns_ns_records'),
                        "is_wildcard": typosquat_data.get('is_wildcard'),
                        "wildcard_types": typosquat_data.get('wildcard_types'),
                        # GeoIP information
                        "geoip_country": typosquat_data.get('geoip_country'),
                        "geoip_city": typosquat_data.get('geoip_city'),
                        "geoip_organization": typosquat_data.get('geoip_organization'),
                        # Risk analysis
                        "risk_analysis_total_score": typosquat_data.get('risk_analysis_total_score'),
                        "risk_analysis_risk_level": typosquat_data.get('risk_analysis_risk_level'),
                        "risk_analysis_version": typosquat_data.get('risk_analysis_version'),
                        "risk_analysis_timestamp": typosquat_data.get('risk_analysis_timestamp'),
                        "risk_analysis_category_scores": typosquat_data.get('risk_analysis_category_scores'),
                        "risk_analysis_risk_factors": typosquat_data.get('risk_analysis_risk_factors'),
                        # PhishLabs information (consolidated into JSONB)
                        "phishlabs_data": None  # Will be set below
                    }
                    
                    # Set PhishLabs data properly with serialization
                    if 'phishlabs_data' in typosquat_data and typosquat_data.get('phishlabs_data') is not None and typosquat_data.get('phishlabs_data') != "null":
                        # Use provided phishlabs_data directly
                        typosquat_params["phishlabs_data"] = TyposquatFindingsRepository._serialize_jsonb_data(typosquat_data.get('phishlabs_data'))
                    elif any(key.startswith('phishlabs_') for key in typosquat_data.keys()):
                        # Build from individual fields
                        phishlabs_dict = {
                            "incident_id": int(typosquat_data.get('phishlabs_incident_id')) if typosquat_data.get('phishlabs_incident_id') is not None else None,
                            "url": typosquat_data.get('phishlabs_url'),
                            "category_code": int(typosquat_data.get('phishlabs_category_code')) if typosquat_data.get('phishlabs_category_code') is not None else None,
                            "category_name": typosquat_data.get('phishlabs_category_name'),
                            "status": typosquat_data.get('phishlabs_status'),
                            "comment": typosquat_data.get('phishlabs_comment'),
                            "product": typosquat_data.get('phishlabs_product'),
                            "create_date": typosquat_data.get('phishlabs_create_date'),
                            "assignee": typosquat_data.get('phishlabs_assignee'),
                            "last_comment": typosquat_data.get('phishlabs_last_comment'),
                            "group_category_name": typosquat_data.get('phishlabs_group_category_name'),
                            "action_description": typosquat_data.get('phishlabs_action_description'),
                            "status_description": typosquat_data.get('phishlabs_status_description'),
                            "mitigation_start": typosquat_data.get('phishlabs_mitigation_start'),
                            "date_resolved": typosquat_data.get('phishlabs_date_resolved'),
                            "severity_name": typosquat_data.get('phishlabs_severity_name'),
                            "mx_record": typosquat_data.get('phishlabs_mx_record'),
                            "ticket_status": typosquat_data.get('phishlabs_ticket_status'),
                            "resolution_status": typosquat_data.get('phishlabs_resolution_status'),
                            "incident_status": typosquat_data.get('phishlabs_incident_status'),
                            "last_updated": typosquat_data.get('phishlabs_last_updated')
                        }
                        typosquat_params["phishlabs_data"] = TyposquatFindingsRepository._serialize_jsonb_data(phishlabs_dict)
                    
                    # Only include threatstream_data if it exists in the input data, is not None, and not string "null"
                    if ('threatstream_data' in typosquat_data and 
                        typosquat_data.get('threatstream_data') is not None and 
                        typosquat_data.get('threatstream_data') != "null"):
                        typosquat_params["threatstream_data"] = typosquat_data.get('threatstream_data')
                    
                    # Only include recordedfuture_data if it exists in the input data, is not None, and not string "null"
                    if ('recordedfuture_data' in typosquat_data and 
                        typosquat_data.get('recordedfuture_data') is not None and 
                        typosquat_data.get('recordedfuture_data') != "null"):
                        typosquat_params["recordedfuture_data"] = typosquat_data.get('recordedfuture_data')
                    
                    # Only include source if it exists in the input data, is not None, and not string "null"
                    if ('source' in typosquat_data and 
                        typosquat_data.get('source') is not None and 
                        typosquat_data.get('source') != "null"):
                        typosquat_params["source"] = typosquat_data.get('source')
                    
                    # Parked domain detection fields
                    if 'is_parked' in typosquat_data:
                        typosquat_params["is_parked"] = typosquat_data.get('is_parked')
                    if 'parked_detection_timestamp' in typosquat_data:
                        typosquat_params["parked_detection_timestamp"] = typosquat_data.get('parked_detection_timestamp')
                    if 'parked_detection_reasons' in typosquat_data:
                        typosquat_params["parked_detection_reasons"] = typosquat_data.get('parked_detection_reasons')
                    if 'parked_confidence' in typosquat_data:
                        typosquat_params["parked_confidence"] = typosquat_data.get('parked_confidence')
                        typosquat_params["parked_detection_reasons"] = typosquat_data.get('parked_detection_reasons')

                    # Set auto_resolve for new record (ProtectedDomainSimilarityService will update when similarities are computed)
                    settings = getattr(program, 'typosquat_auto_resolve_settings', None) or {}
                    min_parked = settings.get('min_parked_confidence_percent')
                    min_similarity = settings.get('min_similarity_percent')
                    typosquat_params["auto_resolve"] = _compute_auto_resolve(
                        typosquat_params.get('parked_confidence'),
                        typosquat_data.get('protected_domain_similarities'),
                        min_parked,
                        min_similarity,
                    )

                    typosquat = TyposquatDomain(**typosquat_params)
                    
                    db.add(typosquat)
                    db.commit()
                    db.refresh(typosquat)
                    
                    # Trigger async protected domain similarity calculation (non-blocking)
                    protected_domains = program.protected_domains or []
                    if protected_domains:
                        asyncio.create_task(
                            ProtectedDomainSimilarityService.calculate_and_update_for_domain(
                                str(typosquat.id),
                                typosquat_data.get('typo_domain'),
                                protected_domains
                            )
                        )

                    event_data = {
                        "event": "finding.created",
                        "finding_type": "typosquat",
                        "record_id": str(typosquat.id),
                        "name": typosquat_data.get('typo_domain'),
                        "program_name": typosquat_data.get('program_name'),
                        "apex_domain": apex_domain_name,
                        "fuzzer_types": typosquat_data.get('fuzzers', []),
                        "risk_score": typosquat_data.get('risk_analysis_total_score'),
                        "domain_registered": typosquat_data.get('domain_registered'),
                        "whois_registrar": typosquat_data.get('whois_registrar'),
                        "phishlabs_incident_id": typosquat_data.get('phishlabs_incident_id')
                    }
                    
                    return str(typosquat.id), "created", event_data
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error upserting typosquat domain: {str(e)}")
                raise
    
    @staticmethod
    async def recalculate_protected_domain_similarities(program_name: str, batch_size: int = 100) -> Dict[str, Any]:
        """
        Recalculate protected domain similarities for all typosquat domains in a program.
        
        This should be called when protected_domains list changes for a program.
        Runs asynchronously in batches to avoid blocking.
        
        Args:
            program_name: Name of the program
            batch_size: Number of domains to process per batch
            
        Returns:
            Summary dict with counts of updated/failed domains
        """
        return await ProtectedDomainSimilarityService.recalculate_for_program_by_name(
            program_name, batch_size
        )

    @staticmethod
    async def recalculate_protected_domain_similarities_for_finding(finding_id: str) -> Dict[str, Any]:
        """Recalculate protected-domain similarity rows for one typosquat finding."""
        try:
            try:
                fid = uuid.UUID(str(finding_id))
            except ValueError:
                return {"status": "error", "error": "Invalid finding ID", "total": 0, "updated": 0, "failed": 0}

            async with get_db_session() as db:
                row = (
                    db.query(TyposquatDomain)
                    .options(joinedload(TyposquatDomain.program))
                    .filter(TyposquatDomain.id == fid)
                    .first()
                )
                if not row:
                    return {"status": "error", "error": "Finding not found", "total": 0, "updated": 0, "failed": 0}

                program = row.program
                if not program:
                    return {"status": "error", "error": "Finding has no program", "total": 0, "updated": 0, "failed": 0}

                protected = list(program.protected_domains or [])
                if not protected:
                    return {
                        "status": "warning",
                        "message": "No protected domains configured for this program",
                        "total": 0,
                        "updated": 0,
                        "failed": 0,
                    }

                domain_uuid = str(row.id)
                typo_domain = row.typo_domain

            ok = await ProtectedDomainSimilarityService.calculate_and_update_for_domain(
                domain_uuid,
                typo_domain,
                protected,
            )
            if ok:
                return {
                    "status": "success",
                    "message": "Similarities recalculated for this domain",
                    "total": 1,
                    "updated": 1,
                    "failed": 0,
                }
            return {
                "status": "error",
                "message": "Failed to update similarities",
                "error": "Domain record could not be updated",
                "total": 1,
                "updated": 0,
                "failed": 1,
            }
        except Exception as e:
            logger.error(f"Error recalculating similarities for finding {finding_id}: {e}")
            return {"status": "error", "error": str(e), "total": 0, "updated": 0, "failed": 0}

    @staticmethod
    async def get_typosquat_by_id(domain_id: str) -> Optional[Dict[str, Any]]:
        """Get a typosquat domain by ID"""
        async with get_db_session() as db:
            try:
                # Query with LEFT JOIN to User table to get assigned_to username
                result = (
                    db.query(TyposquatDomain, User.username)
                    .options(joinedload(TyposquatDomain.typosquat_apex))
                    .outerjoin(User, TyposquatDomain.assigned_to == func.cast(User.id, String))
                    .filter(TyposquatDomain.id == domain_id)
                    .first()
                )

                if not result:
                    return None

                typosquat, assigned_to_username = result
                _whois = TyposquatFindingsRepository._whois_public_fields_from_apex(typosquat)

                return {
                    'id': str(typosquat.id),
                    'typo_domain': typosquat.typo_domain,
                    'fuzzers': typosquat.fuzzer_types,
                    'info': {},  # info_data column removed
                    'timestamp': typosquat.detected_at.isoformat() if typosquat.detected_at else None,
                    'program_name': typosquat.program.name if typosquat.program else None,
                    'status': typosquat.status,
                    'assigned_to': typosquat.assigned_to,
                    'assigned_to_username': assigned_to_username,
                    'fix_timestamp': typosquat.fixed_at.isoformat() if typosquat.fixed_at else None,
                    'notes': typosquat.notes,
                    'created_at': typosquat.created_at.isoformat() if typosquat.created_at else None,
                    'updated_at': typosquat.updated_at.isoformat() if typosquat.updated_at else None,
                    'apex_domain_id': typosquat.apex_typosquat_domain_id,
                    # Domain information
                    'domain_registered': typosquat.domain_registered,
                    'dns_a_records': typosquat.dns_a_records,
                    'dns_mx_records': typosquat.dns_mx_records,
                    'dns_ns_records': typosquat.dns_ns_records,
                    'is_wildcard': typosquat.is_wildcard,
                    'wildcard_types': typosquat.wildcard_types,
                    # WHOIS information (from typosquat_apex_domains)
                    'whois_registrar': _whois['whois_registrar'],
                    'whois_creation_date': _whois['whois_creation_date'],
                    'whois_expiration_date': _whois['whois_expiration_date'],
                    'whois_registrant_name': _whois['whois_registrant_name'],
                    'whois_registrant_country': _whois['whois_registrant_country'],
                    'whois_admin_email': _whois['whois_admin_email'],
                    # GeoIP information
                    'geoip_country': typosquat.geoip_country,
                    'geoip_city': typosquat.geoip_city,
                    'geoip_organization': typosquat.geoip_organization,
                    # Risk analysis
                    'risk_analysis_total_score': typosquat.risk_analysis_total_score,
                    'risk_analysis_risk_level': typosquat.risk_analysis_risk_level,
                    'risk_analysis_version': typosquat.risk_analysis_version,
                    'risk_analysis_timestamp': typosquat.risk_analysis_timestamp.isoformat() if typosquat.risk_analysis_timestamp else None,
                    'risk_analysis_category_scores': typosquat.risk_analysis_category_scores,
                    'risk_analysis_risk_factors': typosquat.risk_analysis_risk_factors,
                    # Threatstream data
                    'threatstream_data': typosquat.threatstream_data,
                    # RecordedFuture data
                    'recordedfuture_data': typosquat.recordedfuture_data,
                    # Source
                    'source': typosquat.source,
                    # Action taken
                    'action_taken': typosquat.action_taken,
                    # PhishLabs information (from consolidated JSONB)
                    'phishlabs_data': typosquat.phishlabs_data,
                    # Parked domain detection
                    'is_parked': typosquat.is_parked,
                    'parked_detection_timestamp': typosquat.parked_detection_timestamp.isoformat() if typosquat.parked_detection_timestamp else None,
                    'parked_detection_reasons': typosquat.parked_detection_reasons,
                    'parked_confidence': typosquat.parked_confidence,
                    # Protected domain similarities
                    'protected_domain_similarities': typosquat.protected_domain_similarities,
                    # Auto-resolve flag
                    'auto_resolve': typosquat.auto_resolve,
                    # AI analysis
                    'ai_analysis': typosquat.ai_analysis,
                    'ai_analyzed_at': typosquat.ai_analyzed_at.isoformat() if typosquat.ai_analyzed_at else None,
                    # Closure history (resolved / dismissed), with usernames
                    'closure_events': _closure_events_for_api(db, typosquat.closure_events),
                    **_last_closure_summary(typosquat.closure_events, typosquat.last_closure_at),
                }
                
            except Exception as e:
                logger.error(f"Error getting typosquat domain {domain_id}: {str(e)}")
                raise

    @staticmethod
    async def get_ai_analysis_context(domain_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full context for AI analysis: finding, URLs, and screenshot extracted texts.
        Used by runner jobs to build prompts without DB access.
        """
        from sqlalchemy.orm import joinedload

        async with get_db_session() as db:
            try:
                domain = db.query(TyposquatDomain).filter(TyposquatDomain.id == domain_id).first()
                if not domain:
                    return None

                finding = await TyposquatFindingsRepository.get_typosquat_by_id(domain_id)
                if not finding:
                    return None

                urls_raw = db.query(TyposquatURL).filter(
                    TyposquatURL.typosquat_domain_id == domain_id
                ).limit(20).all()
                urls = [
                    {
                        "url": u.url,
                        "http_status_code": u.http_status_code,
                        "title": u.title,
                        "technologies": u.technologies or [],
                        "content_type": u.content_type,
                        "path": u.path,
                        "final_url": u.final_url,
                        "body_preview": u.body_preview,
                    }
                    for u in urls_raw
                ]
                url_ids = [u.id for u in urls_raw]

                screenshot_texts = []
                if url_ids:
                    screenshots_query = (
                        db.query(TyposquatScreenshot)
                        .options(joinedload(TyposquatScreenshot.url))
                        .filter(TyposquatScreenshot.url_id.in_(url_ids))
                        .order_by(TyposquatScreenshot.url_id)
                    )
                    seen_hashes = set()
                    for screenshot in screenshots_query.all():
                        if screenshot.image_hash and screenshot.image_hash not in seen_hashes:
                            seen_hashes.add(screenshot.image_hash)
                            url_str = screenshot.url.url if screenshot.url else "N/A"
                            screenshot_texts.append({
                                "url": url_str,
                                "extracted_text": screenshot.extracted_text or "",
                            })
                            if len(screenshot_texts) >= 2:
                                break

                program = (
                    db.query(Program)
                    .filter(Program.id == domain.program_id)
                    .first()
                )
                system_prompt, user_content_prefix = await resolve_typosquat_prompts(
                    program.ai_analysis_settings if program else None
                )

                return {
                    "finding": finding,
                    "urls": urls,
                    "screenshot_texts": screenshot_texts,
                    "system_prompt": system_prompt,
                    "user_content_prefix": user_content_prefix,
                }
            except Exception as e:
                logger.error(f"Error getting AI analysis context for {domain_id}: {str(e)}")
                raise

    @staticmethod
    async def get_unanalyzed_ai_finding_ids(
        program_id: str,
        batch_size: int = 50,
        reanalyze_after_days: Optional[int] = None,
    ) -> List[str]:
        """Get IDs of typosquat findings that need AI analysis."""
        from datetime import timedelta

        cutoff = None
        if reanalyze_after_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=reanalyze_after_days)

        async with get_db_session() as db:
            query = db.query(TyposquatDomain.id).filter(
                TyposquatDomain.program_id == program_id,
            )
            if cutoff:
                from sqlalchemy import or_
                query = query.filter(
                    or_(
                        TyposquatDomain.ai_analyzed_at.is_(None),
                        TyposquatDomain.ai_analyzed_at < cutoff,
                    )
                )
            else:
                query = query.filter(TyposquatDomain.ai_analyzed_at.is_(None))
            ids = [str(row[0]) for row in query.limit(batch_size).all()]
        return ids
        
    @staticmethod
    async def execute_typosquat_query(query: Dict[str, Any], limit: int = 1000000, skip: int = 0, sort: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute typosquat query with PostgreSQL"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return []  # Return empty list immediately if no program access
                
                sql_query = (
                    db.query(TyposquatDomain)
                    .options(joinedload(TyposquatDomain.typosquat_apex))
                    .join(Program)
                )
                
                # Apply program access filtering using shared utility
                sql_query = TyposquatFindingsRepository.apply_program_access_filter(sql_query, query, Program, needs_join=False)
                
                # Apply other filters
                sql_query = TyposquatFindingsRepository._apply_typosquat_filters(sql_query, query)
                
                # Apply sorting
                if sort:
                    for field, direction in sort.items():
                        if hasattr(TyposquatDomain, field):
                            if direction == 1:
                                sql_query = sql_query.order_by(asc(getattr(TyposquatDomain, field)))
                            else:
                                sql_query = sql_query.order_by(desc(getattr(TyposquatDomain, field)))
                
                # Apply pagination
                sql_query = sql_query.offset(skip).limit(limit)
                
                typosquats = sql_query.all()
                
                result = []
                for typosquat in typosquats:
                    logger.info(f"Typosquat: {typosquat}")
                    _w = TyposquatFindingsRepository._whois_public_fields_from_apex(typosquat)
                    result.append({
                        'id': str(typosquat.id),
                        'apex_domain_id': typosquat.apex_typosquat_domain_id,
                        'typo_domain': typosquat.typo_domain,
                        'fuzzers': typosquat.fuzzer_types,
                        'info': {},  # info_data column removed
                        'timestamp': typosquat.detected_at.isoformat() if typosquat.detected_at else None,
                        'program_name': typosquat.program.name if typosquat.program else None,
                        'created_at': typosquat.created_at.isoformat() if typosquat.created_at else None,
                        'updated_at': typosquat.updated_at.isoformat() if typosquat.updated_at else None,
                        'risk_score': typosquat.risk_score,
                        'status': typosquat.status,
                        'assigned_to': typosquat.assigned_to,
                        'notes': typosquat.notes,
                        'fixed_at': typosquat.fixed_at.isoformat() if typosquat.fixed_at else None,
                        # Domain information
                        'domain_registered': typosquat.domain_registered,
                        'dns_a_records': typosquat.dns_a_records,
                        'dns_mx_records': typosquat.dns_mx_records,
                        'dns_ns_records': typosquat.dns_ns_records,
                        'is_wildcard': typosquat.is_wildcard,
                        'wildcard_types': typosquat.wildcard_types,
                        # WHOIS information (typosquat_apex_domains)
                        'whois_registrar': _w['whois_registrar'],
                        'whois_creation_date': _w['whois_creation_date'],
                        'whois_expiration_date': _w['whois_expiration_date'],
                        'whois_registrant_name': _w['whois_registrant_name'],
                        'whois_registrant_country': _w['whois_registrant_country'],
                        'whois_admin_email': _w['whois_admin_email'],
                        # GeoIP information
                        'geoip_country': typosquat.geoip_country,
                        'geoip_city': typosquat.geoip_city,
                        'geoip_organization': typosquat.geoip_organization,
                        # Risk analysis
                        'risk_analysis_total_score': typosquat.risk_analysis_total_score,
                        'risk_analysis_risk_level': typosquat.risk_analysis_risk_level,
                        'risk_analysis_version': typosquat.risk_analysis_version,
                        'risk_analysis_timestamp': typosquat.risk_analysis_timestamp.isoformat() if typosquat.risk_analysis_timestamp else None,
                        'risk_analysis_category_scores': typosquat.risk_analysis_category_scores,
                        'risk_analysis_risk_factors': typosquat.risk_analysis_risk_factors,
                        # Threatstream data
                        'threatstream_data': typosquat.threatstream_data,
                        # PhishLabs information (from consolidated JSONB)
                        'phishlabs_data': typosquat.phishlabs_data,
                        # RecordedFuture data
                        'recordedfuture_data': typosquat.recordedfuture_data,
                        # Source
                        'source': typosquat.source,
                        'is_parked': typosquat.is_parked,
                        'parked_detection_timestamp': typosquat.parked_detection_timestamp.isoformat() if typosquat.parked_detection_timestamp else None,
                        'parked_detection_reasons': typosquat.parked_detection_reasons,
                        'ai_analysis': typosquat.ai_analysis,
                        'ai_analyzed_at': typosquat.ai_analyzed_at.isoformat() if typosquat.ai_analyzed_at else None,
                        **_last_closure_summary(typosquat.closure_events, typosquat.last_closure_at),
                    })
                
                return result
                
            except Exception as e:
                logger.error(f"Error executing typosquat query: {str(e)}")
                raise
    
    @staticmethod
    async def get_typosquat_query_count(query: Dict[str, Any]) -> int:
        """Get count for typosquat query"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return 0  # Return 0 immediately if no program access
                
                sql_query = db.query(func.count(TyposquatDomain.id)).join(Program)
                
                # Apply program access filtering using shared utility
                sql_query = TyposquatFindingsRepository.apply_program_access_filter(sql_query, query, Program, needs_join=False)
                
                # Apply other filters
                sql_query = TyposquatFindingsRepository._apply_typosquat_filters(sql_query, query)
                return sql_query.scalar()
                
            except Exception as e:
                logger.error(f"Error getting typosquat query count: {str(e)}")
                raise

    # =====================
    # Typed Typosquat Query
    # =====================
    @staticmethod
    async def search_typosquat_typed(
        *,
        search_typed: Optional[str] = None,
        exact_match_typed: Optional[str] = None,
        status: Optional[List[str]] = None,
        registrar_contains: Optional[str] = None,
        country: Optional[str] = None,
        min_risk_score: Optional[int] = None,
        max_risk_score: Optional[int] = None,
        has_ip: Optional[bool] = None,
        ip_contains: Optional[str] = None,
        is_wildcard: Optional[bool] = None,
        is_parked: Optional[bool] = None,
        auto_resolve: Optional[bool] = None,
        http_status: Optional[int] = None,
        has_phishlabs: Optional[bool] = None,
        has_whois_registrar: Optional[bool] = None,
        phishlabs_incident_status: Optional[List[str]] = None,
        has_threatstream: Optional[bool] = None,
        source: Optional[str] = None,
        assigned_to_username: Optional[str] = None,
        apex_domain: Optional[str] = None,
        apex_only: Optional[bool] = None,
        threatstream_id: Optional[str] = None,
        min_threatstream_score: Optional[int] = None,
        max_threatstream_score: Optional[int] = None,
        similarity_protected_domain: Optional[str] = None,
        min_similarity_percent: Optional[float] = None,
        created_at_from: Optional[datetime] = None,
        created_at_to: Optional[datetime] = None,
        updated_at_from: Optional[datetime] = None,
        updated_at_to: Optional[datetime] = None,
        last_closure_at_from: Optional[datetime] = None,
        last_closure_at_to: Optional[datetime] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed typosquat findings search optimized for PostgreSQL.
        Returns a dict with keys: items (list[dict]), total_count (int)
        """
        async with get_db_session() as db:
            try:
                # Import User model here to avoid circular imports
                from models.postgres import User

                base_query = (
                    db.query(
                        TyposquatDomain.id.label("id"),
                        TyposquatDomain.typo_domain.label("typo_domain"),
                        Program.name.label("program_name"),
                        TyposquatDomain.status.label("status"),
                        TyposquatDomain.assigned_to.label("assigned_to"),
                        User.username.label("assigned_to_username"),
                        TyposquatDomain.risk_score.label("risk_score"),
                        TyposquatApexDomain.whois_registrar.label("whois_registrar"),
                        TyposquatDomain.geoip_country.label("geoip_country"),
                        TyposquatDomain.dns_a_records.label("dns_a_records"),
                        TyposquatDomain.dns_ns_records.label("dns_ns_records"),
                        TyposquatDomain.is_wildcard.label("is_wildcard"),
                        TyposquatApexDomain.whois_creation_date.label("whois_creation_date"),
                        TyposquatDomain.phishlabs_data.label("phishlabs_data"),
                        TyposquatDomain.threatstream_data.label("threatstream_data"),
                        TyposquatDomain.recordedfuture_data.label("recordedfuture_data"),
                        TyposquatDomain.source.label("source"),
                        TyposquatDomain.action_taken.label("action_taken"),
                        TyposquatDomain.updated_at.label("updated_at"),
                        # Parked domain detection
                        TyposquatDomain.is_parked.label("is_parked"),
                        TyposquatDomain.parked_detection_timestamp.label("parked_detection_timestamp"),
                        TyposquatDomain.parked_detection_reasons.label("parked_detection_reasons"),
                        TyposquatDomain.parked_confidence.label("parked_confidence"),
                        TyposquatDomain.auto_resolve.label("auto_resolve"),
                        TyposquatDomain.ai_analysis.label("ai_analysis"),
                        TyposquatDomain.ai_analyzed_at.label("ai_analyzed_at"),
                        TyposquatDomain.closure_events.label("closure_events"),
                        TyposquatDomain.last_closure_at.label("last_closure_at"),
                    )
                    .select_from(TyposquatDomain)
                    .join(
                        TyposquatApexDomain,
                        TyposquatApexDomain.id == TyposquatDomain.apex_typosquat_domain_id,
                    )
                    .join(Program, Program.id == TyposquatDomain.program_id)
                    .outerjoin(User, User.id == func.cast(
                        func.nullif(TyposquatDomain.assigned_to, ''),
                        User.id.type
                    ))
                )

                # Filters
                if programs is not None and len(programs) > 0:
                    base_query = base_query.filter(Program.name.in_(programs))

                if search_typed:
                    base_query = base_query.filter(TyposquatDomain.typo_domain.ilike(f"%{search_typed}%"))
                
                if exact_match_typed:
                    base_query = base_query.filter(TyposquatDomain.typo_domain == exact_match_typed)

                if status:
                    base_query = base_query.filter(TyposquatDomain.status.in_(status))

                if registrar_contains:
                    base_query = base_query.filter(
                        TyposquatApexDomain.whois_registrar.ilike(f"%{registrar_contains}%")
                    )

                if country:
                    base_query = base_query.filter(TyposquatDomain.geoip_country == country)

                if min_risk_score is not None:
                    base_query = base_query.filter(TyposquatDomain.risk_score >= min_risk_score)
                if max_risk_score is not None:
                    base_query = base_query.filter(TyposquatDomain.risk_score <= max_risk_score)

                if has_ip is True:
                    # Filter for records that have non-empty dns_a_records array
                    base_query = base_query.filter(
                        and_(
                            TyposquatDomain.dns_a_records.isnot(None),
                            func.array_length(TyposquatDomain.dns_a_records, 1) > 0
                        )
                    )
                elif has_ip is False:
                    # Filter for records that have empty or null dns_a_records array
                    base_query = base_query.filter(
                        or_(
                            TyposquatDomain.dns_a_records.is_(None),
                            func.array_length(TyposquatDomain.dns_a_records, 1) == 0
                        )
                    )

                if ip_contains:
                    # Cast array to text and perform substring match (simpler and efficient)
                    base_query = base_query.filter(
                        TyposquatDomain.dns_a_records.cast(String).ilike(f"%{ip_contains}%")
                    )

                if is_wildcard is True:
                    base_query = base_query.filter(TyposquatDomain.is_wildcard.is_(True))
                elif is_wildcard is False:
                    base_query = base_query.filter(
                        or_(TyposquatDomain.is_wildcard.is_(False), TyposquatDomain.is_wildcard.is_(None))
                    )

                if is_parked is True:
                    base_query = base_query.filter(TyposquatDomain.is_parked.is_(True))
                elif is_parked is False:
                    base_query = base_query.filter(
                        or_(TyposquatDomain.is_parked.is_(False), TyposquatDomain.is_parked.is_(None))
                    )

                if auto_resolve is True:
                    base_query = base_query.filter(TyposquatDomain.auto_resolve.is_(True))
                elif auto_resolve is False:
                    base_query = base_query.filter(
                        or_(TyposquatDomain.auto_resolve.is_(False), TyposquatDomain.auto_resolve.is_(None))
                    )

                if has_phishlabs is True:
                    base_query = base_query.filter(TyposquatDomain.phishlabs_data.isnot(None))
                elif has_phishlabs is False:
                    base_query = base_query.filter(TyposquatDomain.phishlabs_data.is_(None))

                if has_whois_registrar is True:
                    # Filter for records that have non-empty whois_registrar
                    base_query = base_query.filter(
                        and_(
                            TyposquatApexDomain.whois_registrar.isnot(None),
                            func.trim(TyposquatApexDomain.whois_registrar) != ''
                        )
                    )
                elif has_whois_registrar is False:
                    # Filter for records that have empty or null whois_registrar
                    base_query = base_query.filter(
                        or_(
                            TyposquatApexDomain.whois_registrar.is_(None),
                            func.trim(TyposquatApexDomain.whois_registrar) == ''
                        )
                    )

                if phishlabs_incident_status and len(phishlabs_incident_status) > 0:
                    # Build conditions for each selected status
                    status_conditions = []
                    for status_value in phishlabs_incident_status:
                        if status_value == 'no_incident':
                            # No incident: either no phishlabs_data or no incident_id
                            status_conditions.append(
                                or_(
                                    TyposquatDomain.phishlabs_data.is_(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').is_(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') == 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') == ''
                                )
                            )
                        elif status_value == 'monitoring':
                            # Monitoring: has incident and incident_status = 'Monitoring'
                            status_conditions.append(
                                and_(
                                    TyposquatDomain.phishlabs_data.isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != '',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_status') == 'Monitoring'
                                )
                            )
                        elif status_value == 'other':
                            # Other: has incident but incident_status != 'Monitoring'
                            status_conditions.append(
                                and_(
                                    TyposquatDomain.phishlabs_data.isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != '',
                                    or_(
                                        TyposquatDomain.phishlabs_data.op('->>')('incident_status') != 'Monitoring',
                                        TyposquatDomain.phishlabs_data.op('->')('incident_status').is_(None)
                                    )
                                )
                            )

                    # Combine all status conditions with OR
                    if status_conditions:
                        base_query = base_query.filter(or_(*status_conditions))

                # Threatstream filters
                if has_threatstream is True:
                    base_query = base_query.filter(TyposquatDomain.threatstream_data.isnot(None))
                elif has_threatstream is False:
                    base_query = base_query.filter(TyposquatDomain.threatstream_data.is_(None))

                if threatstream_id:
                    # Filter by specific threatstream ID within the JSON data
                    base_query = base_query.filter(
                        TyposquatDomain.threatstream_data.cast(String).like(f'%"id": {threatstream_id}%')
                    )

                if min_threatstream_score is not None or max_threatstream_score is not None:
                    # For threat score filtering, we need to use JSON path queries
                    if min_threatstream_score is not None:
                        base_query = base_query.filter(
                            func.cast(TyposquatDomain.threatstream_data.op('->>')('threatscore'), Integer) >= min_threatstream_score
                        )
                    if max_threatstream_score is not None:
                        base_query = base_query.filter(
                            func.cast(TyposquatDomain.threatstream_data.op('->>')('threatscore'), Integer) <= max_threatstream_score
                        )

                if source:
                    if source == 'no_source':
                        # Filter for findings with no source (NULL or empty)
                        base_query = base_query.filter(
                            (TyposquatDomain.source.is_(None)) | (TyposquatDomain.source == '')
                        )
                    else:
                        base_query = base_query.filter(TyposquatDomain.source == source)

                if assigned_to_username:
                    if assigned_to_username == 'unassigned':
                        # Filter for unassigned findings
                        base_query = base_query.filter(User.username.is_(None))
                    else:
                        # Filter for specific username
                        base_query = base_query.filter(User.username == assigned_to_username)

                if apex_domain:
                    base_query = base_query.filter(TyposquatApexDomain.apex_domain == apex_domain)

                if apex_only is True:
                    base_query = base_query.filter(
                        TyposquatDomain.typo_domain == TyposquatApexDomain.apex_domain
                    )

                if created_at_from is not None:
                    base_query = base_query.filter(TyposquatDomain.created_at >= created_at_from)
                if created_at_to is not None:
                    base_query = base_query.filter(TyposquatDomain.created_at <= created_at_to)
                if updated_at_from is not None:
                    base_query = base_query.filter(TyposquatDomain.updated_at >= updated_at_from)
                if updated_at_to is not None:
                    base_query = base_query.filter(TyposquatDomain.updated_at <= updated_at_to)
                if last_closure_at_from is not None:
                    base_query = base_query.filter(TyposquatDomain.last_closure_at >= last_closure_at_from)
                if last_closure_at_to is not None:
                    base_query = base_query.filter(TyposquatDomain.last_closure_at <= last_closure_at_to)

                # Protected domain similarity filter
                # Filter by similarity to a specific protected domain with optional minimum percentage
                if similarity_protected_domain or min_similarity_percent is not None:
                    # Build the JSONB filter condition
                    # protected_domain_similarities is a JSONB array like:
                    # [{"protected_domain": "example.com", "similarity_percent": 85.0, "calculated_at": "..."}]
                    if similarity_protected_domain and min_similarity_percent is not None:
                        # Filter by both protected domain and minimum similarity
                        # Use jsonb_array_elements to search within the array
                        base_query = base_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    and_(
                                        text("elem->>'protected_domain' = :protected_domain"),
                                        text("(elem->>'similarity_percent')::float >= :min_similarity")
                                    )
                                )
                            ).params(protected_domain=similarity_protected_domain, min_similarity=min_similarity_percent)
                        )
                    elif similarity_protected_domain:
                        # Filter by protected domain only (any similarity)
                        base_query = base_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    text("elem->>'protected_domain' = :protected_domain")
                                )
                            ).params(protected_domain=similarity_protected_domain)
                        )
                    elif min_similarity_percent is not None:
                        # Filter by minimum similarity with any protected domain
                        base_query = base_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    text("(elem->>'similarity_percent')::float >= :min_similarity")
                                )
                            ).params(min_similarity=min_similarity_percent)
                        )

                # Count - include the same joins as the main query for consistency
                count_query = (
                    db.query(func.count())
                    .select_from(TyposquatDomain)
                    .join(
                        TyposquatApexDomain,
                        TyposquatApexDomain.id == TyposquatDomain.apex_typosquat_domain_id,
                    )
                    .join(Program, Program.id == TyposquatDomain.program_id)
                    .outerjoin(
                        User,
                        User.id
                        == func.cast(
                            func.nullif(TyposquatDomain.assigned_to, ""),
                            User.id.type,
                        ),
                    )
                )
                if programs is not None and len(programs) > 0:
                    count_query = count_query.filter(Program.name.in_(programs))
                if search_typed:
                    count_query = count_query.filter(TyposquatDomain.typo_domain.ilike(f"%{search_typed}%"))
                if exact_match_typed:
                    count_query = count_query.filter(TyposquatDomain.typo_domain == exact_match_typed)
                if status:
                    count_query = count_query.filter(TyposquatDomain.status.in_(status))
                if registrar_contains:
                    count_query = count_query.filter(
                        TyposquatApexDomain.whois_registrar.ilike(f"%{registrar_contains}%")
                    )
                if country:
                    count_query = count_query.filter(TyposquatDomain.geoip_country == country)
                if min_risk_score is not None:
                    count_query = count_query.filter(TyposquatDomain.risk_score >= min_risk_score)
                if max_risk_score is not None:
                    count_query = count_query.filter(TyposquatDomain.risk_score <= max_risk_score)
                if has_ip is True:
                    # Filter for records that have non-empty dns_a_records array
                    count_query = count_query.filter(
                        and_(
                            TyposquatDomain.dns_a_records.isnot(None),
                            func.array_length(TyposquatDomain.dns_a_records, 1) > 0
                        )
                    )
                elif has_ip is False:
                    # Filter for records that have empty or null dns_a_records array
                    count_query = count_query.filter(
                        or_(
                            TyposquatDomain.dns_a_records.is_(None),
                            func.array_length(TyposquatDomain.dns_a_records, 1) == 0
                        )
                    )
                if ip_contains:
                    # Cast array to text and perform substring match (simpler and efficient)
                    count_query = count_query.filter(
                        TyposquatDomain.dns_a_records.cast(String).ilike(f"%{ip_contains}%")
                    )
                if is_wildcard is True:
                    count_query = count_query.filter(TyposquatDomain.is_wildcard.is_(True))
                elif is_wildcard is False:
                    count_query = count_query.filter(or_(TyposquatDomain.is_wildcard.is_(False), TyposquatDomain.is_wildcard.is_(None)))
                if is_parked is True:
                    count_query = count_query.filter(TyposquatDomain.is_parked.is_(True))
                elif is_parked is False:
                    count_query = count_query.filter(or_(TyposquatDomain.is_parked.is_(False), TyposquatDomain.is_parked.is_(None)))
                if has_phishlabs is True:
                    count_query = count_query.filter(TyposquatDomain.phishlabs_data.isnot(None))
                elif has_phishlabs is False:
                    count_query = count_query.filter(TyposquatDomain.phishlabs_data.is_(None))

                if has_whois_registrar is True:
                    count_query = count_query.filter(
                        and_(
                            TyposquatApexDomain.whois_registrar.isnot(None),
                            func.trim(TyposquatApexDomain.whois_registrar) != "",
                        )
                    )
                elif has_whois_registrar is False:
                    count_query = count_query.filter(
                        or_(
                            TyposquatApexDomain.whois_registrar.is_(None),
                            func.trim(TyposquatApexDomain.whois_registrar) == "",
                        )
                    )

                if phishlabs_incident_status and len(phishlabs_incident_status) > 0:
                    # Build conditions for each selected status
                    status_conditions = []
                    for status_value in phishlabs_incident_status:
                        if status_value == 'no_incident':
                            # No incident: either no phishlabs_data or no incident_id
                            status_conditions.append(
                                or_(
                                    TyposquatDomain.phishlabs_data.is_(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').is_(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') == 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') == ''
                                )
                            )
                        elif status_value == 'monitoring':
                            # Monitoring: has incident and incident_status = 'Monitoring'
                            status_conditions.append(
                                and_(
                                    TyposquatDomain.phishlabs_data.isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != '',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_status') == 'Monitoring'
                                )
                            )
                        elif status_value == 'other':
                            # Other: has incident but incident_status != 'Monitoring'
                            status_conditions.append(
                                and_(
                                    TyposquatDomain.phishlabs_data.isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->')('incident_id').isnot(None),
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != 'null',
                                    TyposquatDomain.phishlabs_data.op('->>')('incident_id') != '',
                                    or_(
                                        TyposquatDomain.phishlabs_data.op('->>')('incident_status') != 'Monitoring',
                                        TyposquatDomain.phishlabs_data.op('->')('incident_status').is_(None)
                                    )
                                )
                            )

                    # Combine all status conditions with OR
                    if status_conditions:
                        count_query = count_query.filter(or_(*status_conditions))

                if auto_resolve is True:
                    count_query = count_query.filter(TyposquatDomain.auto_resolve.is_(True))
                elif auto_resolve is False:
                    count_query = count_query.filter(
                        or_(TyposquatDomain.auto_resolve.is_(False), TyposquatDomain.auto_resolve.is_(None))
                    )

                # Threatstream filters for count query
                if has_threatstream is True:
                    count_query = count_query.filter(TyposquatDomain.threatstream_data.isnot(None))
                elif has_threatstream is False:
                    count_query = count_query.filter(TyposquatDomain.threatstream_data.is_(None))

                if threatstream_id:
                    # Filter by specific threatstream ID within the JSON data
                    count_query = count_query.filter(
                        TyposquatDomain.threatstream_data.cast(String).like(f'%"id": {threatstream_id}%')
                    )

                if min_threatstream_score is not None or max_threatstream_score is not None:
                    # For threat score filtering, we need to use JSON path queries
                    if min_threatstream_score is not None:
                        count_query = count_query.filter(
                            func.cast(TyposquatDomain.threatstream_data.op('->>')('threatscore'), Integer) >= min_threatstream_score
                        )
                    if max_threatstream_score is not None:
                        count_query = count_query.filter(
                            func.cast(TyposquatDomain.threatstream_data.op('->>')('threatscore'), Integer) <= max_threatstream_score
                        )

                if source:
                    if source == 'no_source':
                        # Filter for findings with no source (NULL or empty)
                        count_query = count_query.filter(
                            (TyposquatDomain.source.is_(None)) | (TyposquatDomain.source == '')
                        )
                    else:
                        count_query = count_query.filter(TyposquatDomain.source == source)

                if assigned_to_username:
                    if assigned_to_username == 'unassigned':
                        # Filter for unassigned findings
                        count_query = count_query.filter(User.username.is_(None))
                    else:
                        # Filter for specific username
                        count_query = count_query.filter(User.username == assigned_to_username)

                if apex_domain:
                    count_query = count_query.filter(TyposquatApexDomain.apex_domain == apex_domain)

                if apex_only is True:
                    count_query = count_query.filter(
                        TyposquatDomain.typo_domain == TyposquatApexDomain.apex_domain
                    )

                if created_at_from is not None:
                    count_query = count_query.filter(TyposquatDomain.created_at >= created_at_from)
                if created_at_to is not None:
                    count_query = count_query.filter(TyposquatDomain.created_at <= created_at_to)
                if updated_at_from is not None:
                    count_query = count_query.filter(TyposquatDomain.updated_at >= updated_at_from)
                if updated_at_to is not None:
                    count_query = count_query.filter(TyposquatDomain.updated_at <= updated_at_to)
                if last_closure_at_from is not None:
                    count_query = count_query.filter(TyposquatDomain.last_closure_at >= last_closure_at_from)
                if last_closure_at_to is not None:
                    count_query = count_query.filter(TyposquatDomain.last_closure_at <= last_closure_at_to)

                # Protected domain similarity filter for count query
                if similarity_protected_domain or min_similarity_percent is not None:
                    if similarity_protected_domain and min_similarity_percent is not None:
                        count_query = count_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    and_(
                                        text("elem->>'protected_domain' = :protected_domain"),
                                        text("(elem->>'similarity_percent')::float >= :min_similarity")
                                    )
                                )
                            ).params(protected_domain=similarity_protected_domain, min_similarity=min_similarity_percent)
                        )
                    elif similarity_protected_domain:
                        count_query = count_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    text("elem->>'protected_domain' = :protected_domain")
                                )
                            ).params(protected_domain=similarity_protected_domain)
                        )
                    elif min_similarity_percent is not None:
                        count_query = count_query.filter(
                            func.exists(
                                select(literal(1)).select_from(
                                    func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                                ).where(
                                    text("(elem->>'similarity_percent')::float >= :min_similarity")
                                )
                            ).params(min_similarity=min_similarity_percent)
                        )

                total_count = count_query.scalar() or 0

                # Sorting
                sort_dir_func = asc if sort_dir == "asc" else desc
                sort_map = {
                    "typo_domain": TyposquatDomain.typo_domain,
                    "status": TyposquatDomain.status,
                    "risk_score": TyposquatDomain.risk_score,
                    "whois_creation_date": TyposquatApexDomain.whois_creation_date,
                    "phishlabs_data": TyposquatDomain.phishlabs_data,
                    "program_name": Program.name,
                    "source": TyposquatDomain.source,
                    "updated_at": TyposquatDomain.updated_at,
                    "is_parked": TyposquatDomain.is_parked,
                }

                # Handle special sorting cases for JSON fields
                if sort_by == "phishlabs_incident_id":
                    # Sort by incident_id within phishlabs_data JSON using PostgreSQL ->> operator
                    sort_col = TyposquatDomain.phishlabs_data.op('->>')('incident_id')
                    base_query = base_query.order_by(sort_dir_func(sort_col))
                elif sort_by == "ai_analysis_threat_level":
                    # Sort by threat_level from ai_analysis JSONB: high=1, medium=2, low=3, benign=4, null=5
                    threat_level_col = TyposquatDomain.ai_analysis.op('->>')('threat_level')
                    severity = case(
                        (threat_level_col == 'high', 1),
                        (threat_level_col == 'medium', 2),
                        (threat_level_col == 'low', 3),
                        (threat_level_col == 'benign', 4),
                        else_=5
                    )
                    base_query = base_query.order_by(sort_dir_func(severity))
                elif sort_by == "last_closure_at":
                    lc = TyposquatDomain.last_closure_at
                    if sort_dir == "asc":
                        base_query = base_query.order_by(asc(lc).nullsfirst())
                    else:
                        base_query = base_query.order_by(desc(lc).nullslast())
                else:
                    sort_col = sort_map.get(sort_by, TyposquatDomain.updated_at)
                    base_query = base_query.order_by(sort_dir_func(sort_col))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append({
                        "id": str(row.id),
                        "typo_domain": row.typo_domain,
                        "program_name": row.program_name,
                        "status": row.status,
                        "assigned_to": row.assigned_to,
                        "assigned_to_username": row.assigned_to_username,
                        "risk_score": row.risk_score,
                        "whois_registrar": row.whois_registrar,
                        "geoip_country": row.geoip_country,
                        "dns_a_records": row.dns_a_records,
                        "is_wildcard": row.is_wildcard,
                        "whois_creation_date": row.whois_creation_date.isoformat() if row.whois_creation_date else None,
                        "phishlabs_data": row.phishlabs_data,
                        "threatstream_data": row.threatstream_data,
                        "recordedfuture_data": row.recordedfuture_data,
                        "source": row.source,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                        # Parked domain detection
                        "is_parked": row.is_parked,
                        "parked_detection_timestamp": row.parked_detection_timestamp.isoformat() if row.parked_detection_timestamp else None,
                        "parked_detection_reasons": row.parked_detection_reasons,
                        "parked_confidence": row.parked_confidence,
                        "auto_resolve": getattr(row, 'auto_resolve', False),
                        "ai_analysis": getattr(row, 'ai_analysis', None),
                        "ai_analyzed_at": row.ai_analyzed_at.isoformat() if getattr(row, 'ai_analyzed_at', None) else None,
                        **_last_closure_summary(
                            getattr(row, "closure_events", None),
                            getattr(row, "last_closure_at", None),
                        ),
                    })

                return {"items": items, "total_count": total_count}

            except Exception as e:
                logger.error(f"Error executing typed typosquat search: {str(e)}")
                raise
    
    @staticmethod
    def _apply_typosquat_filters(query, filters: Dict[str, Any]):
        """Apply MongoDB-style filters to SQLAlchemy query for typosquat domains"""
        if not filters:
            return query
        
        conditions = []
        
        for key, value in filters.items():
            if key == 'typo_domain':
                if isinstance(value, dict) and '$regex' in value:
                    # Handle regex pattern for typo_domain
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if 'i' in options:  # Case insensitive
                        conditions.append(TyposquatDomain.typo_domain.ilike(f'%{pattern}%'))
                    else:
                        conditions.append(TyposquatDomain.typo_domain.like(f'%{pattern}%'))
                else:
                    conditions.append(TyposquatDomain.typo_domain == value)
            elif key == 'program_name':
                # Program filtering is now handled by the shared utility
                # Skip this key to avoid duplicate filtering
                continue
            elif key in ('min_similarity_percent', 'similarity_protected_domain'):
                # Handled after the loop (JSONB protected_domain_similarities)
                continue
            elif key == 'risk_score':
                # Handle risk score filtering using new schema field
                if isinstance(value, dict):
                    if '$gte' in value:
                        conditions.append(TyposquatDomain.risk_score >= value['$gte'])
                    elif '$lte' in value:
                        conditions.append(TyposquatDomain.risk_score <= value['$lte'])
                    else:
                        conditions.append(TyposquatDomain.risk_score >= value)
                else:
                    conditions.append(TyposquatDomain.risk_score >= value)
            elif key == 'geoip_country':
                # Handle country filtering using new schema field
                conditions.append(TyposquatDomain.geoip_country == value)
            elif key == 'whois_registrar':
                # WHOIS is stored on typosquat_apex_domains
                if isinstance(value, dict) and '$regex' in value:
                    pattern = value.get('$regex', '')
                    opt = value.get('$options', '')
                    if 'i' in opt:
                        conditions.append(
                            exists().where(
                                and_(
                                    TyposquatApexDomain.id
                                    == TyposquatDomain.apex_typosquat_domain_id,
                                    TyposquatApexDomain.whois_registrar.ilike(f'%{pattern}%'),
                                )
                            )
                        )
                    else:
                        conditions.append(
                            exists().where(
                                and_(
                                    TyposquatApexDomain.id
                                    == TyposquatDomain.apex_typosquat_domain_id,
                                    TyposquatApexDomain.whois_registrar.like(f'%{pattern}%'),
                                )
                            )
                        )
                else:
                    conditions.append(
                        exists().where(
                            and_(
                                TyposquatApexDomain.id
                                == TyposquatDomain.apex_typosquat_domain_id,
                                TyposquatApexDomain.whois_registrar == value,
                            )
                        )
                    )
            elif key == 'dns_a_records':
                # Handle DNS A records filtering using new schema field
                if isinstance(value, dict) and '$regex' in value:
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if 'i' in options:  # Case insensitive
                        conditions.append(TyposquatDomain.dns_a_records.astext.ilike(f'%{pattern}%'))
                    else:
                        conditions.append(TyposquatDomain.dns_a_records.astext.like(f'%{pattern}%'))
                elif isinstance(value, dict) and '$exists' in value:
                    if value.get('$exists'):
                        conditions.append(TyposquatDomain.dns_a_records.isnot(None))
                    else:
                        conditions.append(TyposquatDomain.dns_a_records.is_(None))
                else:
                    conditions.append(TyposquatDomain.dns_a_records.astext == value)
            elif key == 'is_wildcard':
                # Handle wildcard filtering using new schema field
                if isinstance(value, dict) and '$exists' in value:
                    if value.get('$exists'):
                        conditions.append(TyposquatDomain.is_wildcard.isnot(None))
                    else:
                        conditions.append(TyposquatDomain.is_wildcard.is_(None))
                else:
                    conditions.append(TyposquatDomain.is_wildcard == value)
            elif key == 'status':
                # Handle status filtering
                if isinstance(value, dict) and '$ne' in value:
                    conditions.append(TyposquatDomain.status != value['$ne'])
                else:
                    conditions.append(TyposquatDomain.status == value)
            elif key == 'assigned_to':
                # Handle assigned_to filtering
                if isinstance(value, dict) and '$ne' in value:
                    conditions.append(TyposquatDomain.assigned_to != value['$ne'])
                else:
                    conditions.append(TyposquatDomain.assigned_to == value)
            elif key == 'phishlabs_incident_id':
                # Handle PhishLabs incident filtering - use JSONB field
                if isinstance(value, dict) and '$exists' in value:
                    if value.get('$exists'):
                        conditions.append(TyposquatDomain.phishlabs_data.isnot(None))
                    else:
                        conditions.append(TyposquatDomain.phishlabs_data.is_(None))
                else:
                    # Filter by incident_id within the JSONB structure
                    conditions.append(TyposquatDomain.phishlabs_data['incident_id'].astext.cast(Integer) == value)
            elif key == '$and':
                # Handle $and operator - flatten the AND conditions
                for and_filter in value:
                    # Apply each AND filter directly to the query
                    query = TyposquatFindingsRepository._apply_typosquat_filters(query, and_filter)
                return query  # Return early since we've modified the query directly
            elif key == '$or':
                # Handle $or operator - flatten the OR conditions
                or_conditions = []
                for or_filter in value:
                    # Process each OR filter and collect conditions
                    for or_key, or_value in or_filter.items():
                        if or_key == 'phishlabs_incident_id':
                            if isinstance(or_value, dict) and '$exists' in or_value:
                                if or_value.get('$exists'):
                                    or_conditions.append(TyposquatDomain.phishlabs_data.isnot(None))
                                else:
                                    or_conditions.append(TyposquatDomain.phishlabs_data.is_(None))
                            else:
                                # Filter by incident_id within the JSONB structure
                                or_conditions.append(TyposquatDomain.phishlabs_data['incident_id'].astext.cast(Integer) == or_value)
                        # Add other OR conditions as needed
                if or_conditions:
                    conditions.append(or_(*or_conditions))
            elif key == '$regex':
                # Handle regex patterns - typo_domain is used for domain matching
                if isinstance(value, dict):
                    pattern = value.get('$regex', '')
                    if pattern:
                        conditions.append(func.regexp_match(TyposquatDomain.typo_domain, pattern))

        # Protected domain similarity filter (JSONB protected_domain_similarities)
        similarity_params = {}
        if filters.get('similarity_protected_domain') is not None or filters.get('min_similarity_percent') is not None:
            sp = filters.get('similarity_protected_domain')
            mp = filters.get('min_similarity_percent')
            if sp is not None and mp is not None:
                conditions.append(
                    func.exists(
                        select(literal(1)).select_from(
                            func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                        ).where(
                            and_(
                                text("elem->>'protected_domain' = :protected_domain"),
                                text("(elem->>'similarity_percent')::float >= :min_similarity")
                            )
                        )
                    )
                )
                similarity_params = {'protected_domain': sp, 'min_similarity': mp}
            elif sp is not None:
                conditions.append(
                    func.exists(
                        select(literal(1)).select_from(
                            func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                        ).where(text("elem->>'protected_domain' = :protected_domain"))
                    )
                )
                similarity_params = {'protected_domain': sp}
            elif mp is not None:
                conditions.append(
                    func.exists(
                        select(literal(1)).select_from(
                            func.jsonb_array_elements(TyposquatDomain.protected_domain_similarities).alias('elem')
                        ).where(text("(elem->>'similarity_percent')::float >= :min_similarity"))
                    )
                )
                similarity_params = {'min_similarity': mp}

        if conditions:
            query = query.filter(and_(*conditions))
        if similarity_params:
            query = query.params(**similarity_params)
        return query
    
    @staticmethod
    async def get_typosquat_stats_by_risk_level(query: Dict[str, Any]) -> Dict[str, int]:
        """Get typosquat domains stats by risk level"""
        async with get_db_session() as db:
            try:
                sql_query = db.query(TyposquatDomain).join(Program)
                sql_query = TyposquatFindingsRepository._apply_typosquat_filters(sql_query, query)
                
                # Get counts by risk level
                stats = {
                    'critical': 0,  # risk_score >= 80
                    'high': 0,      # risk_score >= 60
                    'medium': 0,    # risk_score >= 40
                    'low': 0,       # risk_score >= 20
                    'info': 0       # risk_score < 20
                }
                
                # Count by risk score ranges
                critical_count = sql_query.filter(TyposquatDomain.risk_score >= 80).count()
                high_count = sql_query.filter(
                    and_(TyposquatDomain.risk_score >= 60, TyposquatDomain.risk_score < 80)
                ).count()
                medium_count = sql_query.filter(
                    and_(TyposquatDomain.risk_score >= 40, TyposquatDomain.risk_score < 60)
                ).count()
                low_count = sql_query.filter(
                    and_(TyposquatDomain.risk_score >= 20, TyposquatDomain.risk_score < 40)
                ).count()
                info_count = sql_query.filter(
                    or_(TyposquatDomain.risk_score < 20, TyposquatDomain.risk_score.is_(None))
                ).count()
                
                stats['critical'] = critical_count
                stats['high'] = high_count
                stats['medium'] = medium_count
                stats['low'] = low_count
                stats['info'] = info_count
                
                return stats
                
            except Exception as e:
                logger.error(f"Error getting typosquat stats: {str(e)}")
                raise
    
    @staticmethod
    async def get_distinct_typosquat_values(field_name: str, filter_data: Dict[str, Any]) -> List[str]:
        """Get distinct values for a field in typosquat domains"""
        async with get_db_session() as db:
            try:
                # Start with base query - always join with Program for consistency
                sql_query = db.query(TyposquatDomain).join(Program)
                sql_query = TyposquatFindingsRepository._apply_typosquat_filters(sql_query, filter_data)
                
                if field_name == 'typo_domain':
                    values = sql_query.with_entities(TyposquatDomain.typo_domain).distinct().all()
                elif field_name == 'program_name':
                    values = sql_query.with_entities(Program.name).distinct().all()
                elif field_name == 'fuzzers':
                    # For array fields, we need to unnest - use separate query to avoid JOIN issues
                    base_query = db.query(TyposquatDomain)
                    base_query = TyposquatFindingsRepository._apply_typosquat_filters(base_query, filter_data)
                    values = base_query.with_entities(func.unnest(TyposquatDomain.fuzzer_types)).distinct().all()
                elif field_name == 'geoip_country':
                    # Extract country using new schema field
                    values = sql_query.with_entities(
                        TyposquatDomain.geoip_country
                    ).filter(
                        TyposquatDomain.geoip_country.isnot(None)
                    ).distinct().all()
                elif field_name == 'whois_registrar':
                    values = (
                        sql_query.join(
                            TyposquatApexDomain,
                            TyposquatApexDomain.id == TyposquatDomain.apex_typosquat_domain_id,
                        )
                        .with_entities(TyposquatApexDomain.whois_registrar)
                        .filter(TyposquatApexDomain.whois_registrar.isnot(None))
                        .distinct()
                        .all()
                    )
                elif field_name == 'risk_score':
                    # Extract risk score using new schema field
                    values = sql_query.with_entities(
                        TyposquatDomain.risk_score
                    ).filter(
                        TyposquatDomain.risk_score.isnot(None)
                    ).distinct().all()
                elif field_name == 'status':
                    # Extract status using new schema field
                    values = sql_query.with_entities(
                        TyposquatDomain.status
                    ).filter(
                        TyposquatDomain.status.isnot(None)
                    ).distinct().all()
                elif field_name == 'assigned_to':
                    # Extract assigned_to using new schema field
                    values = sql_query.with_entities(
                        TyposquatDomain.assigned_to
                    ).filter(
                        TyposquatDomain.assigned_to.isnot(None)
                    ).distinct().all()
                elif field_name == 'assigned_to_username':
                    # Extract assigned_to_username by joining with User table
                    from models.postgres import User
                    values = sql_query.join(
                        User, User.id == func.cast(
                            func.nullif(TyposquatDomain.assigned_to, ''),
                            User.id.type
                        )
                    ).with_entities(
                        User.username
                    ).filter(
                        User.username.isnot(None)
                    ).distinct().all()
                elif field_name == 'source':
                    # Extract source using new schema field
                    values = sql_query.with_entities(
                        TyposquatDomain.source
                    ).filter(
                        TyposquatDomain.source.isnot(None)
                    ).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct typosquat values: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_typosquat_values_typed(field_name: str, programs: Optional[List[str]] = None) -> List[str]:
        """Get distinct typosquat values with program scoping (typed)."""
        async with get_db_session() as db:
            try:
                base = db.query(TyposquatDomain).join(Program)
                if programs:
                    base = base.filter(Program.name.in_(programs))

                if field_name == 'typo_domain':
                    values = base.with_entities(TyposquatDomain.typo_domain).distinct().all()
                elif field_name == 'program_name':
                    values = base.with_entities(Program.name).distinct().all()
                elif field_name == 'fuzzers':
                    values = db.query(func.unnest(TyposquatDomain.fuzzer_types)).distinct().all()
                elif field_name == 'geoip_country':
                    values = base.with_entities(TyposquatDomain.geoip_country).filter(TyposquatDomain.geoip_country.isnot(None)).distinct().all()
                elif field_name == 'whois_registrar':
                    values = (
                        base.join(
                            TyposquatApexDomain,
                            TyposquatApexDomain.id == TyposquatDomain.apex_typosquat_domain_id,
                        )
                        .with_entities(TyposquatApexDomain.whois_registrar)
                        .filter(TyposquatApexDomain.whois_registrar.isnot(None))
                        .distinct()
                        .all()
                    )
                elif field_name == 'risk_score':
                    values = base.with_entities(TyposquatDomain.risk_score).filter(TyposquatDomain.risk_score.isnot(None)).distinct().all()
                elif field_name == 'status':
                    values = base.with_entities(TyposquatDomain.status).filter(TyposquatDomain.status.isnot(None)).distinct().all()
                elif field_name == 'assigned_to':
                    values = base.with_entities(TyposquatDomain.assigned_to).filter(
                        func.nullif(TyposquatDomain.assigned_to, '').isnot(None)
                    ).distinct().all()
                elif field_name == 'assigned_to_username':
                    # Join to User to fetch distinct usernames for assigned_to
                    from models.postgres import User
                    values = (
                        base.outerjoin(User, User.id == func.cast(
                            func.nullif(TyposquatDomain.assigned_to, ''),
                            User.id.type
                        ))
                        .with_entities(User.username)
                        .filter(User.username.isnot(None))
                        .distinct()
                        .all()
                    )
                elif field_name == 'source':
                    values = base.with_entities(TyposquatDomain.source).filter(TyposquatDomain.source.isnot(None)).distinct().all()
                elif field_name == 'typosquat_apex_domain':
                    values = (
                        base.join(
                            TyposquatApexDomain,
                            TyposquatApexDomain.id == TyposquatDomain.apex_typosquat_domain_id,
                        )
                        .with_entities(TyposquatApexDomain.apex_domain)
                        .filter(TyposquatApexDomain.apex_domain.isnot(None))
                        .distinct()
                        .all()
                    )
                else:
                    raise ValueError(f"Unsupported field: {field_name}")

                return [str(v[0]) for v in values if v[0] is not None]
            except Exception as e:
                logger.error(f"Error getting typed distinct typosquat values: {str(e)}")
                raise
    
    @staticmethod
    async def get_distinct_typosquat_url_values_typed(field_name: str, programs: Optional[List[str]] = None) -> List[str]:
        """Get distinct typosquat url values with program scoping (typed)."""
        async with get_db_session() as db:
            try:
                base = db.query(TyposquatURL).join(Program)
                if programs:
                    base = base.filter(Program.name.in_(programs))

                if field_name == 'technologies':
                    values = base.with_entities(func.unnest(TyposquatURL.technologies)).distinct().all()
                elif field_name == 'port':
                    values = base.with_entities(TyposquatURL.port).distinct().all()
                elif field_name == 'program_name':
                    values = base.with_entities(Program.name).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")

                return [str(v[0]) for v in values if v[0] is not None]
            except Exception as e:
                logger.error(f"Error getting typed distinct typosquat values: {str(e)}")
                raise

        
    @staticmethod
    async def update_typosquat_domain(domain_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a typosquat domain"""
        async with get_db_session() as db:
            try:
                # Use SELECT FOR UPDATE to prevent race conditions on action_taken field
                typosquat = db.query(TyposquatDomain).filter(TyposquatDomain.id == domain_id).with_for_update().first()
                if not typosquat:
                    return False

                # Force refresh the object to ensure we have the latest database state
                # This prevents SQLAlchemy identity map caching issues with concurrent updates
                db.refresh(typosquat)

                # Debug logging to understand the state inconsistency
                logger.info(f"DEBUG: After refresh, typosquat.action_taken for {domain_id}: {typosquat.action_taken}")

                # Verify database state with a fresh query
                fresh_query = db.query(TyposquatDomain.action_taken).filter(TyposquatDomain.id == domain_id).scalar()
                logger.info(f"DEBUG: Fresh query action_taken for {domain_id}: {fresh_query}")

                if typosquat.action_taken != fresh_query:
                    logger.warning(f"DEBUG: Object state mismatch! Object: {typosquat.action_taken}, DB: {fresh_query}")
                    # Force the object to match the database state
                    typosquat.action_taken = fresh_query

                prev_status = typosquat.status or "new"

                whois_payload = TyposquatFindingsRepository._whois_subset_from_typosquat_data(
                    update_data
                )
                for k in list(whois_payload.keys()):
                    update_data.pop(k, None)
                # Client must not overwrite append-only closure history
                update_data.pop("closure_events", None)
                update_data.pop("last_closure_at", None)
                if whois_payload:
                    apex_name = extract_apex_domain(typosquat.typo_domain)
                    apex = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                        db,
                        apex_name,
                        typosquat.program_id,
                        whois_payload,
                    )
                    if typosquat.apex_typosquat_domain_id != apex.id:
                        typosquat.apex_typosquat_domain_id = apex.id

                # Check if status is being updated and if RecordedFuture data exists
                status_updated = False
                assignment_updated = False
                new_status = None
                comment = None
                action_taken = None

                if 'status' in update_data:
                    status_updated = True
                    new_status = update_data['status']

                if 'assigned_to' in update_data:
                    assignment_updated = True

                # Extract comment for RecordedFuture log_entry
                if 'comment' in update_data:
                    comment = update_data['comment']
                    # Remove comment from update_data as it's not a direct field on the model
                    update_data.pop('comment')

                # Extract action_taken for RecordedFuture added_actions_taken and database storage
                action_taken_for_database = None
                if 'action_taken' in update_data:
                    logger.info(f"Processing action_taken update for domain {domain_id}: '{update_data['action_taken']}'")
                    logger.info(f"Acquiring database lock for domain {domain_id} to update action_taken")
                    # Keep original value for RecordedFuture processing (expects single string)
                    action_taken = update_data['action_taken']

                    # Handle action_taken as a database field - append to existing array
                    current_actions = list(typosquat.action_taken or [])  # Create a copy to avoid reference issues
                    logger.info(f"DEBUG: Processing action_taken update - incoming action: '{action_taken}', current_actions: {current_actions}")

                    # Convert single action to list format for database storage
                    if isinstance(action_taken, str) and action_taken:
                        if action_taken not in current_actions:
                            current_actions.append(action_taken)
                            action_taken_for_database = current_actions
                            logger.info(f"DEBUG: Action '{action_taken}' NOT found in current_actions, appending. New array: {action_taken_for_database}")
                        else:
                            logger.info(f"DEBUG: Action '{action_taken}' ALREADY EXISTS in current_actions: {current_actions}, skipping append")
                            action_taken_for_database = None

                    # Remove action_taken from update_data to handle it separately
                    update_data.pop('action_taken')

                if 'user_rf_uhash' in update_data:
                    user_rf_uhash = update_data['user_rf_uhash']
                    update_data.pop('user_rf_uhash')
                else:
                    user_rf_uhash = None
                # Check if RecordedFuture data exists in the database
                logger.debug(f"typosquat.recordedfuture_data: {typosquat.recordedfuture_data}")
                has_recordedfuture_data = (
                    typosquat.recordedfuture_data is not None and 
                    typosquat.recordedfuture_data.get('alert_id') is not None
                )
                logger.debug(f"has_recordedfuture_data: {has_recordedfuture_data}")
                # Update fields
                for key, value in update_data.items():
                    if hasattr(typosquat, key):
                        if key.startswith('phishlabs_') and key != 'phishlabs_data':
                            # Handle PhishLabs fields - consolidate into phishlabs_data JSONB
                            if typosquat.phishlabs_data is None:
                                typosquat.phishlabs_data = {}

                            # Map old field names to new JSONB keys
                            field_mapping = {
                                'phishlabs_incident_id': 'incident_id',
                                'phishlabs_url': 'url',
                                'phishlabs_category_code': 'category_code',
                                'phishlabs_category_name': 'category_name',
                                'phishlabs_status': 'status',
                                'phishlabs_comment': 'comment',
                                'phishlabs_product': 'product',
                                'phishlabs_create_date': 'create_date',
                                'phishlabs_assignee': 'assignee',
                                'phishlabs_last_comment': 'last_comment',
                                'phishlabs_group_category_name': 'group_category_name',
                                'phishlabs_action_description': 'action_description',
                                'phishlabs_status_description': 'status_description',
                                'phishlabs_mitigation_start': 'mitigation_start',
                                'phishlabs_date_resolved': 'date_resolved',
                                'phishlabs_severity_name': 'severity_name',
                                'phishlabs_mx_record': 'mx_record',
                                'phishlabs_ticket_status': 'ticket_status',
                                'phishlabs_resolution_status': 'resolution_status',
                                'phishlabs_incident_status': 'incident_status',
                                'phishlabs_last_updated': 'last_updated'
                            }

                            if key in field_mapping:
                                jsonb_key = field_mapping[key]
                                # Only update PhishLabs fields if value is not None and not string "null"
                                if value is not None and value != "null":
                                    # Handle type conversions for specific fields
                                    if jsonb_key in ['incident_id', 'category_code']:
                                        try:
                                            typosquat.phishlabs_data[jsonb_key] = int(value)
                                        except (ValueError, TypeError) as e:
                                            logger.warning(f"Failed to convert {key} to int: {value}, error: {e}")
                                            typosquat.phishlabs_data[jsonb_key] = value
                                    else:
                                        typosquat.phishlabs_data[jsonb_key] = value
                        else:
                            # Handle all other fields with null protection
                            # Special case for assigned_to: allow None to unassign users
                            if key == 'assigned_to':
                                setattr(typosquat, key, value)
                            # Only update other fields if value is not None and not string "null"
                            elif value is not None and value != "null":
                                setattr(typosquat, key, value)
                            # Special handling for JSONB fields - preserve existing data when merging
                            elif key in ['phishlabs_data', 'threatstream_data', 'recordedfuture_data']:
                                # If the value is None or "null", skip the update to preserve existing data
                                logger.debug(f"Skipping update for {key} field as value is None or 'null', preserving existing data")
                    else:
                        logger.warning(f"TyposquatDomain model does not have attribute '{key}', skipping update")
                
                # Update action_taken field separately if provided
                if action_taken_for_database is not None:
                    # Capture old_actions BEFORE modifying typosquat.action_taken to avoid reference issues
                    old_actions = list(typosquat.action_taken or [])  # Create a copy to avoid reference issues
                    typosquat.action_taken = action_taken_for_database
                    logger.info(f"Updated action_taken for domain {domain_id}: {old_actions} -> {action_taken_for_database}")

                # Append-only closure history; sync fixed_at for legacy views (e.g. security_summary)
                if status_updated and new_status:
                    ns = new_status
                    ps = prev_status or "new"
                    if ns in _TERMINAL_CLOSURE_STATUSES and ps != ns:
                        closed_at_naive = datetime.utcnow()
                        closed_at_str = closed_at_naive.isoformat() + "Z"
                        existing_ev = typosquat.closure_events
                        if existing_ev is None or not isinstance(existing_ev, list):
                            existing_ev = []
                        ev: Dict[str, Any] = {
                            "to_status": ns,
                            "closed_at": closed_at_str,
                            "closed_by_user_id": typosquat.assigned_to or None,
                        }
                        typosquat.closure_events = list(existing_ev) + [ev]
                        typosquat.last_closure_at = closed_at_naive
                        if ns == "resolved":
                            typosquat.fixed_at = closed_at_naive
                    elif ns in ("new", "inprogress") and ps in _TERMINAL_CLOSURE_STATUSES:
                        typosquat.fixed_at = None

                typosquat.updated_at = datetime.utcnow()
                logger.debug(f"Committing database changes for domain {domain_id}")
                db.commit()
                logger.debug(f"Database lock released for domain {domain_id}")
                
                # Update RecordedFuture alert status if conditions are met
                # IMPORTANT: RecordedFuture API only allows actions_taken when status is "Dismissed" or "Resolved"
                # So we:
                # 1. Always store action_taken values in database (regardless of status)
                # 2. Call RF API when status is updated (any status) OR when assignment is updated
                # 3. Only send actions_taken when status is dismissed/resolved
                should_update_recordedfuture = (
                    has_recordedfuture_data and
                    (status_updated or assignment_updated)
                )

                if should_update_recordedfuture:
                    # Prepare log_entry and added_actions_taken for RecordedFuture API
                    log_entry = comment if comment and comment.strip() else None
                    added_actions_taken = None

                    # Determine the status to send to RecordedFuture
                    # If status is being updated, use new_status
                    # If only assignment is being updated, use current status from database
                    rf_status = new_status if status_updated else typosquat.status

                    # Only prepare actions_taken when status is being updated to dismissed/resolved
                    # RecordedFuture API only allows actions_taken for these statuses
                    if status_updated and new_status and new_status.lower() in ['dismissed', 'resolved']:
                        added_actions_taken = []

                        # Use ALL stored action_taken values from database (not just the current one being added)
                        # Get the current state after any updates
                        current_stored_actions = typosquat.action_taken or []
                        logger.debug(f"Processing stored action_taken values for RecordedFuture: {current_stored_actions}")

                        # Map all stored actions to RecordedFuture format
                        for stored_action in current_stored_actions:
                            if isinstance(stored_action, str) and stored_action:
                                mapped_action = TyposquatFindingsRepository._map_action_taken_to_recordedfuture(stored_action)
                                if mapped_action:
                                    if mapped_action not in added_actions_taken:  # Avoid duplicates
                                        added_actions_taken.append(mapped_action)
                                        logger.debug(f"Mapped stored action '{stored_action}' to RecordedFuture action '{mapped_action}'")
                                    else:
                                        logger.debug(f"RecordedFuture action '{mapped_action}' already in list, skipping duplicate")
                                else:
                                    logger.warning(f"No RecordedFuture action mapping found for stored action: {stored_action}")

                    if status_updated and assignment_updated:
                        logger.info(f"Updating RecordedFuture alert for typosquat domain {domain_id}: status to '{rf_status}' and assignment")
                    elif status_updated:
                        logger.info(f"Updating RecordedFuture alert status for typosquat domain {domain_id} to '{rf_status}'")
                    elif assignment_updated:
                        logger.info(f"Updating RecordedFuture alert assignment for typosquat domain {domain_id} with status '{rf_status}'")

                    if log_entry:
                        logger.info(f"Including log_entry: {log_entry}")
                    if added_actions_taken:
                        logger.info(f"Including {len(added_actions_taken)} mapped actions_taken: {added_actions_taken}")
                    else:
                        logger.info("No actions_taken to include in RecordedFuture update")

                    await TyposquatFindingsRepository._update_recordedfuture_alert_status(
                        typosquat,
                        rf_status,
                        log_entry=log_entry,
                        added_actions_taken=added_actions_taken,
                        user_rf_uhash=user_rf_uhash
                    )
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating typosquat domain {domain_id}: {str(e)}")
                raise
    
    @staticmethod
    async def _update_recordedfuture_alert_status(typosquat: TyposquatDomain, new_status: str, log_entry: Optional[str] = None, added_actions_taken: Optional[List[str]] = None, user_rf_uhash: Optional[str] = None) -> None:
        """
        Update RecordedFuture alert status for a typosquat domain.
        
        Args:
            typosquat: The TyposquatDomain object with recordedfuture_data
            new_status: The new status to set in RecordedFuture
        """
        try:
            # Validate that we have a status to update
            if not new_status:
                logger.warning(f"No status provided for RecordedFuture update for typosquat domain {typosquat.id}")
                return
            
            logger.debug(f"Called _update_recordedfuture_alert_status for typosquat domain {typosquat.id} with new status {new_status}")
            # Extract playbook alert ID from recordedfuture_data
            alert_id = typosquat.recordedfuture_data.get('alert_id')
            if not alert_id:
                logger.warning(f"No alert_id found in recordedfuture_data for typosquat domain {typosquat.id}")
                return
            
            # Get program name from the typosquat domain's program relationship
            program_name = None
            if hasattr(typosquat, 'program') and typosquat.program:
                program_name = typosquat.program.name
            elif hasattr(typosquat, 'program_id') and typosquat.program_id:
                # If program relationship is not loaded, get program name by ID
                program_data = await ProgramRepository.get_program(str(typosquat.program_id))
                if program_data:
                    program_name = program_data.get('name')
            
            if not program_name:
                logger.warning(f"No program name found for typosquat domain {typosquat.id}")
                return
            
            # Map internal status to RecordedFuture status
            rf_status = TyposquatFindingsRepository._map_status_to_recordedfuture(new_status)
            logger.debug(f"Mapped internal status {new_status} to RecordedFuture status {rf_status}")
            if not rf_status:
                logger.warning(f"No RecordedFuture status mapping found for status: {new_status}")
                return
            
            logger.info(f"Updating RecordedFuture alert {alert_id} status to '{rf_status}' for typosquat domain {typosquat.id} with user_rf_uhash {user_rf_uhash}")
            payload = {
                "program_name": program_name,
                "alert_id": alert_id,
                "new_status": rf_status,
                "user_rf_uhash": user_rf_uhash
            }
            if log_entry:
                payload["log_entry"] = log_entry
            if added_actions_taken:
                payload["added_actions_taken"] = added_actions_taken
            
            # Call RecordedFuture API
            result = await change_playbook_alert_status(
                **payload
            )
            
            if result.get("success"):
                logger.info(f"Successfully updated RecordedFuture alert {alert_id} status to '{rf_status}'")
            else:
                logger.error(f"Failed to update RecordedFuture alert {alert_id} status: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error updating RecordedFuture alert status for typosquat domain {typosquat.id}: {str(e)}")
            # Don't raise the exception to avoid breaking the main update operation
    
    @staticmethod
    def _map_status_to_recordedfuture(internal_status: str) -> Optional[str]:
        """
        Map internal typosquat domain status to RecordedFuture alert status.
        
        Args:
            internal_status: Internal status value
            
        Returns:
            RecordedFuture status string or None if no mapping exists
        """
        if not internal_status:
            return None
        
        status_mapping = {
            'new': 'New',
            'inprogress': 'InProgress',
            'resolved': 'Resolved',
            'dismissed': 'Dismissed'
        }
        
        return status_mapping.get(internal_status.lower())

    @staticmethod
    def _map_action_taken_to_recordedfuture(action_taken: str) -> Optional[str]:
        """
        Map internal action_taken value to RecordedFuture API action value.

        Args:
            action_taken: Internal action_taken value

        Returns:
            RecordedFuture action string or None if no mapping exists
        """
        action_mapping = {
            'monitoring': 'domain_abuse.monitoring',
            'takedown_requested': 'domain_abuse.takedown',
            'reported_google_safe_browsing': 'domain_abuse.reported_safe_browsing',
            'blocked_firewall': 'domain_abuse.firewall_block',  # Placeholder
            'other': 'domain_abuse.other'  # Placeholder
        }

        return action_mapping.get(action_taken.lower())

    @staticmethod
    async def get_dashboard_kpis(
        days: int = 30,
        single_date: Optional[str] = None,
        program: Optional[str] = None,
        accessible_programs: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get KPIs for typosquat domain dashboard.

        Args:
            days: Number of days to look back for trends (ignored if single_date or custom range)
            single_date: Single date in YYYY-MM-DD format for single day analysis
            program: Optional program filter
            accessible_programs: Programs accessible to the current user
            date_from: Custom range start YYYY-MM-DD (inclusive), use with date_to
            date_to: Custom range end YYYY-MM-DD (inclusive), use with date_from

        Returns:
            Dict containing dashboard KPIs
        """
        try:
            async with get_db_session() as db:
                from datetime import timedelta
                from sqlalchemy import text
                from datetime import datetime as dt

                custom_from: Optional[str] = None
                custom_to: Optional[str] = None

                # Calculate date range: custom range takes precedence over single_date and days
                if date_from and date_to:
                    from_dt = dt.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    to_dt = dt.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    start_date = from_dt
                    end_date = to_dt + timedelta(days=1)
                    is_single_day = from_dt.date() == to_dt.date()
                    custom_from = date_from
                    custom_to = date_to
                elif single_date:
                    single_dt = dt.strptime(single_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    start_date = single_dt
                    end_date = single_dt + timedelta(days=1)
                    is_single_day = True
                else:
                    # Use same logic as single date - end_date is start of next day
                    now = datetime.now(timezone.utc)
                    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = today_start + timedelta(days=1)  # Start of tomorrow
                    start_date = today_start - timedelta(days=days-1)  # Start of first day in range
                    is_single_day = False

                    # Debug logging
                    logger.info(f"Dashboard date range calculation - days: {days}, now: {now}")
                    logger.info(f"Dashboard date range - start: {start_date}, end: {end_date}")
                    logger.info(f"Dashboard date range - today included: {now.date() >= start_date.date() and now.date() <= end_date.date()}")
                    logger.info(f"Dashboard date range - start_date type: {type(start_date)}, end_date type: {type(end_date)}")
                    logger.info(f"Dashboard date range - start_date TZ: {start_date.tzinfo}, end_date TZ: {end_date.tzinfo}")

                    # Test query to check if today's data exists (simplified, no program filter)
                    test_query = text("""
                        SELECT
                            DATE(al.created_at AT TIME ZONE 'UTC') as date,
                            COUNT(*) as count
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                        GROUP BY DATE(al.created_at AT TIME ZONE 'UTC')
                        ORDER BY date
                    """)
                    test_params = {"start_date": start_date, "end_date": end_date}
                    test_result = db.execute(test_query, test_params)
                    test_rows = test_result.fetchall()
                    logger.info(f"Test query found {len(test_rows)} days with data:")
                    for row in test_rows:
                        logger.info(f"  {row.date}: {row.count} records")

                # Build program filter conditions
                program_condition = ""
                if accessible_programs:
                    program_list = "', '".join(accessible_programs)
                    program_condition = f"AND p.name IN ('{program_list}')"
                elif program:
                    program_condition = "AND p.name = :program_name"

                # 1. Current status distribution
                status_query = text(f"""
                    SELECT
                        td.status,
                        COUNT(*) as count
                    FROM typosquat_domains td
                    JOIN programs p ON td.program_id = p.id
                    WHERE 1=1 {program_condition}
                    GROUP BY td.status
                    ORDER BY td.status
                """)

                status_params = {}
                if program and not accessible_programs:
                    status_params["program_name"] = program

                status_result = db.execute(status_query, status_params)
                status_distribution = {row.status: row.count for row in status_result.fetchall()}

                # 2. Assignee distribution
                assignee_query = text(f"""
                    SELECT
                        COALESCE(u.username, 'Unassigned') as assignee,
                        COUNT(*) as count
                    FROM typosquat_domains td
                    JOIN programs p ON td.program_id = p.id
                    LEFT JOIN users u ON u.id = NULLIF(td.assigned_to, '')::uuid
                    WHERE 1=1 {program_condition}
                    GROUP BY u.username
                    ORDER BY count DESC
                    LIMIT 10
                """)

                assignee_result = db.execute(assignee_query, status_params)
                assignee_distribution = {row.assignee: row.count for row in assignee_result.fetchall()}

                # 3. Resolution and dismissal trends over time
                trends_query = text(f"""
                    SELECT
                        DATE(al.created_at AT TIME ZONE 'UTC') as date,
                        COALESCE(al.new_value->>'status', 'unknown') as new_status,
                        COUNT(*) as count
                    FROM action_logs al
                    JOIN typosquat_domains td ON al.entity_id = td.id::text
                    JOIN programs p ON td.program_id = p.id
                    WHERE al.entity_type = 'typosquat_finding'
                        AND al.action_type = 'status_change'
                        AND al.created_at >= :start_date
                        AND al.created_at < :end_date
                        AND al.new_value->>'status' IN ('resolved', 'dismissed')
                        {program_condition}
                    GROUP BY DATE(al.created_at AT TIME ZONE 'UTC'), al.new_value->>'status'
                    ORDER BY date
                """)

                trends_params = {
                    "start_date": start_date,
                    "end_date": end_date
                }
                if program and not accessible_programs:
                    trends_params["program_name"] = program

                trends_result = db.execute(trends_query, trends_params)
                trends_data = []
                for row in trends_result.fetchall():
                    trends_data.append({
                        "date": row.date.isoformat(),
                        "status": row.new_status,
                        "count": row.count
                    })

                # Debug logging for trends data
                logger.info(f"Dashboard trends data found {len(trends_data)} records")
                if trends_data:
                    logger.info(f"Trends date range: {min(d['date'] for d in trends_data)} to {max(d['date'] for d in trends_data)}")
                    today_str = datetime.now(timezone.utc).date().isoformat()
                    today_records = [d for d in trends_data if d['date'] == today_str]
                    logger.info(f"Today ({today_str}) records in trends: {len(today_records)}")

                # 4. Action taken distribution for resolved findings and GSB reports
                actions_query = text(f"""
                    SELECT
                        action_taken,
                        COUNT(*) as count
                    FROM (
                        -- Resolved findings with action_taken metadata
                        SELECT
                            al.metadata->>'action_taken' as action_taken
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.action_type = 'status_change'
                            AND al.new_value->>'status' = 'resolved'
                            AND al.metadata->>'action_taken' IS NOT NULL
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            {program_condition}

                        UNION ALL

                        -- Google Safe Browsing reports
                        SELECT
                            'reported_google_safe_browsing' as action_taken
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.action_type = 'google_safe_browsing_reported'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            {program_condition}
                    ) combined_actions
                    WHERE action_taken IS NOT NULL
                    GROUP BY action_taken
                    ORDER BY count DESC
                """)

                actions_result = db.execute(actions_query, trends_params)
                actions_distribution = {row.action_taken: row.count for row in actions_result.fetchall() if row.action_taken}

                # 5. Summary statistics
                summary_query = text(f"""
                    SELECT
                        COUNT(*) as total_findings,
                        COUNT(CASE WHEN td.status = 'resolved' THEN 1 END) as resolved_count,
                        COUNT(CASE WHEN td.status = 'dismissed' THEN 1 END) as dismissed_count,
                        COUNT(CASE WHEN td.status = 'inprogress' THEN 1 END) as inprogress_count,
                        COUNT(CASE WHEN td.status = 'new' THEN 1 END) as new_count,
                        COUNT(CASE WHEN td.assigned_to IS NOT NULL THEN 1 END) as assigned_count
                    FROM typosquat_domains td
                    JOIN programs p ON td.program_id = p.id
                    WHERE 1=1 {program_condition}
                """)

                summary_result = db.execute(summary_query, status_params)
                summary_row = summary_result.fetchone()

                # 6. Recent activity (last 24 hours)
                recent_activity_query = text(f"""
                    SELECT
                        COUNT(*) as recent_changes
                    FROM action_logs al
                    JOIN typosquat_domains td ON al.entity_id = td.id::text
                    JOIN programs p ON td.program_id = p.id
                    WHERE al.entity_type = 'typosquat_finding'
                        AND al.action_type = 'status_change'
                        AND al.created_at >= :recent_start
                        {program_condition}
                """)

                recent_params = {
                    "recent_start": end_date - timedelta(hours=24)
                }
                if program and not accessible_programs:
                    recent_params["program_name"] = program

                recent_result = db.execute(recent_activity_query, recent_params)
                recent_changes = recent_result.fetchone().recent_changes

                # 7. Daily breakdown (only if not single day)
                daily_breakdown = []
                if not is_single_day:
                    daily_query = text(f"""
                        WITH latest_actions AS (
                            SELECT
                                al.entity_id,
                                al.action_type,
                                al.new_value,
                                al.metadata,
                                al.user_id,
                                DATE(al.created_at AT TIME ZONE 'UTC') as action_date,
                                ROW_NUMBER() OVER (
                                    PARTITION BY al.entity_id, al.action_type
                                    ORDER BY al.created_at DESC
                                ) as rn
                            FROM action_logs al
                            JOIN typosquat_domains td ON al.entity_id = td.id::text
                            JOIN programs p ON td.program_id = p.id
                            WHERE al.entity_type = 'typosquat_finding'
                                AND al.created_at >= :start_date
                                AND al.created_at < :end_date
                                {program_condition}
                        )
                        SELECT
                            action_date as date,
                            COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'resolved' AND rn = 1 THEN 1 END) as resolved_count,
                            COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'dismissed' AND rn = 1 THEN 1 END) as dismissed_count,
                            COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'inprogress' AND rn = 1 THEN 1 END) as inprogress_count,
                            COUNT(CASE WHEN action_type = 'assignment_change' AND rn = 1 THEN 1 END) as assignment_count,
                            COUNT(CASE WHEN action_type = 'status_change' AND COALESCE(metadata->>'action_taken', '') = 'takedown_requested' AND rn = 1 THEN 1 END) as takedown_requested_count,
                            COUNT(CASE WHEN action_type = 'phishlabs_incident_created' AND rn = 1 THEN 1 END) as phishlabs_count,
                            COUNT(CASE WHEN action_type = 'google_safe_browsing_reported' AND rn = 1 THEN 1 END) as gsb_count
                        FROM latest_actions
                        WHERE rn = 1
                        GROUP BY action_date
                        ORDER BY date
                    """)

                    daily_result = db.execute(daily_query, trends_params)
                    for row in daily_result.fetchall():
                        daily_breakdown.append({
                            "date": row.date.isoformat(),
                            "resolved_count": row.resolved_count,
                            "dismissed_count": row.dismissed_count,
                            "inprogress_count": row.inprogress_count,
                            "assignment_count": row.assignment_count,
                            "takedown_requested_count": row.takedown_requested_count,
                            "phishlabs_count": row.phishlabs_count,
                            "gsb_count": row.gsb_count
                        })

                    # Debug logging for daily breakdown
                    logger.info(f"Dashboard daily breakdown found {len(daily_breakdown)} records")
                    if daily_breakdown:
                        logger.info(f"Daily breakdown date range: {min(d['date'] for d in daily_breakdown)} to {max(d['date'] for d in daily_breakdown)}")
                        today_str = datetime.now(timezone.utc).date().isoformat()
                        today_daily = [d for d in daily_breakdown if d['date'] == today_str]
                        logger.info(f"Today ({today_str}) records in daily breakdown: {len(today_daily)}")

                # 8. Team performance metrics (within selected period)
                team_performance_query = text(f"""
                    WITH latest_actions AS (
                        SELECT
                            al.entity_id,
                            al.action_type,
                            al.new_value,
                            al.user_id,
                            u.username,
                            ROW_NUMBER() OVER (
                                PARTITION BY al.entity_id, al.action_type
                                ORDER BY al.created_at DESC
                            ) as rn
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        LEFT JOIN users u ON u.id = al.user_id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            AND u.username IS NOT NULL
                            {program_condition}
                    ),
                    user_actions AS (
                        SELECT
                            username,
                            COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'resolved' AND rn = 1 THEN 1 END) as resolved_count,
                            COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'dismissed' AND rn = 1 THEN 1 END) as dismissed_count,
                            COUNT(CASE WHEN action_type = 'assignment_change' AND new_value->>'assigned_to_username' = username AND rn = 1 THEN 1 END) as assignment_count,
                            COUNT(CASE WHEN action_type = 'phishlabs_incident_created' AND rn = 1 THEN 1 END) as phishlabs_count,
                            COUNT(CASE WHEN action_type = 'google_safe_browsing_reported' AND rn = 1 THEN 1 END) as gsb_count
                        FROM latest_actions
                        WHERE rn = 1
                        GROUP BY username
                    )
                    SELECT
                        username,
                        resolved_count,
                        dismissed_count,
                        assignment_count,
                        phishlabs_count,
                        gsb_count,
                        (resolved_count + dismissed_count + assignment_count + phishlabs_count + gsb_count) as total_actions
                    FROM user_actions
                    WHERE (resolved_count + dismissed_count + assignment_count + phishlabs_count + gsb_count) > 0
                    ORDER BY total_actions DESC
                    LIMIT 20
                """)

                team_result = db.execute(team_performance_query, trends_params)
                team_performance = []
                for row in team_result.fetchall():
                    team_performance.append({
                        "username": row.username,
                        "resolved_count": row.resolved_count,
                        "dismissed_count": row.dismissed_count,
                        "assignment_count": row.assignment_count,
                        "phishlabs_count": row.phishlabs_count,
                        "gsb_count": row.gsb_count,
                        "total_actions": row.total_actions
                    })

                # 9. Period activity summary
                period_activity_query = text(f"""
                    WITH latest_actions AS (
                        SELECT
                            al.entity_id,
                            al.action_type,
                            al.new_value,
                            ROW_NUMBER() OVER (
                                PARTITION BY al.entity_id, al.action_type
                                ORDER BY al.created_at DESC
                            ) as rn
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            {program_condition}
                    )
                    SELECT
                        COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'resolved' AND rn = 1 THEN 1 END) as resolved_count,
                        COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'dismissed' AND rn = 1 THEN 1 END) as dismissed_count,
                        COUNT(CASE WHEN action_type = 'status_change' AND new_value->>'status' = 'inprogress' AND rn = 1 THEN 1 END) as inprogress_count,
                        COUNT(CASE WHEN action_type = 'assignment_change' AND rn = 1 THEN 1 END) as assignment_count,
                        COUNT(CASE WHEN action_type = 'phishlabs_incident_created' AND rn = 1 THEN 1 END) as phishlabs_count,
                        COUNT(CASE WHEN action_type = 'google_safe_browsing_reported' AND rn = 1 THEN 1 END) as gsb_count
                    FROM latest_actions
                    WHERE rn = 1
                """)

                period_result = db.execute(period_activity_query, trends_params)
                period_summary = period_result.fetchone()

                # 10. Daily creation breakdown by source
                creation_breakdown_query = text(f"""
                    SELECT
                        DATE(td.created_at AT TIME ZONE 'UTC') as date,
                        COALESCE(td.source, 'manual') as source,
                        COUNT(*) as count
                    FROM typosquat_domains td
                    JOIN programs p ON td.program_id = p.id
                    WHERE td.created_at >= :start_date
                        AND td.created_at < :end_date
                        {program_condition}
                    GROUP BY DATE(td.created_at AT TIME ZONE 'UTC'), COALESCE(td.source, 'manual')
                    ORDER BY date, source
                """)

                creation_result = db.execute(creation_breakdown_query, trends_params)
                creation_breakdown = []
                for row in creation_result.fetchall():
                    creation_breakdown.append({
                        "date": row.date.isoformat(),
                        "source": row.source,
                        "count": row.count
                    })

                # 11. Time-series breakdown (hourly for single day, daily for period)
                time_series_data = []
                if is_single_day:
                    # Query for hourly activity counts (resolved/dismissed status changes)
                    hourly_activity_query = text(f"""
                        SELECT
                            EXTRACT(HOUR FROM al.created_at AT TIME ZONE 'UTC') as hour,
                            al.new_value->>'status' as status,
                            COUNT(*) as count
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.action_type = 'status_change'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            AND al.new_value->>'status' IN ('resolved', 'dismissed')
                            {program_condition}
                        GROUP BY EXTRACT(HOUR FROM al.created_at AT TIME ZONE 'UTC'), al.new_value->>'status'
                    """)

                    # Query for hourly creation counts
                    hourly_creation_query = text(f"""
                        SELECT
                            EXTRACT(HOUR FROM td.created_at AT TIME ZONE 'UTC') as hour,
                            COUNT(*) as count
                        FROM typosquat_domains td
                        JOIN programs p ON td.program_id = p.id
                        WHERE td.created_at >= :start_date
                            AND td.created_at < :end_date
                            {program_condition}
                        GROUP BY EXTRACT(HOUR FROM td.created_at AT TIME ZONE 'UTC')
                    """)

                    # Execute both queries
                    activity_result = db.execute(hourly_activity_query, trends_params)
                    creation_result = db.execute(hourly_creation_query, trends_params)

                    # Build hourly data structure with all 24 hours
                    hourly_dict = {hour: {"hour": f"{hour:02d}", "created": 0, "resolved": 0, "dismissed": 0} for hour in range(24)}

                    # Populate activity data
                    for row in activity_result.fetchall():
                        hour = int(row.hour)
                        status = row.status
                        count = row.count
                        if status in ['resolved', 'dismissed']:
                            hourly_dict[hour][status] = count

                    # Populate creation data
                    for row in creation_result.fetchall():
                        hour = int(row.hour)
                        count = row.count
                        hourly_dict[hour]["created"] = count

                    # Convert to sorted list
                    time_series_data = [hourly_dict[hour] for hour in range(24)]
                else:
                    # Query for daily activity counts (resolved/dismissed status changes)
                    daily_activity_query = text(f"""
                        SELECT
                            DATE(al.created_at AT TIME ZONE 'UTC') as date,
                            al.new_value->>'status' as status,
                            COUNT(*) as count
                        FROM action_logs al
                        JOIN typosquat_domains td ON al.entity_id = td.id::text
                        JOIN programs p ON td.program_id = p.id
                        WHERE al.entity_type = 'typosquat_finding'
                            AND al.action_type = 'status_change'
                            AND al.created_at >= :start_date
                            AND al.created_at < :end_date
                            AND al.new_value->>'status' IN ('resolved', 'dismissed')
                            {program_condition}
                        GROUP BY DATE(al.created_at AT TIME ZONE 'UTC'), al.new_value->>'status'
                    """)

                    # Query for daily creation counts
                    daily_creation_query = text(f"""
                        SELECT
                            DATE(td.created_at AT TIME ZONE 'UTC') as date,
                            COUNT(*) as count
                        FROM typosquat_domains td
                        JOIN programs p ON td.program_id = p.id
                        WHERE td.created_at >= :start_date
                            AND td.created_at < :end_date
                            {program_condition}
                        GROUP BY DATE(td.created_at AT TIME ZONE 'UTC')
                    """)

                    # Execute both queries
                    activity_result = db.execute(daily_activity_query, trends_params)
                    creation_result = db.execute(daily_creation_query, trends_params)

                    # Build daily data structure
                    from datetime import timedelta
                    daily_dict = {}
                    current_date = start_date.date()
                    end_dt = end_date.date()
                    while current_date < end_dt:
                        date_str = current_date.isoformat()
                        daily_dict[date_str] = {"date": date_str, "created": 0, "resolved": 0, "dismissed": 0}
                        current_date += timedelta(days=1)

                    # Populate activity data
                    for row in activity_result.fetchall():
                        date_str = row.date.isoformat()
                        status = row.status
                        count = row.count
                        if date_str in daily_dict and status in ['resolved', 'dismissed']:
                            daily_dict[date_str][status] = count

                    # Populate creation data
                    for row in creation_result.fetchall():
                        date_str = row.date.isoformat()
                        count = row.count
                        if date_str in daily_dict:
                            daily_dict[date_str]["created"] = count

                    # Convert to sorted list
                    time_series_data = [daily_dict[date] for date in sorted(daily_dict.keys())]

                # Compile dashboard data
                dashboard_data = {
                    "lifetime_totals": {
                        "total_findings": summary_row.total_findings,
                        "resolved_count": summary_row.resolved_count,
                        "dismissed_count": summary_row.dismissed_count,
                        "inprogress_count": summary_row.inprogress_count,
                        "new_count": summary_row.new_count,
                        "assigned_count": summary_row.assigned_count,
                        "recent_changes_24h": recent_changes
                    },
                    "period_summary": {
                        "resolved_count": period_summary.resolved_count,
                        "dismissed_count": period_summary.dismissed_count,
                        "inprogress_count": period_summary.inprogress_count,
                        "assignment_count": period_summary.assignment_count,
                        "phishlabs_count": period_summary.phishlabs_count,
                        "gsb_count": period_summary.gsb_count
                    },
                    "status_distribution": status_distribution,
                    "assignee_distribution": assignee_distribution,
                    "resolution_trends": trends_data,
                    "action_distribution": actions_distribution,
                    "daily_breakdown": daily_breakdown,
                    "creation_breakdown": creation_breakdown,
                    "team_performance": team_performance,
                    "time_series_data": time_series_data,
                    "date_range": {
                        "start_date": start_date.isoformat(),
                        "end_date": end_date.isoformat() if not is_single_day else start_date.isoformat(),
                        "days": (end_date.date() - start_date.date()).days if custom_from else days,
                        "single_date": None if custom_from else single_date,
                        "is_single_day": is_single_day,
                        **(
                            {"date_from": custom_from, "date_to": custom_to}
                            if custom_from and custom_to
                            else {}
                        ),
                    }
                }

                return dashboard_data

        except Exception as e:
            logger.error(f"Error getting dashboard KPIs: {str(e)}")
            raise

    @staticmethod
    async def find_related_typosquat_domains(typo_domain: str, program_name: Optional[str] = None) -> List[str]:
        """
        Find all typosquat domain IDs that share the same base domain.
        
        Args:
            typo_domain: The reference typo domain
            program_name: Optional program filter
            
        Returns:
            List of domain IDs that share the same base domain
        """
        try:
            base_domain = extract_apex_domain(typo_domain)
            logger.info(f"Finding related domains for base domain: {base_domain}")
            
            async with get_db_session() as db:
                query = db.query(TyposquatDomain.id, TyposquatDomain.typo_domain)
                
                # Join with Program if program_name is specified
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                
                # Find all domains that have the same base domain
                all_domains = query.all()
                
                related_ids = []
                for domain_id, domain in all_domains:
                    domain_base = extract_apex_domain(domain)
                    if domain_base == base_domain:
                        related_ids.append(str(domain_id))
                
                logger.info(f"Found {len(related_ids)} related domains for base domain {base_domain}")
                return related_ids
                
        except Exception as e:
            logger.error(f"Error finding related typosquat domains for {typo_domain}: {str(e)}")
            return []

    @staticmethod
    async def get_related_typosquat_domains(typo_domain: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all typosquat domains that share the same base domain as the given domain.
        Returns a list of complete domain dictionaries for display purposes.
        
        Uses the new apex_typosquat_domain_id foreign key for efficient queries when available,
        falls back to string matching for legacy data.
        
        Args:
            typo_domain: The reference typo domain
            program_name: Optional program filter
            
        Returns:
            List of complete domain dictionaries with all fields
        """
        try:
            logger.info(f"Getting related domains for {typo_domain}, program: {program_name}")
            
            async with get_db_session() as db:
                # First, try to find the reference domain record to get its apex_typosquat_domain_id
                query = db.query(TyposquatDomain)
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                else:
                    query = query.outerjoin(Program)
                
                reference_domain = query.filter(TyposquatDomain.typo_domain == typo_domain).first()
                
                if not reference_domain:
                    logger.warning(f"Reference domain {typo_domain} not found")
                    return []
                
                # Check if the reference domain has apex_typosquat_domain_id populated (new schema)
                if reference_domain.apex_typosquat_domain_id:
                    logger.info(f"Using efficient apex_typosquat_domain_id query for {typo_domain}")
                    return await TyposquatFindingsRepository._get_related_domains_by_apex_id(
                        reference_domain.apex_typosquat_domain_id, program_name
                    )
                else:
                    logger.info(f"Falling back to legacy string matching for {typo_domain}")
                    return await TyposquatFindingsRepository._get_related_domains_by_string_matching(
                        typo_domain, program_name
                    )
                
        except Exception as e:
            logger.error(f"Error getting related typosquat domains for {typo_domain}: {str(e)}")
            return []

    @staticmethod
    async def _get_related_domains_by_apex_id(apex_id: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Efficient method using apex_typosquat_domain_id foreign key.
        """
        try:
            async with get_db_session() as db:
                query = db.query(TyposquatDomain)
                
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                else:
                    query = query.outerjoin(Program)
                
                # Simple indexed query using foreign key
                related_domains_query = (
                    query.options(joinedload(TyposquatDomain.typosquat_apex))
                    .filter(TyposquatDomain.apex_typosquat_domain_id == apex_id)
                    .order_by(TyposquatDomain.typo_domain)
                )
                
                results = related_domains_query.all()
                logger.info(f"Apex ID query returned {len(results)} related domains")
                
                return TyposquatFindingsRepository._convert_domains_to_dict_list(results)
                
        except Exception as e:
            logger.error(f"Error in apex ID query: {str(e)}")
            return []

    @staticmethod
    async def _get_related_domains_by_string_matching(typo_domain: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Legacy method using string matching (fallback for domains without apex_typosquat_domain_id).
        """
        try:
            base_domain = extract_apex_domain(typo_domain)
            logger.info(f"Using legacy string matching for base domain: {base_domain}")
            
            async with get_db_session() as db:
                query = db.query(TyposquatDomain).options(
                    joinedload(TyposquatDomain.typosquat_apex)
                )
                
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                else:
                    query = query.outerjoin(Program)
                
                # Get all domains and filter by base domain
                all_domains = query.all()
                logger.info(f"String matching query returned {len(all_domains)} total domains")
                
                related_domains = []
                for result in all_domains:
                    domain_base = extract_apex_domain(result.typo_domain)
                    if domain_base == base_domain:
                        related_domains.append(result)
                
                logger.info(f"Found {len(related_domains)} matching domains via string matching")
                return TyposquatFindingsRepository._convert_domains_to_dict_list(related_domains)
                
        except Exception as e:
            logger.error(f"Error in string matching query: {str(e)}")
            return []

    @staticmethod
    def _convert_domains_to_dict_list(domain_results) -> List[Dict[str, Any]]:
        """
        Convert SQLAlchemy domain results to dictionary list.
        """
        related_domains = []
        for result in domain_results:
            try:
                _w = TyposquatFindingsRepository._whois_public_fields_from_apex(result)
                domain_dict = {
                    "id": str(result.id),
                    "typo_domain": result.typo_domain,
                    "program_name": result.program.name if result.program else None,
                    "status": getattr(result, 'status', None),  # Handle missing status column
                    "risk_analysis_total_score": result.risk_analysis_total_score,
                    "dns_a_records": result.dns_a_records or [],
                    "geoip_country": result.geoip_country,
                    "whois_registrar": _w["whois_registrar"],
                    "whois_creation_date": _w["whois_creation_date"],
                    "domain_registered": result.domain_registered,
                    "is_wildcard": result.is_wildcard,
                    "created_at": result.created_at.isoformat() if result.created_at else None,
                    "updated_at": result.updated_at.isoformat() if result.updated_at else None,
                    "detected_at": result.detected_at.isoformat() if result.detected_at else None,  # Use detected_at instead of timestamp
                    "fuzzer_types": result.fuzzer_types or [],  # Use correct field name
                    "notes": result.notes,
                    "assigned_to": getattr(result, 'assigned_to', None),  # Handle missing assigned_to column
                    "apex_typosquat_domain_id": str(result.apex_typosquat_domain_id) if result.apex_typosquat_domain_id else None
                }
                related_domains.append(domain_dict)
            except Exception as e:
                logger.error(f"Error converting domain {getattr(result, 'typo_domain', 'unknown')} to dict: {str(e)}")
                continue
        
        return related_domains

    @staticmethod
    async def get_related_typosquat_urls(typo_domain: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all typosquat URLs for domains that share the same apex domain as the given domain.
        
        Args:
            typo_domain: The reference typo domain
            program_name: Optional program filter
            
        Returns:
            List of URL dictionaries with domain information
        """
        try:
            logger.info(f"Getting related URLs for {typo_domain}, program: {program_name}")
            
            async with get_db_session() as db:
                # First, find the reference domain to get its apex_typosquat_domain_id
                query = db.query(TyposquatDomain)
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                else:
                    query = query.outerjoin(Program)
                
                reference_domain = query.filter(TyposquatDomain.typo_domain == typo_domain).first()
                
                if not reference_domain:
                    logger.warning(f"Reference domain {typo_domain} not found")
                    return []
                
                # Check if the reference domain has apex_typosquat_domain_id populated
                if reference_domain.apex_typosquat_domain_id:
                    logger.info("Using efficient apex_typosquat_domain_id query for related URLs")
                    return await TyposquatFindingsRepository._get_related_urls_by_apex_id(
                        reference_domain.apex_typosquat_domain_id, program_name
                    )
                else:
                    logger.info("Falling back to legacy approach for related URLs")
                    # Fallback: get base domain and find related domains, then their URLs
                    base_domain = extract_apex_domain(typo_domain)
                    return await TyposquatFindingsRepository._get_related_urls_by_string_matching(
                        base_domain, program_name
                    )
                
        except Exception as e:
            logger.error(f"Error getting related typosquat URLs for {typo_domain}: {str(e)}")
            return []

    @staticmethod
    async def _get_related_urls_by_apex_id(apex_id: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Efficient method to get URLs for all domains sharing the same apex domain.
        """
        try:
            async with get_db_session() as db:
                # Build query to get URLs from all related domains
                from models.postgres import TyposquatURL
                
                # Start with TyposquatURL and join TyposquatDomain
                query = db.query(TyposquatURL, TyposquatDomain).join(
                    TyposquatDomain, TyposquatURL.typosquat_domain_id == TyposquatDomain.id
                )
                
                # Join Program table via TyposquatDomain.program_id
                if program_name:
                    query = query.join(Program, TyposquatDomain.program_id == Program.id).filter(Program.name == program_name)
                else:
                    query = query.outerjoin(Program, TyposquatDomain.program_id == Program.id)
                
                # Filter by apex domain ID
                query = query.filter(TyposquatDomain.apex_typosquat_domain_id == apex_id)
                query = query.order_by(TyposquatDomain.typo_domain, TyposquatURL.url)
                
                results = query.all()
                logger.info(f"Apex ID URL query returned {len(results)} URLs from related domains")
                
                return TyposquatFindingsRepository._convert_urls_to_dict_list(results)
                
        except Exception as e:
            logger.error(f"Error in apex ID URL query: {str(e)}")
            return []

    @staticmethod
    async def _get_related_urls_by_string_matching(base_domain: str, program_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Legacy method to get URLs for related domains using string matching.
        """
        try:
            async with get_db_session() as db:
                from models.postgres import TyposquatURL
                
                # Get all domains with the same base domain
                domain_query = db.query(TyposquatDomain)
                if program_name:
                    domain_query = domain_query.join(Program).filter(Program.name == program_name)
                else:
                    domain_query = domain_query.outerjoin(Program)
                
                all_domains = domain_query.all()
                
                # Filter by base domain
                related_domain_ids = []
                for domain in all_domains:
                    domain_base = extract_apex_domain(domain.typo_domain)
                    if domain_base == base_domain:
                        related_domain_ids.append(domain.id)
                
                if not related_domain_ids:
                    return []
                
                # Get URLs for these related domains
                url_query = db.query(TyposquatURL, TyposquatDomain).join(
                    TyposquatDomain, TyposquatURL.typosquat_domain_id == TyposquatDomain.id
                ).outerjoin(Program, TyposquatDomain.program_id == Program.id).filter(TyposquatDomain.id.in_(related_domain_ids))
                
                url_query = url_query.order_by(TyposquatDomain.typo_domain, TyposquatURL.url)
                
                results = url_query.all()
                logger.info(f"String matching URL query returned {len(results)} URLs from {len(related_domain_ids)} related domains")
                
                return TyposquatFindingsRepository._convert_urls_to_dict_list(results)
                
        except Exception as e:
            logger.error(f"Error in string matching URL query: {str(e)}")
            return []

    @staticmethod
    def _convert_urls_to_dict_list(url_results) -> List[Dict[str, Any]]:
        """
        Convert SQLAlchemy URL results with domain info to dictionary list.
        """
        related_urls = []
        for url_result, domain_result in url_results:
            try:
                url_dict = {
                    "id": str(url_result.id),
                    "url": url_result.url,
                    "hostname": url_result.hostname,
                    "port": url_result.port,
                    "path": url_result.path,
                    "scheme": url_result.scheme,
                    "http_status_code": url_result.http_status_code,
                    "http_method": url_result.http_method,
                    "response_time_ms": url_result.response_time_ms,
                    "content_type": url_result.content_type,
                    "content_length": url_result.content_length,
                    "line_count": url_result.line_count,
                    "word_count": url_result.word_count,
                    "title": url_result.title,
                    "final_url": url_result.final_url,
                    "technologies": url_result.technologies or [],
                    "response_body_hash": url_result.response_body_hash,
                    "body_preview": url_result.body_preview,
                    "favicon_hash": url_result.favicon_hash,
                    "favicon_url": url_result.favicon_url,
                    "redirect_chain": url_result.redirect_chain,
                    "chain_status_codes": url_result.chain_status_codes or [],
                    "extracted_links": [],  # TyposquatURL doesn't have extracted_links functionality
                    "notes": url_result.notes,
                    "created_at": url_result.created_at.isoformat() if url_result.created_at else None,
                    "updated_at": url_result.updated_at.isoformat() if url_result.updated_at else None,
                    # Domain information
                    "typo_domain": domain_result.typo_domain,
                    "domain_id": str(domain_result.id),
                    "program_name": domain_result.program.name if domain_result.program else None
                }
                related_urls.append(url_dict)
            except Exception as e:
                logger.error(f"Error converting URL {getattr(url_result, 'url', 'unknown')} to dict: {str(e)}")
                continue
        
        return related_urls

    @staticmethod
    async def delete_typosquat_domain(domain_id: str) -> bool:
        """Delete a typosquat domain"""
        async with get_db_session() as db:
            try:
                typosquat = db.query(TyposquatDomain).filter(TyposquatDomain.id == domain_id).first()
                if not typosquat:
                    return False

                # Log related records that will be cascade deleted
                urls_count = db.query(TyposquatURL).filter(
                    TyposquatURL.typosquat_domain_id == typosquat.id
                ).count()
                if urls_count > 0:
                    logger.info(f"Will cascade delete {urls_count} URLs for domain {typosquat.typo_domain}")

                # Delete the domain (related records will be cascade deleted by database)
                logger.info(f"Deleting typosquat domain: {typosquat.typo_domain} (ID: {typosquat.id})")
                db.delete(typosquat)
                db.commit()

                return True

            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting typosquat domain {domain_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_typosquat_findings_batch(finding_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple typosquat findings by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                found_domains = []
                not_found_ids = []

                logger.info(f"Starting batch delete for finding IDs: {finding_ids}")

                # First, collect all domains to be deleted and check for apex domain relationships
                domains_to_delete = []
                apex_domains = set()
                child_domains = []

                for finding_id in finding_ids:
                    logger.info(f"Looking for typosquat domain with ID: {finding_id}")
                    typosquat = (
                        db.query(TyposquatDomain)
                        .options(joinedload(TyposquatDomain.typosquat_apex))
                        .filter(TyposquatDomain.id == finding_id)
                        .first()
                    )
                    if typosquat:
                        domains_to_delete.append(typosquat)
                        found_domains.append(typosquat.typo_domain)

                        apex_row = typosquat.typosquat_apex
                        if apex_row and typosquat.typo_domain == apex_row.apex_domain:
                            apex_domains.add(typosquat.id)
                        else:
                            child_domains.append(typosquat)
                    else:
                        logger.warning(f"Typosquat domain with ID {finding_id} not found")
                        not_found_ids.append(finding_id)
                        db.query(TyposquatDomain).count()
                        if isinstance(finding_id, str):
                            try:
                                # Try to convert to UUID if it's a string
                                import uuid
                                uuid_obj = uuid.UUID(finding_id)
                                logger.info(f"Converted ID to UUID: {uuid_obj}")
                                
                                # Try querying with UUID
                                typosquat_uuid = db.query(TyposquatDomain).filter(TyposquatDomain.id == uuid_obj).first()
                                if typosquat_uuid:
                                    logger.info(f"Found domain with UUID query: {typosquat_uuid.typo_domain}")
                                else:
                                    logger.info("UUID query also returned no results")
                            except ValueError as e:
                                logger.warning(f"ID {finding_id} is not a valid UUID: {e}")
                        else:
                            logger.warning(f"ID {finding_id} is not a string, type: {type(finding_id)}")

                # Delete all domains - the database will handle cascade deletes automatically
                for domain in domains_to_delete:
                    logger.info(f"Deleting typosquat domain: {domain.typo_domain} (ID: {domain.id})")

                    # Log related records that will be cascade deleted
                    urls_count = db.query(TyposquatURL).filter(
                        TyposquatURL.typosquat_domain_id == domain.id
                    ).count()
                    if urls_count > 0:
                        logger.info(f"Will cascade delete {urls_count} URLs for domain {domain.typo_domain}")

                    # Delete the domain (related records will be cascade deleted by database)
                    db.delete(domain)
                    deleted_count += 1

                logger.info(f"About to commit deletion of {deleted_count} domains: {found_domains}")
                db.commit()
                logger.info(f"Successfully committed deletion of {deleted_count} domains")

                return {
                    "deleted_count": deleted_count,
                    "requested_count": len(finding_ids),
                    "failed_count": len(finding_ids) - deleted_count,
                    "deleted_domains": found_domains,
                    "not_found_ids": not_found_ids
                }

            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting typosquat findings: {str(e)}")
                raise

    @staticmethod
    async def apply_filter_retroactively(
        program_name: str,
        dry_run: bool = False,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Apply typosquat filtering rules retroactively to existing domains.
        Deletes domains that fail the filter. For RecordedFuture-sourced domains
        with non-resolved status, resolves the RF alert before deletion.
        """
        program = await ProgramRepository.get_program_by_name(program_name)
        if not program:
            return {
                "status": "error",
                "reason": "program_not_found",
                "message": f"Program '{program_name}' not found",
                "deleted": 0,
                "rf_resolved": 0,
                "skipped": 0,
                "errors": [],
                "dry_run": dry_run,
            }

        filtering_settings = program.get("typosquat_filtering_settings") or {}
        if not filtering_settings.get("enabled", False):
            return {
                "status": "skipped",
                "reason": "filtering_disabled",
                "message": "Typosquat filtering is disabled for this program",
                "deleted": 0,
                "rf_resolved": 0,
                "skipped": 0,
                "errors": [],
                "dry_run": dry_run,
            }

        protected_domains = program.get("protected_domains") or []
        protected_prefixes = program.get("protected_subdomain_prefixes") or []
        asset_apex_domains = await ApexDomainAssetsRepository.get_apex_domain_names_for_program(
            program_name
        )

        deleted = 0
        rf_resolved = 0
        skipped = 0
        errors: List[str] = []
        offset = 0

        while True:
            async with get_db_session() as db:
                query = (
                    db.query(TyposquatDomain)
                    .join(Program, TyposquatDomain.program_id == Program.id)
                    .filter(Program.name == program_name)
                    .order_by(TyposquatDomain.id)
                    .offset(offset)
                    .limit(batch_size)
                )
                domains = query.all()

            if not domains:
                break

            to_delete: List[tuple] = []
            for domain in domains:
                passes, reason = TyposquatFilteringService.should_insert_domain(
                    domain.typo_domain,
                    protected_domains,
                    protected_prefixes,
                    filtering_settings,
                    asset_apex_domains=asset_apex_domains,
                )
                if passes:
                    skipped += 1
                    continue

                source = (domain.source or "").lower()
                status = (domain.status or "").lower()
                rf_data = domain.recordedfuture_data or {}
                to_delete.append((str(domain.id), source, status, rf_data))

            for domain_id, source, status, rf_data in to_delete:
                try:
                    if source == "recordedfuture" and status not in ("resolved", "dismissed"):
                        alert_id = rf_data.get("alert_id")
                        if not alert_id:
                            raw_alert = rf_data.get("raw_alert", {})
                            alert_id = raw_alert.get("playbook_alert_id")

                        if alert_id and not dry_run:
                            try:
                                result = await change_playbook_alert_status(
                                    program_name=program_name,
                                    alert_id=alert_id,
                                    new_status="Resolved",
                                    log_entry="Auto-resolved: domain removed by retroactive filter",
                                )
                                if result.get("success"):
                                    rf_resolved += 1
                                else:
                                    logger.warning(
                                        f"Failed to resolve RF alert {alert_id}: {result.get('message')}"
                                    )
                            except Exception as rf_err:
                                logger.warning(f"RF resolution failed for alert {alert_id}: {rf_err}")
                        elif dry_run and alert_id:
                            rf_resolved += 1

                    if not dry_run:
                        deleted_ok = await TyposquatFindingsRepository.delete_typosquat_domain(domain_id)
                        if deleted_ok:
                            deleted += 1
                        else:
                            errors.append(f"Failed to delete domain {domain_id}")
                    else:
                        deleted += 1
                except Exception as e:
                    logger.error(f"Error processing domain {domain_id}: {e}")
                    errors.append(f"{domain_id}: {str(e)}")

            offset += batch_size

        return {
            "status": "success",
            "message": f"Retroactive filter applied: {deleted} deleted, {rf_resolved} RF resolved, {skipped} kept"
            + (" (dry run)" if dry_run else ""),
            "deleted": deleted,
            "rf_resolved": rf_resolved,
            "skipped": skipped,
            "errors": errors,
            "dry_run": dry_run,
        }

    # Risk score calculation methods
    @staticmethod
    async def calculate_single_typosquat_risk_score(domain_id: str) -> Dict[str, Any]:
        """Calculate risk score for a single typosquat domain"""
        async with get_db_session() as db:
            try:
                # Get the domain
                typosquat = (
                    db.query(TyposquatDomain)
                    .options(joinedload(TyposquatDomain.typosquat_apex))
                    .filter(TyposquatDomain.id == domain_id)
                    .first()
                )
                if not typosquat:
                    return {
                        'status': 'error',
                        'message': f'Domain not found: {domain_id}'
                    }
                
                # Get program configuration
                program_name = typosquat.program.name if typosquat.program else None
                domain_name = typosquat.typo_domain
                
                logger.info(f"Processing domain {domain_name} (program: {program_name})")
                
                # Get program configuration from assets
                program_config = None
                if program_name:
                    program = await ProgramRepository.get_program_by_name(program_name)
                    if program:
                        program_config = program
                        logger.info(f"Retrieved program config for {program_name}")
                
                # Calculate detailed risk analysis
                detailed_analysis = await TyposquatFindingsRepository._calculate_risk_score(typosquat, program_config)
                
                
                # Update the domain with new detailed risk analysis
                typosquat.risk_score = detailed_analysis['total_score']
                # Update the new risk analysis fields
                typosquat.risk_analysis_total_score = detailed_analysis['total_score']
                typosquat.risk_analysis_risk_level = detailed_analysis['risk_level']
                typosquat.risk_analysis_version = detailed_analysis['version']
                typosquat.risk_analysis_timestamp = detailed_analysis['analysis_timestamp']
                typosquat.risk_analysis_category_scores = detailed_analysis['category_scores']
                typosquat.risk_analysis_risk_factors = detailed_analysis['risk_factors']
                # Don't update info_data - keep it empty as requested
                typosquat.updated_at = datetime.utcnow()
                
                db.commit()
                
                # Update auto_resolve flag (domain may have been updated by similarity service; this handles timing)
                asyncio.create_task(TyposquatAutoResolveService.update_auto_resolve_for_domain(domain_id))
                
                return {
                    'status': 'success',
                    'domain': typosquat.typo_domain,
                    'risk_score': detailed_analysis['total_score'],
                    'detailed_analysis': detailed_analysis,
                    'program_name': program_name
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error calculating risk score for domain {domain_id}: {str(e)}")
                return {
                    'status': 'error',
                    'message': str(e)
                }
    
    @staticmethod
    async def calculate_typosquat_risk_scores(program_name: Optional[str] = None, finding_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Calculate risk scores for typosquat domains, optionally filtered by program or specific finding IDs"""
        async with get_db_session() as db:
            try:
                # Build query filter
                query = db.query(TyposquatDomain).options(
                    joinedload(TyposquatDomain.typosquat_apex)
                )
                
                if finding_ids:
                    # Calculate risk for specific finding IDs
                    query = query.filter(TyposquatDomain.id.in_(finding_ids))
                    logger.info(f"Processing {len(finding_ids)} specific typosquat domains for risk score calculation")
                elif program_name:
                    # Calculate risk for all domains in a program
                    query = query.join(Program).filter(Program.name == program_name)
                    logger.info(f"Processing all typosquat domains in program {program_name} for risk score calculation")
                else:
                    # Calculate risk for all domains
                    logger.info("Processing all typosquat domains for risk score calculation")
                
                domains = query.all()
                total_count = len(domains)
                updated_count = 0
                
                
                # Cache program configurations to avoid repeated database queries
                program_configs = {}
                
                for domain in domains:
                    try:
                        domain_name = domain.typo_domain
                        domain_program = domain.program.name if domain.program else None
                        
                        
                        # Get program configuration for THIS DOMAIN's program_name
                        program_config = None
                        if domain_program:
                            if domain_program not in program_configs:
                                program_configs[domain_program] = await ProgramRepository.get_program_by_name(domain_program)
                            program_config = program_configs[domain_program]
                            logger.info(f"Using program config for domain's program: {domain_program}")
                        else:
                            logger.warning(f"No program_name found for domain {domain_name}, using no config")
                        
                        # Calculate detailed risk analysis using the domain's own program configuration
                        detailed_analysis = await TyposquatFindingsRepository._calculate_risk_score(domain, program_config)
                        
                        # Update the domain with new detailed risk analysis (all fields)
                        domain.risk_score = detailed_analysis['total_score']
                        domain.risk_analysis_total_score = detailed_analysis['total_score']
                        domain.risk_analysis_risk_level = detailed_analysis['risk_level']
                        domain.risk_analysis_version = detailed_analysis['version']
                        domain.risk_analysis_timestamp = detailed_analysis['analysis_timestamp']
                        domain.risk_analysis_category_scores = detailed_analysis['category_scores']
                        domain.risk_analysis_risk_factors = detailed_analysis['risk_factors']
                        domain.updated_at = datetime.utcnow()
                        
                        updated_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error updating domain {domain.typo_domain}: {str(e)}")
                        continue
                
                db.commit()
                
                logger.info(f"Risk score recalculation complete: {updated_count}/{total_count} domains updated")
                
                return {
                    'status': 'success',
                    'total_domains': total_count,
                    'updated_count': updated_count,
                    'program_name': program_name
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in calculate_typosquat_risk_scores: {str(e)}")
                return {
                    'status': 'error',
                    'message': str(e),
                    'total_domains': 0,
                    'updated_count': 0
                }
    
    @staticmethod
    async def _get_typosquat_domain_http_and_ssl_data(typosquat_domain_id: str) -> Dict[str, Any]:
        """Fetch HTTP status codes and SSL issuer information from related typosquat_urls and typosquat_certificates"""
        async with get_db_session() as db:
            try:
                # Fetch all URLs for this typosquat domain
                urls = db.query(TyposquatURL).filter(
                    TyposquatURL.typosquat_domain_id == typosquat_domain_id
                ).all()
                
                # Extract HTTP status codes and certificate IDs
                http_status_codes = []
                certificate_ids = set()
                
                for url in urls:
                    if url.http_status_code:
                        http_status_codes.append(url.http_status_code)
                    if url.typosquat_certificate_id:
                        certificate_ids.add(str(url.typosquat_certificate_id))
                
                # Fetch SSL issuer information from certificates
                ssl_issuers = []
                has_ssl = False
                
                if certificate_ids:
                    certificates = db.query(TyposquatCertificate).filter(
                        TyposquatCertificate.id.in_(list(certificate_ids))
                    ).all()
                    
                    for cert in certificates:
                        if cert.issuer_organization:
                            ssl_issuers.extend(cert.issuer_organization)
                    
                    has_ssl = True
                
                return {
                    'http_status_codes': http_status_codes,
                    'ssl_issuers': list(set(ssl_issuers)),  # Remove duplicates
                    'has_ssl': has_ssl,
                    'url_count': len(urls)
                }
                
            except Exception as e:
                logger.error(f"Error fetching HTTP/SSL data for typosquat domain {typosquat_domain_id}: {str(e)}")
                return {
                    'http_status_codes': [],
                    'ssl_issuers': [],
                    'has_ssl': False,
                    'url_count': 0
                }

    @staticmethod
    async def _calculate_risk_score(typosquat_data, program_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Calculate detailed risk analysis for a typosquat domain based on various factors"""
        try:
            
            # Initialize detailed risk analysis structure
            detailed_analysis = {
                'total_score': 0,
                'risk_level': 'info',
                'version': '2.1',
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'category_scores': {
                    'similarity_factors': 0,
                    'registration_factors': 0,
                    'ssl_factors': 0,
                    'hosting_factors': 0,
                    'content_factors': 0,
                    'age_factors': 0,
                    'behavioral_factors': 0
                },
                'risk_factors': {}
            }
            
            total_score = 0
            
            # === SIMILARITY FACTORS ===
            similarity_score = 0
            similarity_indicators = []
            similarity_details = {}
            
            # Extract domain name and protected domain similarities
            typo_domain = typosquat_data.typo_domain
            protected_similarities = typosquat_data.protected_domain_similarities
            
            # Helper function for Levenshtein distance calculation
            def levenshtein_distance(s1, s2):
                if len(s1) < len(s2):
                    return levenshtein_distance(s2, s1)
                if len(s2) == 0:
                    return len(s1)
                previous_row = list(range(len(s2) + 1))
                for i, c1 in enumerate(s1):
                    current_row = [i + 1]
                    for j, c2 in enumerate(s2):
                        insertions = previous_row[j + 1] + 1
                        deletions = current_row[j] + 1
                        substitutions = previous_row[j] + (c1 != c2)
                        current_row.append(min(insertions, deletions, substitutions))
                    previous_row = current_row
                return previous_row[-1]
            
            # Parse protected_similarities if it's a string (JSONB can be returned as string)
            if protected_similarities and isinstance(protected_similarities, str):
                try:
                    protected_similarities = json.loads(protected_similarities)
                except (json.JSONDecodeError, TypeError):
                    protected_similarities = None
            
            if typo_domain and protected_similarities and len(protected_similarities) > 0:
                # Get the highest similarity score (list is pre-sorted by similarity_percent desc)
                best_match = protected_similarities[0]
                similarity_ratio = best_match['similarity_percent'] / 100.0
                protected_domain = best_match['protected_domain']
                
                similarity_details['typo_domain'] = typo_domain
                similarity_details['protected_domain'] = protected_domain
                similarity_details['similarity_percent'] = best_match['similarity_percent']
                similarity_details['similarity_ratio'] = round(similarity_ratio, 3)
                # Include top 3 similarities for context
                similarity_details['all_similarities'] = protected_similarities[:3]
                
                # Remove TLD for detailed comparison
                typo_base = tldextract.extract(typo_domain).domain if '.' in typo_domain else typo_domain
                protected_base = tldextract.extract(protected_domain).domain if '.' in protected_domain else protected_domain
                
                # Calculate edit distance for additional context
                edit_distance = levenshtein_distance(typo_base.lower(), protected_base.lower())
                similarity_details['edit_distance'] = edit_distance
                
                # Calculate length difference
                length_diff = abs(len(typo_base) - len(protected_base))
                similarity_details['length_difference'] = length_diff
                
                # Check for single character operations (only if similarity is high enough)
                if edit_distance == 1 and similarity_ratio >= 0.8:
                    similarity_score += 20  # High risk - single character change
                    similarity_indicators.append("single_character_change")
                elif edit_distance == 2 and similarity_ratio >= 0.7:
                    similarity_score += 15  # Medium-high risk - two character changes
                    similarity_indicators.append("two_character_changes")
                elif edit_distance <= 3 and similarity_ratio >= 0.6:
                    similarity_score += 10  # Medium risk - few character changes
                    similarity_indicators.append("few_character_changes")
                
                # High similarity percentage scoring (reduced scores)
                if similarity_ratio >= 0.95:
                    similarity_score += 15  # Very similar
                    similarity_indicators.append("very_high_similarity")
                elif similarity_ratio >= 0.85:
                    similarity_score += 12  # High similarity
                    similarity_indicators.append("high_similarity")
                elif similarity_ratio >= 0.75:
                    similarity_score += 8  # Medium similarity
                    similarity_indicators.append("medium_similarity")
                elif similarity_ratio >= 0.65:
                    similarity_score += 5  # Low similarity
                    similarity_indicators.append("low_similarity")
                
                # Length-based scoring (only for very similar domains)
                if length_diff == 0 and similarity_ratio >= 0.8:
                    similarity_score += 8  # Same length - substitution attack
                    similarity_indicators.append("same_length_substitution")
                elif length_diff == 1 and similarity_ratio >= 0.7:
                    similarity_score += 5  # One character difference
                    similarity_indicators.append("one_character_length_diff")
                
                # Check for common character substitutions
                common_substitutions = {
                    'a': ['@', '4'], 'e': ['3'], 'i': ['1', '!'], 'o': ['0'], 
                    's': ['$', '5'], 't': ['7'], 'l': ['1'], 'g': ['9']
                }
                
                substitution_found = False
                for orig_char, substitutes in common_substitutions.items():
                    if orig_char in protected_base.lower():
                        for sub_char in substitutes:
                            if sub_char in typo_base.lower():
                                similarity_score += 8
                                similarity_indicators.append("common_character_substitution")
                                similarity_details['substitution_detected'] = f"{orig_char} -> {sub_char}"
                                substitution_found = True
                                break
                        if substitution_found:
                            break
                
                # Check for keyboard layout proximity
                keyboard_layout = [
                    'qwertyuiop',
                    'asdfghjkl',
                    'zxcvbnm'
                ]
                
                def get_key_neighbors(char):
                    neighbors = []
                    for row in keyboard_layout:
                        if char in row:
                            idx = row.index(char)
                            if idx > 0:
                                neighbors.append(row[idx-1])
                            if idx < len(row) - 1:
                                neighbors.append(row[idx+1])
                    return neighbors
                
                for i, (c1, c2) in enumerate(zip(protected_base.lower(), typo_base.lower())):
                    if c1 != c2 and c2 in get_key_neighbors(c1):
                        similarity_score += 10
                        similarity_indicators.append("keyboard_layout_typo")
                        similarity_details['keyboard_typo_detected'] = f"{c1} -> {c2}"
                        break
                
                # Domain confusion potential (only for very high similarity)
                if similarity_ratio >= 0.90:
                    similarity_score += 12
                    similarity_indicators.append("high_confusion_potential")
                
                logger.info(f"Similarity analysis: {typo_domain} vs {protected_domain} (protected domain)")
                logger.info(f"Edit distance: {edit_distance}, Similarity ratio: {similarity_ratio:.3f}")
                logger.info(f"Similarity score: {similarity_score}")
            
            if similarity_score > 0:
                detailed_analysis['risk_factors']['similarity_factors'] = {
                    'score': similarity_score,
                    'indicators': similarity_indicators,
                    'details': similarity_details
                }
                detailed_analysis['category_scores']['similarity_factors'] = similarity_score
                total_score += similarity_score
            
            # === REGISTRATION FACTORS ===
            registration_score = 0
            registration_indicators = []
            registration_details = {}
            
            # Domain registration check - use new normalized fields
            domain_registered = typosquat_data.domain_registered
            
            if domain_registered:
                registration_score += 15
                registration_indicators.append("domain_is_registered")
                registration_details['domain_registered'] = True
                logger.debug("Domain is registered: +15 points")
            else:
                registration_details['domain_registered'] = False
            
            apex_row = getattr(typosquat_data, "typosquat_apex", None)
            registrar = apex_row.whois_registrar if apex_row else None

            registration_details['registrar'] = registrar
            logger.debug(f"Registrar extracted: {registrar}")
            
            if registrar:
                # Only add points if registrar is not in safe list
                if program_config and 'safe_registrar' in program_config:
                    logger.debug(f"Program safe registrars: {program_config.get('safe_registrar')}")

                    if registrar not in program_config.get('safe_registrar', []):
                        registration_score += 12
                        registration_indicators.append("unsafe_registrar")
                        registration_details['registrar_safe'] = False
                        logger.debug("Registrar not in safe list: +12 points")
                    else:
                        registration_details['registrar_safe'] = True
                        logger.debug("Registrar is in safe list: no penalty")
                else:
                    # If no safe list configured, having a registrar is normal, add minimal points
                    registration_score += 5
                    registration_indicators.append("has_registrar_no_config")
                    registration_details['registrar_safe'] = None
                    logger.debug("Has registrar (no safe list): +5 points")
            
            if registration_score > 0:
                detailed_analysis['risk_factors']['registration_factors'] = {
                    'score': registration_score,
                    'indicators': registration_indicators,
                    'details': registration_details
                }
                detailed_analysis['category_scores']['registration_factors'] = registration_score
                total_score += registration_score
            
            # === AGE FACTORS ===
            age_score = 0
            age_indicators = []
            age_details = {}
            
            creation_date = apex_row.whois_creation_date if apex_row else None

            if creation_date:
                try:
                    if isinstance(creation_date, str):
                        created = datetime.fromisoformat(creation_date.replace('Z', '+00:00'))
                    else:
                        created = creation_date
                    
                    age_days = (datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc)).days
                    age_details['age_days'] = age_days
                    age_details['creation_date'] = created.isoformat()
                    
                    if age_days < 30:
                        age_score += 12
                        age_indicators.append("very_recently_registered")
                        logger.debug(f"Recently registered ({age_days} days): +12 points")
                    elif age_days < 90:
                        age_score += 8
                        age_indicators.append("recently_registered")
                        logger.debug(f"Recently registered ({age_days} days): +8 points")
                except Exception as e:
                    logger.debug(f"Error parsing creation date: {e}")
                    age_details['parsing_error'] = str(e)
            
            if age_score > 0:
                detailed_analysis['risk_factors']['age_factors'] = {
                    'score': age_score,
                    'indicators': age_indicators,
                    'details': age_details
                }
                detailed_analysis['category_scores']['age_factors'] = age_score
                total_score += age_score
            
            # === SSL FACTORS ===
            ssl_score = 0
            ssl_indicators = []
            ssl_details = {}
            
            # SSL certificate check - fetch from related typosquat_urls and typosquat_certificates
            http_ssl_data = await TyposquatFindingsRepository._get_typosquat_domain_http_and_ssl_data(str(typosquat_data.id))
            has_ssl = http_ssl_data['has_ssl']
            ssl_issuers = http_ssl_data['ssl_issuers']
            
            ssl_details['has_ssl'] = has_ssl
            ssl_details['ssl_issuers'] = ssl_issuers
            ssl_details['url_count'] = http_ssl_data['url_count']
            logger.debug(f"SSL issuers extracted: {ssl_issuers}")
            
            if has_ssl:
                # Only add points if SSL issuer is not in safe list
                if program_config and 'safe_ssl_issuer' in program_config:
                    logger.debug(f"Program safe SSL issuers: {program_config.get('safe_ssl_issuer')}")
                    
                    # Check if any of the SSL issuers are not in the safe list
                    unsafe_issuers = [issuer for issuer in ssl_issuers if issuer not in program_config.get('safe_ssl_issuer', [])]
                    if unsafe_issuers:
                        ssl_score += 10
                        ssl_indicators.append("unsafe_ssl_issuer")
                        ssl_details['ssl_issuer_safe'] = False
                        ssl_details['unsafe_issuers'] = unsafe_issuers
                        logger.debug(f"Unsafe SSL issuers found: {unsafe_issuers} (+10 points)")
                    else:
                        ssl_details['ssl_issuer_safe'] = True
                        logger.debug("All SSL issuers are in safe list: no penalty")
                else:
                    # If no safe list configured, having SSL is mildly suspicious for typosquat
                    ssl_score += 5
                    ssl_indicators.append("has_ssl_no_config")
                    ssl_details['ssl_issuer_safe'] = None
                    logger.debug("Has SSL certificate (no safe list): +5 points")
            else:
                ssl_details['has_ssl'] = False
            
            if ssl_score > 0:
                detailed_analysis['risk_factors']['ssl_factors'] = {
                    'score': ssl_score,
                    'indicators': ssl_indicators,
                    'details': ssl_details
                }
                detailed_analysis['category_scores']['ssl_factors'] = ssl_score
                total_score += ssl_score
            
            # === HOSTING FACTORS ===
            hosting_score = 0
            hosting_indicators = []
            hosting_details = {}
            
            # IP address check - use new normalized fields
            dns_a_records = typosquat_data.dns_a_records
            
            has_ip = bool(dns_a_records and len(dns_a_records) > 0)
            hosting_details['has_ip'] = has_ip
            hosting_details['ip_address'] = dns_a_records[0] if dns_a_records else None
            
            # DNS records check
            has_dns = has_ip  # If we have IP, we have DNS
            hosting_details['has_dns'] = has_dns
            
            # HTTP response check - fetch from related typosquat_urls
            http_status_codes = http_ssl_data['http_status_codes']
            hosting_details['http_status_codes'] = http_status_codes
            
            # Check for HTTP 200 responses (most suspicious for typosquat)
            if 200 in http_status_codes:
                hosting_score += 10
                hosting_indicators.append("http_200_response")
                logger.debug("HTTP 200 response found: +10 points")
            elif http_status_codes:
                hosting_score += 3
                hosting_indicators.append("http_response")
                logger.debug(f"HTTP responses found: {http_status_codes} (+3 points)")
            
            # Combined IP + DNS + HTTP check - active hosting
            if has_ip and has_dns and http_status_codes:
                hosting_score += 8
                hosting_indicators.append("active_hosting")
                hosting_details['active_hosting'] = True
                logger.debug("Active domain (IP + DNS + HTTP): +8 points")
            else:
                hosting_details['active_hosting'] = False
            
            # Country check - penalize certain high-risk countries - use new normalized fields
            country = typosquat_data.geoip_country
            
            hosting_details['country'] = country
            
            if country:
                high_risk_countries = ['CN', 'RU', 'TR', 'BD', 'PK', 'IN', 'ID', 'VN', 'IR', 'IQ']
                if country in high_risk_countries:
                    hosting_score += 8
                    hosting_indicators.append("high_risk_country")
                    hosting_details['high_risk_country'] = True
                    logger.debug(f"High-risk country ({country}): +8 points")
                else:
                    hosting_details['high_risk_country'] = False
            
            if hosting_score > 0:
                detailed_analysis['risk_factors']['hosting_factors'] = {
                    'score': hosting_score,
                    'indicators': hosting_indicators,
                    'details': hosting_details
                }
                detailed_analysis['category_scores']['hosting_factors'] = hosting_score
                total_score += hosting_score
            
            # === CONTENT FACTORS ===
            content_score = 0
            content_indicators = []
            content_details = {}
            
            # Check for parking page content - fetch from related typosquat_urls
            # Get titles from all related URLs
            
            if http_ssl_data['url_count'] > 0:
                # We already have the URLs from the helper method, but we need to fetch titles
                # For now, we'll note that we have URLs but can't access titles without another query
                # This could be optimized by modifying the helper method to include titles
                content_details['has_http_content'] = True
                content_details['url_count'] = http_ssl_data['url_count']
                content_details['note'] = "Titles available in related typosquat_urls table"
                
                # For now, we'll give a baseline score for having HTTP content
                content_score += 3
                content_indicators.append("has_http_content")
                logger.debug(f"Found {http_ssl_data['url_count']} URLs with potential content (+3 points)")
            else:
                content_details['has_http_content'] = False
                content_details['url_count'] = 0
            
            if content_score > 0:
                detailed_analysis['risk_factors']['content_factors'] = {
                    'score': content_score,
                    'indicators': content_indicators,
                    'details': content_details
                }
                detailed_analysis['category_scores']['content_factors'] = content_score
                total_score += content_score
            
            # Cap total score at 100
            total_score = min(total_score, 100)
            
            # Determine risk level
            if total_score >= 80:
                risk_level = 'critical'
            elif total_score >= 60:
                risk_level = 'high'
            elif total_score >= 40:
                risk_level = 'medium'
            elif total_score >= 20:
                risk_level = 'low'
            else:
                risk_level = 'info'
            
            detailed_analysis['total_score'] = total_score
            detailed_analysis['risk_level'] = risk_level
            
            return detailed_analysis
            
        except Exception as e:
            logger.error(f"Error calculating risk score: {str(e)}")
            return {
                'total_score': 0,
                'risk_level': 'info',
                'version': '2.1',
                'analysis_timestamp': datetime.now(timezone.utc).isoformat(),
                'category_scores': {},
                'risk_factors': {},
                'error': str(e)
            } 

    # ===== TYPOSQUAT URL AND SCREENSHOT METHODS =====

    @staticmethod
    async def create_or_update_typosquat_url(url_data: Dict[str, Any]) -> tuple[Optional[str], bool, Optional[str]]:
        """Create a new typosquat URL or update if exists with merged data.
        Returns (url_id, was_created, typosquat_domain_id) where was_created is True only for newly created assets."""
        async with get_db_session() as db:
            try:
               
                # TyposquatURL is already imported at the top
                normalized_url = normalize_url_for_storage(url_data.get('url'))
                # Find program by name
                program = db.query(Program).filter(Program.name == url_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{url_data.get('program_name')}' not found")

                asset_apex_domains = await ApexDomainAssetsRepository.get_apex_domain_names_for_program(
                    program.name
                )

                # Find the typosquat domain to associate with this URL
                typosquat_domain = None
                if url_data.get('typosquat_domain'):
                    # If typosquat_domain is provided, find it by the domain name
                    typosquat_domain = db.query(TyposquatDomain).filter(
                        TyposquatDomain.typo_domain == url_data.get('typosquat_domain')
                    ).first()
                    if not typosquat_domain:
                        # Check filtering before auto-creating the domain
                        typo_domain_name = url_data.get('typosquat_domain')
                        protected_domains = getattr(program, 'protected_domains', None) or []
                        protected_prefixes = getattr(program, 'protected_subdomain_prefixes', None) or []
                        filtering_settings = getattr(program, 'typosquat_filtering_settings', None) or {}

                        passes_filter, filter_reason = TyposquatFilteringService.should_insert_domain(
                            typo_domain_name, protected_domains, protected_prefixes, filtering_settings,
                            asset_apex_domains=asset_apex_domains,
                        )
                        if not passes_filter:
                            logger.info(f"Typosquat URL rejected: domain '{typo_domain_name}' filtered out ({filter_reason}), skipping URL {url_data.get('url')}")
                            return None, False, None

                        logger.info(f"Auto-creating typosquat domain '{typo_domain_name}' for URL {url_data.get('url')}")

                        apex_domain_name = extract_apex_domain(typo_domain_name)
                        apex_row = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                            db, apex_domain_name, program.id, None
                        )

                        typosquat_domain = TyposquatDomain(
                            id=uuid.uuid4(),
                            typo_domain=typo_domain_name,
                            program_id=program.id,
                            detected_at=datetime.utcnow(),
                            status='new',
                            apex_typosquat_domain_id=apex_row.id,
                            notes=f"Auto-created from typosquat URL: {url_data.get('url')}"
                        )
                        db.add(typosquat_domain)
                        db.flush()
                        logger.info(f"Successfully created typosquat domain with ID: {typosquat_domain.id}")
                elif url_data.get('typosquat_domain_id'):
                    # If typosquat_domain_id is provided, find it by ID
                    typosquat_domain = db.query(TyposquatDomain).filter(
                        TyposquatDomain.id == url_data.get('typosquat_domain_id')
                    ).first()
                    if not typosquat_domain:
                        raise ValueError(f"Typosquat domain with ID '{url_data.get('typosquat_domain_id')}' not found")
                else:
                    # Try to find by hostname if no domain specified
                    hostname = url_data.get('hostname')
                    if hostname:
                        typosquat_domain = db.query(TyposquatDomain).filter(
                            TyposquatDomain.typo_domain == hostname
                        ).first()
                        if not typosquat_domain:
                            # Check filtering before auto-creating the domain
                            protected_domains = getattr(program, 'protected_domains', None) or []
                            protected_prefixes = getattr(program, 'protected_subdomain_prefixes', None) or []
                            filtering_settings = getattr(program, 'typosquat_filtering_settings', None) or {}

                            passes_filter, filter_reason = TyposquatFilteringService.should_insert_domain(
                                hostname, protected_domains, protected_prefixes, filtering_settings,
                                asset_apex_domains=asset_apex_domains,
                            )
                            if not passes_filter:
                                logger.info(f"Typosquat URL rejected: domain '{hostname}' filtered out ({filter_reason}), skipping URL {url_data.get('url')}")
                                return None, False, None

                            logger.info(f"Auto-creating typosquat domain '{hostname}' for URL {url_data.get('url')}")

                            apex_domain_name = extract_apex_domain(hostname)
                            apex_row = TyposquatFindingsRepository.find_or_create_typosquat_apex_in_session(
                                db, apex_domain_name, program.id, None
                            )

                            typosquat_domain = TyposquatDomain(
                                id=uuid.uuid4(),
                                typo_domain=hostname,
                                program_id=program.id,
                                detected_at=datetime.utcnow(),
                                status='new',
                                apex_typosquat_domain_id=apex_row.id,
                                notes=f"Auto-created from typosquat URL: {url_data.get('url')}"
                            )
                            db.add(typosquat_domain)
                            db.flush()
                            logger.info(f"Successfully created typosquat domain with ID: {typosquat_domain.id}")
                
                # Handle SSL certificate creation if SSL data is present
                typosquat_certificate_id = None
                # Check for SSL data in the url_data directly, TLS field, or in the info field (worker output format)
                ssl_data = None
                if url_data.get('tls') and isinstance(url_data.get('tls'), dict):
                    # Use TLS data from httpx output (preferred)
                    ssl_data = url_data.get('tls')
                    logger.debug(f"Using TLS data from httpx for certificate creation: {ssl_data.get('subject_cn', 'unknown')}")
                elif url_data.get('ssl') and isinstance(url_data.get('ssl'), dict):
                    ssl_data = url_data.get('ssl')
                elif url_data.get('info') and isinstance(url_data.get('info'), dict) and url_data.get('info', {}).get('ssl'):
                    ssl_data = url_data.get('info', {}).get('ssl')
                
                if ssl_data and isinstance(ssl_data, dict):
                    try:
                        # Check if this is TLS data from httpx (new format) or old SSL data
                        is_httpx_tls = 'tls_version' in ssl_data or 'probe_status' in ssl_data
                        
                        if is_httpx_tls:
                            # Handle httpx TLS data format
                            if ssl_data.get('probe_status') and ssl_data.get('subject_cn') and ssl_data.get('issuer_cn'):
                                # Parse dates from httpx TLS format
                                valid_from = None
                                valid_until = None
                                
                                if ssl_data.get('not_before'):
                                    try:
                                        # httpx uses ISO format like "2025-07-05T09:30:41Z"
                                        valid_from = datetime.fromisoformat(ssl_data.get('not_before').replace('Z', '+00:00'))
                                    except:
                                        logger.warning(f"Could not parse httpx not_before date: {ssl_data.get('not_before')}")
                                
                                if ssl_data.get('not_after'):
                                    try:
                                        # httpx uses ISO format like "2025-10-03T09:30:40Z"
                                        valid_until = datetime.fromisoformat(ssl_data.get('not_after').replace('Z', '+00:00'))
                                    except:
                                        logger.warning(f"Could not parse httpx not_after date: {ssl_data.get('not_after')}")
                                
                                # Extract certificate information from httpx TLS data
                                certificate_data = {
                                    'subject_dn': ssl_data.get('subject_dn', ''),
                                    'subject_cn': ssl_data.get('subject_cn', ''),
                                    'subject_alternative_names': ssl_data.get('subject_an', []),
                                    'valid_from': valid_from,
                                    'valid_until': valid_until,
                                    'issuer_dn': ssl_data.get('issuer_dn', ''),
                                    'issuer_cn': ssl_data.get('issuer_cn', ''),
                                    'issuer_organization': ssl_data.get('issuer_organization', []),
                                    'serial_number': ssl_data.get('serial', ''),
                                    'fingerprint_hash': ssl_data.get('fingerprint_hash', {}).get('sha256', ''),
                                    'program_name': url_data.get('program_name'),
                                    'notes': f"Auto-generated from typosquat URL httpx TLS data: {url_data.get('url')}"
                                }
                            else:
                                logger.warning(f"Incomplete httpx TLS data for URL {url_data.get('url')}: missing required fields")
                                ssl_data = None
                        else:
                            # Handle old SSL data format
                            if ssl_data.get('has_ssl') and ssl_data.get('issuer') and ssl_data.get('subject'):
                                # Parse dates from the old worker output format
                                valid_from = None
                                valid_until = None
                                
                                if ssl_data.get('valid_from'):
                                    try:
                                        # Handle format like "Jul  5 09:30:41 2025 GMT"
                                        if parser:
                                            valid_from = parser.parse(ssl_data.get('valid_from'))
                                        else:
                                            # Fallback to basic parsing if dateutil is not available
                                            valid_from = datetime.fromisoformat(ssl_data.get('valid_from').replace('Z', '+00:00'))
                                    except:
                                        try:
                                            valid_from = datetime.fromisoformat(ssl_data.get('valid_from').replace('Z', '+00:00'))
                                        except:
                                            logger.warning(f"Could not parse valid_from date: {ssl_data.get('valid_from')}")
                                
                                if ssl_data.get('valid_to'):
                                    try:
                                        # Handle format like "Oct  3 09:30:40 2025 GMT"
                                        if parser:
                                            valid_until = parser.parse(ssl_data.get('valid_to'))
                                        else:
                                            # Fallback to basic parsing if dateutil is not available
                                            valid_until = datetime.fromisoformat(ssl_data.get('valid_to').replace('Z', '+00:00'))
                                    except:
                                        try:
                                            valid_until = datetime.fromisoformat(ssl_data.get('valid_to').replace('Z', '+00:00'))
                                        except:
                                            logger.warning(f"Could not parse valid_to date: {ssl_data.get('valid_to')}")
                                
                                # Extract certificate information from old SSL data
                                certificate_data = {
                                    'subject_dn': f"CN={ssl_data.get('subject', {}).get('commonName', '')}",
                                    'subject_cn': ssl_data.get('subject', {}).get('commonName', ''),
                                    'subject_alternative_names': [],
                                    'valid_from': valid_from,
                                    'valid_until': valid_until,
                                    'issuer_dn': f"CN={ssl_data.get('issuer', {}).get('commonName', '')}, O={ssl_data.get('issuer', {}).get('organizationName', '')}, C={ssl_data.get('issuer', {}).get('countryName', '')}",
                                    'issuer_cn': ssl_data.get('issuer', {}).get('commonName', ''),
                                    'issuer_organization': [ssl_data.get('issuer', {}).get('organizationName', '')] if ssl_data.get('issuer', {}).get('organizationName') else [],
                                    'serial_number': f"typosquat_{url_data.get('hostname', '')}_{ssl_data.get('valid_from', '')}_{ssl_data.get('valid_to', '')}",
                                    'fingerprint_hash': f"typosquat_{url_data.get('hostname', '')}_{ssl_data.get('valid_from', '')}",
                                    'program_name': url_data.get('program_name'),
                                    'notes': f"Auto-generated from typosquat URL: {url_data.get('url')}"
                                }
                            else:
                                logger.warning(f"Incomplete old SSL data for URL {url_data.get('url')}: missing required fields")
                                ssl_data = None
                        
                        # Only create certificate if we have valid dates
                        if valid_from and valid_until:
                            # Create or update the certificate
                            typosquat_certificate_id = await TyposquatFindingsRepository.create_or_update_typosquat_certificate(certificate_data)
                            
                    except Exception as cert_error:
                        logger.warning(f"Failed to create typosquat certificate for URL {url_data.get('url')}: {str(cert_error)}")
                        # Continue without certificate - don't fail the URL creation
                        pass
                
                # Check if URL already exists
                existing = db.query(TyposquatURL).filter(TyposquatURL.url == normalized_url).first()
                
                if existing:
                    # Check if data is different and update if needed
                    updated = False
                    
                    # Update typosquat_domain_id if provided and different
                    if typosquat_domain and existing.typosquat_domain_id != typosquat_domain.id:
                        existing.typosquat_domain_id = typosquat_domain.id
                        updated = True
                    
                    # Update HTTP status code if provided and different
                    if url_data.get('http_status_code') is not None and url_data.get('http_status_code') != existing.http_status_code:
                        existing.http_status_code = url_data.get('http_status_code')
                        updated = True
                    
                    # Update HTTP method if provided and different
                    if url_data.get('http_method') and url_data.get('http_method') != existing.http_method:
                        existing.http_method = url_data.get('http_method')
                        updated = True
                    
                    # Update response time if provided and different
                    if url_data.get('response_time_ms') is not None and url_data.get('response_time_ms') != existing.response_time_ms:
                        existing.response_time_ms = url_data.get('response_time_ms')
                        updated = True
                    
                    # Update content type if provided and different
                    if url_data.get('content_type') and url_data.get('content_type') != existing.content_type:
                        existing.content_type = url_data.get('content_type')
                        updated = True
                    
                    # Update content length if provided and different
                    if url_data.get('content_length') is not None and url_data.get('content_length') != existing.content_length:
                        existing.content_length = url_data.get('content_length')
                        updated = True
                    
                    # Update line count if provided and different
                    if url_data.get('line_count') is not None and url_data.get('line_count') != existing.line_count:
                        existing.line_count = url_data.get('line_count')
                        updated = True
                    
                    # Update word count if provided and different
                    if url_data.get('word_count') is not None and url_data.get('word_count') != existing.word_count:
                        existing.word_count = url_data.get('word_count')
                        updated = True
                    
                    # Update title if provided and different
                    if url_data.get('title') and url_data.get('title') != existing.title:
                        existing.title = url_data.get('title')
                        updated = True
                    
                    # Update final URL if provided and different
                    if url_data.get('final_url') is not None and url_data.get('final_url') != existing.final_url:
                        existing.final_url = url_data.get('final_url')
                        updated = True
                    
                    # Update technologies if provided and different
                    if url_data.get('technologies') and url_data.get('technologies') != existing.technologies:
                        existing.technologies = url_data.get('technologies')
                        updated = True
                    
                    # Update response body hash if provided and different
                    if url_data.get('response_body_hash') and url_data.get('response_body_hash') != existing.response_body_hash:
                        existing.response_body_hash = url_data.get('response_body_hash')
                        updated = True
                    
                    # Update body preview if provided and different
                    if url_data.get('body_preview') and url_data.get('body_preview') != existing.body_preview:
                        existing.body_preview = url_data.get('body_preview')
                        updated = True
                    
                    # Update favicon hash if provided and different
                    if url_data.get('favicon_hash') and url_data.get('favicon_hash') != existing.favicon_hash:
                        existing.favicon_hash = url_data.get('favicon_hash')
                        updated = True
                    
                    # Update favicon URL if provided and different
                    if url_data.get('favicon_url') and url_data.get('favicon_url') != existing.favicon_url:
                        existing.favicon_url = url_data.get('favicon_url')
                        updated = True
                    
                    # Update redirect chain if provided and different
                    if url_data.get('redirect_chain') is not None and url_data.get('redirect_chain') != existing.redirect_chain:
                        existing.redirect_chain = url_data.get('redirect_chain')
                        updated = True
                    
                    # Update chain status codes if provided and different
                    if url_data.get('chain_status_codes') and url_data.get('chain_status_codes') != existing.chain_status_codes:
                        existing.chain_status_codes = url_data.get('chain_status_codes')
                        updated = True
                    
                    # Note: extracted links are now handled through the separate extracted_links table
                    # and should be updated via UrlAssetsRepository methods
                    
                    # Update notes if provided and different
                    if url_data.get('notes') and url_data.get('notes') != existing.notes:
                        existing.notes = url_data.get('notes')
                        updated = True
                    
                    # Update typosquat_certificate_id if we created/updated a certificate
                    if typosquat_certificate_id and existing.typosquat_certificate_id != typosquat_certificate_id:
                        existing.typosquat_certificate_id = typosquat_certificate_id
                        updated = True
                    
                    # Update timestamp if any changes were made
                    if updated:
                        existing.updated_at = datetime.utcnow()
                        logger.debug(f"Updated existing typosquat URL {url_data.get('url')}")
                    else:
                        logger.info(f"Typosquat URL {url_data.get('url')} already exists with same data, skipping")
                    
                    db.commit()
                    return str(existing.id), False, str(existing.typosquat_domain_id) if existing.typosquat_domain_id else None  # Existing asset, not newly created
                else:
                    # Create new typosquat URL
                    url = TyposquatURL(
                        url=normalized_url,
                        hostname=url_data.get('hostname'),
                        port=url_data.get('port'),
                        path=url_data.get('path'),
                        scheme=url_data.get('scheme'),
                        http_status_code=url_data.get('http_status_code'),  # Fixed: was 'status_code'
                        http_method=url_data.get('http_method', 'GET'),  # Fixed: was 'method'
                        response_time_ms=url_data.get('response_time_ms'),  # Fixed: was 'response_time'
                        content_type=url_data.get('content_type'),
                        content_length=url_data.get('content_length'),
                        line_count=url_data.get('line_count'),  # Fixed: was 'lines'
                        word_count=url_data.get('word_count'),  # Fixed: was 'words'
                        title=url_data.get('title'),
                        final_url=url_data.get('final_url'),
                        technologies=url_data.get('technologies', []),
                        response_body_hash=url_data.get('response_body_hash'),  # Fixed: was 'resp_body_hash'
                        body_preview=url_data.get('body_preview'),
                        favicon_hash=url_data.get('favicon_hash'),
                        favicon_url=url_data.get('favicon_url'),
                        redirect_chain=url_data.get('redirect_chain'),
                        chain_status_codes=url_data.get('chain_status_codes', []),
                        typosquat_certificate_id=typosquat_certificate_id,
                        program_id=program.id,
                        typosquat_domain_id=typosquat_domain.id if typosquat_domain else None,
                        notes=url_data.get('notes')
                    )
                    
                    db.add(url)
                    db.commit()
                    db.refresh(url)
                    
                    return str(url.id), True, str(url.typosquat_domain_id) if url.typosquat_domain_id else None  # Newly created asset
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating typosquat URL: {str(e)}")
                raise

    @staticmethod
    async def store_typosquat_screenshot(image_data: bytes, filename: str, content_type: str, program_name: Optional[str] = None, url: Optional[str] = None, workflow_id: Optional[str] = None, step_name: Optional[str] = None, extracted_text: Optional[str] = None, source_created_at: Optional[str] = None, source: Optional[str] = None) -> str:
        """Store typosquat screenshot"""
        async with get_db_session() as db:
            try:
                # Validate required parameters
                if not url or not url.strip():
                    raise ValueError("URL is required for screenshot storage")
                
                if not program_name or not program_name.strip():
                    raise ValueError("Program name is required for screenshot storage")
                
                # These models are already imported at the top
                url = normalize_url_for_storage(url)
                import hashlib
                image_hash = hashlib.sha256(image_data).hexdigest()

                # Parse source_created_at from ISO 8601 string if provided
                parsed_source_created_at = None
                if source_created_at and source_created_at.strip():
                    try:
                        dt = datetime.fromisoformat(source_created_at.replace("Z", "+00:00"))
                        # Convert to naive UTC for timestamp without time zone storage
                        if dt.tzinfo:
                            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                        parsed_source_created_at = dt
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse source_created_at: {source_created_at}")
                
                # Find or create typosquat URL record first
                url_record = None
                if url:
                    url_record = db.query(TyposquatURL).filter(TyposquatURL.url == url).first()
                    if not url_record:
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        hostname = parsed.hostname or ""

                        # Find program by name
                        program = db.query(Program).filter(Program.name == program_name).first() if program_name else None

                        # Check if the domain exists; if not, check filtering before auto-creating
                        if hostname and program:
                            existing_domain = db.query(TyposquatDomain).filter(
                                TyposquatDomain.typo_domain == hostname
                            ).first()
                            if not existing_domain:
                                protected_domains = getattr(program, 'protected_domains', None) or []
                                protected_prefixes = getattr(program, 'protected_subdomain_prefixes', None) or []
                                filtering_settings = getattr(program, 'typosquat_filtering_settings', None) or {}
                                asset_apex_domains = await ApexDomainAssetsRepository.get_apex_domain_names_for_program(
                                    program_name
                                )

                                passes_filter, filter_reason = TyposquatFilteringService.should_insert_domain(
                                    hostname, protected_domains, protected_prefixes, filtering_settings,
                                    asset_apex_domains=asset_apex_domains,
                                )
                                if not passes_filter:
                                    raise ValueError(
                                        f"Screenshot rejected: domain '{hostname}' filtered out ({filter_reason})"
                                    )

                        url_record = TyposquatURL(
                            url=url,
                            hostname=hostname,
                            port=parsed.port or (443 if parsed.scheme == "https" else 80),
                            path=parsed.path or "/",
                            scheme=parsed.scheme or "http",
                            program_id=program.id if program else None
                        )
                        db.add(url_record)
                        db.flush()  # Get the ID

                # Ensure we have a URL record - screenshots require a URL
                if not url_record:
                    logger.warning(f"Cannot create screenshot without URL record for: {url}")
                    raise ValueError("Screenshot requires a valid URL record")
                
                logger.info(f"Using URL record ID: {url_record.id} for screenshot creation")
                
                # Check if this exact image already exists for this URL (per-URL deduplication)
                existing_screenshot = None
                existing_screenshot = db.query(TyposquatScreenshot).filter(
                    TyposquatScreenshot.image_hash == image_hash,
                    TyposquatScreenshot.url_id == url_record.id
                ).first()
                
                if existing_screenshot:
                    # Image already exists for this URL, just update the existing screenshot record
                    # Update capture count and timestamp
                    existing_screenshot.capture_count += 1
                    existing_screenshot.last_captured_at = datetime.utcnow()
                    
                    # Update workflow_id, step_name, program_name, extracted_text, source_created_at, source if provided
                    if workflow_id:
                        existing_screenshot.workflow_id = workflow_id
                    if step_name:
                        existing_screenshot.step_name = step_name
                    if program_name:
                        existing_screenshot.program_name = program_name
                    if extracted_text is not None:
                        existing_screenshot.extracted_text = extracted_text
                    if parsed_source_created_at is not None and existing_screenshot.source_created_at is None:
                        existing_screenshot.source_created_at = parsed_source_created_at
                    if source and source.strip() and existing_screenshot.source is None:
                        existing_screenshot.source = source.strip()
                    
                    db.commit()
                    return str(existing_screenshot.file_id)
                
                # Create new typosquat screenshot file
                screenshot_file = TyposquatScreenshotFile(
                    file_content=image_data,
                    content_type=content_type,
                    filename=filename,
                    file_size=len(image_data)
                )
                db.add(screenshot_file)
                db.flush()  # Get the ID
                
                # Create typosquat screenshot record
                screenshot_data = {
                    "url_id": url_record.id,  # Always set to the valid URL record ID
                    "file_id": screenshot_file.id,
                    "image_hash": image_hash,
                    "workflow_id": workflow_id,
                    "step_name": step_name,
                    "program_name": program_name,
                    "capture_count": 1,
                    "last_captured_at": datetime.utcnow(),  # Set the required last_captured_at field
                    "extracted_text": extracted_text,
                    "source_created_at": parsed_source_created_at,
                    "source": source.strip() if source and source.strip() else None
                }
                
                screenshot = TyposquatScreenshot(**screenshot_data)
                db.add(screenshot)
                db.commit()
                
                return str(screenshot_file.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error storing typosquat screenshot: {str(e)}")
                raise

    @staticmethod
    async def get_typosquat_screenshot(file_id: str) -> Optional[Dict[str, Any]]:
        """Get typosquat screenshot by file ID"""
        async with get_db_session() as db:
            try:
                from uuid import UUID
                
                # Convert string ID to UUID
                file_uuid = UUID(file_id)
                
                # Get typosquat screenshot file
                file_data = db.query(TyposquatScreenshotFile).filter(TyposquatScreenshotFile.id == file_uuid).first()
                if not file_data:
                    return None
                
                # Get typosquat screenshot metadata
                screenshot = db.query(TyposquatScreenshot).filter(TyposquatScreenshot.file_id == file_uuid).first()
                
                # Get URL data if screenshot exists
                url_data = None
                if screenshot and screenshot.url_id:
                    url_data = db.query(TyposquatURL).filter(TyposquatURL.id == screenshot.url_id).first()
                
                # Create capture_timestamps array
                capture_timestamps = []
                if screenshot and screenshot.created_at:
                    capture_timestamps.append(screenshot.created_at.isoformat())
                if screenshot and screenshot.last_captured_at and screenshot.last_captured_at != screenshot.created_at:
                    capture_timestamps.append(screenshot.last_captured_at.isoformat())
                
                return {
                    "_id": str(screenshot.id) if screenshot else None,
                    "file_id": str(file_data.id),
                    "filename": file_data.filename,
                    "content_type": file_data.content_type,
                    "file_size": file_data.file_size,
                    "file_content": file_data.file_content,
                    "upload_date": file_data.created_at.isoformat() if file_data.created_at else None,
                    "metadata": {
                        "url": url_data.url if url_data else None,
                        "image_hash": screenshot.image_hash if screenshot else None,
                        "workflow_id": screenshot.workflow_id if screenshot else None,
                        "step_name": screenshot.step_name if screenshot else None,
                        "program_name": screenshot.program_name if screenshot else None,
                        "capture_count": screenshot.capture_count if screenshot else 1,
                        "last_captured_at": screenshot.last_captured_at.isoformat() if screenshot and screenshot.last_captured_at else None,
                        "capture_timestamps": capture_timestamps,
                        "extracted_text": screenshot.extracted_text if screenshot else None,
                        "source_created_at": screenshot.source_created_at.isoformat() if screenshot and screenshot.source_created_at else None,
                        "source": screenshot.source if screenshot else None
                    }
                }
                
            except Exception as e:
                logger.error(f"Error getting typosquat screenshot: {str(e)}")
                raise

    @staticmethod
    async def list_typosquat_screenshots(program_name: Optional[str] = None, url: Optional[str] = None, workflow_id: Optional[str] = None, step_name: Optional[str] = None, limit: int = 100, skip: int = 0, sort: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
        """List typosquat screenshots"""
        async with get_db_session() as db:
            try:
                # Always join with URL table to get the URL
                query = db.query(TyposquatScreenshot, TyposquatScreenshotFile, TyposquatURL).join(
                    TyposquatScreenshotFile, TyposquatScreenshot.file_id == TyposquatScreenshotFile.id
                ).join(
                    TyposquatURL, TyposquatScreenshot.url_id == TyposquatURL.id
                )
                
                # Apply filters
                if program_name:
                    query = query.filter(TyposquatScreenshot.program_name == program_name)
                if workflow_id:
                    query = query.filter(TyposquatScreenshot.workflow_id == workflow_id)
                if step_name:
                    query = query.filter(TyposquatScreenshot.step_name == step_name)
                if url:
                    # Filter by URL
                    query = query.filter(TyposquatURL.url == url)
                
                # Apply sorting
                if sort:
                    for field, direction in sort.items():
                        if hasattr(TyposquatScreenshot, field):
                            column = getattr(TyposquatScreenshot, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                        elif hasattr(TyposquatScreenshotFile, field):
                            column = getattr(TyposquatScreenshotFile, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                        elif hasattr(TyposquatURL, field):
                            column = getattr(TyposquatURL, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                else:
                    # Default sort by created_at descending
                    query = query.order_by(TyposquatScreenshot.created_at.desc())
                
                # Apply pagination
                query = query.offset(skip).limit(limit)
                
                results = []
                for screenshot, file_data, url_data in query.all():
                    # Create capture_timestamps array
                    capture_timestamps = []
                    if screenshot.created_at:
                        capture_timestamps.append(screenshot.created_at.isoformat())
                    if screenshot.last_captured_at and screenshot.last_captured_at != screenshot.created_at:
                        capture_timestamps.append(screenshot.last_captured_at.isoformat())
                    
                    results.append({
                        "_id": str(screenshot.id),  # Use screenshot.id as _id
                        "file_id": str(file_data.id),
                        "filename": file_data.filename,
                        "content_type": file_data.content_type,
                        "file_size": file_data.file_size,
                        "upload_date": file_data.created_at.isoformat() if file_data.created_at else None,  # Add upload_date
                        "metadata": {
                            "url": url_data.url,
                            "image_hash": screenshot.image_hash,
                            "workflow_id": screenshot.workflow_id,
                            "step_name": screenshot.step_name,
                            "program_name": screenshot.program_name,
                            "capture_count": screenshot.capture_count,
                            "last_captured_at": screenshot.last_captured_at.isoformat() if screenshot.last_captured_at else None,
                            "capture_timestamps": capture_timestamps,
                            "source_created_at": screenshot.source_created_at.isoformat() if screenshot.source_created_at else None,
                            "source": screenshot.source
                        }
                    })
                
                return results
                
            except Exception as e:
                logger.error(f"Error listing typosquat screenshots: {str(e)}")
                raise

    # ===== TYPOSQUAT CERTIFICATE METHODS =====

    @staticmethod
    async def create_or_update_typosquat_certificate(certificate_data: Dict[str, Any]) -> str:
        """Create a new typosquat certificate or update if exists with merged data"""
        async with get_db_session() as db:
            try:
                #logger.debug(f"Creating or updating typosquat certificate for domain: {certificate_data.get('subject_cn')}")
                
                # Find program by name
                program = db.query(Program).filter(Program.name == certificate_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{certificate_data.get('program_name')}' not found")
                

                
                # Check if certificate already exists based on serial number
                existing = db.query(TyposquatCertificate).filter(
                    TyposquatCertificate.serial_number == certificate_data.get('serial_number')
                ).first()
                
                if existing:
                    # Update existing certificate
                    updated = False
                    
                    # Update fields if provided and different
                    if 'subject_dn' in certificate_data and certificate_data.get('subject_dn') != existing.subject_dn:
                        existing.subject_dn = certificate_data.get('subject_dn')
                        updated = True
                    
                    if 'subject_cn' in certificate_data and certificate_data.get('subject_cn') != existing.subject_cn:
                        existing.subject_cn = certificate_data.get('subject_cn')
                        updated = True
                    
                    if 'subject_alternative_names' in certificate_data and certificate_data.get('subject_alternative_names') != existing.subject_alternative_names:
                        existing.subject_alternative_names = certificate_data.get('subject_alternative_names')
                        updated = True
                    
                    if 'valid_from' in certificate_data and certificate_data.get('valid_from') != existing.valid_from:
                        existing.valid_from = certificate_data.get('valid_from')
                        updated = True
                    
                    if 'valid_until' in certificate_data and certificate_data.get('valid_until') != existing.valid_until:
                        existing.valid_until = certificate_data.get('valid_until')
                        updated = True
                    
                    if 'issuer_dn' in certificate_data and certificate_data.get('issuer_dn') != existing.issuer_dn:
                        existing.issuer_dn = certificate_data.get('issuer_dn')
                        updated = True
                    
                    if 'issuer_cn' in certificate_data and certificate_data.get('issuer_cn') != existing.issuer_cn:
                        existing.issuer_cn = certificate_data.get('issuer_cn')
                        updated = True
                    
                    if 'issuer_organization' in certificate_data and certificate_data.get('issuer_organization') != existing.issuer_organization:
                        existing.issuer_organization = certificate_data.get('issuer_organization')
                        updated = True
                    
                    if 'fingerprint_hash' in certificate_data and certificate_data.get('fingerprint_hash') != existing.fingerprint_hash:
                        existing.fingerprint_hash = certificate_data.get('fingerprint_hash')
                        updated = True
                    
                    if 'notes' in certificate_data and certificate_data.get('notes') != existing.notes:
                        existing.notes = certificate_data.get('notes')
                        updated = True
                    
                    # Update timestamp if any changes were made
                    if updated:
                        existing.updated_at = datetime.utcnow()
                        #logger.debug(f"Updated existing typosquat certificate {certificate_data.get('serial_number')}")
                   # else:
                        #logger.info(f"Typosquat certificate {certificate_data.get('serial_number')} already exists with same data, skipping")
                    
                    db.commit()
                    return str(existing.id)
                else:
                    # Create new typosquat certificate
                    certificate = TyposquatCertificate(
                        subject_dn=certificate_data.get('subject_dn'),
                        subject_cn=certificate_data.get('subject_cn'),
                        subject_alternative_names=certificate_data.get('subject_alternative_names', []),
                        valid_from=certificate_data.get('valid_from'),
                        valid_until=certificate_data.get('valid_until'),
                        issuer_dn=certificate_data.get('issuer_dn'),
                        issuer_cn=certificate_data.get('issuer_cn'),
                        issuer_organization=certificate_data.get('issuer_organization', []),
                        serial_number=certificate_data.get('serial_number'),
                        fingerprint_hash=certificate_data.get('fingerprint_hash'),
                        program_id=program.id,
                        notes=certificate_data.get('notes')
                    )
                    
                    db.add(certificate)
                    db.commit()
                    db.refresh(certificate)
                    
                    return str(certificate.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating typosquat certificate: {str(e)}")
                raise

    @staticmethod
    async def get_typosquat_certificate_by_id(certificate_id: str) -> Optional[Dict[str, Any]]:
        """Get a typosquat certificate by ID"""
        async with get_db_session() as db:
            try:
                certificate = db.query(TyposquatCertificate).filter(TyposquatCertificate.id == certificate_id).first()
                if not certificate:
                    return None
                
                certificate_dict = certificate.to_dict()
                # Add program name to the response
                certificate_dict['program_name'] = certificate.program.name if certificate.program else None
                
                return certificate_dict
                
            except Exception as e:
                logger.error(f"Error getting typosquat certificate {certificate_id}: {str(e)}")
                raise

    @staticmethod
    async def list_typosquat_certificates(program_name: Optional[str] = None, limit: int = 100, skip: int = 0) -> List[Dict[str, Any]]:
        """List typosquat certificates with optional filtering"""
        async with get_db_session() as db:
            try:
                query = db.query(TyposquatCertificate)
                
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                
                query = query.offset(skip).limit(limit)
                certificates = query.all()
                
                result = []
                for certificate in certificates:
                    certificate_dict = certificate.to_dict()
                    # Add program name to the response
                    certificate_dict['program_name'] = certificate.program.name if certificate.program else None
                    result.append(certificate_dict)
                
                return result
                
            except Exception as e:
                logger.error(f"Error listing typosquat certificates: {str(e)}")
                raise

    @staticmethod
    async def update_typosquat_certificate(certificate_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a typosquat certificate"""
        async with get_db_session() as db:
            try:
                certificate = db.query(TyposquatCertificate).filter(TyposquatCertificate.id == certificate_id).first()
                if not certificate:
                    return False
                
                # Update fields with null protection
                for key, value in update_data.items():
                    if hasattr(certificate, key):
                        # Only update if value is not None and not string "null"
                        if value is not None and value != "null":
                            setattr(certificate, key, value)
                
                certificate.updated_at = datetime.utcnow()
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating typosquat certificate {certificate_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_typosquat_certificate(certificate_id: str) -> bool:
        """Delete a typosquat certificate"""
        async with get_db_session() as db:
            try:
                certificate = db.query(TyposquatCertificate).filter(TyposquatCertificate.id == certificate_id).first()
                if not certificate:
                    return False
                
                db.delete(certificate)
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting typosquat certificate {certificate_id}: {str(e)}")
                raise

    # ===== TYPOSQUAT URL RETRIEVAL METHODS =====

    @staticmethod
    async def get_typosquat_urls_by_domain(domain: Optional[str] = None, program_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get typosquat URLs filtered by domain and/or program"""
        async with get_db_session() as db:
            try:
                query = db.query(TyposquatURL)
                
                if domain:
                    query = query.filter(TyposquatURL.hostname == domain)
                
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                
                query = query.limit(limit)
                urls = query.all()
                
                result = []
                for url in urls:
                    url_dict = url.to_dict()
                    # Add program name to the response
                    url_dict['program_name'] = url.program.name if url.program else None
                    
                    # Add typosquat domain information if available
                    if url.typosquat_domain:
                        url_dict['typo_domain'] = url.typosquat_domain.typo_domain
                        url_dict['typosquat_type'] = getattr(url.typosquat_domain, 'typosquat_type', None)
                    else:
                        url_dict['typo_domain'] = None
                        url_dict['typosquat_type'] = None
                    
                    result.append(url_dict)
                
                return result
                
            except Exception as e:
                logger.error(f"Error getting typosquat URLs by domain {domain}: {str(e)}")
                raise

    @staticmethod
    async def get_typosquat_url_by_id(url_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific typosquat URL by ID"""
        async with get_db_session() as db:
            try:
                url = db.query(TyposquatURL).filter(TyposquatURL.id == url_id).first()
                if not url:
                    return None
                
                url_dict = url.to_dict()
                # Add program name to the response
                url_dict['program_name'] = url.program.name if url.program else None
                
                return url_dict
                
            except Exception as e:
                logger.error(f"Error getting typosquat URL {url_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_typosquat_url(url_id: str) -> bool:
        """Delete a typosquat URL by ID"""
        async with get_db_session() as db:
            try:
                url = db.query(TyposquatURL).filter(TyposquatURL.id == url_id).first()
                if not url:
                    return False
                
                db.delete(url)
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting typosquat URL {url_id}: {str(e)}")
                raise

    @staticmethod
    async def update_typosquat_url_notes(url_id: str, notes: str) -> bool:
        """Update notes for a typosquat URL"""
        async with get_db_session() as db:
            try:
                url = db.query(TyposquatURL).filter(TyposquatURL.id == url_id).first()
                if not url:
                    return False
                
                url.notes = notes
                url.updated_at = datetime.utcnow()
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating typosquat URL notes {url_id}: {str(e)}")
                raise




    # ===== TYPOSQUAT URL SEARCH METHODS =====

    @staticmethod
    async def search_typosquat_urls(
        search_params: Dict[str, Any],
        sort_by: str = "url",
        sort_dir: str = "asc",
        limit: int = 25,
        skip: int = 0
    ) -> Dict[str, Any]:
        """Search typosquat URLs with filtering and pagination"""
        async with get_db_session() as db:
            try:
                base_query = db.query(TyposquatURL).join(Program).outerjoin(TyposquatDomain, TyposquatURL.typosquat_domain_id == TyposquatDomain.id)
                
                # Apply search filters
                if search_params.get("search"):
                    search_term = f"%{search_params['search']}%"
                    base_query = base_query.filter(
                        or_(
                            TyposquatURL.url.ilike(search_term),
                            TyposquatURL.hostname.ilike(search_term),
                            TyposquatURL.title.ilike(search_term)
                        )
                    )
                
                if search_params.get("exact_match"):
                    base_query = base_query.filter(TyposquatURL.url == search_params["exact_match"])
                
                if search_params.get("protocol"):
                    base_query = base_query.filter(TyposquatURL.scheme == search_params["protocol"])
                
                if search_params.get("status_code"):
                    base_query = base_query.filter(TyposquatURL.http_status_code == search_params["status_code"])
                
                if search_params.get("only_root"):
                    base_query = base_query.filter(TyposquatURL.path == '/')
                
                if search_params.get("technology_text"):
                    tech_term = f"%{search_params['technology_text']}%"
                    base_query = base_query.filter(TyposquatURL.technologies.any(tech_term))
                
                if search_params.get("technology"):
                    base_query = base_query.filter(TyposquatURL.technologies.contains([search_params["technology"]]))
                
                if search_params.get("programs"):
                    base_query = base_query.filter(Program.name.in_(search_params["programs"]))
                
                # Get total count before applying pagination
                total_count = base_query.count()
                
                # Apply sorting
                if sort_dir == "desc":
                    base_query = base_query.order_by(desc(getattr(TyposquatURL, sort_by)))
                else:
                    base_query = base_query.order_by(asc(getattr(TyposquatURL, sort_by)))
                
                # Apply pagination
                base_query = base_query.offset(skip).limit(limit)
                
                urls = base_query.all()
                
                result = []
                for url in urls:
                    url_dict = url.to_dict()
                    # Add program name to the response
                    url_dict['program_name'] = url.program.name if url.program else None
                    result.append(url_dict)
                
                return {
                    "items": result,
                    "total_count": total_count
                }
                
            except Exception as e:
                logger.error(f"Error searching typosquat URLs: {str(e)}")
                raise

    @staticmethod
    async def delete_typosquat_urls_batch(url_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple typosquat URLs by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                
                for url_id in url_ids:
                    url = db.query(TyposquatURL).filter(TyposquatURL.id == url_id).first()
                    if url:
                        db.delete(url)
                        deleted_count += 1
                    else:
                        not_found_count += 1
                
                db.commit()
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "total_requested": len(url_ids)
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting typosquat URLs: {str(e)}")
                raise

    # ===== TYPOSQUAT SCREENSHOT SEARCH METHODS =====

    @staticmethod
    async def search_typosquat_screenshots(
        search_params: Dict[str, Any],
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 20,
        skip: int = 0
    ) -> Dict[str, Any]:
        """Search typosquat screenshots with filtering and pagination"""
        async with get_db_session() as db:
            try:
                # Start with TyposquatScreenshot and join with TyposquatURL and TyposquatScreenshotFile
                # TyposquatScreenshot has url_id -> TyposquatURL
                # TyposquatScreenshot has file_id -> TyposquatScreenshotFile
                # TyposquatURL has typosquat_domain_id -> TyposquatDomain
                base_query = db.query(TyposquatScreenshot).join(TyposquatURL, TyposquatScreenshot.url_id == TyposquatURL.id).join(TyposquatScreenshotFile, TyposquatScreenshot.file_id == TyposquatScreenshotFile.id)
                
                # Apply search filters
                if search_params.get("search_url"):
                    search_term = f"%{search_params['search_url']}%"
                    base_query = base_query.filter(TyposquatURL.url.ilike(search_term))
                
                if search_params.get("url_equals"):
                    base_query = base_query.filter(TyposquatURL.url == search_params["url_equals"])
                
                if search_params.get("typosquat_type"):
                    # Filter by typosquat type - this would need to be stored in the database
                    # For now, we'll skip this filter as it's not implemented in the current schema
                    # TODO: Implement typosquat type filtering when the schema supports it
                    pass
                
                if search_params.get("exclude_parked"):
                    base_query = base_query.outerjoin(TyposquatDomain, TyposquatURL.typosquat_domain_id == TyposquatDomain.id)
                    base_query = base_query.filter(
                        or_(
                            TyposquatDomain.id.is_(None),
                            TyposquatDomain.is_parked.is_(False),
                            TyposquatDomain.is_parked.is_(None),
                        )
                    )
                
                if search_params.get("programs"):
                    # Filter by program_name field in TyposquatScreenshot
                    base_query = base_query.filter(TyposquatScreenshot.program_name.in_(search_params["programs"]))
                
                # Get total count before applying pagination
                total_count = base_query.count()
                
                # Map sort_by to actual field names
                sort_field_mapping = {
                    "upload_date": "created_at",
                    "created_at": "created_at",
                    "last_captured_at": "last_captured_at"
                }
                actual_sort_field = sort_field_mapping.get(sort_by, "created_at")
                
                # Apply sorting
                if sort_dir == "desc":
                    base_query = base_query.order_by(desc(getattr(TyposquatScreenshot, actual_sort_field)))
                else:
                    base_query = base_query.order_by(asc(getattr(TyposquatScreenshot, actual_sort_field)))
                
                # Apply pagination
                base_query = base_query.offset(skip).limit(limit)
                
                screenshots = base_query.all()
                
                result = []
                for screenshot in screenshots:
                    screenshot_dict = screenshot.to_dict()
                    
                    # Add program name from the field
                    screenshot_dict['program_name'] = screenshot.program_name
                    
                    # Add URL information
                    if screenshot.url:
                        screenshot_dict['url'] = screenshot.url.url
                        screenshot_dict['hostname'] = screenshot.url.hostname
                        
                        # Add domain information if available
                        if screenshot.url.typosquat_domain:
                            screenshot_dict['typo_domain'] = screenshot.url.typosquat_domain.typo_domain
                    
                    # Add file information
                    if screenshot.file:
                        screenshot_dict['file_size'] = screenshot.file.file_size
                        screenshot_dict['filename'] = screenshot.file.filename
                        screenshot_dict['content_type'] = screenshot.file.content_type
                    
                    # Create metadata structure for frontend compatibility
                    screenshot_dict['metadata'] = {
                        'url': screenshot_dict.get('url'),
                        'typo_domain': screenshot_dict.get('typo_domain'),
                        'program_name': screenshot_dict.get('program_name'),
                        'capture_count': screenshot_dict.get('capture_count'),
                        'workflow_id': screenshot_dict.get('workflow_id'),
                        'step_name': screenshot_dict.get('step_name'),
                        'image_hash': screenshot_dict.get('image_hash'),
                        'source_created_at': screenshot_dict.get('source_created_at'),
                        'source': screenshot_dict.get('source')
                    }
                    
                    result.append(screenshot_dict)
                
                return {
                    "items": result,
                    "total_count": total_count
                }
                
            except Exception as e:
                logger.error(f"Error searching typosquat screenshots: {str(e)}")
                raise

    @staticmethod
    async def delete_typosquat_screenshots_batch(screenshot_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple typosquat screenshots by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                
                for screenshot_id in screenshot_ids:
                    screenshot = db.query(TyposquatScreenshot).filter(TyposquatScreenshot.id == screenshot_id).first()
                    if screenshot:
                        db.delete(screenshot)
                        deleted_count += 1
                    else:
                        not_found_count += 1
                
                db.commit()
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "total_requested": len(screenshot_ids)
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting typosquat screenshots: {str(e)}")
                raise
