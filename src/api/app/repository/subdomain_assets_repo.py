from sqlalchemy import func, desc, asc, and_
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, Optional, List, Union
import logging
from .program_repo import ProgramRepository
from datetime import datetime, timezone
from uuid import UUID
from utils.domain_utils import extract_apex_domain
from models.postgres import (
    Program, ApexDomain, Subdomain, IP, SubdomainIP
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin

logger = logging.getLogger(__name__)

# Suppress noisy filelock DEBUG logs and tldextract filelock logs
logging.getLogger("filelock").setLevel(logging.WARNING)
logging.getLogger("tldextract.cache").setLevel(logging.WARNING)


class SubdomainAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""

    @staticmethod
    async def get_domain_by_id(domain_id: str) -> Optional[Dict[str, Any]]:
        """Get domain (subdomain) by ID"""
        async with get_db_session() as db:
            try:
                domain = db.query(Subdomain).join(ApexDomain).filter(Subdomain.id == domain_id).first()
                if not domain:
                    return None

                # Get associated IPs for this subdomain (with ip_id for linking)
                ip_rows = db.query(IP.id, IP.ip_address).join(
                    SubdomainIP, IP.id == SubdomainIP.ip_id
                ).filter(
                    SubdomainIP.subdomain_id == domain.id
                ).all()

                ip_list = [{'ip': str(ip[1]), 'ip_id': str(ip[0])} for ip in ip_rows]

                return {
                    'id': str(domain.id),
                    'name': domain.name,
                    'program_name': domain.program.name if domain.program else None,
                    'apex_domain': domain.apex_domain.name if domain.apex_domain else None,
                    'is_wildcard': domain.is_wildcard,
                    'cname_record': domain.cname_record,
                    'ip': ip_list,
                    'notes': domain.notes,
                    'created_at': domain.created_at.isoformat() if domain.created_at else None,
                    'updated_at': domain.updated_at.isoformat() if domain.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting domain by id {domain_id}: {str(e)}")
                raise

    @staticmethod
    async def get_domain_by_name(domain_name: str, programs: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get domain (subdomain) by name. If programs specified, restrict to those programs."""
        domain_id = None
        async with get_db_session() as db:
            try:
                query = db.query(Subdomain).join(Program).filter(Subdomain.name == domain_name)
                if programs is not None and len(programs) > 0:
                    query = query.filter(Program.name.in_(programs))
                domain = query.first()
                if not domain:
                    return None
                domain_id = str(domain.id)
            except Exception as e:
                logger.error(f"Error getting domain by name {domain_name}: {str(e)}")
                raise
        return await SubdomainAssetsRepository.get_domain_by_id(domain_id)

    # Update methods
    @staticmethod
    async def update_domain(domain_id: str, domain_data: Dict[str, Any]) -> bool:
        """Update a domain"""
        async with get_db_session() as db:
            try:
                domain = db.query(Subdomain).filter(Subdomain.id == domain_id).first()
                if not domain:
                    return False
                
                for key, value in domain_data.items():
                    if hasattr(domain, key):
                        setattr(domain, key, value)
                
                domain.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating domain {domain_id}: {str(e)}")
                raise

    # =====================
    # Typed Subdomain Query
    # =====================
    @staticmethod
    async def search_subdomains_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        apex_domain: Optional[Union[str, List[str]]] = None,
        wildcard: Optional[bool] = None,
        has_ips: Optional[bool] = None,
        ip: Optional[Union[str, List[str]]] = None,
        has_cname: Optional[bool] = None,
        cname_contains: Optional[str] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed subdomain search optimized for PostgreSQL.

        Returns a dict with keys: items (list[dict]), total_count (int)
        """
        async with get_db_session() as db:
            try:

                # Build base query with LEFT JOIN to IPs for aggregation
                count_ip_col = func.count(func.distinct(IP.id))
                ip_array_col = func.array_remove(
                    func.array_agg(func.distinct(func.host(IP.ip_address))),
                    None,
                )

                base_query = (
                    db.query(
                        Subdomain.id.label("id"),
                        Subdomain.name.label("name"),
                        Program.name.label("program_name"),
                        ApexDomain.name.label("apex_domain"),
                        Subdomain.is_wildcard.label("is_wildcard"),
                        Subdomain.cname_record.label("cname_record"),
                        Subdomain.created_at.label("created_at"),
                        Subdomain.updated_at.label("updated_at"),
                        ip_array_col.label("ip"),
                        count_ip_col.label("ip_count"),
                    )
                    .select_from(Subdomain)
                    .join(Program, Program.id == Subdomain.program_id)
                    .join(ApexDomain, ApexDomain.id == Subdomain.apex_domain_id)
                    .outerjoin(SubdomainIP, Subdomain.id == SubdomainIP.subdomain_id)
                    .outerjoin(IP, IP.id == SubdomainIP.ip_id)
                )

                # Filters
                if programs is not None and len(programs) > 0:
                    base_query = base_query.filter(Program.name.in_(programs))

                if search:
                    base_query = base_query.filter(Subdomain.name.ilike(f"%{search}%"))
                
                if exact_match:
                    base_query = base_query.filter(Subdomain.name == exact_match)

                if apex_domain:
                    if isinstance(apex_domain, list):
                        base_query = base_query.filter(ApexDomain.name.in_(apex_domain))
                    else:
                        base_query = base_query.filter(ApexDomain.name == apex_domain)

                if wildcard is not None:
                    base_query = base_query.filter(Subdomain.is_wildcard == bool(wildcard))

                if has_cname is not None:
                    if has_cname:
                        base_query = base_query.filter(Subdomain.cname_record.isnot(None))
                    else:
                        base_query = base_query.filter(Subdomain.cname_record.is_(None))

                if cname_contains:
                    base_query = base_query.filter(Subdomain.cname_record.ilike(f"%{cname_contains}%"))

                # Filter by specific IP addresses
                if ip is not None:
                    if isinstance(ip, list):
                        if len(ip) > 0:
                            base_query = base_query.filter(func.host(IP.ip_address).in_(ip))
                    elif isinstance(ip, str) and ip.strip():
                        base_query = base_query.filter(func.host(IP.ip_address) == ip.strip())

                # Defer has_ips to HAVING with aggregated count to avoid correlated subquery issues
                _apply_has_ips_having = None
                if has_ips is not None:
                    if has_ips:
                        _apply_has_ips_having = func.count(func.distinct(IP.id)) > 0
                    else:
                        _apply_has_ips_having = func.count(func.distinct(IP.id)) == 0

                # Grouping for aggregation
                base_query = base_query.group_by(
                    Subdomain.id,
                    Subdomain.name,
                    Program.name,
                    ApexDomain.name,
                    Subdomain.is_wildcard,
                    Subdomain.cname_record,
                    Subdomain.created_at,
                    Subdomain.updated_at,
                )

                # Apply HAVING for has_ips if needed
                if _apply_has_ips_having is not None:
                    base_query = base_query.having(_apply_has_ips_having)

                # Sorting
                sort_by_normalized = (sort_by or "updated_at").lower()
                sort_dir_normalized = (sort_dir or "desc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "name":
                    base_query = base_query.order_by(direction_func(Subdomain.name))
                elif sort_by_normalized == "apex_domain":
                    base_query = base_query.order_by(direction_func(ApexDomain.name))
                elif sort_by_normalized == "program_name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "is_wildcard":
                    base_query = base_query.order_by(direction_func(Subdomain.is_wildcard))
                elif sort_by_normalized == "cname_record":
                    base_query = base_query.order_by(direction_func(Subdomain.cname_record))
                elif sort_by_normalized == "ip_count":
                    base_query = base_query.order_by(direction_func(count_ip_col))
                else:  # updated_at default
                    base_query = base_query.order_by(direction_func(Subdomain.updated_at))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                # Execute
                rows = base_query.all()

                items: List[Dict[str, Any]] = []
                for r in rows:
                    item = {
                        "id": str(r.id),
                        "name": r.name,
                        "program_name": r.program_name,
                        "apex_domain": r.apex_domain,
                        "is_wildcard": r.is_wildcard,
                        "cname_record": r.cname_record,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        "ip": list(r.ip) if r.ip else [],
                        "ip_count": int(r.ip_count or 0),
                    }
                    items.append(item)

                # Count total distinct subdomains matching filters
                # Build a subquery selecting matching subdomain ids for accurate counting
                count_base = (
                    db.query(Subdomain.id)
                    .select_from(Subdomain)
                    .join(Program, Program.id == Subdomain.program_id)
                    .join(ApexDomain, ApexDomain.id == Subdomain.apex_domain_id)
                    .outerjoin(SubdomainIP, Subdomain.id == SubdomainIP.subdomain_id)
                    .outerjoin(IP, IP.id == SubdomainIP.ip_id)
                )

                if programs is not None and len(programs) > 0:
                    count_base = count_base.filter(Program.name.in_(programs))

                if search:
                    count_base = count_base.filter(Subdomain.name.ilike(f"%{search}%"))

                if apex_domain:
                    if isinstance(apex_domain, list):
                        count_base = count_base.filter(ApexDomain.name.in_(apex_domain))
                    else:
                        count_base = count_base.filter(ApexDomain.name == apex_domain)

                if wildcard is not None:
                    count_base = count_base.filter(Subdomain.is_wildcard == bool(wildcard))

                if has_cname is not None:
                    if has_cname:
                        count_base = count_base.filter(Subdomain.cname_record.isnot(None))
                    else:
                        count_base = count_base.filter(Subdomain.cname_record.is_(None))

                if cname_contains:
                    count_base = count_base.filter(Subdomain.cname_record.ilike(f"%{cname_contains}%"))

                count_base = count_base.group_by(Subdomain.id)
                if _apply_has_ips_having is not None:
                    count_base = count_base.having(_apply_has_ips_having)

                total_count = db.query(func.count()).select_from(count_base.subquery()).scalar() or 0

                return {"items": items, "total_count": int(total_count)}

            except Exception as e:
                logger.error(f"Error executing typed subdomain search: {str(e)}")
                raise

    @staticmethod
    async def create_or_update_subdomain(
        subdomain_data: Dict[str, Any],
    ) -> tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Create a new subdomain or update if exists with merged data.
        Returns (subdomain_id, action, event_data, apex_created_event) where action is
        'created', 'updated', 'skipped', or 'out_of_scope'; event_data is the subdomain
        payload for the unified processor; apex_created_event is set when this call
        auto-created the ApexDomain row (for assets.apex_domain.created)."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == subdomain_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{subdomain_data.get('program_name')}' not found")
                
                # Scope check for the subdomain hostname
                hostname = subdomain_data.get('name')
                program_name = subdomain_data.get('program_name')
                if not hostname:
                    raise ValueError("'name' (subdomain) is required")
                if not await ProgramRepository.is_domain_in_scope(hostname, program_name):
                    logger.info(f"Subdomain '{hostname}' is out of scope for program '{program_name}'")
                    return "", "out_of_scope", None, None

                # Determine apex domain: use provided or extract from hostname
                apex_domain_name = subdomain_data.get('apex_domain') or extract_apex_domain(hostname)
                apex_auto_created = False
                apex_domain = db.query(ApexDomain).filter(
                    and_(ApexDomain.name == apex_domain_name, ApexDomain.program_id == program.id)
                ).first()
                if not apex_domain:
                    # Create apex domain if it doesn't exist
                    apex_domain = ApexDomain(
                        name=apex_domain_name,
                        program_id=program.id,
                        notes=None,
                    )
                    db.add(apex_domain)
                    db.commit()
                    db.refresh(apex_domain)
                    apex_auto_created = True

                apex_created_event: Optional[Dict[str, Any]] = None
                if apex_auto_created:
                    apex_created_event = {
                        "event": "asset.created",
                        "asset_type": "apex_domain",
                        "record_id": str(apex_domain.id),
                        "name": apex_domain_name,
                        "program_name": program_name,
                        "notes": None,
                        "whois_status": None,
                    }

                # Check if subdomain already exists for this program
                existing = db.query(Subdomain).filter(
                    and_(Subdomain.name == subdomain_data.get('name'), Subdomain.program_id == program.id)
                ).first()
                
                if existing:
                    # Check current IP count before any updates (for resolved event detection)
                    current_ip_count = db.query(SubdomainIP).filter(SubdomainIP.subdomain_id == existing.id).count()
                    # Also capture existing IP addresses BEFORE processing for enrichment detection
                    existing_ip_addresses = set()
                    existing_ips = db.query(IP.ip_address).join(
                        SubdomainIP, IP.id == SubdomainIP.ip_id
                    ).filter(SubdomainIP.subdomain_id == existing.id).all()
                    existing_ip_addresses = {ip[0] for ip in existing_ips}
                    logger.debug(f"Existing subdomain {subdomain_data.get('name')} (ID: {existing.id}): current IP count = {current_ip_count}, existing IPs = {existing_ip_addresses}")

                    # DEBUG: Log what data was sent
                    logger.debug(f"Subdomain finder data for {subdomain_data.get('name')}: {subdomain_data}")

                    # Track what fields actually changed for meaningful update detection
                    meaningful_changes = []

                    # Update is_wildcard if provided and different
                    if 'is_wildcard' in subdomain_data and subdomain_data.get('is_wildcard') != existing.is_wildcard:
                        existing.is_wildcard = subdomain_data.get('is_wildcard')
                        meaningful_changes.append('is_wildcard')

                    # Update cname_record if provided and different
                    if 'cname_record' in subdomain_data and subdomain_data.get('cname_record') != existing.cname_record:
                        existing.cname_record = subdomain_data.get('cname_record')
                        meaningful_changes.append('cname_record')

                    # Update wildcard_types if provided and different
                    provided_wildcard_types = (
                        subdomain_data.get('wildcard_types')
                        if subdomain_data.get('wildcard_types') is not None
                        else subdomain_data.get('wildcard_type')
                    )
                    if provided_wildcard_types is not None and provided_wildcard_types != existing.wildcard_types:
                        existing.wildcard_types = provided_wildcard_types
                        meaningful_changes.append('wildcard_types')

                    # Update apex domain if different (when provided/extracted)
                    # This is a data correction, not a meaningful update from the task's perspective
                    apex_domain_changed = False
                    if existing.apex_domain_id != apex_domain.id:
                        existing.apex_domain_id = apex_domain.id
                        apex_domain_changed = True
                        logger.debug(f"Corrected apex domain association for existing subdomain {subdomain_data.get('name')}")

                    # Update notes if provided and different
                    if subdomain_data.get('notes') and subdomain_data.get('notes') != existing.notes:
                        existing.notes = subdomain_data.get('notes')
                        meaningful_changes.append('notes')

                    # Merge IP relationships if provided
                    if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list):
                        logger.debug(f"Processing {len(subdomain_data['ip'])} IPs for existing subdomain {subdomain_data.get('name')}")
                        for ip_address in subdomain_data['ip']:
                            if not isinstance(ip_address, str):
                                continue
                            logger.debug(f"Processing IP {ip_address} for subdomain {subdomain_data.get('name')}")
                            ip = db.query(IP).filter(
                                and_(IP.ip_address == ip_address, IP.program_id == program.id)
                            ).first()
                            if not ip:
                                try:
                                    ip = IP(
                                        ip_address=ip_address,
                                        program_id=program.id,
                                    )
                                    db.add(ip)
                                    db.commit()
                                    db.refresh(ip)
                                    logger.debug(f"Created new IP {ip_address} with ID {ip.id}")
                                except IntegrityError:
                                    db.rollback()
                                    ip = db.query(IP).filter(IP.ip_address == ip_address).first()
                                    if not ip:
                                        raise
                            # Ensure relationship exists
                            rel_exists = (
                                db.query(SubdomainIP)
                                .filter(
                                    SubdomainIP.subdomain_id == existing.id,
                                    SubdomainIP.ip_id == ip.id,
                                )
                                .first()
                            )
                            if not rel_exists:
                                db.add(SubdomainIP(subdomain_id=existing.id, ip_id=ip.id))
                                db.commit()
                                logger.debug(f"Added IP relationship: subdomain {existing.id} -> IP {ip.id}")
                                meaningful_changes.append('ip_relationship')

                    # Check if subdomain was resolved or enriched with additional IPs
                    if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list) and len(subdomain_data['ip']) > 0:
                        new_ip_count = db.query(SubdomainIP).filter(SubdomainIP.subdomain_id == existing.id).count()
                        logger.debug(f"Subdomain {subdomain_data.get('name')}: current_ip_count={current_ip_count}, new_ip_count={new_ip_count}, has_ip_data={len(subdomain_data['ip'])}")

                        # Track newly added IPs for enrichment event
                        enriched_ips = []
                        if current_ip_count > 0 and new_ip_count > current_ip_count:
                            logger.debug(f"Checking for enrichment: current={current_ip_count}, new={new_ip_count}")
                            logger.debug(f"Existing IPs for subdomain (before processing): {existing_ip_addresses}")
                            logger.debug(f"Input IPs: {subdomain_data['ip']}")

                            # Check which IPs from the input were newly added
                            for ip_addr in subdomain_data['ip']:
                                if ip_addr not in existing_ip_addresses:
                                    enriched_ips.append(ip_addr)
                                    logger.debug(f"Found new IP: {ip_addr}")
                            logger.debug(f"Enriched IPs: {enriched_ips}")

                        if current_ip_count == 0 and new_ip_count > 0:
                            # Subdomain was resolved! Event publishing removed (handled by unified processor)
                            logger.info(f"Subdomain {subdomain_data.get('name')} was resolved (got first IP)")
                        elif current_ip_count > 0 and new_ip_count > current_ip_count and enriched_ips:
                            # Subdomain was enriched with additional IPs - event publishing removed (handled by unified processor)
                            logger.info(f"Subdomain {subdomain_data.get('name')} was enriched with {len(enriched_ips)} additional IP(s)")
                        else:
                            if current_ip_count > 0 and new_ip_count > current_ip_count:
                                logger.debug(f"Enrichment condition met but enriched_ips is empty: {enriched_ips}")
                            else:
                                logger.debug(f"Enrichment condition not met: current={current_ip_count}, new={new_ip_count}, enriched_ips={enriched_ips}")

                    # Update timestamp if any changes were made
                    if meaningful_changes:
                        existing.updated_at = datetime.now(timezone.utc)
                        #logger.debug(f"Updated existing subdomain {subdomain_data.get('name')}")
                    #else:
                    #    logger.debug(f"Subdomain {subdomain_data.get('name')} already exists with same data, skipping")

                    db.commit()

                    # Determine action based on what actually changed
                    # Only mark as "updated" if meaningful changes occurred, not just data corrections
                    logger.debug(f"Subdomain {subdomain_data.get('name')} - meaningful_changes: {meaningful_changes}, apex_domain_changed: {apex_domain_changed}")
                    if meaningful_changes:
                        # Meaningful changes occurred - this is a real update
                        action = "updated"
                        logger.debug(f"Subdomain {subdomain_data.get('name')} updated with changes: {meaningful_changes}")
                    elif apex_domain_changed:
                        # Only apex domain was corrected - this is not a meaningful update
                        action = "skipped"
                        logger.debug(f"Subdomain {subdomain_data.get('name')} had apex domain corrected, marked as skipped")
                    else:
                        # No changes at all - this is a duplicate/skipped operation
                        action = "skipped"
                        logger.debug(f"Subdomain {subdomain_data.get('name')} had no changes, marked as skipped")

                    # Prepare rich event data for unified processor
                    event_data = None
                    if action in ["updated"] and meaningful_changes:
                        # For updates, include the rich data that was changed
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "subdomain",
                            "record_id": str(existing.id),
                            "name": subdomain_data.get('name'),
                            "program_name": subdomain_data.get('program_name'),
                            "apex_domain": subdomain_data.get('apex_domain') or extract_apex_domain(subdomain_data.get('name')),
                            "ip": subdomain_data.get('ip', []),
                            "cname_record": subdomain_data.get('cname_record'),
                            "is_wildcard": subdomain_data.get('is_wildcard'),
                            "previous_ip_count": current_ip_count,
                            "new_ip_count": db.query(SubdomainIP).filter(SubdomainIP.subdomain_id == existing.id).count(),
                            "resolution_status": "enriched" if current_ip_count > 0 and db.query(SubdomainIP).filter(SubdomainIP.subdomain_id == existing.id).count() > current_ip_count else None
                        }

                    return str(existing.id), action, event_data, apex_created_event
                else:
                    # Create new subdomain
                    subdomain = Subdomain(
                        name=subdomain_data.get('name'),
                        apex_domain_id=apex_domain.id,
                        is_wildcard=subdomain_data.get('is_wildcard', False),
                        program_id=program.id,
                        cname_record=subdomain_data.get('cname_record'),
                        wildcard_types=(
                            subdomain_data.get('wildcard_types')
                            if subdomain_data.get('wildcard_types') is not None
                            else subdomain_data.get('wildcard_type', [])
                        ),
                        notes=subdomain_data.get('notes'),
                    )
                    
                    db.add(subdomain)
                    db.commit()
                    db.refresh(subdomain)
                    
                    # Handle IP relationships if provided
                    if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list):
                        for ip_address in subdomain_data['ip']:
                            if not isinstance(ip_address, str):
                                continue
                            ip = db.query(IP).filter(
                                and_(IP.ip_address == ip_address, IP.program_id == program.id)
                            ).first()
                            if not ip:
                                try:
                                    ip = IP(ip_address=ip_address, program_id=program.id)
                                    db.add(ip)
                                    db.commit()
                                    db.refresh(ip)
                                except IntegrityError:
                                    db.rollback()
                                    ip = db.query(IP).filter(IP.ip_address == ip_address).first()
                                    if not ip:
                                        raise
                            db.add(SubdomainIP(subdomain_id=subdomain.id, ip_id=ip.id))
                        db.commit()

                    # Check if newly created subdomain was created with IPs
                    if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list) and len(subdomain_data['ip']) > 0:
                        ip_count = len(subdomain_data['ip'])
                        # New subdomain with IPs - event publishing removed (handled by unified processor)
                        logger.info(f"New subdomain {subdomain_data.get('name')} was created with {ip_count} IP(s)")
                    else:
                        # New subdomain created without IPs - event publishing removed (handled by unified processor)
                        logger.info(f"New subdomain {subdomain_data.get('name')} was created without IPs")

                    # Prepare rich event data for newly created subdomain
                    event_data = {
                        "event": "asset.created",
                        "asset_type": "subdomain",
                        "record_id": str(subdomain.id),
                        "name": subdomain_data.get('name'),
                        "program_name": subdomain_data.get('program_name'),
                        "apex_domain": subdomain_data.get('apex_domain') or extract_apex_domain(subdomain_data.get('name')),
                        "ip": subdomain_data.get('ip', []),
                        "cname_record": subdomain_data.get('cname_record'),
                        "is_wildcard": subdomain_data.get('is_wildcard'),
                        "previous_ip_count": 0,
                        "new_ip_count": ip_count if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list) and len(subdomain_data['ip']) > 0 else 0,
                        "resolution_status": "created_resolved" if 'ip' in subdomain_data and isinstance(subdomain_data['ip'], list) and len(subdomain_data['ip']) > 0 else None
                    }

                    return str(subdomain.id), "created", event_data, apex_created_event
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating subdomain: {str(e)}")
                raise

    @staticmethod
    async def delete_subdomain(subdomain_id: str) -> bool:
        """Delete a single subdomain by ID"""
        async with get_db_session() as db:
            try:
                subdomain = db.query(Subdomain).filter(Subdomain.id == subdomain_id).first()
                if not subdomain:
                    return False
                
                db.delete(subdomain)
                db.commit()
                
                logger.info(f"Successfully deleted subdomain with ID: {subdomain_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting subdomain {subdomain_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_subdomains_batch(subdomain_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple subdomains by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for subdomain_id in subdomain_ids:
                    try:
                        # Skip null/undefined IDs
                        if subdomain_id is None:
                            error_count += 1
                            error_msg = "Invalid subdomain ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if subdomain_id == "":
                            error_count += 1
                            error_msg = "Invalid subdomain ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            subdomain_uuid = UUID(subdomain_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid subdomain ID format '{subdomain_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the subdomain
                        subdomain = db.query(Subdomain).filter(Subdomain.id == subdomain_uuid).first()
                        
                        if not subdomain:
                            not_found_count += 1
                            logger.warning(f"Subdomain with ID {subdomain_id} not found")
                            continue
                        
                        # Delete the subdomain
                        db.delete(subdomain)
                        deleted_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting subdomain {subdomain_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                logger.info(f"Batch delete completed for subdomains: {deleted_count} deleted, {not_found_count} not found, {error_count} errors")
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for subdomains: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in subdomain assets"""
        from sqlalchemy import func
        
        async with get_db_session() as db:
            try:
                query = db.query(Subdomain).join(Program, Program.id == Subdomain.program_id)
                
                # Apply program filter if provided
                if filter_data and filter_data.get('program_name'):
                    program_value = filter_data['program_name']
                    if isinstance(program_value, list):
                        if len(program_value) == 0:
                            return []
                        query = query.filter(Program.name.in_(program_value))
                    else:
                        query = query.filter(Program.name == program_value)
                
                # Get distinct values based on field name
                if field_name == 'name':
                    values = query.with_entities(Subdomain.name).distinct().all()
                elif field_name == 'apex_domain':
                    values = query.join(ApexDomain, ApexDomain.id == Subdomain.apex_domain_id).with_entities(ApexDomain.name).distinct().all()
                elif field_name == 'wildcard_types':
                    # For array fields, we need to unnest the arrays to get individual values
                    values = query.with_entities(func.unnest(Subdomain.wildcard_types)).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for subdomain assets")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in subdomain assets: {str(e)}")
                raise