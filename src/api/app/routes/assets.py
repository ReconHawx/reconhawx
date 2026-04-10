from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Query
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field
import logging
from services.unified_asset_processor import unified_asset_processor
from repository.common_assets_repo import CommonAssetsRepository

logger = logging.getLogger(__name__)

router = APIRouter()

# Lightweight request model for distinct endpoints
class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

# Pydantic model for asset processing response
class AssetProcessingResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None
    processing_mode: str  # Always "unified_async"
    summary: Dict[str, Any]

# Pydantic model for asset details
class AssetDetail(BaseModel):
    record_id: Optional[str] = None
    name: str
    program_name: str
    reason: Optional[str] = None
    error: Optional[str] = None

# Pydantic model for detailed asset counts
class AssetTypeCounts(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int = 0
    out_of_scope: int = 0
    failed: int
    created_assets: List[AssetDetail] = []
    updated_assets: List[AssetDetail] = []
    skipped_assets: List[AssetDetail] = []
    failed_assets: List[AssetDetail] = []
    errors: List[str] = []

class DetailedAssetSummary(BaseModel):
    total_assets: int
    asset_types: Dict[str, int]  # Legacy format
    detailed_counts: Dict[str, AssetTypeCounts]  # New detailed format
    results: Optional[Dict[str, Any]] = None  # Legacy results for backward compatibility

# === Existing endpoints continue below ===

@router.post("", include_in_schema=True, response_model=AssetProcessingResponse)
@router.post("/", include_in_schema=True, response_model=AssetProcessingResponse)
async def receive_asset(request: Request, background_tasks: BackgroundTasks):
    """
    Receive asset data from workflow runner using unified processing.

    Handles asset types only (not findings):
    - Assets: subdomains, IPs, URLs, services, certificates, apex domains
    - Always processes asynchronously (never blocks API)
    - Uses unified bulk processing with rich event data
    
    Note: For security findings (nuclei, typosquat), use dedicated endpoints:
    - Nuclei findings: POST /findings/nuclei
    - Typosquat findings: POST /findings/typosquat
    """
    try:
        data = await request.json()

        # Validate required fields
        program_name = data.get("program_name")
        if not program_name:
            raise HTTPException(status_code=400, detail="program_name is required")

        # Extract and prepare asset data
        asset_data = await _extract_asset_data(data)

        # Calculate total asset count
        total_assets = sum(len(assets) for assets in asset_data.values() if isinstance(assets, list))

        if total_assets == 0:
            raise HTTPException(status_code=400, detail="No assets provided for processing")

        # Use unified processor - always async, never blocks API
        job_id = await unified_asset_processor.process_assets_unified(asset_data, program_name)

        logger.info(f"Started unified asset processing job {job_id} with {total_assets} assets")

        return AssetProcessingResponse(
            status="processing",
            message=f"Started unified processing of {total_assets} assets",
            job_id=job_id,
            processing_mode="unified_async",
            summary={
                "total_assets": total_assets,
                "asset_types": {k: len(v) for k, v in asset_data.items() if isinstance(v, list)},
                "processing_method": "unified_async"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating asset processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start asset processing: {str(e)}")

@router.get("/job/{job_id}", include_in_schema=True)
async def get_asset_job_status(job_id: str):
    """
    Get the status of a unified asset processing job
    """
    try:
        job_status = await unified_asset_processor.get_job_status(job_id)
        if not job_status:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return job_status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting job status for {job_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get job status: {str(e)}")

@router.get("/common/latest", include_in_schema=True)
async def get_latest_assets(
    program_name: Optional[str] = Query(None, description="Filter by program name"),
    limit: int = Query(5, ge=1, le=20, description="Number of latest items to return per type"),
    days_ago: Optional[int] = Query(None, ge=1, le=365, description="Only return assets created within the last N days")
):
    """
    Get the latest assets for dashboard display
    """
    try:
        # Get latest assets
        latest_assets = await CommonAssetsRepository.get_latest_assets(program_name, limit, days_ago)
        
        return {
            "status": "success",
            "data": {
                "latest_assets": latest_assets
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting latest assets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get latest assets: {str(e)}")


@router.get("/common/debug", include_in_schema=True)
async def debug_common_endpoints(
    program_name: Optional[str] = Query(None, description="Filter by program name")
):
    """
    Debug endpoint to help troubleshoot common endpoints
    """
    try:
        from models.postgres import Program, ApexDomain, Subdomain, IP, Service, URL, Certificate, NucleiFinding, TyposquatDomain
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
                    'apex_domains': db.query(ApexDomain).filter(ApexDomain.program_id == program_id).count(),
                    'subdomains': db.query(Subdomain).filter(Subdomain.program_id == program_id).count(),
                    'ips': db.query(IP).filter(IP.program_id == program_id).count(),
                    'urls': db.query(URL).filter(URL.program_id == program_id).count(),
                    'services': db.query(Service).filter(Service.program_id == program_id).count(),
                    'certificates': db.query(Certificate).filter(Certificate.program_id == program_id).count(),
                    'nuclei_findings': db.query(NucleiFinding).filter(NucleiFinding.program_id == program_id).count(),
                    'typosquat_findings': db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).count()
                }
            else:
                counts = {
                    'apex_domains': db.query(ApexDomain).count(),
                    'subdomains': db.query(Subdomain).count(),
                    'ips': db.query(IP).count(),
                    'urls': db.query(URL).count(),
                    'services': db.query(Service).count(),
                    'certificates': db.query(Certificate).count(),
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

async def _extract_asset_data(data: Dict[str, Any]) -> Dict[str, List]:
    """Extract and prepare asset data from the request (assets only, not findings)"""
    # Initialize asset data structure - only actual assets, not findings
    asset_data = {
        "subdomain": [],
        "ip": [],
        "url": [],
        "service": [],
        "certificate": [],
        "apex_domain": []
    }
    
    if "assets" in data:
        assets = data["assets"]
        
        # Skip nuclei findings - use dedicated /findings/nuclei endpoint
        if "nuclei" in assets and assets["nuclei"]:
            logger.warning(f"Ignoring {len(assets['nuclei'])} nuclei findings sent to /assets endpoint. Use /findings/nuclei instead.")
        
        # Process domains and their IPs
        if "subdomain" in assets:
            logger.info("Processing subdomains and their IPs")
            for subdomain in assets["subdomain"]:
                if isinstance(subdomain, dict):
                    # Add program name if not present
                    if "program_name" not in subdomain and "program_name" in data:
                        subdomain["program_name"] = data["program_name"]
                    asset_data["subdomain"].append(subdomain)

        if "ip" in assets:
            logger.info("Processing standalone IPs")
            for ip_entry in assets["ip"]:
                if isinstance(ip_entry, dict) and "ip" in ip_entry:
                    # Add program name if not present
                    if "program_name" not in ip_entry and "program_name" in data:
                        ip_entry["program_name"] = data["program_name"]
                    asset_data["ip"].append(ip_entry)
        
        if "url" in assets:
            logger.info("Processing urls")
            for url in assets["url"]:
                if isinstance(url, dict) and "url" in url:
                    # Add program name if not present
                    if "program_name" not in url and "program_name" in data:
                        url["program_name"] = data["program_name"]
                    asset_data["url"].append(url)

        if "service" in assets:
            logger.info("Processing services")
            for service in assets["service"]:
                if isinstance(service, dict) and "ip" in service:
                    # Add program name if not present
                    if "program_name" not in service and "program_name" in data:
                        service["program_name"] = data["program_name"]
                    asset_data["service"].append(service)

        if "certificate" in assets:
            logger.info("Processing certificates")
            for certificate in assets["certificate"]:
                if isinstance(certificate, dict) and "subject_dn" in certificate:
                    # Add program name if not present
                    if "program_name" not in certificate and "program_name" in data:
                        certificate["program_name"] = data["program_name"]
                    asset_data["certificate"].append(certificate)

        if "apex_domain" in assets:
            logger.info("Processing apex domains")
            for apex_domain in assets["apex_domain"]:
                if isinstance(apex_domain, dict) and "name" in apex_domain:
                    # Add program name if not present
                    if "program_name" not in apex_domain and "program_name" in data:
                        apex_domain["program_name"] = data["program_name"]
                    asset_data["apex_domain"].append(apex_domain)

        # Skip typosquat findings - use dedicated /findings/typosquat endpoint
        if "typosquat" in assets and assets["typosquat"]:
            logger.warning(f"Ignoring {len(assets['typosquat'])} typosquat findings sent to /assets endpoint. Use /findings/typosquat instead.")

    return asset_data

def _extract_asset_name(asset_type: str, asset: Dict[str, Any]) -> str:
    """Extract the appropriate name field based on asset type"""
    if asset_type in ["subdomain", "apex_domain"]:
        return asset.get("name", "unknown")
    elif asset_type == "ip":
        return asset.get("ip", "unknown")
    elif asset_type == "url":
        return asset.get("url", "unknown")
    elif asset_type == "service":
        ip = asset.get("ip", "unknown")
        port = asset.get("port", "unknown")
        return f"{ip}:{port}"
    elif asset_type == "certificate":
        return asset.get("subject_dn", "unknown")
    else:
        return "unknown"

