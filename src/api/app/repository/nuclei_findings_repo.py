from sqlalchemy import and_, or_, func, desc, asc
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

from models.postgres import (
    NucleiFinding, Program, IP
)
from db import get_db_session
# Direct import to avoid circular import
from utils.query_filters import QueryFilterUtils, ProgramAccessMixin
from services.event_publisher import publisher

logger = logging.getLogger(__name__)

class NucleiFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for findings operations"""
    
    @staticmethod
    async def create_or_update_nuclei_finding(finding_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new nuclei finding or update if exists with merged data.
        Returns (finding_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == finding_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{finding_data.get('program_name')}' not found")
                
                # Find IP if provided
                ip = None
                if finding_data.get('ip'):
                    ip = db.query(IP).filter(IP.ip_address == finding_data.get('ip')).first()
                
                # Check if finding already exists based on unique constraint fields
                constraint_fields = {
                    'url': finding_data.get('url'),
                    'template_id': finding_data.get('template_id'),
                    'matcher_name': finding_data.get('matcher_name'),
                    'program_id': program.id,
                    'matched_at': finding_data.get('matched_at')
                }
                logger.info(f"🔍 NUCLEI REPO DEBUG: Checking for existing finding with constraint fields: {constraint_fields}")
                
                existing = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.url == finding_data.get('url'),
                        NucleiFinding.template_id == finding_data.get('template_id'),
                        NucleiFinding.matcher_name == finding_data.get('matcher_name'),
                        NucleiFinding.program_id == program.id,
                        NucleiFinding.matched_at == finding_data.get('matched_at')
                    )
                ).first()
                
                if existing:
                    logger.info(f"🔍 NUCLEI REPO DEBUG: Found existing finding with ID: {existing.id}")
                    # Check if data is different and update if needed
                    updated = False
                    
                    # Update fields that might change between scans
                    if 'severity' in finding_data and finding_data.get('severity') != existing.severity:
                        existing.severity = finding_data.get('severity')
                        updated = True
                    
                    if 'description' in finding_data and finding_data.get('description') != existing.description:
                        existing.description = finding_data.get('description')
                        updated = True
                    
                    if 'extracted_results' in finding_data and finding_data.get('extracted_results') != existing.extracted_results:
                        existing.extracted_results = finding_data.get('extracted_results', [])
                        updated = True
                    
                    if 'info_data' in finding_data and finding_data.get('info') != existing.info_data:
                        existing.info_data = finding_data.get('info', {})
                        updated = True
                    
                    if 'matched_line' in finding_data and finding_data.get('matched_line') != existing.matched_line:
                        existing.matched_line = finding_data.get('matched_line')
                        updated = True
                    
                    if 'notes' in finding_data and finding_data.get('notes') != existing.notes:
                        existing.notes = finding_data.get('notes')
                        updated = True
                    
                    # Update IP if provided and different
                    if ip and existing.ip_id != ip.id:
                        existing.ip_id = ip.id
                        updated = True
                    
                    # Update timestamp if any changes were made
                    if updated:
                        existing.updated_at = datetime.utcnow()
                        #logger.debug(f"Updated existing nuclei finding {finding_data.get('url')} with template {finding_data.get('template_id')}")
                    #else:
                    #    logger.info(f"Nuclei finding {finding_data.get('url')} with template {finding_data.get('template_id')} already exists with same data, skipping")
                    
                    db.commit()
                    action = "updated" if updated else "skipped"
                    logger.info(f"🔍 NUCLEI REPO DEBUG: Returning existing finding - ID: {existing.id}, Action: {action}")
                    return str(existing.id), action
                else:
                    # Create new nuclei finding
                    logger.info("🔍 NUCLEI REPO DEBUG: No existing finding found, creating new one")
                    nuclei_finding = NucleiFinding(
                        url=finding_data.get('url'),
                        template_id=finding_data.get('template_id'),
                        template_url=finding_data.get('template_url'),
                        template_path=finding_data.get('template_path'),
                        name=finding_data.get('name'),
                        severity=finding_data.get('severity'),
                        finding_type=finding_data.get('type'),
                        tags=finding_data.get('tags', []),
                        description=finding_data.get('description'),
                        matched_at=finding_data.get('matched_at'),
                        matcher_name=finding_data.get('matcher_name'),
                        ip_id=ip.id if ip else None,
                        hostname=finding_data.get('hostname'),
                        port=finding_data.get('port'),
                        scheme=finding_data.get('scheme'),
                        protocol=finding_data.get('protocol'),
                        matched_line=finding_data.get('matched_line'),
                        extracted_results=finding_data.get('extracted_results', []),
                        info_data=finding_data.get('info', {}),
                        program_id=program.id,
                        notes=finding_data.get('notes')
                    )
                    
                    db.add(nuclei_finding)
                    db.commit()
                    db.refresh(nuclei_finding)
                    
                    logger.info(f"🔍 NUCLEI REPO DEBUG: Created new nuclei finding with ID: {nuclei_finding.id}")
                    logger.info(f"🔍 NUCLEI REPO DEBUG: New finding details - url={nuclei_finding.url}, template_id={nuclei_finding.template_id}, matcher_name={nuclei_finding.matcher_name}, matched_at={nuclei_finding.matched_at}")
                    try:
                        await publisher.publish(
                            "events.findings.created.nuclei",
                            {
                                "event": "finding.created",
                                "type": "nuclei",
                                "program_name": finding_data.get('program_name'),
                                "record_id": str(nuclei_finding.id),
                                "severity": finding_data.get('severity'),
                                "template_id": finding_data.get('template_id'),
                                "url": finding_data.get('url'),
                            },
                        )
                    except Exception:
                        pass
                    return str(nuclei_finding.id), "created"  # Newly created finding
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating nuclei finding: {str(e)}")
                raise
    
    @staticmethod
    async def get_nuclei_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        """Get a nuclei finding by ID"""
        async with get_db_session() as db:
            try:
                finding = db.query(NucleiFinding).filter(NucleiFinding.id == finding_id).first()
                if not finding:
                    return None
                
                return {
                    'id': str(finding.id),
                    'url': finding.url,
                    'template_id': finding.template_id,
                    'template_url': finding.template_url,
                    'template_path': finding.template_path,
                    'name': finding.name,
                    'severity': finding.severity,
                    'type': finding.finding_type,
                    'tags': finding.tags,
                    'description': finding.description,
                    'matched_at': finding.matched_at,
                    'matcher_name': finding.matcher_name,
                    'ip': finding.ip.ip_address if finding.ip else None,
                    'hostname': finding.hostname,
                    'port': finding.port,
                    'scheme': finding.scheme,
                    'protocol': finding.protocol,
                    'matched_line': finding.matched_line,
                    'extracted_results': finding.extracted_results,
                    'info': finding.info_data,
                    'program_name': finding.program.name if finding.program else None,
                    'notes': finding.notes,
                    'created_at': finding.created_at.isoformat() if finding.created_at else None,
                    'updated_at': finding.updated_at.isoformat() if finding.updated_at else None
                }
                
            except Exception as e:
                logger.error(f"Error getting nuclei finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def execute_nuclei_query(query: Dict[str, Any], limit: int = 1000000, skip: int = 0, sort: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute nuclei query with PostgreSQL"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return []  # Return empty list immediately if no program access
                
                sql_query = db.query(NucleiFinding)
                
                # Apply program access filtering using shared utility
                sql_query = NucleiFindingsRepository.apply_program_access_filter(sql_query, query, Program)
                
                # Apply other filters
                sql_query = NucleiFindingsRepository._apply_nuclei_filters(sql_query, query)
                
                # Apply sorting
                if sort:
                    for field, direction in sort.items():
                        if hasattr(NucleiFinding, field):
                            if direction == 1:
                                sql_query = sql_query.order_by(asc(getattr(NucleiFinding, field)))
                            else:
                                sql_query = sql_query.order_by(desc(getattr(NucleiFinding, field)))
                
                # Apply pagination
                sql_query = sql_query.offset(skip).limit(limit)
                
                findings = sql_query.all()
                
                result = []
                for finding in findings:
                    result.append({
                        'id': str(finding.id),
                        'url': finding.url,
                        'template_id': finding.template_id,
                        'name': finding.name,
                        'severity': finding.severity,
                        'type': finding.finding_type,
                        'hostname': finding.hostname,
                        'ip': finding.ip.ip_address if finding.ip else None,
                        'program_name': finding.program.name if finding.program else None,
                        'matched_at': finding.matched_at,
                        'created_at': finding.created_at.isoformat() if finding.created_at else None
                    })
                
                return result
                
            except Exception as e:
                logger.error(f"Error executing nuclei query: {str(e)}")
                raise
    
    @staticmethod
    async def get_nuclei_query_count(query: Dict[str, Any]) -> int:
        """Get count for nuclei query"""
        async with get_db_session() as db:
            try:
                # Check for empty program filter first (optimization)
                if QueryFilterUtils.handle_empty_program_filter(query):
                    return 0  # Return 0 immediately if no program access
                
                sql_query = db.query(func.count(NucleiFinding.id))
                
                # Apply program access filtering using shared utility
                sql_query = NucleiFindingsRepository.apply_program_access_filter(sql_query, query, Program)
                
                # Apply other filters
                sql_query = NucleiFindingsRepository._apply_nuclei_filters(sql_query, query)
                return sql_query.scalar()
                
            except Exception as e:
                logger.error(f"Error getting nuclei query count: {str(e)}")
                raise
    
    @staticmethod
    def _apply_nuclei_filters(query, filters: Dict[str, Any]):
        """Apply MongoDB-style filters to SQLAlchemy query"""
        if not filters:
            return query
        
        conditions = []
        needs_program_join = False
        needs_ip_join = False
        
        for key, value in filters.items():
            if key == 'severity':
                conditions.append(NucleiFinding.severity == value)
            elif key == 'name':
                if isinstance(value, dict) and '$regex' in value:
                    # Handle regex pattern for name
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if 'i' in options:  # Case insensitive
                        conditions.append(NucleiFinding.name.ilike(f'%{pattern}%'))
                    else:
                        conditions.append(NucleiFinding.name.like(f'%{pattern}%'))
                else:
                    conditions.append(NucleiFinding.name == value)
            elif key == 'template_id':
                if isinstance(value, dict) and '$regex' in value:
                    # Handle regex pattern for template_id
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if 'i' in options:  # Case insensitive
                        conditions.append(NucleiFinding.template_id.ilike(f'%{pattern}%'))
                    else:
                        conditions.append(NucleiFinding.template_id.like(f'%{pattern}%'))
                else:
                    conditions.append(NucleiFinding.template_id == value)
            elif key == 'hostname':
                conditions.append(NucleiFinding.hostname == value)
            elif key == 'program_name':
                # Program filtering is now handled by the shared utility
                # Skip this key to avoid duplicate filtering
                continue
            elif key == 'ip':
                conditions.append(IP.ip_address == value)
                needs_ip_join = True
            elif key == '$and':
                # Handle $and operator
                and_conditions = []
                for and_filter in value:
                    and_conditions.append(NucleiFindingsRepository._apply_nuclei_filters(query, and_filter))
                conditions.append(and_(*and_conditions))
            elif key == '$or':
                # Handle $or operator
                or_conditions = []
                for or_filter in value:
                    or_conditions.append(NucleiFindingsRepository._apply_nuclei_filters(query, or_filter))
                conditions.append(or_(*or_conditions))
            elif key == '$regex':
                # Handle regex patterns
                if isinstance(value, dict):
                    pattern = value.get('$regex', '')
                    options = value.get('$options', '')
                    if pattern:
                        if 'i' in options:  # Case insensitive
                            conditions.append(NucleiFinding.hostname.ilike(f'%{pattern}%'))
                        else:
                            conditions.append(NucleiFinding.hostname.like(f'%{pattern}%'))
        
        # Apply joins if needed
        if needs_program_join:
            query = query.join(Program)
        if needs_ip_join:
            query = query.join(IP)
        
        if conditions:
            return query.filter(and_(*conditions))
        
        return query
    
    @staticmethod
    async def get_nuclei_stats_by_severity(query: Dict[str, Any]) -> Dict[str, int]:
        """Get nuclei findings stats by severity"""
        async with get_db_session() as db:
            try:
                sql_query = db.query(NucleiFinding)
                sql_query = NucleiFindingsRepository._apply_nuclei_filters(sql_query, query)
                
                # Get counts by severity
                stats = {
                    'critical': 0,
                    'high': 0,
                    'medium': 0,
                    'low': 0,
                    'info': 0
                }
                
                for severity in stats.keys():
                    # Create a new query for each severity to avoid cartesian product issues
                    severity_query = db.query(NucleiFinding)
                    severity_query = NucleiFindingsRepository._apply_nuclei_filters(severity_query, query)
                    count = severity_query.filter(NucleiFinding.severity == severity).count()
                    stats[severity] = count
                
                return stats
                
            except Exception as e:
                logger.error(f"Error getting nuclei stats: {str(e)}")
                raise
    
    @staticmethod
    async def get_distinct_nuclei_values_typed(field_name: str, programs: Optional[List[str]] = None) -> List[str]:
        """Get distinct nuclei values with program scoping (typed)."""
        async with get_db_session() as db:
            try:
                base = db.query(NucleiFinding).join(Program)
                if programs:
                    base = base.filter(Program.name.in_(programs))

                if field_name == 'name':
                    values = base.with_entities(NucleiFinding.name).distinct().all()
                elif field_name == 'tags':
                    # For tags array field, use unnest to flatten the array and get individual tags
                    # Filter out findings with empty or null tags array
                    # Use coalesce to handle NULL values and array_length to filter empty arrays
                    base = base.filter(
                        and_(
                            NucleiFinding.tags.isnot(None),
                            func.coalesce(func.array_length(NucleiFinding.tags, 1), 0) > 0
                        )
                    )
                    values = base.with_entities(func.unnest(NucleiFinding.tags)).distinct().all()
                    # Log the raw values for debugging
                    logger.info(f"Raw tag values from database: {values[:10] if len(values) > 10 else values}")
                elif field_name == 'template_id':
                    values = base.with_entities(NucleiFinding.template_id).distinct().all()
                elif field_name == 'severity':
                    values = base.with_entities(NucleiFinding.severity).distinct().all()
                elif field_name == 'hostname':
                    values = base.with_entities(NucleiFinding.hostname).distinct().all()
                elif field_name == 'matcher_name':
                    values = base.with_entities(NucleiFinding.matcher_name).distinct().all()
                elif field_name == 'program_name':
                    values = base.with_entities(Program.name).distinct().all()
                elif field_name == 'extracted_results':
                    # For extracted_results array field, use unnest to flatten the array
                    values = base.with_entities(func.unnest(NucleiFinding.extracted_results)).distinct().all()
                else:
                    raise ValueError(f"Unsupported field: {field_name}")

                # Filter out None, empty strings, stringified arrays like "[]" or "['tag']", and sort the results
                result = []
                for v in values:
                    if v[0] is not None:
                        val_str = str(v[0]).strip()
                        # Skip empty strings, "[]", and strings that look like Python lists
                        if val_str and val_str != "[]" and not (val_str.startswith("[") and val_str.endswith("]")):
                            result.append(val_str)

                # Log the filtered results for debugging
                if field_name == 'tags':
                    logger.info(f"Filtered tag values being returned: {sorted(result)[:10] if len(result) > 10 else sorted(result)}")

                return sorted(result)
            except Exception as e:
                logger.error(f"Error getting typed distinct nuclei values: {str(e)}")
                raise

    # =====================
    # Typed Nuclei Query
    # =====================
    @staticmethod
    async def search_nuclei_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        severity: Optional[str] = None,
        tags: Optional[str] = None,
        tags_include: Optional[List[str]] = None,
        tags_exclude: Optional[List[str]] = None,
        template_contains: Optional[str] = None,
        template_exact: Optional[str] = None,
        hostname_contains: Optional[str] = None,
        extracted_results_exact: Optional[str] = None,
        extracted_results_contains: Optional[str] = None,
        programs: Optional[List[str]] = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """
        Execute a strongly-typed nuclei findings search optimized for PostgreSQL.
        Returns a dict with keys: items (list[dict]), total_count (int), severity_distribution (dict)
        """
        async with get_db_session() as db:
            try:
                # Base selectable
                base_query = (
                    db.query(
                        NucleiFinding.id.label("id"),
                        NucleiFinding.url.label("url"),
                        NucleiFinding.template_id.label("template_id"),
                        NucleiFinding.name.label("name"),
                        NucleiFinding.severity.label("severity"),
                        NucleiFinding.tags.label("tags"),
                        NucleiFinding.finding_type.label("type"),
                        NucleiFinding.hostname.label("hostname"),
                        NucleiFinding.matcher_name.label("matcher_name"),
                        Program.name.label("program_name"),
                        NucleiFinding.extracted_results.label("extracted_results"),
                        NucleiFinding.matched_at.label("matched_at"),
                        NucleiFinding.created_at.label("created_at"),
                        NucleiFinding.updated_at.label("updated_at"),
                    )
                    .select_from(NucleiFinding)
                    .join(Program, Program.id == NucleiFinding.program_id)
                )

                # Filters
                if programs is not None and len(programs) > 0:
                    base_query = base_query.filter(Program.name.in_(programs))

                if search:
                    base_query = base_query.filter(NucleiFinding.name.ilike(f"%{search}%"))
                
                if exact_match:
                    base_query = base_query.filter(NucleiFinding.name == exact_match)

                if severity:
                    base_query = base_query.filter(NucleiFinding.severity == severity)

                if tags:
                    base_query = base_query.filter(NucleiFinding.tags.contains(tags))

                if tags_include and len(tags_include) > 0:
                    # Include findings that have ANY of the specified tags (OR logic)
                    # Use PostgreSQL's && (overlap) operator to check if arrays have common elements
                    base_query = base_query.filter(NucleiFinding.tags.op('&&')(tags_include))

                if tags_exclude and len(tags_exclude) > 0:
                    # Exclude findings that have ANY of the specified tags (NOT logic)
                    # Use PostgreSQL's && (overlap) operator with NOT
                    base_query = base_query.filter(~NucleiFinding.tags.op('&&')(tags_exclude))

                if template_contains:
                    base_query = base_query.filter(NucleiFinding.template_id.ilike(f"%{template_contains}%"))
                
                if template_exact:
                    base_query = base_query.filter(NucleiFinding.template_id == template_exact)

                if hostname_contains:
                    base_query = base_query.filter(NucleiFinding.hostname.ilike(f"%{hostname_contains}%"))

                if extracted_results_exact:
                    base_query = base_query.filter(NucleiFinding.extracted_results.any(extracted_results_exact))

                if extracted_results_contains:
                    # Use PostgreSQL array_to_string to convert array to text and search within it
                    base_query = base_query.filter(
                        func.array_to_string(NucleiFinding.extracted_results, ' ').ilike(f"%{extracted_results_contains}%")
                    )

                # Count before pagination
                count_query = db.query(func.count()).select_from(NucleiFinding).join(Program, Program.id == NucleiFinding.program_id)
                if programs is not None and len(programs) > 0:
                    count_query = count_query.filter(Program.name.in_(programs))
                if search:
                    count_query = count_query.filter(NucleiFinding.name.ilike(f"%{search}%"))
                if exact_match:
                    count_query = count_query.filter(NucleiFinding.name == exact_match)
                if severity:
                    count_query = count_query.filter(NucleiFinding.severity == severity)
                if tags:
                    count_query = count_query.filter(NucleiFinding.tags.contains(tags))
                if tags_include and len(tags_include) > 0:
                    count_query = count_query.filter(NucleiFinding.tags.op('&&')(tags_include))
                if tags_exclude and len(tags_exclude) > 0:
                    count_query = count_query.filter(~NucleiFinding.tags.op('&&')(tags_exclude))
                if template_contains:
                    count_query = count_query.filter(NucleiFinding.template_id.ilike(f"%{template_contains}%"))
                if template_exact:
                    count_query = count_query.filter(NucleiFinding.template_id == template_exact)
                if hostname_contains:
                    count_query = count_query.filter(NucleiFinding.hostname.ilike(f"%{hostname_contains}%"))
                if extracted_results_exact:
                    count_query = count_query.filter(NucleiFinding.extracted_results.any(extracted_results_exact))
                if extracted_results_contains:
                    count_query = count_query.filter(
                        func.array_to_string(NucleiFinding.extracted_results, ' ').ilike(f"%{extracted_results_contains}%")
                    )

                total_count = count_query.scalar() or 0

                # Get severity distribution counts
                severity_query = db.query(
                    NucleiFinding.severity,
                    func.count(NucleiFinding.id).label('count')
                ).select_from(NucleiFinding).join(Program, Program.id == NucleiFinding.program_id)
                
                # Apply same filters for severity distribution
                if programs is not None and len(programs) > 0:
                    severity_query = severity_query.filter(Program.name.in_(programs))
                if search:
                    severity_query = severity_query.filter(NucleiFinding.name.ilike(f"%{search}%"))
                if exact_match:
                    severity_query = severity_query.filter(NucleiFinding.name == exact_match)
                if severity:
                    severity_query = severity_query.filter(NucleiFinding.severity == severity)
                if tags:
                    severity_query = severity_query.filter(NucleiFinding.tags.contains(tags))
                if tags_include and len(tags_include) > 0:
                    severity_query = severity_query.filter(NucleiFinding.tags.op('&&')(tags_include))
                if tags_exclude and len(tags_exclude) > 0:
                    severity_query = severity_query.filter(~NucleiFinding.tags.op('&&')(tags_exclude))
                if template_contains:
                    severity_query = severity_query.filter(NucleiFinding.template_id.ilike(f"%{template_contains}%"))
                if template_exact:
                    severity_query = severity_query.filter(NucleiFinding.template_id == template_exact)
                if hostname_contains:
                    severity_query = severity_query.filter(NucleiFinding.hostname.ilike(f"%{hostname_contains}%"))
                if extracted_results_exact:
                    severity_query = severity_query.filter(NucleiFinding.extracted_results.any(extracted_results_exact))
                if extracted_results_contains:
                    severity_query = severity_query.filter(
                        func.array_to_string(NucleiFinding.extracted_results, ' ').ilike(f"%{extracted_results_contains}%")
                    )

                severity_query = severity_query.group_by(NucleiFinding.severity)
                severity_distribution = {row.severity: row.count for row in severity_query.all()}

                # Sorting
                sort_dir_func = asc if sort_dir == "asc" else desc
                sort_map = {
                    "name": NucleiFinding.name,
                    "severity": NucleiFinding.severity,
                    "tags": NucleiFinding.tags,
                    "template_id": NucleiFinding.template_id,
                    "hostname": NucleiFinding.hostname,
                    "url": NucleiFinding.url,
                    "program_name": Program.name,
                    "created_at": NucleiFinding.created_at,
                    "updated_at": NucleiFinding.updated_at,
                }
                sort_col = sort_map.get(sort_by, NucleiFinding.created_at)
                base_query = base_query.order_by(sort_dir_func(sort_col))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for row in rows:
                    items.append({
                        "id": str(row.id),
                        "url": row.url,
                        "tags": row.tags,
                        "template_id": row.template_id,
                        "name": row.name,
                        "severity": row.severity,
                        "type": row.type,
                        "hostname": row.hostname,
                        "matcher_name": row.matcher_name,
                        "program_name": row.program_name,
                        "extracted_results": row.extracted_results,
                        "matched_at": row.matched_at,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    })

                return {
                    "items": items, 
                    "total_count": total_count,
                    "severity_distribution": severity_distribution
                }

            except Exception as e:
                logger.error(f"Error executing typed nuclei search: {str(e)}")
                raise
    
    @staticmethod
    async def update_nuclei_finding(finding_id: str, update_data: Dict[str, Any]) -> bool:
        """Update a nuclei finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(NucleiFinding).filter(NucleiFinding.id == finding_id).first()
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
                logger.error(f"Error updating nuclei finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_nuclei_finding(finding_id: str) -> bool:
        """Delete a nuclei finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(NucleiFinding).filter(NucleiFinding.id == finding_id).first()
                if not finding:
                    return False
                
                db.delete(finding)
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting nuclei finding {finding_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_nuclei_findings_batch(finding_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple nuclei findings by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                
                for finding_id in finding_ids:
                    finding = db.query(NucleiFinding).filter(NucleiFinding.id == finding_id).first()
                    if finding:
                        db.delete(finding)
                        deleted_count += 1
                
                db.commit()
                
                return {
                    "deleted_count": deleted_count,
                    "requested_count": len(finding_ids),
                    "failed_count": len(finding_ids) - deleted_count
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting nuclei findings: {str(e)}")
                raise
