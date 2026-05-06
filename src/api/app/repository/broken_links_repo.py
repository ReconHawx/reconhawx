from sqlalchemy import and_, desc, asc, func
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from models.base import utcnow

from models.postgres import (
    BrokenLink, Program
)
from db import get_db_session, SessionLocal
from fastapi.concurrency import run_in_threadpool
from utils.program_resolve import resolve_program_from_payload
from utils.domain_utils import normalize_hostname
from utils.url_utils import lower_url_host
from utils.query_filters import ProgramAccessMixin
from services.event_publisher import publisher

logger = logging.getLogger(__name__)

class BrokenLinksRepository(ProgramAccessMixin):
    """PostgreSQL repository for broken links operations"""
    
    @staticmethod
    async def create_or_update_broken_link(finding_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new broken link finding or update if exists.
        Returns (finding_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = resolve_program_from_payload(db, finding_data)

                if finding_data.get("domain"):
                    finding_data["domain"] = normalize_hostname(str(finding_data["domain"]))
                if finding_data.get("url"):
                    finding_data["url"] = lower_url_host(str(finding_data["url"])) or finding_data["url"]

                # Check if finding already exists based on unique constraint (program_id, url)
                url = finding_data.get('url')
                existing = None
                if url:
                    existing = db.query(BrokenLink).filter(
                        and_(
                            BrokenLink.program_id == program.id,
                            BrokenLink.url == url
                        )
                    ).first()
                
                if existing:
                    logger.info(f"Found existing broken link finding with ID: {existing.id}")
                    # Update existing finding
                    updated = False
                    
                    if 'status' in finding_data and finding_data.get('status') != existing.status:
                        existing.status = finding_data.get('status')
                        updated = True
                    
                    if 'url' in finding_data and finding_data.get('url') != existing.url:
                        existing.url = finding_data.get('url')
                        updated = True
                    
                    if 'error_code' in finding_data and finding_data.get('error_code') != existing.error_code:
                        existing.error_code = finding_data.get('error_code')
                        updated = True
                    
                    if 'response_data' in finding_data and finding_data.get('response_data') != existing.response_data:
                        existing.response_data = finding_data.get('response_data')
                        updated = True
                    
                    if 'checked_at' in finding_data and finding_data.get('checked_at'):
                        checked_at = finding_data.get('checked_at')
                        if isinstance(checked_at, str):
                            checked_at = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
                        existing.checked_at = checked_at
                        updated = True
                    
                    if 'notes' in finding_data and finding_data.get('notes') != existing.notes:
                        existing.notes = finding_data.get('notes')
                        updated = True
                    
                    # Update new fields
                    if 'link_type' in finding_data and finding_data.get('link_type') != existing.link_type:
                        existing.link_type = finding_data.get('link_type')
                        updated = True
                    
                    if 'media_type' in finding_data and finding_data.get('media_type') != existing.media_type:
                        existing.media_type = finding_data.get('media_type')
                        updated = True
                    
                    if 'reason' in finding_data and finding_data.get('reason') != existing.reason:
                        existing.reason = finding_data.get('reason')
                        updated = True
                    
                    if updated:
                        existing.updated_at = utcnow()
                    
                    db.commit()
                    action = "updated" if updated else "skipped"
                    return str(existing.id), action
                else:
                    # Create new broken link finding
                    checked_at = finding_data.get('checked_at')
                    if checked_at and isinstance(checked_at, str):
                        checked_at = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
                    elif not checked_at:
                        checked_at = utcnow()
                    
                    broken_link = BrokenLink(
                        program_id=program.id,
                        link_type=finding_data.get('link_type', 'social_media'),
                        media_type=finding_data.get('media_type'),
                        domain=finding_data.get('domain'),
                        reason=finding_data.get('reason'),
                        status=finding_data.get('status'),
                        url=finding_data.get('url'),
                        error_code=finding_data.get('error_code'),
                        response_data=finding_data.get('response_data'),
                        checked_at=checked_at,
                        notes=finding_data.get('notes')
                    )
                    
                    db.add(broken_link)
                    db.commit()
                    db.refresh(broken_link)
                    
                    logger.info(f"Created new broken link finding with ID: {broken_link.id}")
                    try:
                        await publisher.publish(
                            "events.findings.created.broken_link",
                            {
                                "event": "finding.created",
                                "type": "broken_link",
                                "program_name": finding_data.get('program_name'),
                                "record_id": str(broken_link.id),
                                "link_type": finding_data.get('link_type', 'social_media'),
                                "media_type": finding_data.get('media_type'),
                                "domain": finding_data.get('domain'),
                                "reason": finding_data.get('reason'),
                                "status": finding_data.get('status'),
                            },
                        )
                    except Exception:
                        pass
                    return str(broken_link.id), "created"
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating broken link finding: {str(e)}")
                raise
    
    @staticmethod
    async def get_broken_link_by_id(finding_id: str) -> Optional[Dict[str, Any]]:
        """Get a broken link finding by ID"""
        async with get_db_session() as db:
            try:
                finding = db.query(BrokenLink).filter(BrokenLink.id == finding_id).first()
                if not finding:
                    return None
                
                return {
                    'id': str(finding.id),
                    'program_id': str(finding.program_id),
                    'program_name': finding.program.name if finding.program else None,
                    'link_type': finding.link_type,
                    'media_type': finding.media_type,
                    'domain': finding.domain,
                    'reason': finding.reason,
                    'status': finding.status,
                    'url': finding.url,
                    'error_code': finding.error_code,
                    'response_data': finding.response_data,
                    'checked_at': finding.checked_at.isoformat() if finding.checked_at else None,
                    'notes': finding.notes,
                    'created_at': finding.created_at.isoformat() if finding.created_at else None,
                    'updated_at': finding.updated_at.isoformat() if finding.updated_at else None
                }
                
            except Exception as e:
                logger.error(f"Error getting broken link finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def search_broken_links(
        program_name: Optional[str] = None,
        link_type: Optional[str] = None,
        media_type: Optional[str] = None,
        status: Optional[str] = None,
        domain_search: Optional[str] = None,
        sort_by: str = "checked_at",
        sort_dir: str = "desc",
        page: int = 1,
        page_size: int = 25
    ) -> Dict[str, Any]:
        """Search broken links with filtering and pagination"""
        async with get_db_session() as db:
            try:
                query = db.query(BrokenLink).join(Program)
                
                # Apply program filter
                if program_name:
                    query = query.filter(Program.name == program_name)
                
                # Apply link type filter
                if link_type:
                    query = query.filter(BrokenLink.link_type == link_type)
                
                # Apply media type filter
                if media_type:
                    query = query.filter(BrokenLink.media_type == media_type)
                
                # Apply status filter
                if status:
                    query = query.filter(BrokenLink.status == status)
                
                # Apply domain search
                if domain_search:
                    query = query.filter(BrokenLink.domain.ilike(f"%{domain_search}%"))
                
                # Apply sorting
                sort_field = getattr(BrokenLink, sort_by, BrokenLink.checked_at)
                if sort_dir.lower() == "asc":
                    query = query.order_by(asc(sort_field))
                else:
                    query = query.order_by(desc(sort_field))
                
                # Get total count before pagination
                total_count = query.count()
                
                # Apply pagination
                offset = (page - 1) * page_size
                query = query.offset(offset).limit(page_size)
                
                findings = query.all()
                
                result = []
                for finding in findings:
                    result.append({
                        'id': str(finding.id),
                        'program_id': str(finding.program_id),
                        'program_name': finding.program.name if finding.program else None,
                        'link_type': finding.link_type,
                        'media_type': finding.media_type,
                        'domain': finding.domain,
                        'reason': finding.reason,
                        'status': finding.status,
                        'url': finding.url,
                        'error_code': finding.error_code,
                        'response_data': finding.response_data,
                        'checked_at': finding.checked_at.isoformat() if finding.checked_at else None,
                        'created_at': finding.created_at.isoformat() if finding.created_at else None,
                        'updated_at': finding.updated_at.isoformat() if finding.updated_at else None
                    })
                
                return {
                    'findings': result,
                    'total': total_count,
                    'page': page,
                    'page_size': page_size,
                    'total_pages': (total_count + page_size - 1) // page_size
                }
                
            except Exception as e:
                logger.error(f"Error searching broken links: {str(e)}")
                raise
    
    @staticmethod
    async def update_broken_link(finding_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a broken link finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(BrokenLink).filter(BrokenLink.id == finding_id).first()
                if not finding:
                    return None
                
                if 'status' in update_data:
                    finding.status = update_data['status']
                
                if 'error_code' in update_data:
                    finding.error_code = update_data['error_code']
                
                if 'response_data' in update_data:
                    finding.response_data = update_data['response_data']
                
                if 'checked_at' in update_data and update_data['checked_at']:
                    checked_at = update_data['checked_at']
                    if isinstance(checked_at, str):
                        checked_at = datetime.fromisoformat(checked_at.replace('Z', '+00:00'))
                    finding.checked_at = checked_at
                
                if 'notes' in update_data:
                    finding.notes = update_data['notes']
                
                finding.updated_at = utcnow()
                
                db.commit()
                db.refresh(finding)
                
                return await BrokenLinksRepository.get_broken_link_by_id(finding_id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating broken link finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_broken_link(finding_id: str) -> bool:
        """Delete a broken link finding"""
        async with get_db_session() as db:
            try:
                finding = db.query(BrokenLink).filter(BrokenLink.id == finding_id).first()
                if not finding:
                    return False
                
                db.delete(finding)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting broken link finding {finding_id}: {str(e)}")
                raise
    
    @staticmethod
    async def delete_broken_links_batch(finding_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple broken link findings by their IDs"""
        async with get_db_session() as db:
            try:
                findings = db.query(BrokenLink).filter(BrokenLink.id.in_(finding_ids)).all()
                
                deleted_count = 0
                not_found_ids = []
                
                for finding in findings:
                    db.delete(finding)
                    deleted_count += 1
                
                # Check which IDs were not found
                found_ids = {str(f.id) for f in findings}
                not_found_ids = [fid for fid in finding_ids if fid not in found_ids]
                
                db.commit()
                
                return {
                    'deleted_count': deleted_count,
                    'not_found_ids': not_found_ids
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error batch deleting broken link findings: {str(e)}")
                raise
    
    @staticmethod
    def _get_broken_links_stats_sync(
        program_name: Optional[str] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            q = (
                db.query(
                    func.count(BrokenLink.id),
                    func.count().filter(BrokenLink.status == "valid"),
                    func.count().filter(BrokenLink.status == "broken"),
                    func.count().filter(BrokenLink.status == "error"),
                    func.count().filter(BrokenLink.status == "throttled"),
                    func.count().filter(BrokenLink.media_type == "facebook"),
                    func.count().filter(BrokenLink.media_type == "instagram"),
                    func.count().filter(BrokenLink.media_type == "twitter"),
                    func.count().filter(BrokenLink.media_type == "x"),
                    func.count().filter(BrokenLink.media_type == "linkedin"),
                )
                .select_from(BrokenLink)
                .join(Program, BrokenLink.program_id == Program.id)
            )
            if program_name:
                q = q.filter(Program.name == program_name)
            elif restrict_to_program_names is not None:
                if len(restrict_to_program_names) == 0:
                    return {
                        "total": 0,
                        "valid": 0,
                        "broken": 0,
                        "error": 0,
                        "throttled": 0,
                        "by_media_type": {},
                    }
                q = q.filter(Program.name.in_(restrict_to_program_names))
            row = q.one()
            labels = ["facebook", "instagram", "twitter", "x", "linkedin"]
            by_media_type: Dict[str, int] = {}
            for i, lab in enumerate(labels):
                c = int(row[5 + i] or 0)
                if c > 0:
                    by_media_type[lab] = c
            return {
                "total": int(row[0] or 0),
                "valid": int(row[1] or 0),
                "broken": int(row[2] or 0),
                "error": int(row[3] or 0),
                "throttled": int(row[4] or 0),
                "by_media_type": by_media_type,
            }
        except Exception as exc:
            logger.error("Error getting broken links stats: %s", exc)
            raise
        finally:
            db.close()

    @staticmethod
    async def get_broken_links_stats(
        program_name: Optional[str] = None,
        restrict_to_program_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Get statistics for broken links"""
        return await run_in_threadpool(
            BrokenLinksRepository._get_broken_links_stats_sync,
            program_name,
            restrict_to_program_names,
        )
