from utils.query_filters import ProgramAccessMixin
from typing import Dict, Any, List, Optional
from models.postgres import AssetStatsResponse, AggregatedAssetStatsResponse, SubdomainStats, ApexDomainStats, IPStats, URLStats, ServiceStats, CertificateStats
from sqlalchemy import and_, or_, desc, func
from models.postgres import Program, ApexDomain, Subdomain, IP, Service, URL, SubdomainIP, Certificate
from db import get_db_session
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class CommonAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""

    @staticmethod
    async def get_detailed_asset_stats(filter_data: Dict[str, Any]) -> AssetStatsResponse:
        """Get detailed asset stats for a program"""
        try:
            # Extract program name from filter data
            program_name = filter_data.get('program_name')
            if not program_name:
                logger.warning("No program_name provided for asset stats")
                return AssetStatsResponse()
            
            async with get_db_session() as db:
                # Get program ID for filtering
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    logger.warning(f"Program {program_name} not found")
                    return AssetStatsResponse()
                
                program_id = program.id
                
                # --- Apex Domain Stats ---
                apex_domain_count = db.query(ApexDomain).filter(
                    ApexDomain.program_id == program_id
                ).count()
                apex_domain_stats = ApexDomainStats(total=apex_domain_count)
                
                # --- Subdomain Stats ---
                # Get total subdomains
                total_subdomains = db.query(Subdomain).filter(
                    Subdomain.program_id == program_id
                ).count()
                
                # Get resolved subdomains (have IP addresses)
                resolved_subdomains = db.query(Subdomain).join(
                    SubdomainIP, Subdomain.id == SubdomainIP.subdomain_id
                ).filter(
                    Subdomain.program_id == program_id
                ).distinct().count()
                
                # Get wildcard subdomains
                wildcard_subdomains = db.query(Subdomain).filter(
                    and_(
                        Subdomain.program_id == program_id,
                        Subdomain.is_wildcard == True
                    )
                ).count()
                
                subdomain_stats = SubdomainStats(
                    total=total_subdomains,
                    resolved=resolved_subdomains,
                    unresolved=total_subdomains - resolved_subdomains,
                    wildcard=wildcard_subdomains
                )
                
                # --- IP Stats ---
                # Get total IPs
                total_ips = db.query(IP).filter(
                    IP.program_id == program_id
                ).count()
                
                # Get resolved IPs (have PTR records)
                resolved_ips = db.query(IP).filter(
                    and_(
                        IP.program_id == program_id,
                        IP.ptr_record.isnot(None),
                        IP.ptr_record != ''
                    )
                ).count()
                
                ip_stats = IPStats(
                    total=total_ips,
                    resolved=resolved_ips,
                    unresolved=total_ips - resolved_ips
                )
                
                # --- URL Stats ---
                # Get total URLs
                total_urls = db.query(URL).filter(
                    URL.program_id == program_id
                ).count()
                
                # Get root URLs (path is '/' or empty)
                root_urls = db.query(URL).filter(
                    and_(
                        URL.program_id == program_id,
                        or_(
                            URL.path == '/',
                            URL.path == '',
                            URL.path.is_(None)
                        )
                    )
                ).count()

                # Get root URLs with with https scheme
                root_urls_https = db.query(URL).filter(
                    and_(
                        URL.program_id == program_id,
                        URL.scheme == 'https',
                        URL.path == '/'
                    )
                ).count()

                # Get root URLs with with http scheme
                root_urls_http = db.query(URL).filter(
                    and_(
                        URL.program_id == program_id,
                        URL.scheme == 'http',
                        URL.path == '/'
                    )
                ).count()
                
                url_stats = URLStats(
                    total=total_urls,
                    root=root_urls,
                    non_root=total_urls - root_urls,
                    root_https=root_urls_https,
                    root_http=root_urls_http
                )
                
                # --- Service Stats ---
                service_count = db.query(Service).filter(
                    Service.program_id == program_id
                ).count()
                
                service_stats = ServiceStats(total=service_count)
                
                # --- Certificate Stats ---
                
                # Get total certificates
                certificate_count = db.query(Certificate).filter(
                    Certificate.program_id == program_id
                ).count()
                
                # Calculate certificate status counts
                now = datetime.utcnow()
                thirty_days_from_now = now + timedelta(days=30)
                
                # Valid certificates (not expired and not expiring soon)
                valid_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id == program_id,
                        Certificate.valid_until > thirty_days_from_now
                    )
                ).count()
                
                # Expiring soon (within 30 days but not expired)
                expiring_soon_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id == program_id,
                        Certificate.valid_until <= thirty_days_from_now,
                        Certificate.valid_until > now
                    )
                ).count()
                
                # Expired certificates
                expired_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id == program_id,
                        Certificate.valid_until <= now
                    )
                ).count()
                
                # Self-signed certificates (issuer DN = subject DN)
                self_signed_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id == program_id,
                        Certificate.issuer_dn == Certificate.subject_dn,
                        Certificate.issuer_dn.isnot(None),
                        Certificate.subject_dn.isnot(None)
                    )
                ).count()
                
                # Wildcard certificates (subject DN contains *. or SAN contains *)
                wildcard_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id == program_id,
                        or_(
                            func.lower(Certificate.subject_dn).like('*%'),
                            func.array_to_string(Certificate.subject_alternative_names, ',').like('*%')
                        )
                    )
                ).count()
                
                certificate_stats = CertificateStats(
                    total=certificate_count,
                    valid=valid_certs,
                    expiring_soon=expiring_soon_certs,
                    expired=expired_certs,
                    self_signed=self_signed_certs,
                    wildcards=wildcard_certs
                )
                
                # --- Combine Results ---
                return AssetStatsResponse(
                    apex_domain_details=apex_domain_stats,
                    subdomain_details=subdomain_stats,
                    ip_details=ip_stats,
                    service_details=service_stats,
                    url_details=url_stats,
                    certificate_details=certificate_stats
                )
                
        except Exception as e:
            logger.exception(f"Error calculating detailed asset stats for filter {filter_data}: {str(e)}")
            # Return default empty stats on error
            return AssetStatsResponse(
                apex_domain_details=ApexDomainStats(),
                subdomain_details=SubdomainStats(),
                ip_details=IPStats(),
                service_details=ServiceStats(),
                url_details=URLStats()
            )

    @staticmethod
    async def get_aggregated_asset_stats(program_names: Optional[List[str]] = None) -> AggregatedAssetStatsResponse:
        """Get aggregated asset stats across multiple programs"""
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
                    logger.warning("No programs found for aggregated asset stats")
                    return AggregatedAssetStatsResponse()
                
                # --- Apex Domain Stats ---
                apex_domain_count = db.query(ApexDomain).filter(
                    ApexDomain.program_id.in_(program_ids)
                ).count()
                apex_domain_stats = ApexDomainStats(total=apex_domain_count)
                
                # --- Subdomain Stats ---
                # Get total subdomains
                total_subdomains = db.query(Subdomain).filter(
                    Subdomain.program_id.in_(program_ids)
                ).count()
                
                # Get resolved subdomains (have IP addresses)
                resolved_subdomains = db.query(Subdomain).join(
                    SubdomainIP, Subdomain.id == SubdomainIP.subdomain_id
                ).filter(
                    Subdomain.program_id.in_(program_ids)
                ).distinct().count()
                
                # Get wildcard subdomains
                wildcard_subdomains = db.query(Subdomain).filter(
                    and_(
                        Subdomain.program_id.in_(program_ids),
                        Subdomain.is_wildcard == True
                    )
                ).count()
                
                subdomain_stats = SubdomainStats(
                    total=total_subdomains,
                    resolved=resolved_subdomains,
                    unresolved=total_subdomains - resolved_subdomains,
                    wildcard=wildcard_subdomains
                )
                
                # --- IP Stats ---
                # Get total IPs
                total_ips = db.query(IP).filter(
                    IP.program_id.in_(program_ids)
                ).count()
                
                # Get resolved IPs (have PTR records)
                resolved_ips = db.query(IP).filter(
                    and_(
                        IP.program_id.in_(program_ids),
                        IP.ptr_record.isnot(None),
                        IP.ptr_record != ''
                    )
                ).count()
                
                ip_stats = IPStats(
                    total=total_ips,
                    resolved=resolved_ips,
                    unresolved=total_ips - resolved_ips
                )
                
                # --- URL Stats ---
                # Get total URLs
                total_urls = db.query(URL).filter(
                    URL.program_id.in_(program_ids)
                ).count()
                
                # Get root URLs (path is '/' or empty)
                root_urls = db.query(URL).filter(
                    and_(
                        URL.program_id.in_(program_ids),
                        or_(
                            URL.path == '/',
                            URL.path == '',
                            URL.path.is_(None)
                        )
                    )
                ).count()
                
                url_stats = URLStats(
                    total=total_urls,
                    root=root_urls,
                    non_root=total_urls - root_urls
                )
                
                # --- Service Stats ---
                service_count = db.query(Service).filter(
                    Service.program_id.in_(program_ids)
                ).count()
                
                service_stats = ServiceStats(total=service_count)
                
                # --- Certificate Stats ---
                # Get total certificates
                certificate_count = db.query(Certificate).filter(
                    Certificate.program_id.in_(program_ids)
                ).count()
                
                # Calculate certificate status counts
                now = datetime.utcnow()
                thirty_days_from_now = now + timedelta(days=30)
                
                # Valid certificates (not expired and not expiring soon)
                valid_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id.in_(program_ids),
                        Certificate.valid_until > thirty_days_from_now
                    )
                ).count()
                
                # Expiring soon (within 30 days but not expired)
                expiring_soon_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id.in_(program_ids),
                        Certificate.valid_until <= thirty_days_from_now,
                        Certificate.valid_until > now
                    )
                ).count()
                
                # Expired certificates
                expired_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id.in_(program_ids),
                        Certificate.valid_until <= now
                    )
                ).count()
                
                # Self-signed certificates (issuer DN = subject DN)
                self_signed_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id.in_(program_ids),
                        Certificate.issuer_dn == Certificate.subject_dn,
                        Certificate.issuer_dn.isnot(None),
                        Certificate.subject_dn.isnot(None)
                    )
                ).count()
                
                # Wildcard certificates (subject DN contains *. or SAN contains *)
                wildcard_certs = db.query(Certificate).filter(
                    and_(
                        Certificate.program_id.in_(program_ids),
                        or_(
                            func.lower(Certificate.subject_dn).like('*%'),
                            func.array_to_string(Certificate.subject_alternative_names, ',').like('*%')
                        )
                    )
                ).count()
                
                certificate_stats = CertificateStats(
                    total=certificate_count,
                    valid=valid_certs,
                    expiring_soon=expiring_soon_certs,
                    expired=expired_certs,
                    self_signed=self_signed_certs,
                    wildcards=wildcard_certs
                )
                
                # --- Combine Results ---
                return AggregatedAssetStatsResponse(
                    total_programs=total_programs,
                    apex_domain_details=apex_domain_stats,
                    subdomain_details=subdomain_stats,
                    ip_details=ip_stats,
                    service_details=service_stats,
                    url_details=url_stats,
                    certificate_details=certificate_stats
                )
                
        except Exception as e:
            logger.exception(f"Error calculating aggregated asset stats: {str(e)}")
            # Return default empty stats on error
            return AggregatedAssetStatsResponse(
                total_programs=0,
                apex_domain_details=ApexDomainStats(),
                subdomain_details=SubdomainStats(),
                ip_details=IPStats(),
                service_details=ServiceStats(),
                url_details=URLStats()
            )

    @staticmethod
    async def get_latest_assets(program_name: Optional[str] = None, limit: int = 5, days_ago: Optional[int] = None) -> Dict[str, List]:
        """Get the latest assets of each type for dashboard display"""
        try:
            logger.info(f"Getting latest assets for program: {program_name}, limit: {limit}, days_ago: {days_ago}")
            async with get_db_session() as db:
                # Get program ID for filtering if specified
                program_id = None
                if program_name:
                    # First, let's check if the program exists and log some debug info
                    all_programs = db.query(Program).all()
                    logger.info(f"Available programs in database: {[p.name for p in all_programs]}")
                    
                    program = db.query(Program).filter(Program.name == program_name).first()
                    if not program:
                        logger.warning(f"Program {program_name} not found")
                        return {}
                    program_id = program.id
                    logger.info(f"Found program {program_name} with ID: {program_id}")
                else:
                    logger.info("No program specified, getting assets from all programs")
                
                # Calculate time filter if specified
                from datetime import datetime, timedelta
                time_filter = None
                if days_ago:
                    cutoff_date = datetime.utcnow() - timedelta(days=days_ago)
                    time_filter = cutoff_date
                    logger.info(f"Filtering assets created after: {cutoff_date}")
                
                latest_assets = {}
                
                try:
                    # --- Latest Apex Domains ---
                    apex_query = db.query(ApexDomain).join(Program)
                    if program_id:
                        apex_query = apex_query.filter(ApexDomain.program_id == program_id)
                    if time_filter:
                        apex_query = apex_query.filter(ApexDomain.created_at >= time_filter)
                    latest_apex = apex_query.order_by(desc(ApexDomain.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_apex)} latest apex domains")
                    latest_assets['apex_domains'] = [
                        {
                            'id': domain.id,
                            'name': domain.name,
                            'created_at': domain.created_at,
                            'program_name': domain.program.name if domain.program else None
                        }
                        for domain in latest_apex
                    ]
                except Exception as e:
                    logger.error(f"Error getting apex domains: {e}")
                    latest_assets['apex_domains'] = []
                
                try:
                    # --- Latest Subdomains ---
                    subdomain_query = db.query(Subdomain).join(Program)
                    if program_id:
                        subdomain_query = subdomain_query.filter(Subdomain.program_id == program_id)
                    if time_filter:
                        subdomain_query = subdomain_query.filter(Subdomain.created_at >= time_filter)
                    latest_subdomains = subdomain_query.order_by(desc(Subdomain.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_subdomains)} latest subdomains")
                    latest_assets['subdomains'] = [
                        {
                            'id': subdomain.id,
                            'name': subdomain.name,
                            'created_at': subdomain.created_at,
                            'program_name': subdomain.program.name if subdomain.program else None,
                            'is_wildcard': subdomain.is_wildcard
                        }
                        for subdomain in latest_subdomains
                    ]
                except Exception as e:
                    logger.error(f"Error getting subdomains: {e}")
                    latest_assets['subdomains'] = []
                
                try:
                    # --- Latest IPs ---
                    ip_query = db.query(IP).join(Program)
                    if program_id:
                        ip_query = ip_query.filter(IP.program_id == program_id)
                    if time_filter:
                        ip_query = ip_query.filter(IP.created_at >= time_filter)
                    latest_ips = ip_query.order_by(desc(IP.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_ips)} latest IPs")
                    latest_assets['ips'] = [
                        {
                            'id': ip.id,
                            'ip': ip.ip_address,  # Fixed: use ip_address not ip
                            'created_at': ip.created_at,
                            'program_name': ip.program.name if ip.program else None,
                            'ptr_record': ip.ptr_record
                        }
                        for ip in latest_ips
                    ]
                except Exception as e:
                    logger.error(f"Error getting IPs: {e}")
                    latest_assets['ips'] = []
                
                try:
                    # --- Latest URLs ---
                    url_query = db.query(URL).join(Program)
                    url_query = url_query.filter(URL.path == "/")
                    if program_id:
                        url_query = url_query.filter(URL.program_id == program_id)
                    if time_filter:
                        url_query = url_query.filter(URL.created_at >= time_filter)
                    latest_urls = url_query.order_by(desc(URL.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_urls)} latest URLs")
                    latest_assets['urls'] = [
                        {
                            'id': url.id,
                            'url': url.url,
                            'created_at': url.created_at,
                            'program_name': url.program.name if url.program else None,
                            'status_code': url.http_status_code,  # Fixed: use http_status_code not status_code
                            'scheme': url.scheme,
                            'hostname': url.hostname
                        }
                        for url in latest_urls
                    ]
                except Exception as e:
                    logger.error(f"Error getting URLs: {e}")
                    latest_assets['urls'] = []
                
                try:
                    # --- Latest Services ---
                    # Use the same approach as the working service search
                    service_query = db.query(Service).join(Program)
                    logger.info("Base service query created")
                    
                    if program_id:
                        service_query = service_query.filter(Service.program_id == program_id)
                        logger.info(f"Applied program filter for ID: {program_id}")
                    
                    if time_filter:
                        service_query = service_query.filter(Service.created_at >= time_filter)
                        logger.info(f"Applied time filter: {time_filter}")
                    
                    # Log the query before ordering and limiting
                    logger.info(f"Service query before ordering: {service_query}")
                    
                    latest_services = service_query.order_by(desc(Service.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_services)} latest services")
                    
                    # Also check total count for this program
                    total_count_query = db.query(Service).join(Program)
                    if program_id:
                        total_count_query = total_count_query.filter(Service.program_id == program_id)
                    total_count = total_count_query.count()
                    logger.info(f"Total services for program {program_id}: {total_count}")
                    
                    # Process services with proper error handling for IP relationships
                    processed_services = []
                    for service in latest_services:
                        try:
                            # Try to get IP address through relationship, with fallback
                            ip_address = None
                            if hasattr(service, 'ip') and service.ip:
                                ip_address = service.ip.ip_address
                                logger.debug(f"Service {service.id} IP from relationship: {ip_address}")
                            else:
                                # Fallback: try to get IP through direct query if relationship fails
                                try:
                                    ip_obj = db.query(IP).filter(IP.id == service.ip_id).first()
                                    ip_address = ip_obj.ip_address if ip_obj else 'N/A'
                                    logger.debug(f"Service {service.id} IP from fallback query: {ip_address}")
                                except Exception as fallback_error:
                                    logger.error(f"Fallback IP query failed for service {service.id}: {fallback_error}")
                                    ip_address = 'N/A'
                            
                            processed_services.append({
                                'id': service.id,
                                'ip': ip_address,
                                'port': service.port,
                                'protocol': service.protocol,
                                'service_name': service.service_name,
                                'created_at': service.created_at,
                                'program_name': service.program.name if service.program else None
                            })
                        except Exception as e:
                            logger.error(f"Error processing service {service.id}: {e}")
                            # Add service with minimal info if IP processing fails
                            processed_services.append({
                                'id': service.id,
                                'ip': 'N/A',
                                'port': service.port,
                                'protocol': service.protocol,
                                'service_name': service.service_name,
                                'created_at': service.created_at,
                                'program_name': service.program.name if service.program else None
                            })
                    
                    latest_assets['services'] = processed_services
                    logger.info(f"Successfully processed {len(processed_services)} services")
                except Exception as e:
                    logger.error(f"Error getting services: {e}")
                    latest_assets['services'] = []
                
                try:
                    # --- Latest Certificates ---
                    cert_query = db.query(Certificate).join(Program)
                    if program_id:
                        cert_query = cert_query.filter(Certificate.program_id == program_id)
                    if time_filter:
                        cert_query = cert_query.filter(Certificate.created_at >= time_filter)
                    latest_certs = cert_query.order_by(desc(Certificate.created_at)).limit(limit).all()
                    logger.info(f"Found {len(latest_certs)} latest certificates")
                    latest_assets['certificates'] = [
                        {
                            'id': cert.id,
                            'subject_dn': cert.subject_dn,
                            'issuer_dn': cert.issuer_dn,
                            'valid_from': cert.valid_from,
                            'valid_until': cert.valid_until,
                            'created_at': cert.created_at,
                            'program_name': cert.program.name if cert.program else None
                        }
                        for cert in latest_certs
                    ]
                except Exception as e:
                    logger.error(f"Error getting certificates: {e}")
                    latest_assets['certificates'] = []
                
                logger.info(f"Returning latest assets: {list(latest_assets.keys())}")
                return latest_assets
                
        except Exception as e:
            logger.exception(f"Error getting latest assets: {str(e)}")
            return {}