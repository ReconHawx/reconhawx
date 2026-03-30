from typing import Dict, Any, Optional, List
from .program_repo import ProgramRepository
import logging
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import and_

from models.postgres import (
    Program, ApexDomain, Subdomain
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin

logger = logging.getLogger(__name__)

WHOIS_DATE_COLUMNS = frozenset(
    {
        "whois_creation_date",
        "whois_expiration_date",
        "whois_updated_date",
        "whois_checked_at",
    }
)

WHOIS_COLUMNS = frozenset(
    {
        "whois_status",
        "whois_registrar",
        "whois_creation_date",
        "whois_expiration_date",
        "whois_updated_date",
        "whois_name_servers",
        "whois_registrant_name",
        "whois_registrant_org",
        "whois_registrant_country",
        "whois_admin_email",
        "whois_tech_email",
        "whois_dnssec",
        "whois_registry_server",
        "whois_response_source",
        "whois_raw_response",
        "whois_error",
        "whois_checked_at",
    }
)


def _parse_optional_datetime(val: Any) -> Optional[datetime]:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


def _normalize_name_servers(val: Any) -> Optional[List[str]]:
    if val is None:
        return None
    if isinstance(val, str):
        val = [val]
    if not isinstance(val, list):
        return None
    out = [str(x).strip().lower() for x in val if x is not None and str(x).strip()]
    return out or None


def _coerce_whois_column(column: str, raw: Any) -> Any:
    if column in WHOIS_DATE_COLUMNS:
        return _parse_optional_datetime(raw)
    if column == "whois_name_servers":
        return _normalize_name_servers(raw)
    return raw


def _name_servers_equal(a: Any, b: Any) -> bool:
    ta = tuple(_normalize_name_servers(a) or [])
    tb = tuple(_normalize_name_servers(b) or [])
    return ta == tb


def _dt_equal(a: Optional[datetime], b: Optional[datetime]) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def _apex_domain_row_to_dict(apex_domain: ApexDomain) -> Dict[str, Any]:
    return {
        "id": str(apex_domain.id),
        "name": apex_domain.name,
        "program_name": apex_domain.program.name if apex_domain.program else None,
        "notes": apex_domain.notes,
        "created_at": apex_domain.created_at.isoformat() if apex_domain.created_at else None,
        "updated_at": apex_domain.updated_at.isoformat() if apex_domain.updated_at else None,
        "whois_status": apex_domain.whois_status,
        "whois_registrar": apex_domain.whois_registrar,
        "whois_creation_date": apex_domain.whois_creation_date.isoformat()
        if apex_domain.whois_creation_date
        else None,
        "whois_expiration_date": apex_domain.whois_expiration_date.isoformat()
        if apex_domain.whois_expiration_date
        else None,
        "whois_updated_date": apex_domain.whois_updated_date.isoformat()
        if apex_domain.whois_updated_date
        else None,
        "whois_name_servers": list(apex_domain.whois_name_servers)
        if apex_domain.whois_name_servers is not None
        else None,
        "whois_registrant_name": apex_domain.whois_registrant_name,
        "whois_registrant_org": apex_domain.whois_registrant_org,
        "whois_registrant_country": apex_domain.whois_registrant_country,
        "whois_admin_email": apex_domain.whois_admin_email,
        "whois_tech_email": apex_domain.whois_tech_email,
        "whois_dnssec": apex_domain.whois_dnssec,
        "whois_registry_server": apex_domain.whois_registry_server,
        "whois_response_source": apex_domain.whois_response_source,
        "whois_raw_response": apex_domain.whois_raw_response,
        "whois_error": apex_domain.whois_error,
        "whois_checked_at": apex_domain.whois_checked_at.isoformat()
        if apex_domain.whois_checked_at
        else None,
    }


def _apply_whois_from_payload(entity: ApexDomain, data: Dict[str, Any]) -> bool:
    """Set WHOIS columns from payload keys. Returns True if any column value changed."""
    if not any(k in data for k in WHOIS_COLUMNS):
        return False
    changed = False
    for col in WHOIS_COLUMNS:
        if col not in data:
            continue
        coerced = _coerce_whois_column(col, data[col])
        current = getattr(entity, col)
        if col == "whois_name_servers":
            if not _name_servers_equal(current, coerced):
                setattr(entity, col, coerced)
                changed = True
        elif col in WHOIS_DATE_COLUMNS:
            if not _dt_equal(current, coerced):
                setattr(entity, col, coerced)
                changed = True
        else:
            if current != coerced:
                setattr(entity, col, coerced)
                changed = True
    return changed

class ApexDomainAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def get_apex_domain_by_id(apex_domain_id: str) -> Optional[Dict[str, Any]]:
        """Get apex domain by ID"""
        async with get_db_session() as db:
            try:
                apex_domain = db.query(ApexDomain).filter(ApexDomain.id == apex_domain_id).first()
                if not apex_domain:
                    return None

                return _apex_domain_row_to_dict(apex_domain)
            except Exception as e:
                logger.error(f"Error getting apex domain by id {apex_domain_id}: {str(e)}")
                raise

    @staticmethod
    async def get_apex_domain_names_for_program(program_name: str) -> List[str]:
        """Return list of apex domain names for a program (for typosquat filtering)."""
        async with get_db_session() as db:
            try:
                rows = (
                    db.query(ApexDomain.name)
                    .join(Program, Program.id == ApexDomain.program_id)
                    .filter(Program.name == program_name)
                    .all()
                )
                return [r[0].lower() for r in rows if r[0]]
            except Exception as e:
                logger.error(f"Error getting apex domain names for program {program_name}: {str(e)}")
                raise

    # Update methods
    @staticmethod
    async def update_apex_domain(apex_domain_id: str, apex_domain_data: Dict[str, Any]) -> bool:
        """Update an apex domain"""
        async with get_db_session() as db:
            try:
                apex_domain = db.query(ApexDomain).filter(ApexDomain.id == apex_domain_id).first()
                if not apex_domain:
                    return False
                
                for key, value in apex_domain_data.items():
                    if hasattr(apex_domain, key):
                        setattr(apex_domain, key, value)
                
                apex_domain.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating apex domain {apex_domain_id}: {str(e)}")
                raise

    # =====================
    # Typed Apex Domains Search
    # =====================
    @staticmethod
    async def search_apex_domains_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        program: Optional[List[str]] = None,
        sort_by: str = "name",
        sort_dir: str = "asc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Typed search for apex domains with pagination and sorting."""
        async with get_db_session() as db:
            try:
                # Base query
                query = db.query(ApexDomain).join(Program, Program.id == ApexDomain.program_id)

                # Filters
                if program is not None:
                    if isinstance(program, list) and len(program) == 0:
                        return {"items": [], "total_count": 0}
                    if isinstance(program, list):
                        query = query.filter(Program.name.in_(program))
                    else:
                        query = query.filter(Program.name == program)

                if search:
                    query = query.filter(ApexDomain.name.ilike(f"%{search}%"))
                
                if exact_match:
                    query = query.filter(ApexDomain.name == exact_match)

                # Count before pagination
                total_count = query.count()

                # Sorting
                sort_col = ApexDomain.name
                if sort_by == "program_name":
                    sort_col = Program.name
                elif sort_by == "updated_at":
                    sort_col = ApexDomain.updated_at
                elif sort_by == "created_at":
                    sort_col = ApexDomain.created_at

                if sort_dir == "desc":
                    sort_col = sort_col.desc()

                query = query.order_by(sort_col)

                # Pagination
                if skip:
                    query = query.offset(skip)
                if limit:
                    query = query.limit(limit)

                rows = query.all()

                items: List[Dict[str, Any]] = [_apex_domain_row_to_dict(a) for a in rows]

                return {"items": items, "total_count": total_count}

            except Exception as e:
                logger.error(f"Error executing typed apex domains search: {str(e)}")
                raise

    @staticmethod
    async def delete_apex_domains_with_subdomains(apex_domain_ids: List[str]) -> Dict[str, Any]:
        """Delete apex domains and their associated subdomains"""
        async with get_db_session() as db:
            try:
                deleted_apex_count = 0
                deleted_subdomain_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for apex_domain_id in apex_domain_ids:
                    try:
                        # Skip null/undefined IDs
                        if apex_domain_id is None:
                            error_count += 1
                            error_msg = "Invalid apex domain ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if apex_domain_id == "":
                            error_count += 1
                            error_msg = "Invalid apex domain ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            apex_domain_uuid = UUID(apex_domain_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid apex domain ID format '{apex_domain_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the apex domain
                        apex_domain = db.query(ApexDomain).filter(ApexDomain.id == apex_domain_uuid).first()
                        
                        if not apex_domain:
                            not_found_count += 1
                            logger.warning(f"Apex domain with ID {apex_domain_id} not found")
                            continue
                        
                        # Find and delete all subdomains associated with this apex domain
                        subdomains = db.query(Subdomain).filter(Subdomain.apex_domain_id == apex_domain_uuid).all()
                        for subdomain in subdomains:
                            db.delete(subdomain)
                            deleted_subdomain_count += 1
                        
                        # Delete the apex domain
                        db.delete(apex_domain)
                        deleted_apex_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting apex domain {apex_domain_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                                
                return {
                    "deleted_apex_count": deleted_apex_count,
                    "deleted_subdomain_count": deleted_subdomain_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for apex domains: {str(e)}")
                raise

    @staticmethod
    async def create_or_update_apex_domain(apex_domain_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new apex domain or update if exists with merged data.
        Returns (apex_domain_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == apex_domain_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{apex_domain_data.get('program_name')}' not found")
                
                # Check if apex domain already exists for this program
                existing = db.query(ApexDomain).filter(
                    and_(ApexDomain.name == apex_domain_data.get('name'), ApexDomain.program_id == program.id)
                ).first()
                
                if not existing:
                    # Check if domain is in program scope (only for new apex domains)
                    hostname = apex_domain_data.get('name')
                    program_name = apex_domain_data.get('program_name')
                    if not await ProgramRepository.is_domain_in_scope(hostname, program_name):
                        raise ValueError(f"Domain '{hostname}' is not in scope for program '{program_name}'")
                
                has_whois_payload = any(
                    k in apex_domain_data
                    for k in WHOIS_COLUMNS
                    if k != "whois_checked_at"
                )
                now_naive = datetime.now(timezone.utc).replace(tzinfo=None)

                if existing:
                    # Check if data is different and update if needed
                    updated = False
                    
                    # Update notes if provided
                    if apex_domain_data.get('notes') is not None and apex_domain_data.get('notes') != existing.notes:
                        existing.notes = apex_domain_data.get('notes')
                        updated = True

                    if has_whois_payload:
                        if _apply_whois_from_payload(existing, apex_domain_data):
                            updated = True
                        existing.whois_checked_at = now_naive
                        updated = True
                    
                    # Update timestamp if any changes were made
                    if updated:
                        existing.updated_at = datetime.now(timezone.utc)
                    
                    db.commit()
                    action = "updated" if updated else "skipped"
                    return str(existing.id), action
                else:
                    # Create new apex domain
                    apex_domain = ApexDomain(
                        name=apex_domain_data.get('name'),
                        program_id=program.id,
                        notes=apex_domain_data.get('notes')
                    )
                    if has_whois_payload:
                        _apply_whois_from_payload(apex_domain, apex_domain_data)
                        apex_domain.whois_checked_at = now_naive
                    
                    db.add(apex_domain)
                    db.commit()
                    db.refresh(apex_domain)
                    
                    return str(apex_domain.id), "created"  # Newly created asset
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating apex domain: {str(e)}")
                raise

    @staticmethod
    async def delete_apex_domain(apex_domain_id: str) -> bool:
        """Delete a single apex domain by ID"""
        async with get_db_session() as db:
            try:
                apex_domain = db.query(ApexDomain).filter(ApexDomain.id == apex_domain_id).first()
                if not apex_domain:
                    return False
                
                db.delete(apex_domain)
                db.commit()
                
                logger.info(f"Successfully deleted apex domain with ID: {apex_domain_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting apex domain {apex_domain_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_apex_domains_batch(apex_domain_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple apex domains by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for apex_domain_id in apex_domain_ids:
                    try:
                        # Skip null/undefined IDs
                        if apex_domain_id is None:
                            error_count += 1
                            error_msg = "Invalid apex domain ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if apex_domain_id == "":
                            error_count += 1
                            error_msg = "Invalid apex domain ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            apex_domain_uuid = UUID(apex_domain_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid apex domain ID format '{apex_domain_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the apex domain
                        apex_domain = db.query(ApexDomain).filter(ApexDomain.id == apex_domain_uuid).first()
                        
                        if not apex_domain:
                            not_found_count += 1
                            logger.warning(f"Apex domain with ID {apex_domain_id} not found")
                            continue
                        
                        # Delete the apex domain
                        db.delete(apex_domain)
                        deleted_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting apex domain {apex_domain_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for apex domains: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in apex domain assets"""
        
        async with get_db_session() as db:
            try:
                query = db.query(ApexDomain).join(Program, Program.id == ApexDomain.program_id)
                
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
                    values = query.with_entities(ApexDomain.name).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for apex domain assets")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in apex domain assets: {str(e)}")
                raise
