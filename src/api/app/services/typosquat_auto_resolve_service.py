"""
Typosquat Auto-Resolve Service - computes and updates auto_resolve flag on typosquat domains.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional

from db import get_db_session
from models.postgres import TyposquatDomain, Program

logger = logging.getLogger(__name__)


def _compute_auto_resolve(
    parked_confidence: Optional[int],
    protected_domain_similarities: Optional[List[Dict[str, Any]]],
    min_parked: Optional[float],
    min_similarity: Optional[float],
) -> bool:
    """Compute whether a finding should be auto-resolved based on program thresholds."""
    if min_parked is None or min_similarity is None:
        return False
    if parked_confidence is None or parked_confidence < min_parked:
        return False
    if not protected_domain_similarities:
        return False
    max_sim = max(s.get("similarity_percent", 0) for s in protected_domain_similarities)
    return max_sim >= min_similarity


class TyposquatAutoResolveService:
    @staticmethod
    async def update_auto_resolve_for_domain(typosquat_id: str) -> bool:
        """Update auto_resolve for a single typosquat domain based on program settings."""
        try:
            async with get_db_session() as db:
                domain_record = db.query(TyposquatDomain).filter(TyposquatDomain.id == typosquat_id).first()
                if not domain_record:
                    return False
                program = db.query(Program).filter(Program.id == domain_record.program_id).first()
                if not program:
                    return False
                settings = getattr(program, 'typosquat_auto_resolve_settings', None) or {}
                min_parked = settings.get("min_parked_confidence_percent")
                min_similarity = settings.get("min_similarity_percent")
                if min_parked is None or min_similarity is None:
                    logger.info(
                        f"Program {program.name} has no typosquat_auto_resolve_settings "
                        f"(min_parked={min_parked}, min_similarity={min_similarity}); auto_resolve will be False"
                    )
                domain_record.auto_resolve = _compute_auto_resolve(
                    domain_record.parked_confidence,
                    domain_record.protected_domain_similarities,
                    min_parked,
                    min_similarity,
                )
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating auto_resolve for domain {typosquat_id}: {e}")
            return False

    @staticmethod
    async def recalculate_auto_resolve_for_program(program_id: str, batch_size: int = 100) -> Dict[str, Any]:
        """Recalculate auto_resolve for all typosquat domains in a program."""
        updated_count = 0
        failed_count = 0
        total_count = 0
        try:
            async with get_db_session() as db:
                program = db.query(Program).filter(Program.id == program_id).first()
                if not program:
                    return {"status": "error", "error": "Program not found", "total": 0, "updated": 0, "failed": 0}
                settings = getattr(program, 'typosquat_auto_resolve_settings', None) or {}
                min_parked = settings.get("min_parked_confidence_percent")
                min_similarity = settings.get("min_similarity_percent")

                total_count = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).count()
                if total_count == 0:
                    return {"status": "success", "total": 0, "updated": 0, "failed": 0}

                logger.info(f"Recalculating auto_resolve for {total_count} domains in program {program_id}")
                offset = 0
                while offset < total_count:
                    domains = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).offset(offset).limit(batch_size).all()
                    if not domains:
                        break
                    for domain in domains:
                        try:
                            domain.auto_resolve = _compute_auto_resolve(
                                domain.parked_confidence,
                                domain.protected_domain_similarities,
                                min_parked,
                                min_similarity,
                            )
                            updated_count += 1
                        except Exception as e:
                            logger.error(f"Error for {domain.typo_domain}: {e}")
                            failed_count += 1
                    db.commit()
                    offset += batch_size
                    await asyncio.sleep(0.1)
                logger.info(f"Auto-resolve recalculation complete: {updated_count} updated, {failed_count} failed")
            return {"status": "success", "total": total_count, "updated": updated_count, "failed": failed_count}
        except Exception as e:
            logger.error(f"Error during auto_resolve recalculation: {e}")
            return {"status": "error", "error": str(e), "total": total_count, "updated": updated_count, "failed": failed_count}
