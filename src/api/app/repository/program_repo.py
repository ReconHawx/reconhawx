from typing import Dict, Any, Optional, List
import logging
import asyncio
from datetime import datetime
import time
from uuid import UUID
import re
from sqlalchemy import desc, asc
from db import get_db_session
from services.protected_domain_similarity_service import ProtectedDomainSimilarityService
from services.typosquat_auto_resolve_service import TyposquatAutoResolveService
from utils.query_filters import ProgramAccessMixin
from models.postgres import (
    Program,
    Screenshot,
    URL,
    Service,
    Subdomain,
    SubdomainIP,
    IP,
    Certificate,
    ApexDomain,
    UserProgramPermission,
    NucleiFinding,
    TyposquatDomain,
    TyposquatURL,
    TyposquatCertificate,
    Workflow,
    WorkflowLog,
    Wordlist,
)

logger = logging.getLogger(__name__)

class ProgramRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def create_program(program_data: Dict[str, Any], restore_from_archive: bool = False) -> str:
        """Create a new program"""
        async with get_db_session() as db:
            try:
                # Check if program already exists
                existing_program = db.query(Program).filter(Program.name == program_data.get('name')).first()
                if existing_program:
                    raise ValueError(f"Program '{program_data.get('name')}' already exists")
                
                # Create new program
                program = Program(
                    name=program_data.get('name'),
                    domain_regex=program_data.get('domain_regex', []),
                    out_of_scope_regex=program_data.get('out_of_scope_regex', []),
                    cidr_list=program_data.get('cidr_list', []),
                    phishlabs_api_key=program_data.get('phishlabs_api_key'),
                    threatstream_api_key=program_data.get('threatstream_api_key'),
                    threatstream_api_user=program_data.get('threatstream_api_user'),
                    recordedfuture_api_key=program_data.get('recordedfuture_api_key'),
                    safe_registrar=program_data.get('safe_registrar', []),
                    safe_ssl_issuer=program_data.get('safe_ssl_issuer', []),
                    protected_domains=program_data.get('protected_domains', []),
                    protected_subdomain_prefixes=program_data.get('protected_subdomain_prefixes', []),
                    typosquat_filtering_settings=program_data.get('typosquat_filtering_settings', {}),
                    ct_monitor_program_settings=program_data.get('ct_monitor_program_settings') or {},
                    ct_monitoring_enabled=bool(program_data.get('ct_monitoring_enabled', False)),
                )
                
                db.add(program)
                db.commit()
                db.refresh(program)
                
                logger.info(f"Created program with ID: {program.id}")
                return str(program.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating program: {str(e)}")
                raise
    
    @staticmethod
    async def is_domain_in_scope(hostname: str, program_name: str) -> bool:
        """Check if a domain is in scope for a program
        
        A domain is in scope if:
        1. It matches at least one pattern in domain_regex (in-scope)
        2. AND it does NOT match any pattern in out_of_scope_regex (exclusions)
        
        Out-of-scope patterns take precedence over in-scope patterns.
        """
        async with get_db_session():
            try:
                # Get program
                program = await ProgramRepository.get_program_by_name(program_name)
                if not program:
                    return False
                
                # First, check if domain matches any in-scope patterns
                matches_in_scope = False
                for regex_pattern in program['domain_regex']:
                    try:
                        if re.match(regex_pattern, hostname):
                            matches_in_scope = True
                            break
                    except re.error:
                        logger.warning(f"Invalid in-scope regex pattern: {regex_pattern}")
                        continue
                
                # If doesn't match in-scope patterns, it's out of scope
                if not matches_in_scope:
                    return False
                
                # Check if domain matches any out-of-scope exclusion patterns
                out_of_scope_patterns = program.get('out_of_scope_regex', [])
                for regex_pattern in out_of_scope_patterns:
                    try:
                        if re.match(regex_pattern, hostname):
                            logger.info(f"Domain '{hostname}' matched out-of-scope pattern '{regex_pattern}' for program '{program_name}'")
                            return False
                    except re.error:
                        logger.warning(f"Invalid out-of-scope regex pattern: {regex_pattern}")
                        continue
                
                # Matched in-scope and didn't match any exclusions
                return True
                
            except Exception as e:
                logger.error(f"Error checking domain scope: {str(e)}")
                return False

    @staticmethod
    async def get_program(program_id: str) -> Optional[Dict[str, Any]]:
        """Get program by ID"""
        async with get_db_session() as db:
            try:
                program = db.query(Program).filter(Program.id == program_id).first()
                if not program:
                    return None
                
                return {
                    'id': str(program.id),
                    'name': program.name,
                    'domain_regex': program.domain_regex,
                    'out_of_scope_regex': program.out_of_scope_regex,
                    'cidr_list': program.cidr_list,
                    'phishlabs_api_key': program.phishlabs_api_key,
                    'threatstream_api_key': program.threatstream_api_key,
                    'threatstream_api_user': program.threatstream_api_user,
                    'recordedfuture_api_key': program.recordedfuture_api_key,
                    'safe_registrar': program.safe_registrar,
                    'safe_ssl_issuer': program.safe_ssl_issuer,
                    'protected_domains': program.protected_domains,
                    'protected_subdomain_prefixes': getattr(program, 'protected_subdomain_prefixes', None) or [],
                    'notification_settings': program.notification_settings,
                    'event_handler_addon_mode': bool(getattr(program, 'event_handler_addon_mode', False)),
                    'typosquat_auto_resolve_settings': getattr(program, 'typosquat_auto_resolve_settings', None) or {},
                    'typosquat_filtering_settings': getattr(program, 'typosquat_filtering_settings', None) or {},
                    'ct_monitor_program_settings': getattr(program, 'ct_monitor_program_settings', None) or {},
                    'ai_analysis_settings': getattr(program, 'ai_analysis_settings', None) or {},
                    'ct_monitoring_enabled': bool(getattr(program, 'ct_monitoring_enabled', False)),
                    'created_at': program.created_at.isoformat() if program.created_at else None,
                    'updated_at': program.updated_at.isoformat() if program.updated_at else None
                }
                
            except Exception as e:
                logger.error(f"Error getting program {program_id}: {str(e)}")
                raise
    
    @staticmethod
    async def get_program_by_name(name: str) -> Optional[Dict[str, Any]]:
        """Get program by name"""
        async with get_db_session() as db:
            try:
                program = db.query(Program).filter(Program.name == name).first()
                if not program:
                    return None
                
                return {
                    'id': str(program.id),
                    'name': program.name,
                    'domain_regex': program.domain_regex,
                    'out_of_scope_regex': program.out_of_scope_regex,
                    'cidr_list': program.cidr_list,
                    'phishlabs_api_key': program.phishlabs_api_key,
                    'threatstream_api_key': program.threatstream_api_key,
                    'threatstream_api_user': program.threatstream_api_user,
                    'recordedfuture_api_key': program.recordedfuture_api_key,
                    'safe_registrar': program.safe_registrar,
                    'safe_ssl_issuer': program.safe_ssl_issuer,
                    'protected_domains': program.protected_domains,
                    'protected_subdomain_prefixes': getattr(program, 'protected_subdomain_prefixes', None) or [],
                    'notification_settings': program.notification_settings,
                    'event_handler_addon_mode': bool(getattr(program, 'event_handler_addon_mode', False)),
                    'typosquat_auto_resolve_settings': getattr(program, 'typosquat_auto_resolve_settings', None) or {},
                    'typosquat_filtering_settings': getattr(program, 'typosquat_filtering_settings', None) or {},
                    'ct_monitor_program_settings': getattr(program, 'ct_monitor_program_settings', None) or {},
                    'ai_analysis_settings': getattr(program, 'ai_analysis_settings', None) or {},
                    'ct_monitoring_enabled': bool(getattr(program, 'ct_monitoring_enabled', False)),
                    'created_at': program.created_at.isoformat() if program.created_at else None,
                    'updated_at': program.updated_at.isoformat() if program.updated_at else None
                }
                
            except Exception as e:
                logger.error(f"Error getting program by name {name}: {str(e)}")
                raise
    
    @staticmethod
    async def update_program(program_id: str, program_data: Dict[str, Any]) -> bool:
        """Update a program"""
        async with get_db_session() as db:
            try:
                program = db.query(Program).filter(Program.id == program_id).first()
                if not program:
                    return False
                
                # Check if protected_domains is being updated
                old_protected_domains = set(program.protected_domains or [])
                new_protected_domains = None
                if 'protected_domains' in program_data:
                    new_protected_domains = set(program_data.get('protected_domains') or [])
                
                # Check if typosquat_auto_resolve_settings is being updated
                old_auto_resolve_settings = getattr(program, 'typosquat_auto_resolve_settings', None) or {}
                new_auto_resolve_settings = program_data.get('typosquat_auto_resolve_settings') if 'typosquat_auto_resolve_settings' in program_data else None
                
                # Update fields
                for key, value in program_data.items():
                    if hasattr(program, key):
                        setattr(program, key, value)
                
                program.updated_at = datetime.utcnow()
                db.commit()
                
                # If typosquat_auto_resolve_settings changed, trigger bulk auto_resolve recalculation
                if new_auto_resolve_settings is not None and new_auto_resolve_settings != old_auto_resolve_settings:
                    logger.info(f"Typosquat auto-resolve settings changed for program {program.name}, triggering bulk recalculation")
                    asyncio.create_task(
                        TyposquatAutoResolveService.recalculate_auto_resolve_for_program(str(program.id))
                    )
                
                # If protected_domains changed, trigger similarity recalculation
                if new_protected_domains is not None and new_protected_domains != old_protected_domains:
                    logger.info(f"Protected domains changed for program {program.name}, triggering similarity recalculation")
                    asyncio.create_task(
                        ProtectedDomainSimilarityService.recalculate_for_program(
                            str(program.id),
                            list(new_protected_domains)
                        )
                    )
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating program {program_id}: {str(e)}")
                raise
    
    # List and count methods
    @staticmethod
    async def list_programs() -> List[Dict[str, Any]]:
        """List all programs"""
        async with get_db_session() as db:
            try:
                programs = db.query(Program).all()
                return [
                    {
                        'id': str(p.id),
                        'name': p.name,
                        'domain_regex': p.domain_regex,
                        'out_of_scope_regex': p.out_of_scope_regex,
                        'cidr_list': p.cidr_list,
                        'safe_registrar': p.safe_registrar,
                        'safe_ssl_issuer': p.safe_ssl_issuer,
                        'phishlabs_api_key': p.phishlabs_api_key,
                        'threatstream_api_key': p.threatstream_api_key,
                        'threatstream_api_user': p.threatstream_api_user,
                        'recordedfuture_api_key': p.recordedfuture_api_key,
                        'protected_domains': p.protected_domains,
                        'protected_subdomain_prefixes': getattr(p, 'protected_subdomain_prefixes', None) or [],
                        'notification_settings': p.notification_settings,
                        'event_handler_addon_mode': bool(getattr(p, 'event_handler_addon_mode', False)),
                        'typosquat_auto_resolve_settings': getattr(p, 'typosquat_auto_resolve_settings', None) or {},
                        'typosquat_filtering_settings': getattr(p, 'typosquat_filtering_settings', None) or {},
                        'ct_monitor_program_settings': getattr(p, 'ct_monitor_program_settings', None) or {},
                        'ai_analysis_settings': getattr(p, 'ai_analysis_settings', None) or {},
                        'ct_monitoring_enabled': bool(getattr(p, 'ct_monitoring_enabled', False)),
                        'created_at': p.created_at.isoformat() if p.created_at else None,
                        'updated_at': p.updated_at.isoformat() if p.updated_at else None
                    }
                    for p in programs
                ]
            except Exception as e:
                logger.error(f"Error listing programs: {str(e)}")
                raise

    @staticmethod
    async def any_ct_monitoring_enabled() -> bool:
        """True if at least one program has CT monitoring enabled."""
        async with get_db_session() as db:
            row = (
                db.query(Program.id)
                .filter(Program.ct_monitoring_enabled.is_(True))
                .limit(1)
                .first()
            )
            return row is not None

    @staticmethod
    async def archive_and_delete_program(program_id: str, program_name: str) -> Dict[str, int]:
        """Archive and delete a program and all its associated assets"""
        async with get_db_session() as db:
            try:
                # Convert string ID to UUID
                program_uuid = UUID(program_id)
                
                # Get the program
                program = db.query(Program).filter(Program.id == program_uuid).first()
                if not program:
                    raise ValueError(f"Program with ID {program_id} not found")
                
                # Count assets to be deleted
                counts = {}
                counts['screenshots'] = db.query(Screenshot).filter(Screenshot.program_name == program_name).count()
                counts['urls'] = db.query(URL).filter(URL.program_id == program_uuid).count()
                counts['services'] = db.query(Service).filter(Service.program_id == program_uuid).count()
                counts['subdomain_ips'] = db.query(SubdomainIP).join(Subdomain).filter(Subdomain.program_id == program_uuid).count()
                counts['subdomains'] = db.query(Subdomain).filter(Subdomain.program_id == program_uuid).count()
                counts['ips'] = db.query(IP).filter(IP.program_id == program_uuid).count()
                counts['certificates'] = db.query(Certificate).filter(Certificate.program_id == program_uuid).count()
                counts['apex_domains'] = db.query(ApexDomain).filter(ApexDomain.program_id == program_uuid).count()
                counts['user_permissions'] = db.query(UserProgramPermission).filter(UserProgramPermission.program_id == program_uuid).count()
                counts['nuclei_findings'] = db.query(NucleiFinding).filter(NucleiFinding.program_id == program_uuid).count()
                counts['typosquat_domains'] = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_uuid).count()
                counts['workflows'] = db.query(Workflow).filter(Workflow.program_id == program_uuid).count()
                counts['workflow_logs'] = db.query(WorkflowLog).filter(WorkflowLog.program_id == program_uuid).count()
                counts['wordlists'] = db.query(Wordlist).filter(Wordlist.program_id == program_uuid).count()
                counts['typosquat_domains'] = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_uuid).count()
                counts['typosquat_urls'] = db.query(TyposquatURL).filter(TyposquatURL.program_id == program_uuid).count()
                counts['typosquat_certificates'] = db.query(TyposquatCertificate).filter(TyposquatCertificate.program_id == program_uuid).count()
                # Delete assets in order to respect foreign key constraints
                # Delete screenshots first (they reference URLs)
                db.query(Screenshot).filter(Screenshot.program_name == program_name).delete()
                
                # Delete URLs
                db.query(URL).filter(URL.program_id == program_uuid).delete()
                
                # Delete services
                db.query(Service).filter(Service.program_id == program_uuid).delete()
                
                # Delete subdomain-IP relationships
                subdomain_ids = [s.id for s in db.query(Subdomain.id).filter(Subdomain.program_id == program_uuid).all()]
                if subdomain_ids:
                    db.query(SubdomainIP).filter(SubdomainIP.subdomain_id.in_(subdomain_ids)).delete()
                
                # Delete subdomains
                db.query(Subdomain).filter(Subdomain.program_id == program_uuid).delete()
                
                # Delete nuclei findings first (they reference ips via ip_id)
                db.query(NucleiFinding).filter(NucleiFinding.program_id == program_uuid).delete()
                
                # Delete IPs
                db.query(IP).filter(IP.program_id == program_uuid).delete()
                
                # Delete certificates
                db.query(Certificate).filter(Certificate.program_id == program_uuid).delete()
                
                # Delete apex domains
                db.query(ApexDomain).filter(ApexDomain.program_id == program_uuid).delete()
                
                # Delete user program permissions
                db.query(UserProgramPermission).filter(UserProgramPermission.program_id == program_uuid).delete()
                
                # Delete typosquat domains
                db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_uuid).delete()
                
                # Delete workflow logs first (they reference workflows)
                db.query(WorkflowLog).filter(WorkflowLog.program_id == program_uuid).delete()
                
                # Delete workflows
                db.query(Workflow).filter(Workflow.program_id == program_uuid).delete()
                
                # Delete wordlists
                db.query(Wordlist).filter(Wordlist.program_id == program_uuid).delete()
                
                # Delete typosquat URLs
                db.query(TyposquatURL).filter(TyposquatURL.program_id == program_uuid).delete()
                
                # Delete typosquat certificates
                db.query(TyposquatCertificate).filter(TyposquatCertificate.program_id == program_uuid).delete()

                # Finally, delete the program
                db.delete(program)
                
                db.commit()
                
                logger.info(f"Successfully archived and deleted program '{program_name}' with {counts} assets")
                return counts
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error archiving and deleting program {program_name}: {str(e)}")
                raise

    @staticmethod
    async def search_programs_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        has_domains: Optional[bool] = None,
        has_ips: Optional[bool] = None,
        has_workflows: Optional[bool] = None,
        has_findings: Optional[bool] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed program search optimized for PostgreSQL.
        This version avoids complex JOINs and aggregations for better performance.

        Returns a dict with keys: items (list[dict]), total_count (int)
        """
        start_time = time.time()
        
        async with get_db_session() as db:
            try:
                # Simple query without complex JOINs - just get programs
                base_query = db.query(Program)
                
                # Apply filters
                if search:
                    base_query = base_query.filter(Program.name.ilike(f"%{search}%"))
                
                if exact_match:
                    base_query = base_query.filter(Program.name == exact_match)
                
                # Apply sorting
                sort_by_normalized = (sort_by or "updated_at").lower()
                sort_dir_normalized = (sort_dir or "desc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc
                
                if sort_by_normalized == "name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "created_at":
                    base_query = base_query.order_by(direction_func(Program.created_at))
                else:  # updated_at default
                    base_query = base_query.order_by(direction_func(Program.updated_at))
                
                # Get total count before pagination
                total_count = base_query.count()
                
                # Apply pagination
                base_query = base_query.offset(skip).limit(limit)
                
                # Execute query
                query_start = time.time()
                programs = base_query.all()
                time.time() - query_start
                
                # Convert to response format
                items = []
                for program in programs:
                    item = {
                        "id": str(program.id),
                        "name": program.name,
                        "domain_regex": list(program.domain_regex) if program.domain_regex else [],
                        "cidr_list": list(program.cidr_list) if program.cidr_list else [],
                        "safe_registrar": list(program.safe_registrar) if program.safe_registrar else [],
                        "safe_ssl_issuer": list(program.safe_ssl_issuer) if program.safe_ssl_issuer else [],
                        "protected_domains": list(program.protected_domains) if program.protected_domains else [],
                        "protected_subdomain_prefixes": list(getattr(program, 'protected_subdomain_prefixes', None) or []),
                        "phishlabs_api_key": program.phishlabs_api_key,
                        "threatstream_api_key": program.threatstream_api_key,
                        "threatstream_api_user": program.threatstream_api_user,
                        "recordedfuture_api_key": program.recordedfuture_api_key,
                        "notification_settings": program.notification_settings or {},
                        "event_handler_addon_mode": bool(getattr(program, 'event_handler_addon_mode', False)),
                        "typosquat_auto_resolve_settings": getattr(program, 'typosquat_auto_resolve_settings', None) or {},
                        "typosquat_filtering_settings": getattr(program, 'typosquat_filtering_settings', None) or {},
                        "ct_monitor_program_settings": getattr(program, 'ct_monitor_program_settings', None) or {},
                        "ai_analysis_settings": getattr(program, 'ai_analysis_settings', None) or {},
                        "created_at": program.created_at.isoformat() if program.created_at else None,
                        "updated_at": program.updated_at.isoformat() if program.updated_at else None,
                        "domain_count": 0,  # Asset counts are available via separate endpoint (common_assets_repo.py)
                        "ip_count": 0,      # Asset counts are available via separate endpoint (common_assets_repo.py)
                        "workflow_count": 0, # Asset counts are available via separate endpoint (common_assets_repo.py)
                        "findings_count": 0, # Asset counts are available via separate endpoint (common_assets_repo.py)
                    }
                    items.append(item)
                
                total_time = time.time() - start_time
                
                return {"items": items, "total_count": total_count}
                
            except Exception as e:
                total_time = time.time() - start_time
                logger.error(f"Error in optimized program search after {total_time:.2f}s: {str(e)}")
                raise

