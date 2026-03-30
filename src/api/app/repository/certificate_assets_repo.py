from sqlalchemy import and_, or_, func, desc, asc, text
from typing import Dict, Any, Optional, List, Union
import logging
from datetime import datetime, timezone
from uuid import UUID

from models.postgres import (
    Program, Certificate
)
from db import get_db_session
from utils.query_filters import ProgramAccessMixin

logger = logging.getLogger(__name__)

class CertificateAssetsRepository(ProgramAccessMixin):
    """PostgreSQL repository for assets operations"""
    
    @staticmethod
    async def get_certificate_by_id(certificate_id: str) -> Optional[Dict[str, Any]]:
        """Get certificate by ID"""
        async with get_db_session() as db:
            try:
                cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
                if not cert:
                    return None

                return {
                    'id': str(cert.id),
                    'subject_dn': cert.subject_dn,
                    'subject_cn': cert.subject_cn,
                    'program_name': cert.program.name if cert.program else None,
                    'issuer_dn': cert.issuer_dn,
                    'issuer_organization': cert.issuer_organization,
                    'tls_version': cert.tls_version,
                    'cipher': cert.cipher,
                    'subject_an': cert.subject_alternative_names,
                    'valid_from': cert.valid_from.isoformat() if cert.valid_from else None,
                    'valid_until': cert.valid_until.isoformat() if cert.valid_until else None,
                    'fingerprint_hash': cert.fingerprint_hash,
                    'serial_number': cert.serial_number,
                    'notes': cert.notes,
                    'created_at': cert.created_at.isoformat() if cert.created_at else None,
                    'updated_at': cert.updated_at.isoformat() if cert.updated_at else None
                }
            except Exception as e:
                logger.error(f"Error getting certificate by id {certificate_id}: {str(e)}")
                raise

    # Update methods
    @staticmethod
    async def update_certificate(certificate_id: str, certificate_data: Dict[str, Any]) -> bool:
        """Update a certificate"""
        async with get_db_session() as db:
            try:
                cert = db.query(Certificate).filter(Certificate.id == certificate_id).first()
                if not cert:
                    return False
                
                for key, value in certificate_data.items():
                    if hasattr(cert, key):
                        setattr(cert, key, value)
                
                cert.updated_at = datetime.now(timezone.utc)
                db.commit()
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error updating certificate {certificate_id}: {str(e)}")
                raise

    # ======================
    # Typed Certificates Query
    # ======================
    @staticmethod
    async def search_certificates_typed(
        *,
        search: Optional[str] = None,
        exact_match: Optional[str] = None,
        program: Optional[Union[str, List[str]]] = None,
        status: Optional[str] = None,  # 'expired' | 'valid' | 'expiring_soon'
        expiring_within_days: int = 30,
        tls_version: Optional[str] = None,
        cipher: Optional[str] = None,
        sort_by: str = "updated_at",
        sort_dir: str = "desc",
        limit: int = 25,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Execute a strongly-typed certificate search optimized for PostgreSQL."""
        async with get_db_session() as db:
            try:
                # Base query
                san_count = func.coalesce(func.cardinality(Certificate.subject_alternative_names), 0)
                base_query = (
                    db.query(
                        Certificate.id.label("id"),
                        Certificate.subject_dn.label("subject_dn"),
                        Certificate.issuer_dn.label("issuer_dn"),
                        Certificate.issuer_organization.label("issuer_organization"),
                        Certificate.tls_version.label("tls_version"),
                        Certificate.cipher.label("cipher"),
                        Certificate.subject_alternative_names.label("subject_alternative_names"),
                        Certificate.valid_from.label("not_valid_before"),
                        Certificate.valid_until.label("valid_until"),
                        Certificate.serial_number.label("serial_number"),
                        Program.name.label("program_name"),
                        Certificate.created_at.label("created_at"),
                        Certificate.updated_at.label("updated_at"),
                        san_count.label("san_count"),
                    )
                    .select_from(Certificate)
                    .join(Program, Program.id == Certificate.program_id, isouter=True)
                )

                # Filters
                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": [], "total_count": 0}
                        base_query = base_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        base_query = base_query.filter(Program.name == program.strip())

                if search:
                    # Match on subject_dn, issuer_dn, SANs, tls_version, and cipher
                    base_query = base_query.filter(
                        or_(
                            Certificate.subject_dn.ilike(f"%{search}%"),
                            Certificate.issuer_dn.ilike(f"%{search}%"),
                            func.array_to_string(Certificate.subject_alternative_names, ', ').ilike(f"%{search}%"),
                            Certificate.tls_version.ilike(f"%{search}%"),
                            Certificate.cipher.ilike(f"%{search}%"),
                        )
                    )
                
                if exact_match:
                    # Exact match only on subject_dn
                    base_query = base_query.filter(Certificate.subject_dn == exact_match)

                if tls_version:
                    base_query = base_query.filter(Certificate.tls_version.ilike(f"%{tls_version}%"))

                if cipher:
                    base_query = base_query.filter(Certificate.cipher.ilike(f"%{cipher}%"))

                if status:
                    now_dt = datetime.utcnow()
                    if status == 'expired':
                        base_query = base_query.filter(Certificate.valid_until < now_dt)
                    elif status == 'valid':
                        base_query = base_query.filter(Certificate.valid_until >= now_dt)
                    elif status == 'expiring_soon':
                        now_dt + func.make_interval(0, 0, 0, expiring_within_days)
                        # SQLAlchemy func.make_interval returns an interval; use now + interval comparison
                        base_query = base_query.filter(
                            and_(
                                Certificate.valid_until >= now_dt,
                                Certificate.valid_until < func.now() + text(f"INTERVAL '{expiring_within_days} days'"),
                            )
                        )

                # Sorting
                sort_by_normalized = (sort_by or "updated_at").lower()
                sort_dir_normalized = (sort_dir or "desc").lower()
                direction_func = asc if sort_dir_normalized == "asc" else desc

                if sort_by_normalized == "subject_dn":
                    base_query = base_query.order_by(direction_func(Certificate.subject_dn))
                elif sort_by_normalized == "valid_until":
                    base_query = base_query.order_by(direction_func(Certificate.valid_until))
                elif sort_by_normalized == "program_name":
                    base_query = base_query.order_by(direction_func(Program.name))
                elif sort_by_normalized == "san_count":
                    base_query = base_query.order_by(direction_func(san_count))
                elif sort_by_normalized == "tls_version":
                    base_query = base_query.order_by(direction_func(Certificate.tls_version))
                elif sort_by_normalized == "cipher":
                    base_query = base_query.order_by(direction_func(Certificate.cipher))
                else:
                    base_query = base_query.order_by(direction_func(Certificate.updated_at))

                # Pagination
                base_query = base_query.offset(skip).limit(limit)

                rows = base_query.all()
                items: List[Dict[str, Any]] = []
                for r in rows:
                    items.append(
                        {
                            "id": str(r.id),
                            "subject_dn": r.subject_dn,
                            "issuer_dn": r.issuer_dn,
                            "issuer_organization": r.issuer_organization,
                            "tls_version": r.tls_version,
                            "cipher": r.cipher,
                            "subject_alternative_names": list(r.subject_alternative_names) if r.subject_alternative_names else [],
                            "not_valid_before": r.not_valid_before.isoformat() if r.not_valid_before else None,
                            "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                            "serial_number": r.serial_number,
                            "program_name": r.program_name,
                            "created_at": r.created_at.isoformat() if r.created_at else None,
                            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                            "san_count": int(r.san_count or 0),
                        }
                    )

                # Count
                count_query = (
                    db.query(func.count(Certificate.id))
                    .select_from(Certificate)
                    .join(Program, Program.id == Certificate.program_id, isouter=True)
                )

                if program is not None:
                    if isinstance(program, list):
                        if len(program) == 0:
                            return {"items": items, "total_count": 0}
                        count_query = count_query.filter(Program.name.in_(program))
                    elif isinstance(program, str) and program.strip():
                        count_query = count_query.filter(Program.name == program.strip())

                if search:
                    count_query = count_query.filter(
                        or_(
                            Certificate.subject_dn.ilike(f"%{search}%"),
                            Certificate.issuer_dn.ilike(f"%{search}%"),
                            func.array_to_string(Certificate.subject_alternative_names, ', ').ilike(f"%{search}%"),
                            Certificate.tls_version.ilike(f"%{search}%"),
                            Certificate.cipher.ilike(f"%{search}%"),
                        )
                    )

                if tls_version:
                    count_query = count_query.filter(Certificate.tls_version.ilike(f"%{tls_version}%"))

                if cipher:
                    count_query = count_query.filter(Certificate.cipher.ilike(f"%{cipher}%"))

                if status:
                    now_dt = datetime.utcnow()
                    if status == 'expired':
                        count_query = count_query.filter(Certificate.valid_until < now_dt)
                    elif status == 'valid':
                        count_query = count_query.filter(Certificate.valid_until >= now_dt)
                    elif status == 'expiring_soon':
                        count_query = count_query.filter(
                            and_(
                                Certificate.valid_until >= now_dt,
                                Certificate.valid_until < func.now() + text(f"INTERVAL '{expiring_within_days} days'"),
                            )
                        )

                total_count = count_query.scalar() or 0
                return {"items": items, "total_count": int(total_count)}

            except Exception as e:
                logger.error(f"Error executing typed certificate search: {str(e)}")
                raise

    @staticmethod
    async def create_or_update_certificate(certificate_data: Dict[str, Any]) -> tuple[str, str]:
        """Create a new certificate or update if exists with merged data.
        Returns (certificate_id, action) where action is 'created', 'updated', or 'skipped'."""
        async with get_db_session() as db:
            try:
                # Find program by name
                program = db.query(Program).filter(Program.name == certificate_data.get('program_name')).first()
                if not program:
                    raise ValueError(f"Program '{certificate_data.get('program_name')}' not found")
                
                # Extract CN from subject DN if not provided
                subject_cn = certificate_data.get('subject_cn')
                if not subject_cn and certificate_data.get('subject_dn'):
                    # Extract CN from subject DN (e.g., "CN=example.com, O=Org" -> "example.com")
                    import re
                    cn_match = re.search(r'CN=([^,]+)', certificate_data.get('subject_dn'))
                    if cn_match:
                        subject_cn = cn_match.group(1)
                    else:
                        subject_cn = certificate_data.get('subject_dn')[:255]  # Fallback
                
                # Extract CN from issuer DN if not provided
                issuer_cn = certificate_data.get('issuer_cn')
                if not issuer_cn and certificate_data.get('issuer_dn'):
                    import re
                    cn_match = re.search(r'CN=([^,]+)', certificate_data.get('issuer_dn'))
                    if cn_match:
                        issuer_cn = cn_match.group(1)
                    else:
                        issuer_cn = certificate_data.get('issuer_dn')[:255]  # Fallback
                
                # Generate serial number if not provided
                serial_number = certificate_data.get('serial_number') or certificate_data.get('serial')
                if not serial_number:
                    import uuid
                    serial_number = str(uuid.uuid4())
                
                # Generate fingerprint hash if not provided
                fingerprint_hash = certificate_data.get('fingerprint_hash')
                if not fingerprint_hash:
                    import hashlib
                    # Create a hash from subject DN and serial number
                    hash_input = f"{certificate_data.get('subject_dn')}{serial_number}"
                    fingerprint_hash = hashlib.sha256(hash_input.encode()).hexdigest()
                
                # Parse dates
                valid_from = datetime.utcnow()
                valid_until = datetime.utcnow()
                
                if certificate_data.get('valid_from') or certificate_data.get('not_valid_before'):
                    try:
                        date_str = certificate_data.get('valid_from') or certificate_data.get('not_valid_before')
                        valid_from = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        valid_from = datetime.utcnow()
                
                if certificate_data.get('valid_until') or certificate_data.get('not_valid_after'):
                    try:
                        date_str = certificate_data.get('valid_until') or certificate_data.get('not_valid_after')
                        valid_until = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        valid_until = datetime.utcnow()
                
                # Check if certificate already exists for this program
                existing = db.query(Certificate).filter(
                    and_(Certificate.serial_number == certificate_data.get('serial_number'), Certificate.program_id == program.id)
                ).first()
                
                if existing:
                    # Track what fields actually changed for meaningful update detection
                    meaningful_changes = []

                    # Define simple fields that should be compared for changes
                    simple_fields = [
                        'subject_cn', 'valid_from', 'valid_until', 'issuer_dn', 'issuer_cn',
                        'serial_number', 'fingerprint_hash', 'notes', 'issuer_organization', 'tls_version', 'cipher'
                    ]

                    for field in simple_fields:
                        if field in certificate_data and certificate_data[field] is not None:
                            existing_value = getattr(existing, field)
                            if certificate_data[field] != existing_value:
                                setattr(existing, field, certificate_data[field])
                                meaningful_changes.append(field)

                    # Handle array fields - subject_alternative_names should be merged
                    if 'subject_alternative_names' in certificate_data and isinstance(certificate_data['subject_alternative_names'], list):
                        existing_sans = existing.subject_alternative_names or []
                        new_sans = certificate_data['subject_alternative_names']
                        merged_sans = list(set(existing_sans + new_sans))  # Remove duplicates
                        if merged_sans != existing_sans:
                            existing.subject_alternative_names = merged_sans
                            meaningful_changes.append('subject_alternative_names')

                    # Update timestamp if any changes were made
                    if meaningful_changes:
                        existing.updated_at = datetime.now(timezone.utc)
                        logger.debug(f"Updated existing certificate {certificate_data.get('subject_dn')} with changes: {meaningful_changes}")
                    #else:
                    #    logger.debug(f"Certificate {certificate_data.get('subject_dn')} already exists with same data, skipping")

                    db.commit()

                    # Determine action based on what actually changed
                    # Only mark as "updated" if meaningful changes occurred
                    if meaningful_changes:
                        # Meaningful changes occurred - this is a real update
                        action = "updated"
                        logger.debug(f"Certificate {certificate_data.get('subject_dn')} updated with changes: {meaningful_changes}")
                    else:
                        # No meaningful changes - this is a duplicate/skipped operation
                        action = "skipped"
                        logger.debug(f"Certificate {certificate_data.get('subject_dn')} had no meaningful changes, marked as skipped")

                    return str(existing.id), action
                else:
                    # Create new certificate
                    certificate = Certificate(
                        subject_dn=certificate_data.get('subject_dn'),
                        subject_cn=subject_cn,
                        tls_version=certificate_data.get('tls_version'),
                        cipher=certificate_data.get('cipher'),
                        subject_alternative_names=certificate_data.get('subject_alternative_names', []) or certificate_data.get('subject_an', []),
                        valid_from=valid_from,
                        valid_until=valid_until,
                        issuer_dn=certificate_data.get('issuer_dn'),
                        issuer_cn=issuer_cn,
                        issuer_organization=certificate_data.get('issuer_organization', []),
                        serial_number=serial_number,
                        fingerprint_hash=fingerprint_hash,
                        program_id=program.id,
                        notes=certificate_data.get('notes')
                    )
                    
                    db.add(certificate)
                    db.commit()
                    db.refresh(certificate)
                    
                    logger.debug(f"Created certificate with ID: {certificate.id}")
                    return str(certificate.id), "created"  # Newly created asset
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error creating/updating certificate: {str(e)}")
                raise

    @staticmethod
    async def delete_certificate(certificate_id: str) -> bool:
        """Delete a single certificate by ID"""
        async with get_db_session() as db:
            try:
                certificate = db.query(Certificate).filter(Certificate.id == certificate_id).first()
                if not certificate:
                    return False
                
                db.delete(certificate)
                db.commit()
                
                logger.info(f"Successfully deleted certificate with ID: {certificate_id}")
                return True
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error deleting certificate {certificate_id}: {str(e)}")
                raise

    @staticmethod
    async def delete_certificates_batch(certificate_ids: List[str]) -> Dict[str, Any]:
        """Delete multiple certificates by their IDs"""
        async with get_db_session() as db:
            try:
                deleted_count = 0
                not_found_count = 0
                error_count = 0
                errors = []
                
                for certificate_id in certificate_ids:
                    try:
                        # Skip null/undefined IDs
                        if certificate_id is None:
                            error_count += 1
                            error_msg = "Invalid certificate ID: None/null value"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Skip empty strings
                        if certificate_id == "":
                            error_count += 1
                            error_msg = "Invalid certificate ID: Empty string"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Convert string ID to UUID
                        try:
                            certificate_uuid = UUID(certificate_id)
                        except ValueError as e:
                            error_count += 1
                            error_msg = f"Invalid certificate ID format '{certificate_id}': {str(e)}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                            continue
                        
                        # Find the certificate
                        certificate = db.query(Certificate).filter(Certificate.id == certificate_uuid).first()
                        
                        if not certificate:
                            not_found_count += 1
                            logger.warning(f"Certificate with ID {certificate_id} not found")
                            continue
                        
                        # Delete the certificate
                        db.delete(certificate)
                        deleted_count += 1
                        
                    except Exception as e:
                        error_count += 1
                        error_msg = f"Error deleting certificate {certificate_id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                
                # Commit all successful deletions
                db.commit()
                
                logger.info(f"Batch delete completed for certificates: {deleted_count} deleted, {not_found_count} not found, {error_count} errors")
                
                return {
                    "deleted_count": deleted_count,
                    "not_found_count": not_found_count,
                    "error_count": error_count,
                    "errors": errors
                }
                
            except Exception as e:
                db.rollback()
                logger.error(f"Error in batch delete for certificates: {str(e)}")
                raise

    @staticmethod
    async def get_distinct_values(field_name: str, filter_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """Get distinct values for a specified field in certificate assets"""
        from sqlalchemy import func
        
        async with get_db_session() as db:
            try:
                query = db.query(Certificate).join(Program, Program.id == Certificate.program_id, isouter=True)
                
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
                if field_name == 'subject_cn':
                    values = query.with_entities(Certificate.subject_cn).distinct().all()
                elif field_name == 'issuer_cn':
                    values = query.with_entities(Certificate.issuer_cn).distinct().all()
                elif field_name == 'subject_alternative_names':
                    # For array fields, we need to unnest the arrays to get individual values
                    values = query.with_entities(func.unnest(Certificate.subject_alternative_names)).distinct().all()
                elif field_name == 'issuer_organization':
                    # For array fields, we need to unnest the arrays to get individual values
                    values = query.with_entities(func.unnest(Certificate.issuer_organization)).distinct().all()
                elif field_name == 'tls_version':
                    values = query.with_entities(Certificate.tls_version).distinct().all()
                elif field_name == 'cipher':
                    values = query.with_entities(Certificate.cipher).distinct().all()
                else:
                    raise ValueError(f"Unsupported field '{field_name}' for certificate assets")
                
                return [str(v[0]) for v in values if v[0] is not None]
                
            except Exception as e:
                logger.error(f"Error getting distinct values for {field_name} in certificate assets: {str(e)}")
                raise