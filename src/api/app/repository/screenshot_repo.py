from sqlalchemy import func, desc, asc
from typing import Dict, Any, Optional, List, Union
import logging
from datetime import datetime
from uuid import UUID

from models.postgres import (
    URL, Screenshot, ScreenshotFile
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin

logger = logging.getLogger(__name__)

class ScreenshotRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def delete_screenshot(screenshot_id: str) -> bool:
        """Delete screenshot by screenshot ID (metadata ID)"""
        async with get_db_session() as db:
            try:
                # Convert string ID to UUID
                screenshot_uuid = UUID(screenshot_id)
                
                # Get screenshot record first
                screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_uuid).first()
                if not screenshot:
                    logger.warning(f"Screenshot with ID {screenshot_id} not found")
                    return False
                
                # Get the file_id from the screenshot record
                file_id = screenshot.file_id
                
                # Delete screenshot record first (due to foreign key)
                db.delete(screenshot)
                
                # Delete file record
                file_data = db.query(ScreenshotFile).filter(ScreenshotFile.id == file_id).first()
                if file_data:
                    db.delete(file_data)
                    db.commit()
                    logger.info(f"Successfully deleted screenshot with ID: {screenshot_id} and file_id: {file_id}")
                    return True
                else:
                    # Screenshot metadata exists but no file - still delete the metadata
                    db.commit()
                    logger.warning(f"Screenshot metadata deleted but file not found for file_id: {file_id}")
                    return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting screenshot: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in screenshot assets"""
        # This is a placeholder implementation since screenshot model is not fully implemented
        # TODO: Implement when screenshot model is available
        logger.warning(f"get_distinct_values not implemented for screenshot assets - field: {field_name}")
        return []
    @staticmethod
    async def search_screenshots_typed(
        *,
        search_url: Optional[str] = None,
        exact_match: Optional[str] = None,
        program: Optional[Union[str, List[str]]] = None,
        sort_by: str = "upload_date",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Execute a typed screenshots search joining file/url metadata, explicit FROMs, no correlated subqueries."""
        async with get_db_session() as db:
            try:
                base_query = (
                    db.query(
                        Screenshot.id.label("_id"),
                        Screenshot.file_id.label("file_id"),
                        URL.url.label("url"),
                        Screenshot.program_name.label("program_name"),
                        Screenshot.workflow_id.label("workflow_id"),
                        Screenshot.step_name.label("step_name"),
                        Screenshot.image_hash.label("image_hash"),
                        Screenshot.created_at.label("upload_date"),
                        Screenshot.last_captured_at.label("last_captured_at"),
                        Screenshot.capture_count.label("capture_count"),
                        Screenshot.extracted_text.label("extracted_text"),
                        ScreenshotFile.file_size.label("file_size"),
                        ScreenshotFile.content_type.label("content_type"),
                        ScreenshotFile.filename.label("filename"),
                    )
                    .select_from(Screenshot)
                    .join(ScreenshotFile, Screenshot.file_id == ScreenshotFile.id)
                    .outerjoin(URL, Screenshot.url_id == URL.id)
                )

                # Filters
                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": [], "total_count": 0}
                        base_query = base_query.filter(Screenshot.program_name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        base_query = base_query.filter(Screenshot.program_name == program.strip())

                if search_url:
                    base_query = base_query.filter(URL.url.ilike(f"%{search_url}%"))

                if exact_match:
                    base_query = base_query.filter(URL.url == exact_match)

                # Sorting
                sort_by_normalized = (sort_by or "upload_date").lower()
                sort_dir_normalized = (sort_dir or "desc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "url":
                    base_query = base_query.order_by(direction_func(URL.url))
                elif sort_by_normalized == "file_size":
                    base_query = base_query.order_by(direction_func(ScreenshotFile.file_size))
                elif sort_by_normalized == "upload_date":
                    base_query = base_query.order_by(direction_func(Screenshot.created_at))
                elif sort_by_normalized == "last_captured_at":
                    base_query = base_query.order_by(direction_func(Screenshot.last_captured_at))
                else:
                    base_query = base_query.order_by(direction_func(Screenshot.created_at))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for r in rows:
                    # Construct response compatible with Screenshots page expectations
                    metadata = {
                        "url": r.url,
                        "program_name": r.program_name,
                        "workflow_id": r.workflow_id,
                        "step_name": r.step_name,
                        "image_hash": r.image_hash,
                        # For simplicity we expose only created_at and last_captured_at
                        "capture_timestamps": [ts for ts in [r.upload_date.isoformat() if r.upload_date else None, r.last_captured_at.isoformat() if r.last_captured_at and r.last_captured_at != r.upload_date else None] if ts],
                        "capture_count": r.capture_count if hasattr(r, 'capture_count') and r.capture_count is not None else 1,
                        "last_captured_at": r.last_captured_at.isoformat() if r.last_captured_at else None,
                        "extracted_text": getattr(r, 'extracted_text', None),
                    }
                    items.append(
                        {
                            "_id": str(r._id),
                            "file_id": str(r.file_id),
                            "program_name": r.program_name,
                            "workflow_id": r.workflow_id,
                            "step_name": r.step_name,
                            "image_hash": r.image_hash,
                            "upload_date": r.upload_date.isoformat() if r.upload_date else None,
                            "created_at": r.upload_date.isoformat() if r.upload_date else None,
                            "last_captured_at": r.last_captured_at.isoformat() if r.last_captured_at else None,
                            "file_size": r.file_size,
                            "content_type": r.content_type,
                            "filename": r.filename,
                            "extracted_text": getattr(r, 'extracted_text', None),
                            "metadata": metadata,
                        }
                    )

                # Count
                count_query = (
                    db.query(func.count(Screenshot.id))
                    .select_from(Screenshot)
                    .join(ScreenshotFile, Screenshot.file_id == ScreenshotFile.id)
                    .outerjoin(URL, Screenshot.url_id == URL.id)
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(Screenshot.program_name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        count_query = count_query.filter(Screenshot.program_name == program.strip())

                if search_url:
                    count_query = count_query.filter(URL.url.ilike(f"%{search_url}%"))
                if exact_match:
                    count_query = count_query.filter(URL.url == exact_match)

                total_count = count_query.scalar() or 0
                return {"items": items, "total_count": int(total_count)}

            except Exception as e:
                logger.error(f"Error executing typed screenshots search: {str(e)}")
                raise

    @staticmethod
    async def _find_existing_screenshot_by_hash(image_hash: str, url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find existing screenshot by hash"""
        async with get_db_session() as db:
            try:
                # Find screenshot by image hash
                screenshot = db.query(Screenshot).filter(Screenshot.image_hash == image_hash).first()
                
                if screenshot:
                    # Get the file data
                    file_data = db.query(ScreenshotFile).filter(ScreenshotFile.id == screenshot.file_id).first()
                    if file_data:
                        return {
                            "screenshot_id": str(screenshot.id),
                            "file_id": str(screenshot.file_id),
                            "url_id": str(screenshot.url_id),
                            "image_hash": screenshot.image_hash,
                            "file_size": file_data.file_size,
                            "content_type": file_data.content_type,
                            "filename": file_data.filename,
                            "created_at": screenshot.created_at.isoformat() if screenshot.created_at else None
                        }
                return None
                
            except Exception as e:
                logger.error(f"Error finding screenshot by hash: {str(e)}")
                raise

    @staticmethod
    async def store_screenshot(image_data: bytes, filename: str, content_type: str, program_name: Optional[str] = None, url: Optional[str] = None, workflow_id: Optional[str] = None, step_name: Optional[str] = None, extracted_text: Optional[str] = None) -> str:
        """Store screenshot"""
        async with get_db_session() as db:
            try:
                import hashlib
                image_hash = hashlib.sha256(image_data).hexdigest()
                
                # Find or create URL record first
                url_record = None
                if url:
                    url_record = db.query(URL).filter(URL.url == url).first()
                    if not url_record:
                        # Create a minimal URL record
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        url_record = URL(
                            url=url,
                            hostname=parsed.hostname or "",
                            port=parsed.port or (443 if parsed.scheme == "https" else 80),
                            path=parsed.path or "/",
                            scheme=parsed.scheme or "http",
                            program_id=None  # No program association for screenshots
                        )
                        db.add(url_record)
                        db.flush()
                
                # Check if this exact image already exists for this URL (per-URL deduplication)
                existing_screenshot = None
                if url_record:
                    existing_screenshot = db.query(Screenshot).filter(
                        Screenshot.image_hash == image_hash,
                        Screenshot.url_id == url_record.id
                    ).first()
                
                if existing_screenshot:
                    # Image already exists for this URL, just update the existing screenshot record
                    # Update capture count and timestamp
                    existing_screenshot.capture_count += 1
                    existing_screenshot.last_captured_at = datetime.utcnow()
                    
                    # Update workflow_id, step_name, program_name, extracted_text if provided
                    if workflow_id:
                        existing_screenshot.workflow_id = workflow_id
                    if step_name:
                        existing_screenshot.step_name = step_name
                    if program_name:
                        existing_screenshot.program_name = program_name
                    if extracted_text is not None:
                        existing_screenshot.extracted_text = extracted_text
                    
                    db.commit()
                    return str(existing_screenshot.file_id)
                
                # Create new screenshot file
                screenshot_file = ScreenshotFile(
                    file_content=image_data,
                    content_type=content_type,
                    filename=filename,
                    file_size=len(image_data)
                )
                db.add(screenshot_file)
                db.flush()  # Get the ID
                
                # Create screenshot record
                screenshot = Screenshot(
                    url_id=url_record.id if url_record else None,
                    file_id=screenshot_file.id,
                    image_hash=image_hash,
                    workflow_id=workflow_id,
                    step_name=step_name,
                    program_name=program_name,
                    capture_count=1,
                    extracted_text=extracted_text
                )
                db.add(screenshot)
                db.commit()
                
                return str(screenshot_file.id)
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error storing screenshot: {str(e)}")
                raise

    @staticmethod
    async def get_screenshot(file_id: str) -> Optional[Dict[str, Any]]:
        """Get screenshot"""
        async with get_db_session() as db:
            try:
                # Convert string ID to UUID
                file_uuid = UUID(file_id)
                
                # Get screenshot file
                file_data = db.query(ScreenshotFile).filter(ScreenshotFile.id == file_uuid).first()
                if not file_data:
                    return None
                
                # Get screenshot metadata
                screenshot = db.query(Screenshot).filter(Screenshot.file_id == file_uuid).first()
                
                # Get URL data if screenshot exists
                url_data = None
                if screenshot and screenshot.url_id:
                    url_data = db.query(URL).filter(URL.id == screenshot.url_id).first()
                
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
                        "extracted_text": screenshot.extracted_text if screenshot else None
                    }
                }
                
            except Exception as e:
                logger.error(f"Error getting screenshot: {str(e)}")
                raise

    @staticmethod
    async def list_screenshots(program_name: Optional[str] = None, url: Optional[str] = None, workflow_id: Optional[str] = None, step_name: Optional[str] = None, limit: int = 100, skip: int = 0, sort: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
        """List screenshots"""
        async with get_db_session() as db:
            try:
                # Always join with URL table to get the URL
                query = db.query(Screenshot, ScreenshotFile, URL).join(
                    ScreenshotFile, Screenshot.file_id == ScreenshotFile.id
                ).join(
                    URL, Screenshot.url_id == URL.id
                )
                
                # Apply filters
                if program_name:
                    query = query.filter(Screenshot.program_name == program_name)
                if workflow_id:
                    query = query.filter(Screenshot.workflow_id == workflow_id)
                if step_name:
                    query = query.filter(Screenshot.step_name == step_name)
                if url:
                    # Filter by URL
                    query = query.filter(URL.url == url)
                
                # Apply sorting
                if sort:
                    for field, direction in sort.items():
                        if hasattr(Screenshot, field):
                            column = getattr(Screenshot, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                        elif hasattr(ScreenshotFile, field):
                            column = getattr(ScreenshotFile, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                        elif hasattr(URL, field):
                            column = getattr(URL, field)
                            if direction == -1:
                                column = column.desc()
                            query = query.order_by(column)
                else:
                    # Default sort by created_at descending
                    query = query.order_by(Screenshot.created_at.desc())
                
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
                            "capture_timestamps": capture_timestamps
                        }
                    })
                
                return results
                
            except Exception as e:
                logger.error(f"Error listing screenshots: {str(e)}")
                raise

    @staticmethod
    async def get_screenshots_count(program_name: Optional[str] = None, url: Optional[str] = None, workflow_id: Optional[str] = None, step_name: Optional[str] = None) -> int:
        """Get screenshots count"""
        async with get_db_session() as db:
            try:
                query = db.query(Screenshot)
                
                # Apply filters
                if program_name:
                    query = query.filter(Screenshot.program_name == program_name)
                if workflow_id:
                    query = query.filter(Screenshot.workflow_id == workflow_id)
                if step_name:
                    query = query.filter(Screenshot.step_name == step_name)
                if url:
                    # Join with URL table to filter by URL
                    query = query.join(URL, Screenshot.url_id == URL.id).filter(URL.url == url)
                
                return query.count()
                
            except Exception as e:
                logger.error(f"Error getting screenshots count: {str(e)}")
                raise

    @staticmethod
    async def get_screenshot_metadata(screenshot_id: str) -> Optional[Dict[str, Any]]:
        """Get screenshot metadata by screenshot ID (metadata ID)"""
        async with get_db_session() as db:
            try:
                # Convert string ID to UUID
                screenshot_uuid = UUID(screenshot_id)
                
                # Get screenshot record first
                screenshot = db.query(Screenshot).filter(Screenshot.id == screenshot_uuid).first()
                if not screenshot:
                    return None
                
                # Get file data using the file_id from screenshot
                file_data = db.query(ScreenshotFile).filter(ScreenshotFile.id == screenshot.file_id).first()
                if not file_data:
                    return None
                
                # Get URL data
                url_data = None
                if screenshot.url_id:
                    url_data = db.query(URL).filter(URL.id == screenshot.url_id).first()
                
                # Create capture_timestamps array
                capture_timestamps = []
                if screenshot.created_at:
                    capture_timestamps.append(screenshot.created_at.isoformat())
                if screenshot.last_captured_at and screenshot.last_captured_at != screenshot.created_at:
                    capture_timestamps.append(screenshot.last_captured_at.isoformat())
                
                return {
                    "_id": str(screenshot.id),
                    "file_id": str(file_data.id),
                    "filename": file_data.filename,
                    "content_type": file_data.content_type,
                    "file_size": file_data.file_size,
                    "upload_date": file_data.created_at.isoformat() if file_data.created_at else None,
                    "metadata": {
                        "url": url_data.url if url_data else None,
                        "image_hash": screenshot.image_hash,
                        "workflow_id": screenshot.workflow_id,
                        "step_name": screenshot.step_name,
                        "program_name": screenshot.program_name,
                        "capture_count": screenshot.capture_count,
                        "last_captured_at": screenshot.last_captured_at.isoformat() if screenshot.last_captured_at else None,
                        "capture_timestamps": capture_timestamps
                    }
                }
                
            except Exception as e:
                logger.error(f"Error getting screenshot metadata: {str(e)}")
                raise

    @staticmethod
    async def get_screenshot_duplicate_stats() -> Dict[str, Any]:
        """Get screenshot duplicate stats"""
        async with get_db_session() as db:
            try:
                # Get total screenshots
                total_screenshots = db.query(Screenshot).count()
                
                # Get unique screenshots (by image_hash)
                unique_screenshots = db.query(Screenshot.image_hash).distinct().count()
                
                # Calculate duplicates
                duplicates = total_screenshots - unique_screenshots
                
                return {
                    "total_screenshots": total_screenshots,
                    "unique_screenshots": unique_screenshots,
                    "duplicates": duplicates
                }
                
            except Exception as e:
                logger.error(f"Error getting screenshot duplicate stats: {str(e)}")
                raise

