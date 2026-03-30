from sqlalchemy import and_, or_, func, desc, asc
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from models.postgres import (
    WPScanFinding, Program
)
from db import get_db_session
# Direct import to avoid circular import
from utils.query_filters import QueryFilterUtils, ProgramAccessMixin
from services.event_publisher import publisher

logger = logging.getLogger(__name__)

class WPScanFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for WPScan findings operations"""
    
    @staticmethod
    async def create_or_update_wpscan_finding(finding_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new WPScan finding or update if exists with merged data.
        Returns (finding_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == finding_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{finding_data.get('program_name')}' not found")
                
                # Check if finding already exists based on unique constraint fields
                existing = db.query(WPScanFinding).filter(
                    and_(
                        WPScanFinding.url == finding_data.get('url'),
                        WPScanFinding.item_name == finding_data.get('item_name'),
                        WPScanFinding.program_id == program.id
                    )
                ).first()
                
                if existing:
                    # Check if data is different and update if needed
                    updated = False
                    
                    # Update fields that might change between scans
                    if 'severity' in finding_data and finding_data.get('severity') != existing.severity:
                        existing.severity = finding_data.get('severity')
                        updated = True
                    
                    if 'description' in finding_data and finding_data.get('description') != existing.description:
                        existing.description = finding_data.get('description')
                        updated = True
                    
                    if 'fixed_in' in finding_data and finding_data.get('fixed_in') != existing.fixed_in:
                        existing.fixed_in = finding_data.get('fixed_in')
                        updated = True
                    
                    if 'references' in finding_data and finding_data.get('references') != existing.references:
                        existing.references = finding_data.get('references', [])
                        updated = True
                    
                    if 'cve_ids' in finding_data and finding_data.get('cve_ids') != existing.cve_ids:
                        existing.cve_ids = finding_data.get('cve_ids', [])
                        updated = True
                    
                    if 'enumeration_data' in finding_data and finding_data.get('enumeration_data') != existing.enumeration_data:
                        existing.enumeration_data = finding_data.get('enumeration_data')
                        updated = True
                    
                    if 'notes' in finding_data and finding_data.get('notes') != existing.notes:
                        existing.notes = finding_data.get('notes')
                        updated = True
                    
                    # Update timestamp if any changes were made
                    if updated:
                        existing.updated_at = datetime.utcnow()
                    
                    db.commit()
                    action = "updated" if updated else "skipped"
                    return str(existing.id), action
                else:
                    # Create new WPScan finding
                    wpscan_finding = WPScanFinding(
                        url=finding_data.get('url'),
                        item_name=finding_data.get('item_name'),
                        item_type=finding_data.get('item_type'),
                        vulnerability_type=finding_data.get('vulnerability_type'),
                        severity=finding_data.get('severity'),
                        title=finding_data.get('title'),
                        description=finding_data.get('description'),
                        fixed_in=finding_data.get('fixed_in'),
                        references=finding_data.get('references', []),
                        cve_ids=finding_data.get('cve_ids', []),
                        enumeration_data=finding_data.get('enumeration_data'),
                        hostname=finding_data.get('hostname'),
                        port=finding_data.get('port'),
                        scheme=finding_data.get('scheme'),
                        program_id=program.id,
                        notes=finding_data.get('notes')
                    )
                    
                    db.add(wpscan_finding)
                    db.commit()
                    db.refresh(wpscan_finding)
                    
                    try:
                        await publisher.publish(
                            "events.findings.created.wpscan",
                            {
                                "event": "finding.created",
                                "type": "wpscan",
                                "program_name": finding_data.get('program_name'),
                                "record_id": str(wpscan_finding.id),
                                "severity": finding_data.get('severity'),
                                "item_name": finding_data.get('item_name'),
                                "item_type": finding_data.get('item_type'),
                                "url": finding_data.get('url'),
                            },
                        )
                    except Exception:
                        pass
                    return str(wpscan_finding.id), "created"
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating WPScan finding: {str(e)}")
                raise
    
    @staticmethod
    async def get_wpscan_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        """Get a WPScan finding by ID"""
        async with get_db_session() as db:
            try:
                finding = db.query(WPScanFinding).filter(WPScanFinding.id == finding_id).first()
                if not finding:
                    return None
                
                return {
                    'id': str(finding.id),
                    'url': finding.url,
                    'item_name': finding.item_name,
                    'item_type': finding.item_type,
                    'vulnerability_type': finding.vulnerability_type,
                    'severity': finding.severity,
                    'title': finding.title,
                    'description': finding.description,
                    'fixed_in': finding.fixed_in,
                    'references': finding.references,
                    'cve_ids': finding.cve_ids,
                    'enumeration_data': finding.enumeration_data,
                    'hostname': finding.hostname,
                    'port': finding.port,
                    'scheme': finding.scheme,
                    'program_name': finding.program.name if finding.program else None,
                    'notes': finding.notes,
                    'status': finding.status,
                    'assigned_to': finding.assigned_to,
                    'created_at': finding.created_at.isoformat() if finding.created_at else None,
                    'updated_at': finding.updated_at.isoformat() if finding.updated_at else None
                }
                
            except Exception as e:
                logger.error(f"Error getting WPScan finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def get_wpscan_query_count(query: Dict[str, Any]) -> int:
        """Get count for WPScan query"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return 0
                
                sql_query = db.query(func.count(WPScanFinding.id))
                
                # Apply program access filtering using shared utility
                sql_query = WPScanFindingsRepository.apply_program_access_filter(sql_query, query, Program)
                
                # Apply other filters
                sql_query = WPScanFindingsRepository._apply_wpscan_filters(sql_query, query)
                return sql_query.scalar()
                
            except Exception as e:
                logger.error(f"Error getting WPScan query count: {str(e)}")
                raise
    
    @staticmethod
    def _apply_wpscan_filters(query, filters: Dict[str, Any]):
        """Apply MongoDB-style filters to SQLAlchemy query"""
        if not filters:
            return query
        
        conditions = []
        
        for key, value in filters.items():
            if key == 'severity':
                conditions.append(WPScanFinding.severity == value)
            elif key == 'item_name':
                if isinstance(value, dict) and '$regex' in value:
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if 'i' in options:
                        conditions.append(WPScanFinding.item_name.ilike(f'%{pattern}%'))
                    else:
                        conditions.append(WPScanFinding.item_name.like(f'%{pattern}%'))
                else:
                    conditions.append(WPScanFinding.item_name == value)
            elif key == 'item_type':
                conditions.append(WPScanFinding.item_type == value)
            elif key == 'hostname':
                conditions.append(WPScanFinding.hostname == value)
            elif key == 'program_name':
                continue  # Handled by program access filter
            elif key == '$and':
                and_conditions = []
                for and_filter in value:
                    and_conditions.append(WPScanFindingsRepository._apply_wpscan_filters(query, and_filter))
                conditions.append(and_(*and_conditions))
            elif key == '$or':
                or_conditions = []
                for or_filter in value:
                    or_conditions.append(WPScanFindingsRepository._apply_wpscan_filters(query, or_filter))
                conditions.append(or_(*or_conditions))
        
        if conditions:
            return query.filter(and_(*conditions))
        
        return query
    
    @staticmethod
    async def get_wpscan_stats_by_severity(query: Dict[str, Any]) -> Dict[str, int]:
        """Get WPScan findings stats by severity"""
        async with get_db_session() as db:
            try:
                sql_query = db.query(WPScanFinding)
                sql_query = WPScanFindingsRepository._apply_wpscan_filters(sql_query, query)
                
                # Get counts by severity
                stats = {
                    'critical': 0,
                    'high': 0,
                    'medium': 0,
                    'low': 0,
                    'info': 0
                }
                
                for severity in stats.keys():
                    severity_query = db.query(WPScanFinding)
                    severity_query = WPScanFindingsRepository._apply_wpscan_filters(severity_query, query)
                    count = severity_query.filter(WPScanFinding.severity == severity).count()
                    stats[severity] = count
                
                return stats
                
            except Exception as e:
                logger.error(f"Error getting WPScan stats: {str(e)}")
                raise
    
    @staticmethod
    async def get_distinct_wpscan_values_typed(field_name: str, programs: Optional[List[str]] = None) -> List[str]:
        """Get distinct WPScan values with program scoping (typed)."""
        async with get_db_session() as db:
            try:
                base = db.query(WPScanFinding).join(Program)
                if programs:
                    base = base.filter(Program.name.in_(programs))

                if field_name == 'item_name':
                    values = base.with_entities(WPScanFinding.item_name).distinct().all()
                elif field_name == 'item_type':
                    values = base.with_entities(WPScanFinding.item_type).distinct().all()
                elif field_name == 'severity':
                    values = base.with_entities(WPScanFinding.severity).distinct().all()
                elif field_name == 'hostname':
                    values = base.with_entities(WPScanFinding.hostname).distinct().all()
                elif field_name == 'vulnerability_type':
                    values = base.with_entities(WPScanFinding.vulnerability_type).distinct().all()
                elif field_name == 'program_name':
                    values = base.with_entities(Program.name).distinct().all()
                elif field_name == 'cve_ids':
                    base = base.filter(
                        and_(
                            WPScanFinding.cve_ids.isnot(None),
                            func.coalesce(func.array_length(WPScanFinding.cve_ids, 1), 0) > 0
                        )
                    )
                    values = base.with_entities(func.unnest(WPScanFinding.cve_ids)).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")

                result = []
                for v in values:
                    if v[0] is not None:
                        val_str = str(v[0]).strip()
                        if val_str and val_str != "[]":
                            result.append(val_str)

                return sorted(result)
            except Exception as e:
                logger.error(f"Error getting typed distinct WPScan values: {str(e)}")
                raise
    
    @staticmethod
    async def search_wpscan_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        severity: Optional[str] = None,
        item_type: Optional[str] = None,
        item_name_contains: Optional[str] = None,
        item_name_exact: Optional[str] = None,
        hostname_contains: Optional[str] = None,
        cve_ids_exact: Optional[str] = None,
        cve_ids_contains: Optional[str] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed WPScan findings search optimized for PostgreSQL.
        Returns a dict with keys: items (list[dict]), total_count (int), severity_distribution (dict)
        """
        async with get_db_session() as db:
            try:
                # Base selectable
                base_query = (
                    db.query(
                        WPScanFinding.id.label("id"),
                        WPScanFinding.url.label("url"),
                        WPScanFinding.item_name.label("item_name"),
                        WPScanFinding.item_type.label("item_type"),
                        WPScanFinding.vulnerability_type.label("vulnerability_type"),
                        WPScanFinding.severity.label("severity"),
                        WPScanFinding.title.label("title"),
                        WPScanFinding.description.label("description"),
                        WPScanFinding.fixed_in.label("fixed_in"),
                        WPScanFinding.references.label("references"),
                        WPScanFinding.cve_ids.label("cve_ids"),
                        WPScanFinding.hostname.label("hostname"),
                        Program.name.label("program_name"),
                        WPScanFinding.created_at.label("created_at"),
                        WPScanFinding.updated_at.label("updated_at"),
                    )
                    .select_from(WPScanFinding)
                    .join(Program, Program.id == WPScanFinding.program_id)
                )

                # Filters
                if programs is not None and len(programs) > 0:
                    base_query = base_query.filter(Program.name.in_(programs))

                if search:
                    base_query = base_query.filter(
                        or_(
                            WPScanFinding.title.ilike(f"%{search}%"),
                            WPScanFinding.item_name.ilike(f"%{search}%"),
                            WPScanFinding.description.ilike(f"%{search}%")
                        )
                    )
                
                if exact_match:
                    base_query = base_query.filter(WPScanFinding.item_name == exact_match)

                if severity:
                    base_query = base_query.filter(WPScanFinding.severity == severity)

                if item_type:
                    base_query = base_query.filter(WPScanFinding.item_type == item_type)

                if item_name_contains:
                    base_query = base_query.filter(WPScanFinding.item_name.ilike(f"%{item_name_contains}%"))
                
                if item_name_exact:
                    base_query = base_query.filter(WPScanFinding.item_name == item_name_exact)

                if hostname_contains:
                    base_query = base_query.filter(WPScanFinding.hostname.ilike(f"%{hostname_contains}%"))

                if cve_ids_exact:
                    base_query = base_query.filter(WPScanFinding.cve_ids.any(cve_ids_exact))

                if cve_ids_contains:
                    base_query = base_query.filter(
                        func.array_to_string(WPScanFinding.cve_ids, ' ').ilike(f"%{cve_ids_contains}%")
                    )

                # Count before pagination
                count_query = db.query(func.count()).select_from(WPScanFinding).join(Program, Program.id == WPScanFinding.program_id)
                if programs is not None and len(programs) > 0:
                    count_query = count_query.filter(Program.name.in_(programs))
                if search:
                    count_query = count_query.filter(
                        or_(
                            WPScanFinding.title.ilike(f"%{search}%"),
                            WPScanFinding.item_name.ilike(f"%{search}%"),
                            WPScanFinding.description.ilike(f"%{search}%")
                        )
                    )
                if exact_match:
                    count_query = count_query.filter(WPScanFinding.item_name == exact_match)
                if severity:
                    count_query = count_query.filter(WPScanFinding.severity == severity)
                if item_type:
                    count_query = count_query.filter(WPScanFinding.item_type == item_type)
                if item_name_contains:
                    count_query = count_query.filter(WPScanFinding.item_name.ilike(f"%{item_name_contains}%"))
                if item_name_exact:
                    count_query = count_query.filter(WPScanFinding.item_name == item_name_exact)
                if hostname_contains:
                    count_query = count_query.filter(WPScanFinding.hostname.ilike(f"%{hostname_contains}%"))
                if cve_ids_exact:
                    count_query = count_query.filter(WPScanFinding.cve_ids.any(cve_ids_exact))
                if cve_ids_contains:
                    count_query = count_query.filter(
                        func.array_to_string(WPScanFinding.cve_ids, ' ').ilike(f"%{cve_ids_contains}%")
                    )

                total_count = count_query.scalar() or 0

                # Get severity distribution counts
                severity_query = db.query(
                    WPScanFinding.severity,
                    func.count(WPScanFinding.id).label('count')
                ).select_from(WPScanFinding).join(Program, Program.id == WPScanFinding.program_id)
                
                # Apply same filters for severity distribution
                if programs is not None and len(programs) > 0:
                    severity_query = severity_query.filter(Program.name.in_(programs))
                if search:
                    severity_query = severity_query.filter(
                        or_(
                            WPScanFinding.title.ilike(f"%{search}%"),
                            WPScanFinding.item_name.ilike(f"%{search}%"),
                            WPScanFinding.description.ilike(f"%{search}%")
                        )
                    )
                if exact_match:
                    severity_query = severity_query.filter(WPScanFinding.item_name == exact_match)
                if severity:
                    severity_query = severity_query.filter(WPScanFinding.severity == severity)
                if item_type:
                    severity_query = severity_query.filter(WPScanFinding.item_type == item_type)
                if item_name_contains:
                    severity_query = severity_query.filter(WPScanFinding.item_name.ilike(f"%{item_name_contains}%"))
                if item_name_exact:
                    severity_query = severity_query.filter(WPScanFinding.item_name == item_name_exact)
                if hostname_contains:
                    severity_query = severity_query.filter(WPScanFinding.hostname.ilike(f"%{hostname_contains}%"))
                if cve_ids_exact:
                    severity_query = severity_query.filter(WPScanFinding.cve_ids.any(cve_ids_exact))
                if cve_ids_contains:
                    severity_query = severity_query.filter(
                        func.array_to_string(WPScanFinding.cve_ids, ' ').ilike(f"%{cve_ids_contains}%")
                    )

                severity_query = severity_query.group_by(WPScanFinding.severity)
                severity_distribution = {row.severity: row.count for row in severity_query.all()}

                # Sorting
                sort_dir_func = asc if sort_dir == "asc" else desc
                sort_map = {
                    "item_name": WPScanFinding.item_name,
                    "item_type": WPScanFinding.item_type,
                    "severity": WPScanFinding.severity,
                    "hostname": WPScanFinding.hostname,
                    "url": WPScanFinding.url,
                    "program_name": Program.name,
                    "created_at": WPScanFinding.created_at,
                    "updated_at": WPScanFinding.updated_at,
                }
                sort_col = sort_map.get(sort_by, WPScanFinding.created_at)
                base_query = base_query.order_by(sort_dir_func(sort_col))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append({
                        "id": str(row.id),
                        "url": row.url,
                        "item_name": row.item_name,
                        "item_type": row.item_type,
                        "vulnerability_type": row.vulnerability_type,
                        "severity": row.severity,
                        "title": row.title,
                        "description": row.description,
                        "fixed_in": row.fixed_in,
                        "references": row.references,
                        "cve_ids": row.cve_ids,
                        "hostname": row.hostname,
                        "program_name": row.program_name,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    })

                return {
                    "items": items, 
                    "total_count": total_count,
                    "severity_distribution": severity_distribution
                }

            except Exception as e:
                logger.error(f"Error executing typed WPScan search: {str(e)}")
                raise
    
    @staticmethod
    async def update_wpscan_finding(finding_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a WPScan finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(WPScanFinding).filter(WPScanFinding.id == finding_id).first()
                if not finding:
                    return False
                
                # Update fields
                for key, value in update_data.items():
                    if hasattr(finding, key):
                        setattr(finding, key, value)
                
                finding.updated_at = datetime.utcnow()
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating WPScan finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_wpscan_finding(finding_id: str) -> bool:
        """Delete a WPScan finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(WPScanFinding).filter(WPScanFinding.id == finding_id).first()
                if not finding:
                    return False
                
                db.delete(finding)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting WPScan finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_wpscan_findings_batch(finding_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple WPScan findings by their IDs"""
        async with get_db_session() as db:
            try:
                findings = db.query(WPScanFinding).filter(WPScanFinding.id.in_(finding_ids)).all()
                
                deleted_count = 0
                not_found_count = 0
                
                for finding in findings:
                    db.delete(finding)
                    deleted_count += 1
                
                not_found_count = len(finding_ids) - deleted_count
                
                db.commit()
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "total_requested": len(finding_ids)
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting WPScan findings: {str(e)}")
                raise
    
    @staticmethod
    async def execute_wpscan_query(query: Dict[str, Any], limit: int = 1000000, skip: int = 0, sort: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute WPScan query with PostgreSQL"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return []
                
                sql_query = db.query(WPScanFinding)
                
                # Apply program access filtering using shared utility
                sql_query = WPScanFindingsRepository.apply_program_access_filter(sql_query, query, Program)
                
                # Apply other filters
                sql_query = WPScanFindingsRepository._apply_wpscan_filters(sql_query, query)
                
                # Apply sorting
                if sort:
                    for field, direction in sort.items():
                        if hasattr(WPScanFinding, field):
                            if direction == 1:
                                sql_query = sql_query.order_by(asc(getattr(WPScanFinding, field)))
                            else:
                                sql_query = sql_query.order_by(desc(getattr(WPScanFinding, field)))
                
                # Apply pagination
                sql_query = sql_query.offset(skip).limit(limit)
                
                findings = sql_query.all()
                
                result = []
                for finding in findings:
                    result.append({
                        'id': str(finding.id),
                        'url': finding.url,
                        'item_name': finding.item_name,
                        'item_type': finding.item_type,
                        'severity': finding.severity,
                        'hostname': finding.hostname,
                        'program_name': finding.program.name if finding.program else None,
                        'created_at': finding.created_at.isoformat() if finding.created_at else None
                    })
                
                return result
                
            except Exception as e:
                logger.error(f"Error executing WPScan query: {str(e)}")
                raise
