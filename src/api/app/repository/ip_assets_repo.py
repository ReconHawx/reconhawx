from sqlalchemy import and_, or_, func, desc, asc
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, Optional, List, Union
import logging
from datetime import datetime, timezone
from uuid import UUID


from models.postgres import (
    Program, IP
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin
from services.event_publisher import publisher
from repository.program_repo import ProgramRepository

logger = logging.getLogger(__name__)

class IPAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def get_ip_by_id(ip_id: str) -> Optional[Dict[str, Any]]:
        """Get IP by ID"""
        async with get_db_session() as db:
            try:
                ip = db.query(IP).filter(IP.id == ip_id).first()
                if not ip:
                    return None

                return {
                    'id': str(ip.id),
                    'ip': ip.ip_address,
                    'program_name': ip.program.name if ip.program else None,
                    'ptr': ip.ptr_record,
                    'service_provider': ip.service_provider,
                    'notes': ip.notes,
                    'created_at': ip.created_at.isoformat() if ip.created_at else None,
                    'updated_at': ip.updated_at.isoformat() if ip.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting IP by id {ip_id}: {str(e)}")
                raise

    # Update methods
    @staticmethod
    async def update_ip(ip_id: str, ip_data: Dict[str, Any]) -> bool:
        """Update an IP"""
        async with get_db_session() as db:
            try:
                ip = db.query(IP).filter(IP.id == ip_id).first()
                if not ip:
                    return False
                
                for key, value in ip_data.items():
                    if hasattr(ip, key):
                        setattr(ip, key, value)
                
                ip.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating IP {ip_id}: {str(e)}")
                raise

    # =================
    # Typed IPs Query
    # =================
    @staticmethod
    async def search_ips_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        program: Optional[Union[str, List[str]]] = None,
        has_ptr: Optional[bool] = None,
        ptr_contains: Optional[str] = None,
        service_provider: Optional[Union[str, List[str]]] = None,
        has_service_provider: Optional[bool] = None,
        sort_by: str = "ip_address",
        sort_dir: str = "asc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Execute a strongly-typed IP search optimized for PostgreSQL."""
        async with get_db_session() as db:
            try:
                # Base select with explicit from and join
                base_query = (
                    db.query(
                        IP.id.label("id"),
                        IP.ip_address.label("ip_address"),
                        Program.name.label("program_name"),
                        IP.ptr_record.label("ptr_record"),
                        IP.service_provider.label("service_provider"),
                        IP.created_at.label("created_at"),
                        IP.updated_at.label("updated_at"),
                    )
                    .select_from(IP)
                    .join(Program, Program.id == IP.program_id)
                )

                # Filters
                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": [], "total_count": 0}
                        base_query = base_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        base_query = base_query.filter(Program.name == program.strip())

                if search:
                    base_query = base_query.filter(func.host(IP.ip_address).ilike(f"%{search}%"))
                
                if exact_match:
                    base_query = base_query.filter(IP.ip_address == exact_match)

                if has_ptr is not None:
                    if has_ptr:
                        base_query = base_query.filter(and_(IP.ptr_record.isnot(None), IP.ptr_record != ""))
                    else:
                        base_query = base_query.filter(or_(IP.ptr_record.is_(None), IP.ptr_record == ""))
            
                if ptr_contains:
                    base_query = base_query.filter(IP.ptr_record.ilike(f"%{ptr_contains}%"))
                
                if service_provider is not None:
                    if isinstance(service_provider, list):
                        #if len(service_provider) == 0:
                        #    return {"items": [], "total_count": 0}
                        base_query = base_query.filter(IP.service_provider.in_(service_provider))
                    elif (isinstance(service_provider, str) and service_provider) or service_provider == "":
                        if service_provider == "":
                            base_query = base_query.filter(IP.service_provider == None)
                        else:
                            base_query = base_query.filter(IP.service_provider == service_provider)

                if has_service_provider is not None:
                    if has_service_provider:
                        base_query = base_query.filter(IP.service_provider.isnot(None), IP.service_provider != "")
                    else:
                        base_query = base_query.filter(or_(IP.service_provider.is_(None), IP.service_provider == ""))
                
                # Sorting
                sort_by_normalized = (sort_by or "ip_address").lower()
                sort_dir_normalized = (sort_dir or "asc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "ip_address":
                    base_query = base_query.order_by(direction_func(IP.ip_address))
                elif sort_by_normalized == "program_name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "ptr_record":
                    base_query = base_query.order_by(direction_func(IP.ptr_record))
                elif sort_by_normalized == "service_provider":
                    base_query = base_query.order_by(direction_func(IP.service_provider))
                else:  # updated_at default
                    base_query = base_query.order_by(direction_func(IP.updated_at))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)
                # Execute
                rows = base_query.all()
                items: List[Dict[str, Any]] = []

                for r in rows:
                    items.append(
                        {
                            "id": str(r.id),
                            "ip_address": str(r.ip_address),
                            "program_name": r.program_name,
                            "ptr_record": r.ptr_record,
                            "service_provider": r.service_provider,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        }
                    )

                # Count
                count_query = (
                    db.query(func.count(IP.id))
                    .select_from(IP)
                    .join(Program, Program.id == IP.program_id)
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        count_query = count_query.filter(Program.name == program.strip())

                if search:
                    count_query = count_query.filter(func.host(IP.ip_address).ilike(f"%{search}%"))
                
                if exact_match:
                    count_query = count_query.filter(IP.ip_address == exact_match)

                if has_ptr is not None:
                    if has_ptr:
                        count_query = count_query.filter(and_(IP.ptr_record.isnot(None), IP.ptr_record != ""))
                    else:
                        count_query = count_query.filter(or_(IP.ptr_record.is_(None), IP.ptr_record == ""))

                if ptr_contains:
                    count_query = count_query.filter(IP.ptr_record.ilike(f"%{ptr_contains}%"))

                if service_provider is not None:
                    if isinstance(service_provider, list):
                        if len(service_provider) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(IP.service_provider.in_(service_provider))
                    elif isinstance(service_provider, str) and service_provider:
                        count_query = count_query.filter(IP.service_provider == service_provider)

                total_count = count_query.scalar() or 0

                return {"items": items, "total_count": int(total_count)}

            except Exception as e:
                logger.error(f"Error executing typed IP search: {str(e)}")
                raise

    @staticmethod
    async def create_or_update_ip(ip_data: Dict[str, Any]) -> tuple[str, str, Optional[Dict[str, Any]]]:
        """Create a new IP or update if exists with merged data.
        Returns (ip_id, action, event_data) where action is 'created', 'updated', 'skipped', or
        'out_of_scope' (empty ip_id when discovered_via_domain is out of program scope)."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == ip_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{ip_data.get('program_name')}' not found")

                disco = ip_data.get("discovered_via_domain")
                if disco and not await ProgramRepository.is_domain_in_scope(disco, program.name):
                    logger.info(
                        f"Skipping IP {ip_data.get('ip')}: hostname '{disco}' is out of scope "
                        f"for program '{program.name}'"
                    )
                    return "", "out_of_scope", None

                # Check if IP already exists for this program
                existing = db.query(IP).filter(
                    and_(IP.ip_address == ip_data.get('ip'), IP.program_id == program.id)
                ).first()
                
                if existing:
                    # Track what fields actually changed for meaningful update detection
                    meaningful_changes = []

                    # Update ptr_record if provided and different
                    if ip_data.get('ptr') and ip_data.get('ptr') != existing.ptr_record:
                        existing.ptr_record = ip_data.get('ptr')
                        meaningful_changes.append('ptr_record')

                    # Update service_provider if provided and different
                    if ip_data.get('service_provider') and ip_data.get('service_provider') != existing.service_provider:
                        existing.service_provider = ip_data.get('service_provider')
                        meaningful_changes.append('service_provider')

                    # Update notes if provided and different
                    if ip_data.get('notes') and ip_data.get('notes') != existing.notes:
                        existing.notes = ip_data.get('notes')
                        meaningful_changes.append('notes')

                    # Update timestamp if any changes were made
                    if meaningful_changes:
                        existing.updated_at = datetime.now(timezone.utc)
                        logger.info(f"IP {ip_data.get('ip')} was updated with changes: {meaningful_changes}")
                    #else:
                    #    logger.debug(f"IP {ip_data.get('ip')} already exists with same data, skipping")

                    db.commit()

                    # Determine action based on what actually changed
                    # Only mark as "updated" if meaningful changes occurred
                    if meaningful_changes:
                        # Meaningful changes occurred - this is a real update
                        action = "updated"
                        logger.debug(f"IP {ip_data.get('ip')} updated with changes: {meaningful_changes}")
                    else:
                        # No meaningful changes - this is a duplicate/skipped operation
                        action = "skipped"
                        logger.debug(f"IP {ip_data.get('ip')} had no meaningful changes, marked as skipped")

                    # Prepare rich event data for unified processor
                    event_data = None
                    if action == "updated" and meaningful_changes:
                        # For updates, include the rich data that was changed
                        event_data = {
                            "event": "asset.updated",
                            "asset_type": "ip",
                            "record_id": str(existing.id),
                            "ip_address": ip_data.get('ip'),
                            "program_name": ip_data.get('program_name'),
                            "ptr_record": ip_data.get('ptr'),
                            "service_provider": ip_data.get('service_provider'),
                            "notes": ip_data.get('notes')
                        }

                    return str(existing.id), action, event_data
                else:
                    # Create new IP (or use existing if race condition)
                    try:
                        ip = IP(
                            ip_address=ip_data.get('ip'),
                            ptr_record=ip_data.get('ptr'),
                            service_provider=ip_data.get('service_provider'),
                            program_id=program.id,
                            notes=ip_data.get('notes')
                        )
                        db.add(ip)
                        db.commit()
                        db.refresh(ip)
                        logger.info(f"IP {ip_data.get('ip')} was created")
                        event_data = {
                            "event": "asset.created",
                            "asset_type": "ip",
                            "record_id": str(ip.id),
                            "ip_address": ip_data.get('ip'),
                            "program_name": ip_data.get('program_name'),
                            "ptr_record": ip_data.get('ptr'),
                            "service_provider": ip_data.get('service_provider'),
                            "notes": ip_data.get('notes')
                        }
                        return str(ip.id), "created", event_data
                    except IntegrityError:
                        # Race condition: IP was created by concurrent request. Fetch and update existing.
                        db.rollback()
                        ip = db.query(IP).filter(IP.ip_address == ip_data.get('ip')).first()
                        if not ip:
                            raise
                        meaningful_changes = []
                        if ip_data.get('ptr') and ip_data.get('ptr') != ip.ptr_record:
                            ip.ptr_record = ip_data.get('ptr')
                            meaningful_changes.append('ptr_record')
                        if ip_data.get('service_provider') and ip_data.get('service_provider') != ip.service_provider:
                            ip.service_provider = ip_data.get('service_provider')
                            meaningful_changes.append('service_provider')
                        if ip_data.get('notes') and ip_data.get('notes') != ip.notes:
                            ip.notes = ip_data.get('notes')
                            meaningful_changes.append('notes')
                        if meaningful_changes:
                            ip.updated_at = datetime.now(timezone.utc)
                            logger.info(f"IP {ip_data.get('ip')} was updated (from race) with changes: {meaningful_changes}")
                        db.commit()
                        db.refresh(ip)
                        action = "updated" if meaningful_changes else "skipped"
                        event_data = {
                            "event": "asset.updated" if meaningful_changes else None,
                            "asset_type": "ip",
                            "record_id": str(ip.id),
                            "ip_address": ip_data.get('ip'),
                            "program_name": ip_data.get('program_name'),
                            "ptr_record": ip.ptr_record,
                            "service_provider": ip.service_provider,
                            "notes": ip.notes
                        } if meaningful_changes else None
                        return str(ip.id), action, event_data
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating IP: {str(e)}")
                raise

    @staticmethod
    async def delete_ip(ip_id: str) -> bool:
        """Delete a single IP by ID"""
        async with get_db_session() as db:
            try:
                ip = db.query(IP).filter(IP.id == ip_id).first()
                if not ip:
                    return False

                # Capture IP data before deletion for event publishing
                ip_data = {
                    "id": str(ip.id),
                    "ip_address": ip.ip_address,
                    "program_name": ip.program.name if ip.program else None,
                    "ptr_record": ip.ptr_record,
                    "service_provider": ip.service_provider,
                    "notes": ip.notes
                }

                db.delete(ip)
                db.commit()

                # Publish IP deleted event
                logger.info(f"IP {ip_data['ip_address']} was deleted")
                try:
                    event_payload = {
                        "event": "asset.deleted",
                        "asset_type": "ip",
                        "record_id": ip_data["id"],
                        "ip_address": ip_data["ip_address"],
                        "program_name": ip_data["program_name"],
                        "ptr_record": ip_data["ptr_record"],
                        "service_provider": ip_data["service_provider"],
                        "notes": ip_data["notes"]
                    }
                    logger.debug(f"Publishing IP deleted event for {ip_data['ip_address']}: {event_payload}")
                    await publisher.publish_immediate(
                        "events.assets.ip.deleted",
                        event_payload
                    )
                    logger.info(f"Successfully published IP deleted event for {ip_data['ip_address']}")
                except Exception as e:
                    logger.error(f"Failed to publish IP deleted event for {ip_data['ip_address']}: {e}")

                return True

            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting IP {ip_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_ips_batch(ip_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple IPs by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for ip_id in ip_ids:
                    try:
                        # Skip null/undefined IDs
                        if ip_id is None:
                            error_count += 1
                            error_msg = "Invalid IP ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if ip_id == "":
                            error_count += 1
                            error_msg = "Invalid IP ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            ip_uuid = UUID(ip_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid IP ID format '{ip_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the IP
                        ip = db.query(IP).filter(IP.id == ip_uuid).first()

                        if not ip:
                            not_found_count += 1
                            logger.warning(f"IP with ID {ip_id} not found")
                            continue

                        # Capture IP data before deletion for event publishing
                        ip_data = {
                            "id": str(ip.id),
                            "ip_address": ip.ip_address,
                            "program_name": ip.program.name if ip.program else None,
                            "ptr_record": ip.ptr_record,
                            "service_provider": ip.service_provider,
                            "notes": ip.notes
                        }

                        # Delete the IP
                        db.delete(ip)
                        deleted_count += 1

                        # Publish IP deleted event for each successful deletion
                        try:
                            event_payload = {
                                "event": "asset.deleted",
                                "asset_type": "ip",
                                "record_id": ip_data["id"],
                                "ip_address": ip_data["ip_address"],
                                "program_name": ip_data["program_name"],
                                "ptr_record": ip_data["ptr_record"],
                                "service_provider": ip_data["service_provider"],
                                "notes": ip_data["notes"]
                            }
                            logger.debug(f"Publishing IP deleted event for {ip_data['ip_address']}: {event_payload}")
                            await publisher.publish_immediate(
                                "events.assets.ip.deleted",
                                event_payload
                            )
                            logger.debug(f"Successfully published IP deleted event for {ip_data['ip_address']}")
                        except Exception as e:
                            logger.error(f"Failed to publish IP deleted event for {ip_data['ip_address']}: {e}")
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting IP {ip_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                logger.info(f"Batch delete completed for IPs: {deleted_count} deleted, {not_found_count} not found, {error_count} errors")
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for IPs: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in IP assets"""
        
        async with get_db_session() as db:
            try:
                query = db.query(IP).join(Program, Program.id == IP.program_id, isouter=True)
                
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
                if field_name == 'ip':
                    values = query.with_entities(IP.ip_address).distinct().all()
                elif field_name == 'ptr_record':
                    values = query.with_entities(IP.ptr_record).distinct().all()
                elif field_name == 'service_provider':
                    values = query.with_entities(IP.service_provider).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for IP assets")
                
                return [str(v[0]) for v in values if v[0] is not None]

            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in IP assets: {str(e)}")
                raise

    @staticmethod
    async def batch_check_ips_exist(ip_addresses: List[str], programs: Optional[List[str]] = None) -> set:
        """
        Check which IP addresses exist in the database for the given programs.
        Optimized for batch processing of large numbers of IPs.

        Args:
            ip_addresses: List of IP addresses to check
            programs: Optional list of program names to filter by

        Returns:
            Set of IP addresses that exist in the database
        """
        async with get_db_session() as db:
            try:
                # Build query to find existing IPs
                query = db.query(IP.ip_address).join(Program, Program.id == IP.program_id)

                # Filter by IP addresses
                if ip_addresses:
                    query = query.filter(IP.ip_address.in_(ip_addresses))

                # Filter by programs if specified
                if programs:
                    query = query.filter(Program.name.in_(programs))

                # Execute query and get results
                existing_ips = query.distinct().all()

                # Convert to set for fast lookup
                existing_ip_set = {str(ip[0]) for ip in existing_ips}

                logger.info(f"Batch IP check: found {len(existing_ip_set)} existing IPs out of {len(ip_addresses)} checked")
                return existing_ip_set

            except Exception as e:
                logger.error(f"Error in batch IP existence check: {str(e)}")
                raise

