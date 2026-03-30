from sqlalchemy import and_, or_, func, desc, asc, String, literal
from sqlalchemy.exc import IntegrityError
from typing import Dict, Any, Optional, List, Union
import logging
from datetime import datetime, timezone
from uuid import UUID

from models.postgres import (
    Program, IP, Service
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin
from services.event_publisher import publisher

logger = logging.getLogger(__name__)

# Common ports to exclude when "uncommon ports only" filter is enabled.
# Curated list of standard/default ports (not the full 0-1023 range, so alternative
# ports like 1022/SSH, 8080/HTTP, 8443/HTTPS are shown).
COMMON_PORTS = frozenset({
    21, 22, 23, 25, 53, 80, 110, 143, 443, 445, 993, 995,  # FTP, SSH, Telnet, SMTP, DNS, HTTP, POP3, IMAP, HTTPS, SMB, IMAPS, POP3S
    3306, 3389, 5432, 5900, 6379, 27017,  # MySQL, RDP, PostgreSQL, VNC, Redis, MongoDB
})

class ServiceAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    # Get by specific field methods
    @staticmethod
    async def get_service_by_ip_port(ip: str, port: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Get service by IP and port"""
        async with get_db_session() as db:
            try:
                port_int = int(port) if isinstance(port, str) else port
                service = db.query(Service).join(IP).filter(
                    and_(IP.ip_address == ip, Service.port == port_int)
                ).first()
                if not service:
                    return None
                
                return {
                    'id': str(service.id),
                    'ip': service.ip.ip_address,
                    'ip_id': str(service.ip.id) if service.ip else None,
                    'port': service.port,
                    'program_name': service.program.name if service.program else None,
                    'service_name': service.service_name,
                    'protocol': service.protocol,
                    'banner': service.banner,
                    'notes': service.notes,
                    'nerva_metadata': service.nerva_metadata,
                    'created_at': service.created_at.isoformat() if service.created_at else None,
                    'updated_at': service.updated_at.isoformat() if service.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting service by IP {ip} and port {port}: {str(e)}")
                raise

    @staticmethod
    async def get_service_by_id(service_id: str) -> Optional[Dict[str, Any]]:
        """Get service by ID"""
        async with get_db_session() as db:
            try:
                service = db.query(Service).join(IP).filter(Service.id == service_id).first()
                if not service:
                    return None

                return {
                    'id': str(service.id),
                    'ip': service.ip.ip_address if service.ip else None,
                    'ip_id': str(service.ip.id) if service.ip else None,
                    'port': service.port,
                    'program_name': service.program.name if service.program else None,
                    'service_name': service.service_name,
                    'protocol': service.protocol,
                    'banner': service.banner,
                    'notes': service.notes,
                    'nerva_metadata': service.nerva_metadata,
                    'created_at': service.created_at.isoformat() if service.created_at else None,
                    'updated_at': service.updated_at.isoformat() if service.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting service by id {service_id}: {str(e)}")
                raise

    # Update methods
    @staticmethod
    async def update_service(service_id: str, service_data: Dict[str, Any]) -> bool:
        """Update a service"""
        async with get_db_session() as db:
            try:
                service = db.query(Service).filter(Service.id == service_id).first()
                if not service:
                    return False
                
                for key, value in service_data.items():
                    if hasattr(service, key):
                        setattr(service, key, value)
                
                service.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating service {service_id}: {str(e)}")
                raise
    
    # ==================
    # Typed Services Query
    # ==================
    @staticmethod
    async def search_services_typed(
        *,
        ip_port_text: Optional[str] = None,
        search_ip: Optional[str] = None,
        exact_match_ip: Optional[str] = None,
        exact_match: Optional[str] = None,
        port: Optional[int] = None,
        protocol: Optional[str] = None,
        service_name: Optional[str] = None,
        service_text: Optional[str] = None,
        ip_port_or: bool = False,
        exclude_common_ports: bool = False,
        program: Optional[Union[str, List[str]]] = None,
        sort_by: str = "ip",
        sort_dir: str = "asc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        async with get_db_session() as db:
            try:
                base_query = (
                    db.query(
                        Service.id.label("id"),
                        func.host(IP.ip_address).label("ip"),
                        Service.port.label("port"),
                        Service.service_name.label("service_name"),
                        Service.protocol.label("protocol"),
                        Service.banner.label("banner"),
                        Service.nerva_metadata.label("nerva_metadata"),
                        Program.name.label("program_name"),
                        Service.created_at.label("created_at"),
                        Service.updated_at.label("updated_at"),
                    )
                    .select_from(Service)
                    .join(IP, IP.id == Service.ip_id)
                    .join(Program, Program.id == Service.program_id)
                )

                # Filters
                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": [], "total_count": 0}
                        base_query = base_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        base_query = base_query.filter(Program.name == program.strip())

                # Prefer ip_port_text if provided
                if ip_port_text:
                    ip_port_expr = func.concat(func.host(IP.ip_address), literal(':'), func.cast(Service.port, String))
                    base_query = base_query.filter(ip_port_expr.ilike(f"%{ip_port_text}%"))
                elif search_ip and port is not None:
                    # support IP or port matching when requested
                    if ip_port_or:
                        base_query = base_query.filter(
                            or_(
                                func.host(IP.ip_address).ilike(f"%{search_ip}%"),
                                Service.port == int(port),
                            )
                        )
                    else:
                        base_query = base_query.filter(
                            and_(
                                func.host(IP.ip_address).ilike(f"%{search_ip}%"),
                                Service.port == int(port),
                            )
                        )
                elif search_ip:
                    base_query = base_query.filter(func.host(IP.ip_address).ilike(f"%{search_ip}%"))
                elif port is not None:
                    base_query = base_query.filter(Service.port == int(port))
                
                # Add exact match IP+port filter (independent of other IP filters)
                if exact_match:
                    # Parse IP:port format like "20.151.252.42:80"
                    if ':' in exact_match:
                        try:
                            ip_part, port_part = exact_match.split(':', 1)
                            base_query = base_query.filter(
                                and_(
                                    IP.ip_address == ip_part.strip(),
                                    Service.port == int(port_part.strip())
                                )
                            )
                        except (ValueError, IndexError):
                            # Invalid format, ignore the filter
                            pass
                    else:
                        # If no colon, treat as IP-only exact match
                        base_query = base_query.filter(IP.ip_address == exact_match)
                
                # Add exact match IP filter (independent of other IP filters)
                if exact_match_ip:
                    base_query = base_query.filter(IP.ip_address == exact_match_ip)
                if protocol:
                    base_query = base_query.filter(Service.protocol == protocol)
                if service_name:
                    base_query = base_query.filter(Service.service_name == service_name)
                if service_text:
                    like = f"%{service_text}%"
                    # ONLY search service_name for text filter per requirement
                    base_query = base_query.filter(Service.service_name.ilike(like))

                # Exclude common ports (curated list; alternative ports like 1022, 8080, 8443 are shown)
                if exclude_common_ports:
                    base_query = base_query.filter(Service.port.notin_(COMMON_PORTS))

                # Sorting
                sort_by_normalized = (sort_by or "ip").lower()
                sort_dir_normalized = (sort_dir or "asc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "ip":
                    base_query = base_query.order_by(direction_func(func.host(IP.ip_address)))
                elif sort_by_normalized == "port":
                    base_query = base_query.order_by(direction_func(Service.port))
                elif sort_by_normalized == "service_name":
                    base_query = base_query.order_by(direction_func(Service.service_name))
                elif sort_by_normalized == "protocol":
                    base_query = base_query.order_by(direction_func(Service.protocol))
                elif sort_by_normalized == "banner":
                    base_query = base_query.order_by(direction_func(Service.banner))
                elif sort_by_normalized == "program_name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "updated_at":
                    base_query = base_query.order_by(direction_func(Service.updated_at))
                else:
                    base_query = base_query.order_by(direction_func(func.host(IP.ip_address)))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for r in rows:
                    items.append(
                        {
                            "id": str(r.id),
                            "ip": r.ip,
                            "port": r.port,
                            "service_name": r.service_name,
                            "protocol": r.protocol,
                            "banner": r.banner,
                            "nerva_metadata": r.nerva_metadata,
                            "program_name": r.program_name,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                        }
                    )

                # Count
                count_query = (
                    db.query(func.count(Service.id))
                    .select_from(Service)
                    .join(IP, IP.id == Service.ip_id)
                    .join(Program, Program.id == Service.program_id)
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        count_query = count_query.filter(Program.name == program.strip())
                if ip_port_text:
                    ip_port_expr = func.concat(func.host(IP.ip_address), literal(':'), func.cast(Service.port, String))
                    count_query = count_query.filter(ip_port_expr.ilike(f"%{ip_port_text}%"))
                elif search_ip and port is not None:
                    if ip_port_or:
                        count_query = count_query.filter(
                            or_(
                                func.host(IP.ip_address).ilike(f"%{search_ip}%"),
                                Service.port == int(port),
                            )
                        )
                    else:
                        count_query = count_query.filter(
                            and_(
                                func.host(IP.ip_address).ilike(f"%{search_ip}%"),
                                Service.port == int(port),
                            )
                        )
                elif search_ip:
                    count_query = count_query.filter(func.host(IP.ip_address).ilike(f"%{search_ip}%"))
                elif port is not None:
                    count_query = count_query.filter(Service.port == int(port))
                
                # Add exact match IP+port filter to count query
                if exact_match:
                    # Parse IP:port format like "20.151.252.42:80"
                    if ':' in exact_match:
                        try:
                            ip_part, port_part = exact_match.split(':', 1)
                            count_query = count_query.filter(
                                and_(
                                    IP.ip_address == ip_part.strip(),
                                    Service.port == int(port_part.strip())
                                )
                            )
                        except (ValueError, IndexError):
                            # Invalid format, ignore the filter
                            pass
                    else:
                        # If no colon, treat as IP-only exact match
                        count_query = count_query.filter(IP.ip_address == exact_match)
                
                # Add exact match IP filter to count query
                if exact_match_ip:
                    count_query = count_query.filter(IP.ip_address == exact_match_ip)
                    
                if protocol:
                    count_query = count_query.filter(Service.protocol == protocol)
                if service_name:
                    count_query = count_query.filter(Service.service_name == service_name)
                if service_text:
                    like = f"%{service_text}%"
                    count_query = count_query.filter(Service.service_name.ilike(like))
                if exclude_common_ports:
                    count_query = count_query.filter(Service.port.notin_(COMMON_PORTS))

                total_count = count_query.scalar() or 0
                return {"items": items, "total_count": int(total_count)}
            except Exception as e:
                logger.error(f"Error executing typed services search: {str(e)}")
                raise

    @staticmethod
    async def create_or_update_service(service_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new service or update if exists with merged data.
        Returns (service_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == service_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{service_data.get('program_name')}' not found")
                if service_data.get('ip') is None:
                    logger.error("IP is required to create/update service")
                    raise ValueError("IP is required to create/update service")
                if service_data.get('port') is None:
                    logger.error("Port is required to create/update service")
                    raise ValueError("Port is required to create/update service")
                # Find or create IP for this program
                ip = db.query(IP).filter(
                    and_(IP.ip_address == service_data.get('ip'), IP.program_id == program.id)
                ).first()
                if not ip:
                    try:
                        # Create the IP if it doesn't exist
                        ip = IP(
                            ip_address=service_data.get('ip'),
                            ptr_record=service_data.get('ptr'),
                            service_provider=service_data.get('service_provider'),
                            program_id=program.id,
                        )
                        db.add(ip)
                        db.commit()
                        db.refresh(ip)
                    except IntegrityError:
                        # Race condition: IP was created by concurrent request. Fetch existing and use it.
                        db.rollback()
                        ip = db.query(IP).filter(IP.ip_address == service_data.get('ip')).first()
                        if not ip:
                            raise
                        # Optionally merge in new metadata if we have it and existing is sparse
                        if service_data.get('ptr') and not ip.ptr_record:
                            ip.ptr_record = service_data.get('ptr')
                        if service_data.get('service_provider') and not ip.service_provider:
                            ip.service_provider = service_data.get('service_provider')
                        db.commit()
                        db.refresh(ip)
                
                # Check if service already exists for this program
                existing = db.query(Service).filter(
                    and_(Service.ip_id == ip.id, Service.port == service_data.get('port'), Service.program_id == program.id)
                ).first()
                
                if existing:
                    # Track what fields actually changed for meaningful update detection
                    meaningful_changes = []

                    # Define simple fields that should be compared for changes
                    simple_fields = [
                        'service_name', 'protocol', 'banner', 'notes', 'nerva_metadata'
                    ]

                    # Compare simple fields
                    for field in simple_fields:
                        if field in service_data and service_data[field] is not None:
                            existing_value = getattr(existing, field)
                            if service_data[field] != existing_value:
                                setattr(existing, field, service_data[field])
                                meaningful_changes.append(field)

                    # Update timestamp if any changes were made
                    if meaningful_changes:
                        existing.updated_at = datetime.now(timezone.utc)
                        logger.debug(f"Updated existing service {service_data.get('ip')}:{service_data.get('port')} with changes: {meaningful_changes}")
                    #else:
                    #    logger.debug(f"Service {service_data.get('ip')}:{service_data.get('port')} already exists with same data, skipping")

                    db.commit()

                    # Determine action based on what actually changed
                    # Only mark as "updated" if meaningful changes occurred
                    if meaningful_changes:
                        # Meaningful changes occurred - this is a real update
                        action = "updated"
                        logger.debug(f"Service {service_data.get('ip')}:{service_data.get('port')} updated with changes: {meaningful_changes}")
                    else:
                        # No meaningful changes - this is a duplicate/skipped operation
                        action = "skipped"
                        logger.debug(f"Service {service_data.get('ip')}:{service_data.get('port')} had no meaningful changes, marked as skipped")

                    return str(existing.id), action
                else:
                    # Create new service
                    service = Service(
                        ip_id=ip.id,
                        port=service_data.get('port'),
                        protocol=service_data.get('protocol', 'tcp'),
                        service_name=service_data.get('service_name', ''),
                        banner=service_data.get('banner'),
                        program_id=program.id,
                        notes=service_data.get('notes'),
                        nerva_metadata=service_data.get('nerva_metadata'),
                    )
                    
                    db.add(service)
                    db.commit()
                    db.refresh(service)
                    
                    #logger.debug(f"Created service with ID: {service.id}")
                    try:
                        await publisher.publish(
                            "events.assets.service.created",
                            {
                                "event": "asset.created",
                                "asset_type": "service",
                                "program_name": service_data.get('program_name'),
                                "record_id": str(service.id),
                                "ip": service_data.get('ip'),
                                "port": service_data.get('port'),
                                "protocol": service_data.get('protocol', 'tcp'),
                                "service_name": service_data.get('service_name', ''),
                            },
                        )
                    except Exception:
                        pass
                    return str(service.id), "created"  # Newly created asset
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating service: {str(e)}")
                raise

    @staticmethod
    async def delete_service(service_id: str) -> bool:
        """Delete a single service by ID"""
        async with get_db_session() as db:
            try:
                service = db.query(Service).filter(Service.id == service_id).first()
                if not service:
                    return False
                
                db.delete(service)
                db.commit()
                
                logger.info(f"Successfully deleted service with ID: {service_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting service {service_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_services_batch(service_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple services by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for service_id in service_ids:
                    try:
                        # Skip null/undefined IDs
                        if service_id is None:
                            error_count += 1
                            error_msg = "Invalid service ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if service_id == "":
                            error_count += 1
                            error_msg = "Invalid service ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            service_uuid = UUID(service_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid service ID format '{service_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the service
                        service = db.query(Service).filter(Service.id == service_uuid).first()
                        
                        if not service:
                            not_found_count += 1
                            logger.warning(f"Service with ID {service_id} not found")
                            continue
                        
                        # Delete the service
                        db.delete(service)
                        deleted_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting service {service_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                logger.info(f"Batch delete completed for services: {deleted_count} deleted, {not_found_count} not found, {error_count} errors")
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for services: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in service assets"""
        
        async with get_db_session() as db:
            try:
                query = db.query(Service).join(Program, Program.id == Service.program_id, isouter=True)
                
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
                if field_name == 'service_name':
                    values = query.with_entities(Service.service_name).distinct().all()
                elif field_name == 'port':
                    values = query.with_entities(Service.port).distinct().all()
                elif field_name == 'protocol':
                    values = query.with_entities(Service.protocol).distinct().all()
                elif field_name == 'banner':
                    values = query.with_entities(Service.banner).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for service assets")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in service assets: {str(e)}")
                raise