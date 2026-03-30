from utils.query_filters import ProgramAccessMixin
from typing import Optional, Dict, Any, List
from models.postgres import FindingsStatsResponse, AggregatedFindingsStatsResponse, NucleiFindingStats, TyposquatFindingStats
from sqlalchemy import and_, desc
from models.postgres import Program, NucleiFinding, TyposquatDomain
from db import get_db_session
import logging

logger = logging.getLogger(__name__)

class CommonFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for findings operations"""

    @staticmethod
    async def get_latest_findings(program_name: Optional[str] = None, limit: int = 5, days_ago: Optional[int] = None) -> Dict[str, List]:
        """Get the latest findings of each type for dashboard display"""
        try:
            logger.info(f"Getting latest findings for program: {program_name}, limit: {limit}, days_ago: {days_ago}")
            async with get_db_session() as db:
                # Get program ID for filtering if specified
                program_id = None
                if program_name:
                    program = db.query(Program).filter(Program.name == program_name).first()
                    if not program:
                        logger.warning(f"Program {program_name} not found")
                        return {}
                    program_id = program.id
                    logger.info(f"Found program {program_name} with ID: {program_id}")
                else:
                    logger.info("No program specified, getting findings from all programs")
                
                # Calculate time filter if specified
                from datetime import datetime, timedelta
                time_filter = None
                if days_ago:
                    cutoff_date = datetime.utcnow() - timedelta(days=days_ago)
                    time_filter = cutoff_date
                    logger.info(f"Filtering findings created after: {cutoff_date}")
                
                latest_findings = {}
                
                try:
                    # --- Latest Nuclei Findings ---
                    nuclei_query = db.query(NucleiFinding).join(Program)
                    
                    if program_id:
                        nuclei_query = nuclei_query.filter(NucleiFinding.program_id == program_id)
                    
                    if time_filter:
                        nuclei_query = nuclei_query.filter(NucleiFinding.created_at >= time_filter)
                    
                    latest_nuclei = nuclei_query.order_by(desc(NucleiFinding.created_at)).limit(limit).all()
                    
                    # Also check total count for this program
                    total_count_query = db.query(NucleiFinding).join(Program)
                    if program_id:
                        total_count_query = total_count_query.filter(NucleiFinding.program_id == program_id)
                    total_count = total_count_query.count()
                    
                    latest_findings['nuclei'] = [
                        {
                            'id': finding.id,
                            'name': finding.name,
                            'severity': finding.severity,
                            'url': finding.url,
                            'template_id': finding.template_id,
                            'created_at': finding.created_at,
                            'program_name': finding.program.name if finding.program else None,
                            'status': getattr(finding, 'status', 'unknown'),  # Handle missing status field
                            'hostname': getattr(finding, 'hostname', None),
                            'type': getattr(finding, 'finding_type', None)
                        }
                        for finding in latest_nuclei
                    ]
                    
                except Exception as e:
                    logger.error(f"Error getting nuclei findings: {e}")
                    latest_findings['nuclei'] = []
                
                try:
                    # --- Latest Typosquat Findings ---
                    typosquat_query = db.query(TyposquatDomain).join(Program)
                    if program_id:
                        typosquat_query = typosquat_query.filter(TyposquatDomain.program_id == program_id)
                    if time_filter:
                        typosquat_query = typosquat_query.filter(TyposquatDomain.created_at >= time_filter)
                    latest_typosquat = typosquat_query.order_by(desc(TyposquatDomain.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_typosquat)} latest typosquat findings")
                    latest_findings['typosquat'] = [
                        {
                            'id': finding.id,
                            'typo_domain': finding.typo_domain,
                            'status': finding.status,
                            'risk_score': finding.risk_score,
                            'created_at': finding.created_at,
                            'program_name': finding.program.name if finding.program else None
                        }
                        for finding in latest_typosquat
                    ]
                except Exception as e:
                    logger.error(f"Error getting typosquat findings: {e}")
                    latest_findings['typosquat'] = []
                
                logger.info(f"Returning latest findings: {list(latest_findings.keys())}")
                return latest_findings
                
        except Exception as e:
            logger.exception(f"Error getting latest findings: {str(e)}")
            return {}

    @staticmethod
    async def get_detailed_findings_stats(filter_data: Dict[str, Any]) -> FindingsStatsResponse:
        """Get detailed findings stats for a program"""
        try:
            # Extract program name from filter data
            program_name = filter_data.get('program_name')
            if not program_name:
                logger.warning("No program_name provided for findings stats")
                return FindingsStatsResponse()
            
            async with get_db_session() as db:
                # Get program ID for filtering
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    logger.warning(f"Program {program_name} not found")
                    return FindingsStatsResponse()
                
                program_id = program.id
                
                # --- Nuclei Findings Stats ---
                # Get total nuclei findings
                total_nuclei = db.query(NucleiFinding).filter(
                    NucleiFinding.program_id == program_id
                ).count()
                
                # Get counts by severity
                critical_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id == program_id,
                        NucleiFinding.severity == 'critical'
                    )
                ).count()
                
                high_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id == program_id,
                        NucleiFinding.severity == 'high'
                    )
                ).count()
                
                medium_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id == program_id,
                        NucleiFinding.severity == 'medium'
                    )
                ).count()
                
                low_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id == program_id,
                        NucleiFinding.severity == 'low'
                    )
                ).count()
                
                info_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id == program_id,
                        NucleiFinding.severity == 'info'
                    )
                ).count()
                
                nuclei_stats = NucleiFindingStats(
                    total=total_nuclei,
                    critical=critical_nuclei,
                    high=high_nuclei,
                    medium=medium_nuclei,
                    low=low_nuclei,
                    info=info_nuclei
                )
                
                # --- Typosquat Findings Stats ---
                # Get total typosquat findings
                total_typosquat = db.query(TyposquatDomain).filter(
                    TyposquatDomain.program_id == program_id
                ).count()
                
                # Get counts by status
                new_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id == program_id,
                        TyposquatDomain.status == 'new'
                    )
                ).count()
                
                investigating_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id == program_id,
                        TyposquatDomain.status == 'investigating'
                    )
                ).count()
                
                confirmed_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id == program_id,
                        TyposquatDomain.status == 'confirmed'
                    )
                ).count()
                
                resolved_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id == program_id,
                        TyposquatDomain.status == 'resolved'
                    )
                ).count()
                
                dismissed_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id == program_id,
                        TyposquatDomain.status == 'dismissed'
                    )
                ).count()
                
                typosquat_stats = TyposquatFindingStats(
                    total=total_typosquat,
                    new=new_typosquat,
                    inprogress=investigating_typosquat,
                    resolved=resolved_typosquat,
                    dismissed=dismissed_typosquat
                )
                
                # --- Combine Results ---
                return FindingsStatsResponse(
                    nuclei_findings=nuclei_stats,
                    typosquat_findings=typosquat_stats
                )
                
        except Exception as e:
            logger.exception(f"Error calculating detailed findings stats for filter {filter_data}: {str(e)}")
            # Return default empty stats on error
            return FindingsStatsResponse(
                nuclei_findings=NucleiFindingStats(),
                typosquat_findings=TyposquatFindingStats()
            )

    @staticmethod
    async def get_aggregated_findings_stats(program_names: Optional[List[str]] = None) -> AggregatedFindingsStatsResponse:
        """Get aggregated findings stats across multiple programs"""
        try:
            async with get_db_session() as db:
                # Build program filter
                if program_names:
                    programs = db.query(Program).filter(Program.name.in_(program_names)).all()
                    program_ids = [p.id for p in programs]
                    total_programs = len(programs)
                else:
                    # Get all programs if none specified
                    programs = db.query(Program).all()
                    program_ids = [p.id for p in programs]
                    total_programs = len(programs)
                
                if not program_ids:
                    logger.warning("No programs found for aggregated findings stats")
                    return AggregatedFindingsStatsResponse()
                
                # --- Nuclei Findings Stats ---
                # Get total nuclei findings
                total_nuclei = db.query(NucleiFinding).filter(
                    NucleiFinding.program_id.in_(program_ids)
                ).count()
                
                # Get counts by severity
                critical_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id.in_(program_ids),
                        NucleiFinding.severity == 'critical'
                    )
                ).count()
                
                high_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id.in_(program_ids),
                        NucleiFinding.severity == 'high'
                    )
                ).count()
                
                medium_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id.in_(program_ids),
                        NucleiFinding.severity == 'medium'
                    )
                ).count()
                
                low_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id.in_(program_ids),
                        NucleiFinding.severity == 'low'
                    )
                ).count()
                
                info_nuclei = db.query(NucleiFinding).filter(
                    and_(
                        NucleiFinding.program_id.in_(program_ids),
                        NucleiFinding.severity == 'info'
                    )
                ).count()
                
                nuclei_stats = NucleiFindingStats(
                    total=total_nuclei,
                    critical=critical_nuclei,
                    high=high_nuclei,
                    medium=medium_nuclei,
                    low=low_nuclei,
                    info=info_nuclei
                )
                
                # --- Typosquat Findings Stats ---
                # Get total typosquat findings
                total_typosquat = db.query(TyposquatDomain).filter(
                    TyposquatDomain.program_id.in_(program_ids)
                ).count()
                
                # Get counts by status
                new_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id.in_(program_ids),
                        TyposquatDomain.status == 'new'
                    )
                ).count()
                
                investigating_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id.in_(program_ids),
                        TyposquatDomain.status == 'investigating'
                    )
                ).count()
                
                resolved_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id.in_(program_ids),
                        TyposquatDomain.status == 'resolved'
                    )
                ).count()
                
                dismissed_typosquat = db.query(TyposquatDomain).filter(
                    and_(
                        TyposquatDomain.program_id.in_(program_ids),
                        TyposquatDomain.status == 'dismissed'
                    )
                ).count()
                
                typosquat_stats = TyposquatFindingStats(
                    total=total_typosquat,
                    new=new_typosquat,
                    inprogress=investigating_typosquat,
                    resolved=resolved_typosquat,
                    dismissed=dismissed_typosquat
                )
                
                # --- Combine Results ---
                return AggregatedFindingsStatsResponse(
                    total_programs=total_programs,
                    nuclei_findings=nuclei_stats,
                    typosquat_findings=typosquat_stats
                )
                
        except Exception as e:
            logger.exception(f"Error calculating aggregated findings stats: {str(e)}")
            # Return default empty stats on error
            return AggregatedFindingsStatsResponse(
                total_programs=0,
                nuclei_findings=NucleiFindingStats(),
                typosquat_findings=TyposquatFindingStats()
            )
