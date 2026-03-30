from sqlalchemy import func, desc, asc, and_
from sqlalchemy.orm import joinedload
from typing import Dict, Any, Optional, List, Union
import logging
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlparse

from models.postgres import (
    Program, URL, ExtractedLink, ExtractedLinkSource,
    Certificate, Service, Subdomain, IP, URLService
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin
from utils import get_root_url
from repository.program_repo import ProgramRepository

logger = logging.getLogger(__name__)

class UrlAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def get_url_by_id(url_id: str) -> Optional[Dict[str, Any]]:
        """Get URL by ID"""
        from models.postgres import URLTechnology
        async with get_db_session() as db:
            try:
                url = (db.query(URL)
                      .options(
                          joinedload(URL.extracted_link_sources).joinedload(ExtractedLinkSource.extracted_link),
                          joinedload(URL.technology_associations).joinedload(URLTechnology.technology),
                          joinedload(URL.service_associations).joinedload(URLService.service)
                      )
                      .filter(URL.id == url_id)
                      .first())
                if not url:
                    return None

                # Get extracted links from the new relationship structure
                extracted_links = [source.extracted_link.link_url for source in url.extracted_link_sources]
                
                # Get technologies from the new relationship structure
                technologies = [assoc.technology.name for assoc in url.technology_associations]

                return {
                    'id': str(url.id),
                    'url': url.url,
                    'host': url.hostname,
                    'hostname': url.hostname,
                    'port': url.port,
                    'scheme': url.scheme,
                    'path': url.path,
                    'certificate_id': str(url.certificate_id) if url.certificate_id else None,
                    'service_ids': [str(a.service_id) for a in url.service_associations],
                    'subdomain_id': str(url.subdomain_id) if url.subdomain_id else None,
                    'program_name': url.program.name if url.program else None,
                    'http_status_code': url.http_status_code,
                    'http_method': url.http_method,
                    'response_time_ms': url.response_time_ms,
                    'title': url.title,
                    'content_length': url.content_length,
                    'content_type': url.content_type,
                    'technologies': technologies,
                    'extracted_links': extracted_links,
                    'final_url': url.final_url,
                    'redirect_chain': url.redirect_chain,
                    'chain_status_codes': url.chain_status_codes,
                    'line_count': url.line_count,
                    'word_count': url.word_count,
                    'response_body_hash': url.response_body_hash,
                    'body_preview': url.body_preview,
                    'favicon_hash': url.favicon_hash,
                    'favicon_url': url.favicon_url,
                    'notes': url.notes,
                    'created_at': url.created_at.isoformat() if url.created_at else None,
                    'updated_at': url.updated_at.isoformat() if url.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting URL by id {url_id}: {str(e)}")
                raise

    # Update methods
    @staticmethod
    async def update_url(url_id: str, url_data: Dict[str, Any]) -> bool:
        """Update a URL"""
        async with get_db_session() as db:
            try:
                url = db.query(URL).filter(URL.id == url_id).first()
                if not url:
                    return False
                
                for key, value in url_data.items():
                    if hasattr(url, key):
                        setattr(url, key, value)
                
                url.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating URL {url_id}: {str(e)}")
                raise

    # ==================
    # Typed URLs Query
    # ==================
    @staticmethod
    async def search_urls_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        protocol: Optional[str] = None,
        hostname: Optional[str] = None,
        status_code: Optional[int] = None,
        only_root: Optional[bool] = None,
        technology_text: Optional[str] = None,
        technology: Optional[str] = None,
        port: Optional[int] = None,
        unusual_ports: Optional[bool] = None,
        program: Optional[Union[str, List[str]]] = None,
        sort_by: str = "url",
        sort_dir: str = "asc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        from models.postgres import URLTechnology, Technology
        async with get_db_session() as db:
            try:
                base_query = (
                    db.query(URL)
                    .join(Program, Program.id == URL.program_id)
                    .options(
                        joinedload(URL.extracted_link_sources).joinedload(ExtractedLinkSource.extracted_link),
                        joinedload(URL.technology_associations).joinedload(URLTechnology.technology),
                        joinedload(URL.service_associations)
                    )
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": [], "total_count": 0}
                        base_query = base_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        base_query = base_query.filter(Program.name == program.strip())

                if search:
                    base_query = base_query.filter(URL.url.ilike(f"%{search}%"))
                
                if exact_match:
                    base_query = base_query.filter(URL.url == exact_match)
                if hostname:
                    base_query = base_query.filter(URL.hostname == hostname)
                if protocol:
                    base_query = base_query.filter(URL.scheme == protocol)
                if status_code is not None and str(status_code).isdigit():
                    base_query = base_query.filter(URL.http_status_code == int(status_code))
                if only_root is True:
                    base_query = base_query.filter(URL.path == '/')
                if technology_text:
                    # Join with technologies table for text search
                    base_query = base_query.join(URLTechnology, URLTechnology.url_id == URL.id).join(Technology, Technology.id == URLTechnology.technology_id)
                    base_query = base_query.filter(Technology.name.ilike(f"%{technology_text}%"))
                if technology:
                    # Exact match on technology name
                    base_query = base_query.join(URLTechnology, URLTechnology.url_id == URL.id).join(Technology, Technology.id == URLTechnology.technology_id)
                    base_query = base_query.filter(Technology.name == technology)
                if port is not None:
                    base_query = base_query.filter(URL.port == port)
                if unusual_ports is True:
                    base_query = base_query.filter(URL.port.notin_([80, 443]))

                sort_by_normalized = (sort_by or "url").lower()
                sort_dir_normalized = (sort_dir or "asc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "url":
                    base_query = base_query.order_by(direction_func(URL.url))
                elif sort_by_normalized == "http_status_code":
                    base_query = base_query.order_by(direction_func(URL.http_status_code))
                elif sort_by_normalized == "program_name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "updated_at":
                    base_query = base_query.order_by(direction_func(URL.updated_at))
                elif sort_by_normalized == "port":
                    base_query = base_query.order_by(direction_func(URL.port))
                else:
                    base_query = base_query.order_by(direction_func(URL.url))

                base_query = base_query.offset(skip).limit(limit)
                urls = base_query.all()
                items: List[Dict[str, Any]] = []
                for url in urls:
                    items.append(
                        {
                            "id": str(url.id),
                            "url": url.url,
                            "hostname": url.hostname,
                            "port": url.port,
                            "path": url.path,
                            "scheme": url.scheme,
                            "certificate_id": str(url.certificate_id) if url.certificate_id else None,
                            "service_ids": [str(a.service_id) for a in url.service_associations],
                            "subdomain_id": str(url.subdomain_id) if url.subdomain_id else None,
                            "http_status_code": url.http_status_code,
                            "title": url.title,
                            "content_length": url.content_length,
                            "content_type": url.content_type,
                            "technologies": [assoc.technology.name for assoc in url.technology_associations],
                            "extracted_links": [source.extracted_link.link_url for source in url.extracted_link_sources],
                            "program_name": url.program.name if url.program else None,
                            "created_at": url.created_at.isoformat() if url.created_at else None,
                            "updated_at": url.updated_at.isoformat() if url.updated_at else None,
                        }
                    )

                count_query = (
                    db.query(func.count(URL.id.distinct()))
                    .select_from(URL)
                    .join(Program, Program.id == URL.program_id)
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        count_query = count_query.filter(Program.name == program.strip())
                if search:
                    count_query = count_query.filter(URL.url.ilike(f"%{search}%"))
                
                if exact_match:
                    count_query = count_query.filter(URL.url == exact_match)
                if hostname:
                    count_query = count_query.filter(URL.hostname == hostname)
                if protocol:
                    count_query = count_query.filter(URL.scheme == protocol)
                if status_code is not None and str(status_code).isdigit():
                    count_query = count_query.filter(URL.http_status_code == int(status_code))
                if only_root is True:
                    count_query = count_query.filter(URL.path == '/')
                if technology_text:
                    count_query = count_query.join(URLTechnology, URLTechnology.url_id == URL.id).join(Technology, Technology.id == URLTechnology.technology_id)
                    count_query = count_query.filter(Technology.name.ilike(f"%{technology_text}%"))
                if technology:
                    count_query = count_query.join(URLTechnology, URLTechnology.url_id == URL.id).join(Technology, Technology.id == URLTechnology.technology_id)
                    count_query = count_query.filter(Technology.name == technology)
                if port is not None:
                    count_query = count_query.filter(URL.port == port)
                if unusual_ports is True:
                    count_query = count_query.filter(URL.port.notin_([80, 443]))

                total_count = count_query.scalar() or 0
                return {"items": items, "total_count": int(total_count)}
            except Exception as e:
                logger.error(f"Error executing typed URLs search: {str(e)}")
                raise

    @staticmethod
    async def _update_extracted_links(db, url_obj: URL, new_links: List[str], program_id: str, program_name: str) -> bool:
        """
        Update extracted links for a URL. Returns True if changes were made.
        Only inserts links whose hostnames are NOT in scope.
        """
        # Get current links for this URL
        current_links = {source.extracted_link.link_url for source in url_obj.extracted_link_sources}
        new_links_set = {link.strip() for link in new_links if link and link.strip()}

        # Filter out links that are in scope (we only want external links)
        filtered_links = set()
        for link_url in new_links_set:
            try:
                parsed = urlparse(link_url)
                hostname = parsed.hostname
                if hostname:
                    # Only add the link if it's NOT in scope (external link)
                    is_in_scope = await ProgramRepository.is_domain_in_scope(hostname, program_name)
                    if not is_in_scope:
                        filtered_links.add(link_url)
                    else:
                        logger.debug(f"Skipping in-scope link: {link_url} (hostname: {hostname})")
                else:
                    # If we can't parse hostname, skip the link
                    logger.debug(f"Skipping link with no hostname: {link_url}")
            except Exception as e:
                logger.debug(f"Error parsing link {link_url}: {e}")
                continue

        # Check if there are any changes
        if current_links == filtered_links:
            return False

        # Remove all existing link sources for this URL
        for source in url_obj.extracted_link_sources:
            db.delete(source)

        # Add new links (only external ones)
        for link_url in filtered_links:
            # Check if the extracted link already exists
            extracted_link = db.query(ExtractedLink).filter(
                ExtractedLink.link_url == link_url,
                ExtractedLink.program_id == program_id
            ).first()

            if not extracted_link:
                # Create new extracted link
                extracted_link = ExtractedLink(
                    link_url=link_url,
                    program_id=program_id
                )
                db.add(extracted_link)
                db.flush()  # Get the ID

            # Create the source relationship
            source = ExtractedLinkSource(
                extracted_link_id=extracted_link.id,
                source_url_id=url_obj.id
            )
            db.add(source)

        return True

    @staticmethod
    def _update_url_technologies(db, url_obj: URL, new_technologies: List[str], program_id: str) -> bool:
        """
        Update technologies for a URL. Returns True if changes were made.
        Manages the many-to-many relationship via url_technologies junction table.
        Technologies are ADDITIVE - existing technologies are always kept, new ones are added.
        """
        from models.postgres import Technology, URLTechnology
        
        # Get current technologies for this URL
        current_techs = {assoc.technology.name for assoc in url_obj.technology_associations}
        
        # Normalize new technologies (same normalization as before)
        normalized_techs = set()
        for tech in new_technologies:
            if tech and tech.strip():
                # Apply same normalization: lowercase and replace special chars with underscore
                normalized = tech.strip().lower()
                normalized = normalized.replace(" ", "_").replace("-", "_").replace(".", "_").replace(":", "_").replace("/", "_")
                normalized_techs.add(normalized)
        
        # If no new technologies provided, don't modify existing ones
        if not normalized_techs:
            return False
        
        # Merge with existing technologies (ALWAYS keep existing + add new)
        merged_techs = current_techs | normalized_techs
        
        # Check if there are any new technologies to add
        if current_techs == merged_techs:
            return False  # No new technologies to add
        
        # Only add the NEW technologies (don't remove existing ones)
        new_techs_to_add = merged_techs - current_techs
        
        for tech_name in new_techs_to_add:
            # Find or create technology
            technology = db.query(Technology).filter(
                Technology.name == tech_name,
                Technology.program_id == program_id
            ).first()
            
            if not technology:
                technology = Technology(
                    name=tech_name,
                    program_id=program_id
                )
                db.add(technology)
                db.flush()  # Get the ID
            
            # Create association
            assoc = URLTechnology(
                technology_id=technology.id,
                url_id=url_obj.id
            )
            db.add(assoc)
        
        return True

    @staticmethod
    def _resolve_url_relations(db, url_data: Dict[str, Any], program_id) -> tuple[Optional[str], List[str], Optional[str]]:
        """Resolve certificate_id, service_ids, subdomain_id from url_data.
        Returns (certificate_id, service_ids, subdomain_id). service_ids is a list (hostname can resolve to multiple IPs)."""
        certificate_id = None
        service_ids: List[str] = []
        subdomain_id = None

        # Certificate: when HTTPS and certificate_serial provided
        scheme = (url_data.get("scheme") or "").lower()
        cert_serial = url_data.get("certificate_serial")
        if cert_serial and scheme == "https":
            cert = db.query(Certificate).filter(
                Certificate.serial_number == cert_serial,
                Certificate.program_id == program_id
            ).first()
            if cert:
                certificate_id = str(cert.id)

        # Services: when ips and port provided - resolve ALL IPs (hostname can resolve to multiple)
        ips = url_data.get("ips") or []
        port = url_data.get("port")
        if ips and port is not None:
            port_int = int(port)
            for ip_val in ips:
                ip_str = ip_val if isinstance(ip_val, str) else str(ip_val)
                ip_obj = db.query(IP).filter(
                    IP.ip_address == ip_str,
                    IP.program_id == program_id
                ).first()
                if ip_obj:
                    svc = db.query(Service).filter(
                        Service.ip_id == ip_obj.id,
                        Service.port == port_int,
                        Service.program_id == program_id
                    ).first()
                    if svc and str(svc.id) not in service_ids:
                        service_ids.append(str(svc.id))

        # Subdomain: when hostname provided
        hostname = url_data.get("hostname")
        if hostname:
            sub = db.query(Subdomain).filter(
                Subdomain.name == hostname,
                Subdomain.program_id == program_id
            ).first()
            if sub:
                subdomain_id = str(sub.id)

        return certificate_id, service_ids, subdomain_id

    @staticmethod
    def _get_relations_from_root_url(db, url: str, program_id, certificate_id, service_ids, subdomain_id) -> tuple[Optional[str], List[str], Optional[str]]:
        """When relations are missing, inherit from the root URL (scheme://host:port/) if it exists.
        Root URL is typically populated by test_http; path URLs from fuzz/crawl/nuclei may lack relations."""
        root_url = get_root_url(url)
        if not root_url or root_url == url:
            return certificate_id, service_ids, subdomain_id
        if certificate_id and service_ids and subdomain_id:
            return certificate_id, service_ids, subdomain_id

        root_url_obj = db.query(URL).options(
            joinedload(URL.service_associations)
        ).filter(
            and_(URL.url == root_url, URL.program_id == program_id)
        ).first()
        if not root_url_obj:
            return certificate_id, service_ids, subdomain_id

        if not certificate_id and root_url_obj.certificate_id:
            certificate_id = str(root_url_obj.certificate_id)
        if not service_ids and root_url_obj.service_associations:
            service_ids = [str(a.service_id) for a in root_url_obj.service_associations]
        if not subdomain_id and root_url_obj.subdomain_id:
            subdomain_id = str(root_url_obj.subdomain_id)

        return certificate_id, service_ids, subdomain_id

    @staticmethod
    def _update_url_services(db, url_obj: URL, new_service_ids: List[str]) -> bool:
        """Update URL-service associations. Returns True if changes were made."""
        current_ids = {str(a.service_id) for a in url_obj.service_associations}
        new_ids = set(new_service_ids)
        if current_ids == new_ids:
            return False
        for assoc in list(url_obj.service_associations):
            db.delete(assoc)
        for svc_id in new_ids:
            assoc = URLService(url_id=url_obj.id, service_id=UUID(svc_id))
            db.add(assoc)
        return True

    @staticmethod
    async def create_or_update_url(url_data: Dict[str, Any]) -> tuple[Optional[str], str]:
        """Create a new URL or update if exists with merged data.
        Returns (url_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                logger.debug(f"create_or_update_url called with URL data: {url_data}")
                # Find program by name
                program = db.query(Program).filter(Program.name == url_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{url_data.get('program_name')}' not found")
                
                # Check if URL hostname is in scope
                try:
                    url_hostname = url_data.get("hostname")
                except:
                    url_hostname = urlparse(url_data.get("url")).hostname
                
                is_in_scope = await ProgramRepository.is_domain_in_scope(url_hostname, program.name)


                if not is_in_scope:
                    logger.debug(f"URL {url_data.get('url')} is not in scope, skipping")
                    return None, "skipped"

                # Resolve relations (certificate, services, subdomain) - processed in same batch
                certificate_id, service_ids, subdomain_id = UrlAssetsRepository._resolve_url_relations(
                    db, url_data, program.id
                )
                # Inherit missing relations from root URL (e.g. https://example.com:443/) when path URLs
                # are added by fuzz/crawl/nuclei without full test_http data
                certificate_id, service_ids, subdomain_id = UrlAssetsRepository._get_relations_from_root_url(
                    db, url_data.get('url', ''), program.id, certificate_id, service_ids, subdomain_id
                )

                # Check if URL already exists for this program
                existing = db.query(URL).filter(
                    and_(URL.url == url_data.get('url'), URL.program_id == program.id)
                ).first()
                
                if existing:
                    # Track what fields actually changed for meaningful update detection
                    meaningful_changes = []

                    # Define simple fields that should be compared for changes
                    simple_fields = [
                        'http_status_code', 'content_type', 'content_length', 'line_count',
                        'word_count', 'title', 'final_url', 'response_body_hash', 'body_preview'
                    ]

                    # Compare simple fields
                    for field in simple_fields:
                        if field in url_data and url_data[field] is not None:
                            existing_value = getattr(existing, field)
                            if url_data[field] != existing_value:
                                setattr(existing, field, url_data[field])
                                meaningful_changes.append(field)

                    # Handle technologies via many-to-many relationship
                    if 'technologies' in url_data and isinstance(url_data['technologies'], list):
                        if UrlAssetsRepository._update_url_technologies(
                            db, existing, url_data['technologies'], str(program.id)
                        ):
                            meaningful_changes.append('technologies')

                    # Handle extracted links
                    if 'extracted_links' in url_data and isinstance(url_data['extracted_links'], list):
                        if await UrlAssetsRepository._update_extracted_links(db, existing, url_data['extracted_links'], str(program.id), program.name):
                            meaningful_changes.append('extracted_links')

                    # Update notes if provided and different (notes is not in the main meaningful fields list)
                    if url_data.get('notes') is not None and url_data.get('notes') != existing.notes:
                        existing.notes = url_data.get('notes')
                        meaningful_changes.append('notes')

                    # Update relations when resolved
                    if certificate_id is not None and str(existing.certificate_id or "") != certificate_id:
                        existing.certificate_id = UUID(certificate_id)
                        meaningful_changes.append('certificate_id')
                    if service_ids and UrlAssetsRepository._update_url_services(db, existing, service_ids):
                        meaningful_changes.append('service_ids')
                    if subdomain_id is not None and str(existing.subdomain_id or "") != subdomain_id:
                        existing.subdomain_id = UUID(subdomain_id)
                        meaningful_changes.append('subdomain_id')

                    # Update timestamp if any changes were made
                    if meaningful_changes:
                        existing.updated_at = datetime.now(timezone.utc)
                        logger.debug(f"Updated existing URL {url_data.get('url')} with changes: {meaningful_changes}")
                    #else:
                        #logger.debug(f"URL {url_data.get('url')} already exists with same data, skipping")

                    db.commit()

                    # Determine action based on what actually changed
                    # Only mark as "updated" if meaningful changes occurred
                    if meaningful_changes:
                        # Meaningful changes occurred - this is a real update
                        action = "updated"
                        logger.debug(f"URL {url_data.get('url')} updated with changes: {meaningful_changes}")
                    else:
                        # No meaningful changes - this is a duplicate/skipped operation
                        action = "skipped"
                        logger.debug(f"URL {url_data.get('url')} had no meaningful changes, marked as skipped")

                    return str(existing.id), action
                else:
                    # Create new URL (without technologies - they'll be added via relationship)
                    url = URL(
                        url=url_data.get('url'),
                        hostname=url_data.get('hostname'),
                        port=url_data.get('port'),
                        path=url_data.get('path'),
                        scheme=url_data.get('scheme'),
                        http_status_code=url_data.get('http_status_code'),
                        http_method=url_data.get('http_method', 'GET'),
                        response_time_ms=url_data.get('response_time_ms'),
                        content_type=url_data.get('content_type'),
                        content_length=url_data.get('content_length'),
                        line_count=url_data.get('line_count'),
                        word_count=url_data.get('word_count'),
                        title=url_data.get('title'),
                        final_url=url_data.get('final_url'),
                        response_body_hash=url_data.get('response_body_hash'),
                        body_preview=url_data.get('body_preview'),
                        favicon_hash=url_data.get('favicon_hash'),
                        favicon_url=url_data.get('favicon_url'),
                        redirect_chain=url_data.get('redirect_chain'),
                        chain_status_codes=url_data.get('chain_status_codes', []),
                        certificate_id=UUID(certificate_id) if certificate_id else None,
                        subdomain_id=UUID(subdomain_id) if subdomain_id else None,
                        program_id=program.id,
                        notes=url_data.get('notes')
                    )

                    db.add(url)
                    db.commit()
                    db.refresh(url)

                    # Add service associations (many-to-many)
                    if service_ids:
                        for svc_id in service_ids:
                            assoc = URLService(url_id=url.id, service_id=UUID(svc_id))
                            db.add(assoc)
                        db.commit()
                    
                    # Add technologies via many-to-many relationship
                    if 'technologies' in url_data and isinstance(url_data['technologies'], list):
                        UrlAssetsRepository._update_url_technologies(
                            db, url, url_data['technologies'], str(program.id)
                        )
                        db.commit()

                    # Add extracted links if provided (only external ones)
                    if 'extracted_links' in url_data and isinstance(url_data['extracted_links'], list):
                        for link_url in url_data['extracted_links']:
                            if link_url and link_url.strip():
                                link_url = link_url.strip()

                                # Check if the link is in scope (skip if it is)
                                try:
                                    parsed = urlparse(link_url)
                                    hostname = parsed.hostname
                                    if hostname:
                                        # Only add the link if it's NOT in scope (external link)
                                        is_in_scope = await ProgramRepository.is_domain_in_scope(hostname, program.name)
                                        if is_in_scope:
                                            logger.debug(f"Skipping in-scope link during URL creation: {link_url} (hostname: {hostname})")
                                            continue
                                    else:
                                        # If we can't parse hostname, skip the link
                                        logger.debug(f"Skipping link with no hostname during URL creation: {link_url}")
                                        continue
                                except Exception as e:
                                    logger.debug(f"Error parsing link during URL creation {link_url}: {e}")
                                    continue

                                # Check if the extracted link already exists
                                extracted_link = db.query(ExtractedLink).filter(
                                    ExtractedLink.link_url == link_url,
                                    ExtractedLink.program_id == program.id
                                ).first()

                                if not extracted_link:
                                    # Create new extracted link
                                    extracted_link = ExtractedLink(
                                        link_url=link_url,
                                        program_id=program.id
                                    )
                                    db.add(extracted_link)
                                    db.flush()  # Get the ID

                                # Create the source relationship
                                source = ExtractedLinkSource(
                                    extracted_link_id=extracted_link.id,
                                    source_url_id=url.id
                                )
                                db.add(source)
                        db.commit()
                
                return str(url.id), "created"  # Newly created asset
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating URL: {str(e)}")
                raise

    @staticmethod
    async def add_extracted_links(url_id: str, links: List[str]) -> bool:
        """Add extracted links to an existing URL. Only adds links whose hostnames are NOT in scope."""
        async with get_db_session() as db:
            try:
                # Find the URL
                url = db.query(URL).filter(URL.id == url_id).first()
                if not url:
                    logger.error(f"URL {url_id} not found")
                    return False

                # Get the program for scope checking
                program = db.query(Program).filter(Program.id == url.program_id).first()
                if not program:
                    logger.error(f"Program not found for URL {url_id}")
                    return False

                # Filter out links that are in scope (we only want external links)
                filtered_links = []
                for link_url in links:
                    if link_url and link_url.strip():
                        link_url = link_url.strip()
                        try:
                            parsed = urlparse(link_url)
                            hostname = parsed.hostname
                            if hostname:
                                # Only add the link if it's NOT in scope (external link)
                                is_in_scope = await ProgramRepository.is_domain_in_scope(hostname, program.name)
                                if not is_in_scope:
                                    filtered_links.append(link_url)
                                else:
                                    logger.debug(f"Skipping in-scope link: {link_url} (hostname: {hostname})")
                            else:
                                # If we can't parse hostname, skip the link
                                logger.debug(f"Skipping link with no hostname: {link_url}")
                        except Exception as e:
                            logger.debug(f"Error parsing link {link_url}: {e}")
                            continue

                # Add new links (avoiding duplicates)
                links_added = 0
                for link_url in filtered_links:
                    # Check if the extracted link already exists
                    extracted_link = db.query(ExtractedLink).filter(
                        ExtractedLink.link_url == link_url,
                        ExtractedLink.program_id == url.program_id
                    ).first()

                    if not extracted_link:
                        # Create new extracted link
                        extracted_link = ExtractedLink(
                            link_url=link_url,
                            program_id=url.program_id
                        )
                        db.add(extracted_link)
                        db.flush()  # Get the ID

                    # Check if source relationship already exists
                    existing_source = db.query(ExtractedLinkSource).filter(
                        ExtractedLinkSource.extracted_link_id == extracted_link.id,
                        ExtractedLinkSource.source_url_id == url.id
                    ).first()

                    if not existing_source:
                        # Create the source relationship
                        source = ExtractedLinkSource(
                            extracted_link_id=extracted_link.id,
                            source_url_id=url.id
                        )
                        db.add(source)
                        links_added += 1

                if links_added > 0:
                    db.commit()
                    logger.debug(f"Added {links_added} external extracted links to URL {url_id}")
                elif filtered_links:
                    logger.debug(f"No new external links to add for URL {url_id} (all were duplicates)")
                else:
                    logger.debug(f"No external links found to add for URL {url_id} (all were in scope)")

                return True

            except Exception as e:
                db.rollback()
                logger.error(f"Error adding extracted links to URL {url_id}: {str(e)}")
                return False

    @staticmethod
    async def delete_url(url_id: str) -> bool:
        """Delete a single URL by ID"""
        async with get_db_session() as db:
            try:
                url = db.query(URL).filter(URL.id == url_id).first()
                if not url:
                    return False
                
                db.delete(url)
                db.commit()
                
                logger.info(f"Successfully deleted URL with ID: {url_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting URL {url_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_urls_batch(url_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple URLs by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for url_id in url_ids:
                    try:
                        # Skip null/undefined IDs
                        if url_id is None:
                            error_count += 1
                            error_msg = "Invalid URL ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if url_id == "":
                            error_count += 1
                            error_msg = "Invalid URL ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            url_uuid = UUID(url_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid URL ID format '{url_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the URL
                        url = db.query(URL).filter(URL.id == url_uuid).first()
                        
                        if not url:
                            not_found_count += 1
                            logger.warning(f"URL with ID {url_id} not found")
                            continue
                        
                        # Delete the URL
                        db.delete(url)
                        deleted_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting URL {url_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                logger.info(f"Batch delete completed for URLs: {deleted_count} deleted, {not_found_count} not found, {error_count} errors")
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for URLs: {str(e)}")
                raise

    @staticmethod
    async def get_technologies_with_urls(
        program_filter: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
        sort_by: Optional[str] = 'count',
        sort_order: Optional[str] = 'desc'
    ) -> Dict[str, Any]:
        """
        Get all technologies with their associated URLs and counts.
        Optimized to use a single efficient query instead of N+1 queries.
        Supports pagination, search, and sorting for better performance with large datasets.
        
        Args:
            program_filter: Optional list of program names to filter by
            page: Page number (1-based)
            page_size: Number of technologies per page
            search: Optional search filter for technology name
            sort_by: Field to sort by ('name' or 'count')
            sort_order: Sort order ('asc' or 'desc')
            
        Returns:
            Dict with 'items' (list of technologies) and 'pagination' metadata
        """
        from sqlalchemy import text
        
        async with get_db_session() as db:
            try:
                # Build filter conditions
                params = {}
                conditions = []
                
                if program_filter:
                    conditions.append("p.name = ANY(:program_filter)")
                    params['program_filter'] = program_filter
                
                if search:
                    conditions.append("t.name ILIKE :search")
                    params['search'] = f"%{search}%"
                
                # Combine conditions with AND
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                
                # First, get total count of technologies for pagination
                # Count only technologies that have associated URLs (matching main query logic)
                count_query = text(f"""
                    SELECT COUNT(DISTINCT t.name)
                    FROM technologies t
                    JOIN url_technologies ut ON ut.technology_id = t.id
                    JOIN urls u ON u.id = ut.url_id
                    JOIN programs p ON p.id = t.program_id
                    WHERE {where_clause}
                """)
                
                count_result = db.execute(count_query, params)
                total_items = count_result.scalar() or 0
                
                # Calculate pagination
                offset = (page - 1) * page_size
                total_pages = (total_items + page_size - 1) // page_size if total_items > 0 else 0
                
                # Determine sort order
                sort_field = 'website_count' if sort_by == 'count' else 'tech_name'
                sort_direction = sort_order.upper() if sort_order in ('asc', 'desc') else 'DESC'
                
                # Build ORDER BY clause
                if sort_by == 'count':
                    order_by = f"ORDER BY website_count {sort_direction}, tech_name ASC"
                else:  # sort by name
                    order_by = f"ORDER BY tech_name {sort_direction}"
                
                # Build optimized query using PostgreSQL to do the heavy lifting
                # This fetches everything in ONE query instead of N+1 queries
                sql_query = text(f"""
                    WITH ranked_urls AS (
                        SELECT 
                            t.name as tech_name,
                            u.id as url_id,
                            u.url,
                            u.hostname,
                            u.scheme,
                            u.port,
                            -- Create root website identifier
                            CASE 
                                WHEN u.port IN (80, 443) OR u.port IS NULL THEN 
                                    COALESCE(u.scheme, 'http') || '://' || u.hostname
                                ELSE 
                                    COALESCE(u.scheme, 'http') || '://' || u.hostname || ':' || u.port
                            END as root_website,
                            -- Rank URLs per technology to limit results
                            ROW_NUMBER() OVER (PARTITION BY t.name ORDER BY u.url) as rn
                        FROM technologies t
                        JOIN url_technologies ut ON ut.technology_id = t.id
                        JOIN urls u ON u.id = ut.url_id
                        JOIN programs p ON p.id = t.program_id
                        WHERE {where_clause}
                    ),
                    unique_websites AS (
                        SELECT DISTINCT ON (tech_name, root_website)
                            tech_name,
                            url_id,
                            url,
                            hostname,
                            COALESCE(scheme, 'http') as scheme,
                            port,
                            root_website
                        FROM ranked_urls
                        WHERE rn <= 100  -- Limit to 100 URLs per technology for performance
                    ),
                    tech_summary AS (
                        SELECT 
                            tech_name,
                            COUNT(DISTINCT root_website) as website_count,
                            json_agg(
                                json_build_object(
                                    'id', url_id,
                                    'url', url,
                                    'rootWebsite', root_website,
                                    'host', hostname,
                                    'scheme', scheme,
                                    'port', port,
                                    'technologies', ARRAY[tech_name]
                                )
                                ORDER BY root_website
                            ) as websites
                        FROM unique_websites
                        GROUP BY tech_name
                    )
                    SELECT 
                        tech_name,
                        website_count,
                        websites
                    FROM tech_summary
                    {order_by}
                    LIMIT :limit OFFSET :offset
                """)
                
                # Add pagination parameters
                params['limit'] = page_size
                params['offset'] = offset
                
                # Execute query with parameters
                result = db.execute(sql_query, params)
                rows = result.fetchall()
                
                # Format results
                technologies = []
                for row in rows:
                    tech_name, website_count, websites_json = row
                    technologies.append({
                        'name': tech_name,
                        'count': website_count,
                        'total_urls': website_count,  # Approximate since we limit
                        'websites': websites_json or []
                    })
                
                return {
                    'items': technologies,
                    'pagination': {
                        'total_items': total_items,
                        'total_pages': total_pages,
                        'current_page': page,
                        'page_size': page_size,
                        'has_next': page < total_pages,
                        'has_prev': page > 1
                    }
                }
                
            except Exception as e:
                logger.error(f"Error getting technologies with URLs: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in URL assets"""
        
        async with get_db_session() as db:
            try:
                query = db.query(URL).join(Program, Program.id == URL.program_id, isouter=True)
                
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
                if field_name == 'hostname':
                    values = query.with_entities(URL.hostname).distinct().all()
                elif field_name == 'scheme':
                    values = query.with_entities(URL.scheme).distinct().all()
                elif field_name == 'technologies':
                    # Query from the new technologies table
                    from models.postgres import Technology
                    tech_query = db.query(Technology).join(Program, Program.id == Technology.program_id)

                    # Apply program filter if provided
                    if filter_data and filter_data.get('program_name'):
                        program_value = filter_data['program_name']
                        if isinstance(program_value, list):
                            if len(program_value) == 0:
                                return []
                            tech_query = tech_query.filter(Program.name.in_(program_value))
                        else:
                            tech_query = tech_query.filter(Program.name == program_value)

                    values = tech_query.with_entities(Technology.name).distinct().all()
                elif field_name == 'extracted_links':
                    # Query from the new extracted_links table structure
                    from models.postgres import ExtractedLink
                    link_query = db.query(ExtractedLink).join(Program, Program.id == ExtractedLink.program_id)

                    # Apply program filter if provided
                    if filter_data and filter_data.get('program_name'):
                        program_value = filter_data['program_name']
                        if isinstance(program_value, list):
                            if len(program_value) == 0:
                                return []
                            link_query = link_query.filter(Program.name.in_(program_value))
                        else:
                            link_query = link_query.filter(Program.name == program_value)

                    values = link_query.with_entities(ExtractedLink.link_url).distinct().all()
                elif field_name == 'content_type':
                    values = query.with_entities(URL.content_type).distinct().all()
                elif field_name == 'title':
                    values = query.with_entities(URL.title).distinct().all()
                elif field_name == 'port':
                    values = query.with_entities(URL.port).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for URL assets")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in URL assets: {str(e)}")
                raise