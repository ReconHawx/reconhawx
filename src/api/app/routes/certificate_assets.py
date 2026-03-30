from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, Optional, List, Literal, Union
from repository import ProgramRepository, CertificateAssetsRepository
from pydantic import BaseModel, Field
from auth.dependencies import get_current_user_from_middleware, get_user_accessible_programs, require_admin_or_manager
from models.user_postgres import UserResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Typed Certificates search
class CertificatesSearchRequest(BaseModel):
    search: Optional[str] = Field(None, description="Substring match across subject DN, issuer DN, SANs, TLS version, and cipher")
    exact_match: Optional[str] = Field(None, description="Exact match on subject DN")
    program: Optional[Union[str, List[str]]] = Field(None, description="Restrict to program(s) within user's access scope")
    status: Optional[Literal['expired','valid','expiring_soon']] = Field(None, description="Filter by certificate status")
    expiring_within_days: int = Field(30, ge=1, le=3650)
    tls_version: Optional[str] = Field(None, description="Filter by TLS version (partial match)")
    cipher: Optional[str] = Field(None, description="Filter by cipher (partial match)")
    sort_by: Literal['subject_dn','valid_until','program_name','san_count','tls_version','cipher','updated_at'] = 'updated_at'
    sort_dir: Literal['asc','desc'] = 'desc'
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=10000)

@router.post("/certificate/search", response_model=Dict[str, Any])
async def search_certificates_typed(request: CertificatesSearchRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    try:
        accessible = get_user_accessible_programs(current_user)
        requested_programs: Optional[List[str]] = None
        if isinstance(request.program, str) and request.program.strip():
            requested_programs = [request.program.strip()]
        elif isinstance(request.program, list):
            requested_programs = [p for p in request.program if isinstance(p, str) and p.strip()]

        programs: Optional[List[str]] = None
        if current_user.is_superuser or "admin" in current_user.roles:
            programs = requested_programs if requested_programs else None
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
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
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
            else:
                programs = allowed

        skip = (request.page - 1) * request.page_size
        result = await CertificateAssetsRepository.search_certificates_typed(
            search=request.search,
            exact_match=request.exact_match,
            program=programs if programs is not None else None,
            status=request.status,
            expiring_within_days=request.expiring_within_days,
            tls_version=request.tls_version,
            cipher=request.cipher,
            sort_by=request.sort_by,
            sort_dir=request.sort_dir,
            limit=request.page_size,
            skip=skip,
        )

        total_count = result.get("total_count", 0)
        total_pages = (total_count + request.page_size - 1) // request.page_size if request.page_size > 0 else 1
        return {
            "status": "success",
            "pagination": {
                "total_items": total_count,
                "total_pages": total_pages,
                "current_page": request.page,
                "page_size": request.page_size,
                "has_next": request.page < total_pages,
                "has_previous": request.page > 1,
            },
            "items": result.get("items", []),
        }
    except Exception as e:
        logger.error(f"Error executing typed certificate search: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error executing typed certificate search: {str(e)}")

# Pydantic models for certificate import functionality  
class CertificateImportData(BaseModel):
    subject_dn: str = Field(..., description="Subject Distinguished Name")
    program_name: Optional[str] = Field(None, description="Program name")
    issuer_dn: Optional[str] = Field(None, description="Issuer Distinguished Name")
    tls_version: Optional[str] = Field(None, description="TLS version")
    cipher: Optional[str] = Field(None, description="Cipher")
    subject_an: Optional[List[str]] = Field(None, description="Subject Alternative Names")
    not_valid_before: Optional[str] = Field(None, description="Not valid before date")
    not_valid_after: Optional[str] = Field(None, description="Not valid after date")
    signature_algorithm: Optional[str] = Field(None, description="Signature algorithm")
    serial_number: Optional[str] = Field(None, description="Serial number")
    notes: Optional[str] = Field(None, description="Investigation notes")

class CertificateImportRequest(BaseModel):
    certificates: List[CertificateImportData] = Field(..., description="List of certificates to import")
    merge: Optional[bool] = Field(True, description="Whether to merge with existing data")
    update_existing: Optional[bool] = Field(False, description="Whether to update existing certificates")
    validate_certificates: Optional[bool] = Field(True, description="Whether to validate certificate data")

# Pydantic model for notes update requests
class NotesUpdateRequest(BaseModel):
    notes: str = Field(..., description="Investigation notes content")

class DistinctRequest(BaseModel):
    filter: Optional[Dict[str, Any]] = None
    # Optional typed hint; not used by current frontend but supported
    program: Optional[Union[str, List[str]]] = None

@router.get("/certificate", response_model=Dict[str, Any])
async def get_specific_certificate(id: Optional[str] = Query(None), current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """List certificates filtered by user program permissions"""
    try:
        if id:
            certificate = await CertificateAssetsRepository.get_certificate_by_id(id)
            if not certificate:
                raise HTTPException(status_code=404, detail=f"Certificate {id} not found")
            certificate_program = certificate.get("program_name")
            if certificate_program:
                accessible_programs = get_user_accessible_programs(current_user)
                if accessible_programs and certificate_program not in accessible_programs:
                    raise HTTPException(status_code=404, detail=f"Certificate {id} not found")
            return {"status": "success", "data": certificate}

    except Exception as e:
        logger.error(f"Error listing certificates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/certificate/import", response_model=Dict[str, Any])
async def import_certificates(request: CertificateImportRequest, current_user: UserResponse = Depends(get_current_user_from_middleware)):
    """
    Import multiple certificates from various sources (JSON, CSV, TXT)
    
    This endpoint accepts a list of certificate objects and imports them into the database.
    It supports validation, merging, and batch processing.
    """
    try:
        # Validate certificates if requested
        if request.validate_certificates:
            invalid_certs = []
            for cert_data in request.certificates:
                # Basic validation for subject DN
                if not cert_data.subject_dn or not cert_data.subject_dn.strip():
                    invalid_certs.append("Empty subject DN")
                    continue
                
                # Validate date formats if provided
                for date_field, date_value in [("not_valid_before", cert_data.not_valid_before), ("not_valid_after", cert_data.not_valid_after)]:
                    if date_value:
                        try:
                            from datetime import datetime
                            # Try to parse as ISO format
                            datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                        except ValueError:
                            try:
                                # Try to parse as common date formats
                                datetime.strptime(date_value, "%Y-%m-%d")
                            except ValueError:
                                invalid_certs.append(f"Invalid {date_field} format: {date_value}")
            
            if invalid_certs:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid certificates: {', '.join(invalid_certs[:10])}{'...' if len(invalid_certs) > 10 else ''}"
                )
        
        # Filter certificates by user program permissions
        allowed_certs = []
        for cert_data in request.certificates:
            if hasattr(current_user, 'program_permissions') and current_user.program_permissions:
                if cert_data.program_name and cert_data.program_name not in current_user.program_permissions:
                    logger.warning(f"User {current_user.username} attempted to import certificate {cert_data.subject_dn} to unauthorized program {cert_data.program_name}")
                    continue
            allowed_certs.append(cert_data)
        
        if not allowed_certs:
            raise HTTPException(
                status_code=403,
                detail="No certificates to import - all certificates belong to programs you don't have access to"
            )
        
        # Process certificates in batches
        imported_count = 0
        errors = []
        
        for cert_data in allowed_certs:
            try:
                cert_dict = {
                    "subject_dn": cert_data.subject_dn.strip(),
                    "program_name": cert_data.program_name,
                    "issuer_dn": cert_data.issuer_dn,
                    "tls_version": cert_data.tls_version,
                    "cipher": cert_data.cipher,
                    "subject_an": cert_data.subject_an or [],
                    "not_valid_before": cert_data.not_valid_before,
                    "not_valid_after": cert_data.not_valid_after,
                    "signature_algorithm": cert_data.signature_algorithm,
                    "serial_number": cert_data.serial_number,
                    "notes": cert_data.notes
                }
                
                # Remove None values, empty strings, and string "null" values
                cert_dict = {k: v for k, v in cert_dict.items() if v is not None and v != "" and v != "null"}
                
                # Use create_or_update_certificate which handles merging automatically
                cert_id = await CertificateAssetsRepository.create_or_update_certificate(cert_dict)
                if cert_id:
                    imported_count += 1
                    logger.debug(f"Imported/updated certificate: {cert_dict['subject_dn']}")
                else:
                    errors.append(f"Failed to create/update certificate: {cert_dict['subject_dn']}")
                        
            except Exception as e:
                error_msg = f"Error processing certificate {cert_data.subject_dn}: {str(e)}"
                logger.error(error_msg)
                errors.append(error_msg)
                continue
        
        # Create programs if needed
        if imported_count > 0:
            for cert_data in allowed_certs:
                if cert_data.program_name:
                    program = await ProgramRepository.get_program_by_name(cert_data.program_name)
                    if not program:
                        program_data = {"name": cert_data.program_name}
                        await ProgramRepository.create_program(program_data)
                        logger.info(f"Created new program: {cert_data.program_name}")
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Import completed: {imported_count} processed",
            "data": {
                "processed_count": imported_count,
                "total_processed": len(allowed_certs),
                "total_submitted": len(request.certificates)
            }
        }
        
        if errors:
            response_data["data"]["errors"] = errors[:10]
            response_data["data"]["error_count"] = len(errors)
            
        if errors and imported_count == 0:
            response_data["status"] = "error"
            response_data["message"] = "Import failed: no certificates were processed successfully"
        elif errors:
            response_data["status"] = "partial_success"
            response_data["message"] += f" ({len(errors)} errors occurred)"
        
        logger.info(f"Certificate import completed by user {current_user.username}: {response_data['message']}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in certificate import endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error importing certificates: {str(e)}"
        )

@router.put("/certificate/{certificate_id}/notes", response_model=Dict[str, Any])
async def update_certificate_notes(certificate_id: str, request: NotesUpdateRequest):
    """Update the investigation notes for a certificate"""
    try:
        success = await CertificateAssetsRepository.update_certificate(certificate_id, {"notes": request.notes})
        
        if not success:
            raise HTTPException(status_code=404, detail="Certificate not found")
        
        return {
            "status": "success",
            "message": "Notes updated successfully",
            "data": {
                "notes": request.notes
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating certificate notes {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/certificate/batch", response_model=Dict[str, Any])
async def delete_certificates_batch(
    request_data: dict,
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete multiple certificates by their IDs"""
    try:
        # Extract asset_ids from request data
        asset_ids = request_data.get("asset_ids", [])
        
        if not asset_ids:
            raise HTTPException(status_code=400, detail="No asset IDs provided")
        
        result = await CertificateAssetsRepository.delete_certificates_batch(asset_ids)
        
        return {
            "status": "success",
            "message": "Batch delete completed for certificate assets",
            "results": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error batch deleting certificate assets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/certificate/{certificate_id}", response_model=Dict[str, Any])
async def delete_certificate(
    certificate_id: str, 
    current_user: UserResponse = Depends(require_admin_or_manager)
):
    """Delete a specific certificate by its ID"""
    try:
        deleted = await CertificateAssetsRepository.delete_certificate(certificate_id)
        
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Certificate with ID {certificate_id} not found")
        
        return {
            "status": "success",
            "message": f"Certificate {certificate_id} deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting certificate {certificate_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/certificate/distinct/{field_name}", response_model=List[str])
async def get_distinct_certificate_field_values(
    field_name: str,
    query: Optional[DistinctRequest] = None,
    current_user: UserResponse = Depends(get_current_user_from_middleware),
):
    """
    Get distinct values for a specified field in certificate assets, optionally applying a filter.
    Allowed fields: subject_cn, issuer_cn, subject_alternative_names, issuer_organization, tls_version, cipher.
    """
    try:
        # Start from incoming filter (legacy shape used by frontend: { filter: { program_name: ... } })
        incoming_filter: Dict[str, Any] = {}
        if query and isinstance(query.filter, dict):
            incoming_filter = dict(query.filter)

        # Determine requested programs (support both typed 'program' and legacy 'filter.program_name')
        requested_programs: Optional[List[str]] = None
        if query and query.program is not None:
            if isinstance(query.program, str) and query.program.strip():
                requested_programs = [query.program.strip()]
            elif isinstance(query.program, list):
                requested_programs = [p for p in query.program if isinstance(p, str) and p.strip()]
        elif "program_name" in incoming_filter:
            pn = incoming_filter.get("program_name")
            if isinstance(pn, str) and pn.strip():
                requested_programs = [pn.strip()]
            elif isinstance(pn, list):
                requested_programs = [p for p in pn if isinstance(p, str) and p.strip()]

        # Enforce program scoping by intersecting with user's accessible programs
        accessible = get_user_accessible_programs(current_user)
        programs: Optional[List[str]] = None
        if current_user.is_superuser or 'admin' in current_user.roles:
            programs = requested_programs if requested_programs else None
        else:
            allowed = accessible or []
            if not allowed:
                return []
            if requested_programs:
                programs = [p for p in requested_programs if p in allowed]
                if not programs:
                    return []
            else:
                programs = allowed

        # Build effective filter_data to pass to repository
        filter_data: Dict[str, Any] = dict(incoming_filter)
        # Normalize program_name in filter_data based on resolved programs
        if programs is not None:
            filter_data["program_name"] = programs
        else:
            # If admin with no explicit program filter, remove any stray program_name
            if "program_name" in filter_data:
                filter_data.pop("program_name", None)

        # Get distinct values using the repository method
        distinct_values = await CertificateAssetsRepository.get_distinct_values(field_name, filter_data)
        # Filter out None values to comply with List[str] response model
        return [value for value in distinct_values if value is not None]

    except ValueError as ve:
        logger.error(f"Value error getting distinct values for {field_name}: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error getting distinct values for field '{field_name}': {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving distinct values for field '{field_name}'"
        )