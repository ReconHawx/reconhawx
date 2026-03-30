from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import logging
from pydantic import BaseModel, Field
from sqlalchemy.orm import joinedload
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs
from models.user_postgres import UserResponse
from repository.common_findings_repo import CommonFindingsRepository

logger = logging.getLogger(__name__)
router = APIRouter()

class QueryFilter(BaseModel):
    filter: Dict[str, Any]
    limit: Optional[int] = None
    skip: Optional[int] = 0
    sort: Optional[Dict[str, int]] = None

# Pydantic model for external links search request
class ExternalLinksSearchRequest(BaseModel):
    program: Optional[str] = Field(None, description="Filter by program name")
    link_search: Optional[str] = Field(None, description="Search within link URLs")
    link_negative: Optional[bool] = Field(False, description="Exclude matches instead of including them")
    root_site: Optional[str] = Field(None, description="Filter by root website")
    sort_by: Optional[str] = Field("url", description="Sort field")
    sort_dir: Optional[str] = Field("asc", description="Sort direction (asc/desc)")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(100, ge=1, le=1000, description="Page size")

# Pydantic model for typosquat processing response


@router.post("/external-links/search", response_model=Dict[str, Any])
async def search_external_links(
    request: ExternalLinksSearchRequest,
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Search external links with filtering and pagination for workflow input.
    
    Returns a flat list of destination URLs (external links) with pagination metadata.
    """
    try:
        from models.postgres import URL, Program, ExtractedLinkSource
        from db import get_db_session
        
        # Resolve programs within user access
        accessible = get_user_accessible_programs(current_user)
        requested_program = request.program
        
        programs: Optional[List[str]] = None
        if current_user.is_superuser or "admin" in current_user.roles:
            programs = [requested_program] if requested_program else None
        else:
            allowed = accessible or []
            if not allowed:
                return {
                    "status": "success",
                    "pagination": {
                        "total_items": 0,
                        "total_pages": 1,
                        "current_page": request.page,
                        "page_size": request.page_size,
                        "has_next": False,
                        "has_previous": False,
                    },
                    "items": [],
                }
            if requested_program:
                if requested_program not in allowed:
                    return {
                        "status": "success",
                        "pagination": {
                            "total_items": 0,
                            "total_pages": 1,
                            "current_page": request.page,
                            "page_size": request.page_size,
                            "has_next": False,
                            "has_previous": False,
                        },
                        "items": [],
                    }
                programs = [requested_program]
            else:
                programs = allowed

        async with get_db_session() as db:
            # Build the PostgreSQL query for URLs that have extracted links
            query = db.query(URL).join(Program).options(joinedload(URL.extracted_link_sources).joinedload(ExtractedLinkSource.extracted_link))
            
            # Apply program filter
            if programs:
                if len(programs) == 1:
                    query = query.filter(Program.name == programs[0])
                else:
                    query = query.filter(Program.name.in_(programs))
            
            # Filter for URLs that have extracted links (via relationship)
            query = query.filter(URL.extracted_link_sources.any())
            
            urls_with_links = query.all()
            
            logger.info(f"Found {len(urls_with_links)} URLs with links for program={requested_program}")
            
            # Extract all unique destination URLs (external links)
            destination_urls_set = set()
            destination_urls_map = {}  # url -> source_url for metadata
            
            for url_obj in urls_with_links:
                try:
                    link_sources = url_obj.extracted_link_sources or []
                    for source in link_sources:
                        link_url = source.extracted_link.link_url
                        # Skip None or empty links
                        if not link_url or not isinstance(link_url, str):
                            continue
                        
                        # Apply link search filter if specified
                        if request.link_search:
                            try:
                                contains = request.link_search.lower() in link_url.lower()
                                # If negative flag set, skip links that CONTAIN search; else include only those containing
                                if (not request.link_negative and not contains) or (request.link_negative and contains):
                                    continue
                            except AttributeError:
                                continue
                        
                        # Apply root site filter if specified
                        if request.root_site:
                            scheme = (url_obj.scheme or 'http').lower()
                            host = url_obj.hostname or ''
                            port = url_obj.port
                            if host:
                                needs_port = port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443))
                                port_part = f":{port}" if needs_port else ''
                                root_site_url = f"{scheme}://{host}{port_part}/"
                            else:
                                root_site_url = url_obj.url or ''
                            
                            if root_site_url != request.root_site:
                                continue
                        
                        # Add to set (deduplicate) and track source URL
                        if link_url not in destination_urls_set:
                            destination_urls_set.add(link_url)
                            destination_urls_map[link_url] = url_obj.url or ''
                        
                except Exception as e:
                    logger.error(f"Error processing URL object: {e}")
                    continue
            
            # Convert to list and sort
            destination_urls_list = list(destination_urls_set)
            
            # Sort the list
            if request.sort_by == "url":
                destination_urls_list.sort(reverse=(request.sort_dir == "desc"))
            else:
                # Default sort by URL ascending
                destination_urls_list.sort()
            
            # Paginate
            total_items = len(destination_urls_list)
            skip = (request.page - 1) * request.page_size
            paginated_urls = destination_urls_list[skip:skip + request.page_size]
            
            # Build response items with metadata
            items = []
            for url in paginated_urls:
                items.append({
                    "url": url,
                    "source_url": destination_urls_map.get(url, "")
                })
            
            total_pages = (total_items + request.page_size - 1) // request.page_size if request.page_size > 0 else 1
            
            return {
                "status": "success",
                "pagination": {
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "current_page": request.page,
                    "page_size": request.page_size,
                    "has_next": request.page < total_pages,
                    "has_previous": request.page > 1,
                },
                "items": items,
            }
            
    except Exception as e:
        logger.error(f"Error searching external links: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error searching external links: {str(e)}"
        )

@router.get("/external-links/", response_model=Dict[str, Any])
async def get_external_links(
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    link_search: Optional[str] = Query(None, description="Search within link URLs"),
    link_negative: Optional[bool] = Query(False, description="Exclude matches instead of including them"),
    root_site: Optional[str] = Query(None, description="Filter by root website"),
    page: Optional[int] = Query(None, description="Page number (optional, for pagination)"),
    page_size: Optional[int] = Query(None, description="Page size (optional, for pagination)"),
    current_user: UserResponse = Depends(get_current_user_from_middleware)
):
    """
    Get external links grouped by destination website.
    
    This endpoint processes URL assets that have a non-empty 'extracted_links' field and groups
    them by destination website, similar to the Django implementation.
    """
    try:
        from models.postgres import URL, Program, ExtractedLinkSource
        from db import get_db_session

        async with get_db_session() as db:
            # Build the PostgreSQL query for URLs that have extracted links
            query = db.query(URL).join(Program).options(joinedload(URL.extracted_link_sources).joinedload(ExtractedLinkSource.extracted_link))
            
            # Apply user program permissions
            accessible_programs = get_user_accessible_programs(current_user)
            # For superusers/admins, accessible_programs is empty (meaning no restrictions)
            if accessible_programs:
                # Regular users are restricted to their accessible programs
                if program_name and program_name not in accessible_programs:
                    # User doesn't have access to the requested program - return empty result
                    return {
                        "dest_grouped_links": {},
                        "grouped_links": {},
                        "root_sites_list": [],
                        "selected_root": root_site,
                        "selected_program": program_name,
                        "link_search": link_search or '',
                        "link_negative": link_negative
                    }
                
                # Filter to accessible programs
                program_filter = Program.name.in_(accessible_programs)
                if program_name:
                    # Both accessible and specific program filter
                    query = query.filter(Program.name == program_name)
                else:
                    # Just accessible programs
                    query = query.filter(program_filter)
            else:
                # Superuser/admin - apply program filter if specified
                if program_name:
                    query = query.filter(Program.name == program_name)
            
            # Filter for URLs that have extracted links (via relationship)
            query = query.filter(URL.extracted_link_sources.any())
            
            urls_with_links = query.all()
            
            logger.info(f"Found {len(urls_with_links)} URLs with links for program_name='{program_name}'")
            
            # Build nested grouping: root -> dest_link -> set(sources)
            grouping = {}
            for i, url_obj in enumerate(urls_with_links):
                try:
                    # Compute root website (scheme://host[:port]/)
                    scheme = (url_obj.scheme or 'http').lower()
                    host = url_obj.hostname or ''
                    port = url_obj.port
                    
                    if host:
                        needs_port = port and not ((scheme == 'http' and port == 80) or (scheme == 'https' and port == 443))
                        port_part = f":{port}" if needs_port else ''
                        root_site_url = f"{scheme}://{host}{port_part}/"
                    else:
                        root_site_url = url_obj.url or ''
                    
                    # Get links from the new relationship structure
                    link_sources = url_obj.extracted_link_sources or []

                    # Process each link in the URL's extracted links relationship
                    for source in link_sources:
                        link_url = source.extracted_link.link_url
                        # Skip None or empty links
                        if not link_url or not isinstance(link_url, str):
                            continue
                            
                        # Apply link search filter if specified
                        if link_search:
                            try:
                                contains = link_search.lower() in link_url.lower()
                                # If negative flag set, skip links that CONTAIN search; else include only those containing
                                if (not link_negative and not contains) or (link_negative and contains):
                                    continue
                            except AttributeError:
                                # link_url might not be a string
                                continue
                        
                        # Add to grouping
                        if root_site_url not in grouping:
                            grouping[root_site_url] = {}
                        if link_url not in grouping[root_site_url]:
                            grouping[root_site_url][link_url] = set()
                        grouping[root_site_url][link_url].add(url_obj.url or '')
                        
                except Exception as e:
                    logger.error(f"Error processing URL object {i}: {e}")
                    logger.error(f"URL object data: {url_obj}")
                    continue
            
            # Convert sets to sorted lists for JSON serialization
            grouped_links_all = {}
            for root_site_url, dest_map in grouping.items():
                entries = []
                for dest, sources in dest_map.items():
                    entries.append({
                        'destination': dest,
                        'sources': sorted(list(sources))
                    })
                # Sort entries by destination for determinism
                grouped_links_all[root_site_url] = sorted(entries, key=lambda x: x['destination'])
            
            # Apply root site filter on sources if provided
            if root_site and root_site in grouped_links_all:
                grouped_links_filtered = {root_site: grouped_links_all[root_site]}
            else:
                grouped_links_filtered = grouped_links_all
            
            # Group by destination website (dest_root) - matching Django implementation
            dest_grouping = {}
            for entries in grouped_links_filtered.values():
                for entry in entries:
                    dest_url = entry['destination']
                    parsed = urlparse(dest_url)
                    dest_scheme = parsed.scheme or 'http'
                    dest_host = parsed.hostname or ''
                    dest_port_part = ''
                    if parsed.port and not ((dest_scheme == 'http' and parsed.port == 80) or (dest_scheme == 'https' and parsed.port == 443)):
                        dest_port_part = f":{parsed.port}"
                    dest_root = f"{dest_scheme}://{dest_host}{dest_port_part}/"
                    
                    # Append to grouping
                    if dest_root not in dest_grouping:
                        dest_grouping[dest_root] = []
                    dest_grouping[dest_root].append(entry)
            
            # Sort link entries inside each dest_root by destination URL
            for dest_root, links in dest_grouping.items():
                dest_grouping[dest_root] = sorted(links, key=lambda x: x['destination'])
            
            # Sort the final grouping by destination root
            dest_grouped_links = dict(sorted(dest_grouping.items()))
            
            # Apply pagination if requested
            pagination_info = None
            if page is not None and page_size is not None:
                total_groups = len(dest_grouped_links)
                total_pages = (total_groups + page_size - 1) // page_size if page_size > 0 else 1
                current_page = min(page, total_pages) if total_pages > 0 else 1
                skip = (current_page - 1) * page_size
                
                # Paginate dest_grouped_links (convert to list, slice, convert back to dict)
                dest_grouped_items = list(dest_grouped_links.items())
                paginated_items = dest_grouped_items[skip:skip + page_size]
                dest_grouped_links = dict(paginated_items)
                
                pagination_info = {
                    "total_items": total_groups,
                    "total_pages": total_pages,
                    "current_page": current_page,
                    "page_size": page_size,
                    "has_next": current_page < total_pages,
                    "has_previous": current_page > 1
                }
            
            result = {
                "dest_grouped_links": dest_grouped_links,
                "grouped_links": dict(sorted(grouped_links_filtered.items())),
                "root_sites_list": sorted(grouped_links_all.keys()),
                "selected_root": root_site,
                "selected_program": program_name,
                "link_search": link_search or '',
                "link_negative": link_negative
            }
            
            if pagination_info:
                result["pagination"] = pagination_info
            
            return result
        
    except Exception as e:
        logger.error(f"Error fetching external links: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching external links: {str(e)}"
        )

@router.get("/common/latest", include_in_schema=True)
async def get_latest_findings(
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    limit: int = Query(5, ge=1, le=20, description="Number of latest items to return per type"),
    days_ago: Optional[int] = Query(None, ge=1, le=365, description="Only return findings created within the last N days")
):
    """
    Get the latest findings for dashboard display
    """
    try:
        latest_findings = await CommonFindingsRepository.get_latest_findings(program_name, limit, days_ago)
        
        return {
            "status": "success",
            "data": latest_findings
        }
        
    except Exception as e:
        logger.error(f"Error getting latest findings: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest findings: {str(e)}")

@router.get("/common/debug", include_in_schema=True)
async def debug_findings_endpoints(
    program_name: Optional[str] = Query(None, description="Filter by program name")
):
    """
    Debug endpoint to help troubleshoot findings endpoints
    """
    try:
        from models.postgres import Program, NucleiFinding, TyposquatDomain
        from db import get_db_session
        
        async with get_db_session() as db:
            # Get all programs
            all_programs = db.query(Program).all()
            program_names = [p.name for p in all_programs]
            
            # Get specific program if requested
            target_program = None
            if program_name:
                target_program = db.query(Program).filter(Program.name == program_name).first()
            
            # Get basic counts
            counts = {}
            if target_program:
                program_id = target_program.id
                counts = {
                    'nuclei_findings': db.query(NucleiFinding).filter(NucleiFinding.program_id == program_id).count(),
                    'typosquat_findings': db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).count()
                }
            else:
                counts = {
                    'nuclei_findings': db.query(NucleiFinding).count(),
                    'typosquat_findings': db.query(TyposquatDomain).count()
                }
            
            return {
                "status": "success",
                "data": {
                    "all_programs": program_names,
                    "target_program": program_name,
                    "target_program_found": target_program is not None,
                    "counts": counts
                }
            }
            
    except Exception as e:
        logger.error(f"Error in debug endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Debug endpoint error: {str(e)}")

# ===== GENERAL FINDINGS ENDPOINTS =====

async def trigger_typosquat_detection_workflow_batch(findings: list):
    """Trigger a single typosquat_detection workflow for multiple domains"""
    try:
        import uuid

        if not findings:
            logger.warning("No findings provided for workflow triggering")
            return

        # Get program name from first finding (assume all findings are from same program)
        first_finding = findings[0]
        program_name = first_finding.get("program_name")
        if not program_name:
            logger.warning("No program_name found in findings")
            return

        # Extract all domain names
        domain_names = []
        for finding in findings:
            domain_name = finding.get("typo_domain")
            if domain_name:
                domain_names.append(domain_name)

        if not domain_names:
            logger.warning("No valid domain names found in findings")
            return

        # Create workflow execution data for batch processing
        execution_id = str(uuid.uuid4())
        workflow_data = {
            "workflow_id": None,  # Custom workflow, not based on a definition
            "execution_id": execution_id,
            "program_name": program_name,
            "name": f"Typosquat_Detection_Batch_{len(domain_names)}_domains",
            "description": f"Batch typosquat detection analysis for {len(domain_names)} domains: {', '.join(domain_names[:3])}{'...' if len(domain_names) > 3 else ''}",
            "variables": {},
            "inputs": {
                "input_1": {
                    "type": "direct",
                    "values": domain_names,  # All domains in this batch
                    "value_type": "domains"
                }
            },
            "steps": [
                {
                    "name": "step_1",
                    "tasks": [
                        {
                            "name": "typosquat_detection",
                            "force": True,
                            "params": {
                                "include_subdomains": False,
                                "analyze_input_as_variations": True,
                            },
                            "task_type": "typosquat_detection",
                            "input_mapping": {
                                "domains": "inputs.input_1"
                            }
                        }
                    ]
                }
            ]
        }

        # Import and use the Kubernetes service to create the workflow job
        try:
            from services.kubernetes import KubernetesService

            k8s_service = KubernetesService()
            await k8s_service.create_runner_job(workflow_data)

            logger.info(f"Successfully triggered single typosquat_detection workflow for {len(domain_names)} domains with execution ID: {execution_id}")

        except ImportError:
            logger.warning("Kubernetes service not available, cannot trigger workflow job")
        except Exception as k8s_error:
            logger.error(f"Failed to create Kubernetes job for batch of {len(domain_names)} domains: {str(k8s_error)}")
            raise

    except Exception as e:
        logger.error(f"Error triggering typosquat_detection workflow batch: {str(e)}")
        raise
