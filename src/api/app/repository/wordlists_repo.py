from sqlalchemy import or_, desc
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timezone

from models.postgres import Wordlist, WordlistFile, Program, Subdomain, ApexDomain
from db import get_db_session

logger = logging.getLogger(__name__)


class WordlistsRepository:
    """PostgreSQL repository for wordlists operations - supports both static and dynamic wordlists"""
    
    # === STATIC WORDLIST METHODS ===
    
    @staticmethod
    async def create_wordlist(
        wordlist_data: Dict[str, Any], 
        file_content: bytes, 
        filename: str, 
        content_type: str,
        created_by: str
    ) -> Optional[Dict[str, Any]]:
        """Create a new static wordlist with file storage"""
        async with get_db_session() as db:
            try:
                # Check if wordlist with same name already exists
                existing = db.query(Wordlist).filter(Wordlist.name == wordlist_data.get('name')).first()
                if existing:
                    logger.warning(f"Wordlist with name {wordlist_data.get('name')} already exists")
                    return None
                
                # Count words in the file content
                word_count = WordlistsRepository._count_words(file_content)
                
                # Find program by name if provided
                program_id = None
                if wordlist_data.get('program_name'):
                    program = db.query(Program).filter(Program.name == wordlist_data.get('program_name')).first()
                    if program:
                        program_id = program.id
                
                # Create file storage record
                wordlist_file = WordlistFile(
                    file_content=file_content,
                    content_type=content_type,
                    filename=filename,
                    file_size=len(file_content)
                )
                
                db.add(wordlist_file)
                db.flush()  # Get the ID without committing
                
                # Create wordlist metadata
                wordlist = Wordlist(
                    name=wordlist_data.get('name'),
                    description=wordlist_data.get('description'),
                    word_count=word_count,
                    tags=wordlist_data.get('tags', []),
                    file_id=wordlist_file.id,
                    program_id=program_id,
                    created_by=created_by,
                    is_active=True,
                    is_dynamic=False
                )
                
                db.add(wordlist)
                db.commit()
                db.refresh(wordlist)
                db.refresh(wordlist_file)
                
                logger.info(f"Created static wordlist with ID: {wordlist.id}, file_id: {wordlist_file.id}")
                
                return {
                    'id': str(wordlist.id),
                    'name': wordlist.name,
                    'description': wordlist.description,
                    'filename': wordlist_file.filename,
                    'content_type': wordlist_file.content_type,
                    'file_size': wordlist_file.file_size,
                    'word_count': wordlist.word_count,
                    'tags': wordlist.tags,
                    'program_name': wordlist_data.get('program_name'),
                    'created_by': wordlist.created_by,
                    'file_id': str(wordlist_file.id),
                    'is_active': wordlist.is_active,
                    'is_dynamic': False,
                    'dynamic_type': None,
                    'dynamic_config': None,
                    'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                    'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating wordlist: {str(e)}")
                return None
    
    # === DYNAMIC WORDLIST METHODS ===
    
    @staticmethod
    async def create_dynamic_wordlist(
        name: str,
        dynamic_type: str,
        program_name: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        created_by: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new dynamic wordlist.
        
        Dynamic wordlists don't store file content - content is generated on download
        based on program assets.
        
        Args:
            name: Name of the wordlist
            dynamic_type: Type of dynamic generation (e.g., "subdomain_prefixes")
            program_name: Program to generate wordlist from
            description: Optional description
            tags: Optional list of tags
            created_by: Username who created the wordlist
            
        Returns:
            Dict with wordlist metadata including word_count (computed at creation time)
        """
        async with get_db_session() as db:
            try:
                logger.info(f"Creating dynamic wordlist: name={name}, type={dynamic_type}, program={program_name}")
                
                # Check if wordlist with same name already exists
                logger.debug("Checking for existing wordlist...")
                existing = db.query(Wordlist).filter(Wordlist.name == name).first()
                if existing:
                    logger.warning(f"Wordlist with name {name} already exists")
                    return None
                
                # Find program by name (required for dynamic wordlists)
                logger.debug(f"Looking up program: {program_name}")
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    logger.error(f"Program {program_name} not found")
                    return None
                
                logger.debug(f"Found program with ID: {program.id}")
                
                # Generate content to get word count
                logger.debug("Generating dynamic content to get word count...")
                word_count, _ = await WordlistsRepository._generate_dynamic_content_internal(
                    db, dynamic_type, str(program.id)
                )
                logger.debug(f"Generated {word_count} entries")
                
                # Create dynamic wordlist metadata
                dynamic_config = {
                    "program_id": str(program.id),
                    "program_name": program_name
                }
                
                logger.debug("Creating Wordlist object...")
                wordlist = Wordlist(
                    name=name,
                    description=description,
                    word_count=word_count,
                    tags=tags or [],
                    file_id=None,  # No file for dynamic wordlists
                    program_id=program.id,
                    created_by=created_by,
                    is_active=True,
                    is_dynamic=True,
                    dynamic_type=dynamic_type,
                    dynamic_config=dynamic_config
                )
                
                logger.debug("Adding wordlist to session...")
                db.add(wordlist)
                logger.debug("Committing transaction...")
                db.commit()
                logger.debug("Refreshing wordlist object...")
                db.refresh(wordlist)
                
                logger.info(f"Created dynamic wordlist with ID: {wordlist.id}, type: {dynamic_type}, program: {program_name}")
                
                return {
                    'id': str(wordlist.id),
                    'name': wordlist.name,
                    'description': wordlist.description,
                    'filename': None,
                    'content_type': 'text/plain',
                    'file_size': None,
                    'word_count': wordlist.word_count,
                    'tags': wordlist.tags,
                    'program_name': program_name,
                    'created_by': wordlist.created_by,
                    'file_id': None,
                    'is_active': wordlist.is_active,
                    'is_dynamic': True,
                    'dynamic_type': dynamic_type,
                    'dynamic_config': dynamic_config,
                    'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                    'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None,
                    'download_uri': f"/wordlists/{wordlist.id}/download"
                }
                
            except Exception as e:
                db.rollback()
                error_msg = str(e)
                logger.error(f"Error creating dynamic wordlist: {error_msg}")
                import traceback
                traceback.print_exc()
                # Re-raise with more specific error message for common issues
                if "is_dynamic" in error_msg or "dynamic_type" in error_msg or "dynamic_config" in error_msg:
                    raise Exception("Database migration V2.37.0 has not been applied. Please run migrations first.")
                if "file_id" in error_msg and "not-null" in error_msg.lower():
                    raise Exception("Database migration V2.37.0 has not been applied. Please run migrations first.")
                raise
    
    @staticmethod
    async def generate_dynamic_content(wordlist_id: str) -> Optional[Dict[str, Any]]:
        """
        Generate content for a dynamic wordlist.
        
        Args:
            wordlist_id: ID of the dynamic wordlist
            
        Returns:
            Dict with content bytes, filename, content_type, and file_size
        """
        async with get_db_session() as db:
            try:
                wordlist = db.query(Wordlist).filter(Wordlist.id == wordlist_id).first()
                
                if not wordlist:
                    logger.error(f"Wordlist {wordlist_id} not found")
                    return None
                
                if not wordlist.is_dynamic:
                    logger.error(f"Wordlist {wordlist_id} is not a dynamic wordlist")
                    return None
                
                dynamic_type = wordlist.dynamic_type
                dynamic_config = wordlist.dynamic_config or {}
                program_id = dynamic_config.get('program_id')
                
                if not program_id:
                    logger.error(f"Dynamic wordlist {wordlist_id} has no program_id in config")
                    return None
                
                # Generate content based on type
                word_count, content_lines = await WordlistsRepository._generate_dynamic_content_internal(
                    db, dynamic_type, program_id
                )
                
                # Convert to bytes
                content = '\n'.join(content_lines).encode('utf-8')
                
                # Update word count in database (it may have changed)
                wordlist.word_count = word_count
                wordlist.updated_at = datetime.now(timezone.utc)
                db.commit()
                
                logger.info(f"Generated dynamic content for wordlist {wordlist_id}: {word_count} words")
                
                return {
                    "content": content,
                    "filename": f"{wordlist.name}.txt",
                    "content_type": "text/plain",
                    "file_size": len(content)
                }
                
            except Exception as e:
                logger.error(f"Error generating dynamic content for wordlist {wordlist_id}: {str(e)}")
                import traceback
                traceback.print_exc()
                return None
    
    @staticmethod
    async def _generate_dynamic_content_internal(db, dynamic_type: str, program_id: str) -> tuple:
        """
        Internal method to generate dynamic content based on type.
        
        Args:
            db: Database session
            dynamic_type: Type of dynamic generation
            program_id: Program UUID string
            
        Returns:
            Tuple of (word_count, content_lines list)
        """
        if dynamic_type == "subdomain_prefixes":
            return await WordlistsRepository._generate_subdomain_prefixes(db, program_id)
        else:
            logger.error(f"Unknown dynamic wordlist type: {dynamic_type}")
            return 0, []
    
    @staticmethod
    async def _generate_subdomain_prefixes(db, program_id: str) -> tuple:
        """
        Generate subdomain prefixes wordlist from program's subdomain assets.
        
        Extracts the subdomain prefix by removing the apex domain suffix.
        
        Examples:
            sub1.domain.com (apex: domain.com) -> sub1
            sub2.domain.com (apex: domain.com) -> sub2
            sub3.sub4.domain.com (apex: domain.com) -> sub3.sub4
            
        Args:
            db: Database session
            program_id: Program UUID string
            
        Returns:
            Tuple of (word_count, content_lines list)
        """
        try:
            # Query all subdomains for this program with their apex domains
            subdomains = db.query(Subdomain, ApexDomain).join(
                ApexDomain, Subdomain.apex_domain_id == ApexDomain.id
            ).filter(
                Subdomain.program_id == program_id
            ).all()
            
            prefixes = set()
            
            for subdomain, apex_domain in subdomains:
                subdomain_name = subdomain.name.lower()
                apex_name = apex_domain.name.lower()
                
                # Extract prefix by removing apex domain suffix
                prefix = WordlistsRepository._extract_prefix(subdomain_name, apex_name)
                
                if prefix:
                    prefixes.add(prefix)
            
            # Sort prefixes for consistent output
            sorted_prefixes = sorted(prefixes)
            
            logger.info(f"Generated {len(sorted_prefixes)} subdomain prefixes for program {program_id}")
            
            return len(sorted_prefixes), sorted_prefixes
            
        except Exception as e:
            logger.error(f"Error generating subdomain prefixes: {str(e)}")
            import traceback
            traceback.print_exc()
            return 0, []
    
    @staticmethod
    def _extract_prefix(subdomain_name: str, apex_domain: str) -> Optional[str]:
        """
        Extract subdomain prefix by removing apex domain suffix.
        
        Args:
            subdomain_name: Full subdomain name (e.g., "sub1.domain.com")
            apex_domain: Apex domain name (e.g., "domain.com")
            
        Returns:
            Prefix string or None if subdomain equals apex domain
            
        Examples:
            ("sub1.domain.com", "domain.com") -> "sub1"
            ("sub3.sub4.domain.com", "domain.com") -> "sub3.sub4"
            ("domain.com", "domain.com") -> None (apex domain itself)
        """
        # Handle case where subdomain is the apex domain itself
        if subdomain_name == apex_domain:
            return None
        
        # Remove apex domain suffix with the dot
        suffix = '.' + apex_domain
        if subdomain_name.endswith(suffix):
            prefix = subdomain_name[:-len(suffix)]
            return prefix if prefix else None
        
        # Fallback: shouldn't happen if data is consistent
        logger.warning(f"Subdomain {subdomain_name} doesn't end with .{apex_domain}")
        return None
    
    # === COMMON METHODS (handle both static and dynamic) ===
    
    @staticmethod
    async def get_wordlist(wordlist_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific wordlist by ID (handles both static and dynamic)"""
        async with get_db_session() as db:
            try:
                wordlist = db.query(Wordlist).filter(Wordlist.id == wordlist_id).first()
                
                if not wordlist:
                    return None
                
                # Get program name
                program_name = None
                if wordlist.program_id:
                    program = db.query(Program).filter(Program.id == wordlist.program_id).first()
                    if program:
                        program_name = program.name
                
                # Handle dynamic vs static wordlists
                if wordlist.is_dynamic:
                    return {
                        'id': str(wordlist.id),
                        'name': wordlist.name,
                        'description': wordlist.description,
                        'filename': None,
                        'content_type': 'text/plain',
                        'file_size': None,
                        'word_count': wordlist.word_count,
                        'tags': wordlist.tags or [],
                        'program_name': program_name,
                        'created_by': wordlist.created_by,
                        'file_id': None,
                        'is_active': wordlist.is_active,
                        'is_dynamic': True,
                        'dynamic_type': wordlist.dynamic_type,
                        'dynamic_config': wordlist.dynamic_config,
                        'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                        'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None,
                        'download_uri': f"/wordlists/{wordlist.id}/download"
                    }
                else:
                    # Static wordlist - get file info
                    wordlist_file = db.query(WordlistFile).filter(WordlistFile.id == wordlist.file_id).first()
                    if not wordlist_file:
                        logger.error(f"Wordlist file not found for wordlist {wordlist_id}")
                        return None
                    
                    return {
                        'id': str(wordlist.id),
                        'name': wordlist.name,
                        'description': wordlist.description,
                        'filename': wordlist_file.filename,
                        'content_type': wordlist_file.content_type,
                        'file_size': wordlist_file.file_size,
                        'word_count': wordlist.word_count,
                        'tags': wordlist.tags or [],
                        'program_name': program_name,
                        'created_by': wordlist.created_by,
                        'file_id': str(wordlist_file.id),
                        'is_active': wordlist.is_active,
                        'is_dynamic': False,
                        'dynamic_type': None,
                        'dynamic_config': None,
                        'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                        'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None,
                        'download_uri': f"/wordlists/{wordlist.id}/download"
                    }
                
            except Exception as e:
                logger.error(f"Error fetching wordlist {wordlist_id}: {str(e)}")
                return None
    
    @staticmethod
    async def get_wordlist_file(wordlist_id: str) -> Optional[Dict[str, Any]]:
        """
        Get wordlist file content.
        
        For static wordlists: returns stored file content
        For dynamic wordlists: generates content on-the-fly
        """
        async with get_db_session() as db:
            try:
                wordlist = db.query(Wordlist).filter(Wordlist.id == wordlist_id).first()
                
                if not wordlist:
                    logger.error(f"Wordlist {wordlist_id} not found")
                    return None
                
                # Handle dynamic wordlists
                if wordlist.is_dynamic:
                    return await WordlistsRepository.generate_dynamic_content(wordlist_id)
                
                # Static wordlist - get file from database
                if not wordlist.file_id:
                    logger.error(f"No file_id found for static wordlist {wordlist_id}")
                    return None
                
                wordlist_file = db.query(WordlistFile).filter(WordlistFile.id == wordlist.file_id).first()
                if not wordlist_file:
                    logger.error(f"Wordlist file {wordlist.file_id} not found")
                    return None
                
                return {
                    "content": wordlist_file.file_content,
                    "filename": wordlist_file.filename,
                    "content_type": wordlist_file.content_type,
                    "file_size": wordlist_file.file_size
                }
                
            except Exception as e:
                logger.error(f"Error fetching wordlist file {wordlist_id}: {str(e)}")
                return None
    
    @staticmethod
    async def list_wordlists(
        skip: int = 0, 
        limit: int = 100, 
        active_only: bool = True,
        program_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None
    ) -> Dict[str, Any]:
        """List wordlists with optional filtering (includes both static and dynamic)"""
        async with get_db_session() as db:
            try:
                # Build query
                query = db.query(Wordlist)
                
                # Apply filters
                if active_only:
                    query = query.filter(Wordlist.is_active == True)
                
                if program_name:
                    query = query.join(Program).filter(Program.name == program_name)
                
                if tags:
                    # PostgreSQL array contains operator - use @> for array containment
                    for tag in tags:
                        query = query.filter(Wordlist.tags.op('@>')([tag]))
                
                if search:
                    query = query.filter(
                        or_(
                            Wordlist.name.ilike(f"%{search}%"),
                            Wordlist.description.ilike(f"%{search}%")
                        )
                    )
                
                # Get total count
                total = query.count()
                
                # Apply pagination and sorting
                wordlists = query.order_by(desc(Wordlist.created_at)).offset(skip).limit(limit).all()
                
                # Convert to dict format
                result_wordlists = []
                for wordlist in wordlists:
                    # Get program name
                    wl_program_name = None
                    if wordlist.program_id:
                        program = db.query(Program).filter(Program.id == wordlist.program_id).first()
                        if program:
                            wl_program_name = program.name
                    
                    if wordlist.is_dynamic:
                        # Dynamic wordlist
                        result_wordlists.append({
                            'id': str(wordlist.id),
                            'name': wordlist.name,
                            'description': wordlist.description,
                            'filename': None,
                            'content_type': 'text/plain',
                            'file_size': None,
                            'word_count': wordlist.word_count,
                            'tags': wordlist.tags or [],
                            'program_name': wl_program_name,
                            'created_by': wordlist.created_by,
                            'file_id': None,
                            'is_active': wordlist.is_active,
                            'is_dynamic': True,
                            'dynamic_type': wordlist.dynamic_type,
                            'dynamic_config': wordlist.dynamic_config,
                            'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                            'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None,
                            'download_uri': f"/wordlists/{wordlist.id}/download"
                        })
                    else:
                        # Static wordlist - get file info
                        wordlist_file = db.query(WordlistFile).filter(WordlistFile.id == wordlist.file_id).first()
                        if not wordlist_file:
                            continue
                        
                        result_wordlists.append({
                            'id': str(wordlist.id),
                            'name': wordlist.name,
                            'description': wordlist.description,
                            'filename': wordlist_file.filename,
                            'content_type': wordlist_file.content_type,
                            'file_size': wordlist_file.file_size,
                            'word_count': wordlist.word_count,
                            'tags': wordlist.tags or [],
                            'program_name': wl_program_name,
                            'created_by': wordlist.created_by,
                            'file_id': str(wordlist_file.id),
                            'is_active': wordlist.is_active,
                            'is_dynamic': False,
                            'dynamic_type': None,
                            'dynamic_config': None,
                            'created_at': wordlist.created_at.isoformat() if wordlist.created_at else None,
                            'updated_at': wordlist.updated_at.isoformat() if wordlist.updated_at else None,
                            'download_uri': f"/wordlists/{wordlist.id}/download"
                        })
                
                return {
                    "wordlists": result_wordlists,
                    "total": total,
                    "skip": skip,
                    "limit": limit
                }
                
            except Exception as e:
                logger.error(f"Error listing wordlists: {str(e)}")
                return {"wordlists": [], "total": 0, "skip": skip, "limit": limit}
    
    @staticmethod
    async def update_wordlist(wordlist_id: str, wordlist_data: Dict[str, Any]) -> bool:
        """Update wordlist metadata"""
        async with get_db_session() as db:
            try:
                # Check if wordlist exists
                wordlist = db.query(Wordlist).filter(Wordlist.id == wordlist_id).first()
                if not wordlist:
                    logger.warning(f"Wordlist {wordlist_id} not found")
                    return False
                
                # Update fields
                if 'name' in wordlist_data:
                    wordlist.name = wordlist_data['name']
                if 'description' in wordlist_data:
                    wordlist.description = wordlist_data['description']
                if 'tags' in wordlist_data:
                    wordlist.tags = wordlist_data['tags']
                if 'is_active' in wordlist_data:
                    wordlist.is_active = wordlist_data['is_active']
                
                # Update program if provided
                if 'program_name' in wordlist_data and wordlist_data['program_name']:
                    program = db.query(Program).filter(Program.name == wordlist_data['program_name']).first()
                    if program:
                        wordlist.program_id = program.id
                    else:
                        logger.warning(f"Program {wordlist_data['program_name']} not found")
                        return False
                
                wordlist.updated_at = datetime.now(timezone.utc)
                db.commit()
                
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating wordlist {wordlist_id}: {str(e)}")
                return False
    
    @staticmethod
    async def delete_wordlist(wordlist_id: str) -> bool:
        """Delete wordlist and its associated file (if static)"""
        async with get_db_session() as db:
            try:
                # Get wordlist to find file_id
                wordlist = db.query(Wordlist).filter(Wordlist.id == wordlist_id).first()
                if not wordlist:
                    logger.warning(f"Wordlist {wordlist_id} not found")
                    return False
                
                file_id = wordlist.file_id
                
                # Delete wordlist metadata first
                db.delete(wordlist)
                
                # Delete file content (only for static wordlists)
                if file_id:
                    wordlist_file = db.query(WordlistFile).filter(WordlistFile.id == file_id).first()
                    if wordlist_file:
                        db.delete(wordlist_file)
                        logger.info(f"Deleted wordlist file {file_id}")
                
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting wordlist {wordlist_id}: {str(e)}")
                return False
    
    @staticmethod
    def _count_words(file_content: bytes) -> int:
        """Count the number of words in the file content"""
        try:
            # Decode content as text
            content = file_content.decode('utf-8', errors='ignore')
            
            # Split by lines and count non-empty lines
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            return len(lines)
            
        except Exception as e:
            logger.error(f"Error counting words: {str(e)}")
            return 0
