"""
Protected Domain Similarity Service - calculates similarity scores between typosquat and protected domains.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any
from db import get_db_session
from models.postgres import TyposquatDomain, Program
from services.typosquat_auto_resolve_service import TyposquatAutoResolveService

logger = logging.getLogger(__name__)

# Bound suffix enumeration for pathological hostnames with many labels
_MAX_LABELS_FOR_SUFFIX_SCAN = 32

# When collapsed-alphanumeric forms match but the literal hostnames differ (e.g. dot-split
# typosquat), do not report 100% — that percentage is reserved for exact FQDN equivalence.
_COLLAPSED_MATCH_NON_LITERAL_CAP = 0.99


def _levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _levenshtein_similarity(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    distance = _levenshtein_distance(s1, s2)
    return 1.0 - (distance / max_len)


def _extract_apex_domain(domain: str) -> str:
    parts = domain.lower().split('.')
    if len(parts) >= 2:
        return '.'.join(parts[-2:])
    return domain.lower()


def _collapse_hostname_alphanumeric(domain: str) -> str:
    """Lowercase hostname, strip trailing dot, keep only alphanumerics (merges labels and drops hyphens/dots)."""
    if not domain:
        return ""
    s = domain.lower().strip().rstrip('.')
    return ''.join(c for c in s if c.isalnum())


def _normalize_fqdn_literal(domain: str) -> str:
    """Case-insensitive FQDN equality helper (trailing dot ignored)."""
    return domain.lower().strip().rstrip('.')


def _typo_suffix_hostnames(typo_fqdn: str) -> List[str]:
    """
    All label-boundary suffixes of typo_fqdn with at least two labels.
    If the hostname has more than _MAX_LABELS_FOR_SUFFIX_SCAN labels, only the last
    _MAX_LABELS_FOR_SUFFIX_SCAN labels are considered (prefix dropped).
    """
    raw = typo_fqdn.lower().strip().rstrip('.')
    labels = [p for p in raw.split('.') if p]
    if not labels:
        return []
    if len(labels) > _MAX_LABELS_FOR_SUFFIX_SCAN:
        labels = labels[-_MAX_LABELS_FOR_SUFFIX_SCAN:]
    n = len(labels)
    if n < 2:
        return [raw]
    return ['.'.join(labels[i:]) for i in range(0, n - 1)]


def _pair_similarity(hostname_fragment: str, protected: str) -> float:
    """Max of apex-vs-apex and collapsed-full vs collapsed-full Levenshtein similarity (0..1)."""
    cand_lit = _normalize_fqdn_literal(hostname_fragment)
    prot_lit = _normalize_fqdn_literal(protected)
    apex_sim = _levenshtein_similarity(
        _extract_apex_domain(hostname_fragment),
        _extract_apex_domain(protected),
    )
    ca = _collapse_hostname_alphanumeric(hostname_fragment)
    cb = _collapse_hostname_alphanumeric(protected)
    coll_sim = _levenshtein_similarity(ca, cb)
    # Identical collapsed strings can still be different hostnames (label-split impersonation).
    # Reserve 100% for literal FQDN match so UI and AI prompts are not misleading.
    if ca == cb and cand_lit != prot_lit:
        coll_sim = min(coll_sim, _COLLAPSED_MATCH_NON_LITERAL_CAP)
    return max(apex_sim, coll_sim)


def best_similarity_typo_to_protected(typo_fqdn: str, protected: str) -> float:
    """
    Best similarity (0..1) between typo FQDN and one protected domain, scanning all
    multi-label suffixes of the typo so deep benign prefixes do not hide impersonation.
    """
    if not typo_fqdn or not protected:
        return 0.0
    best = 0.0
    for cand in _typo_suffix_hostnames(typo_fqdn):
        best = max(best, _pair_similarity(cand, protected))
    return best


class ProtectedDomainSimilarityService:
    @staticmethod
    def calculate_similarities_for_domain(typo_domain: str, protected_domains: List[str]) -> List[Dict[str, Any]]:
        if not protected_domains:
            return []
        similarities = []
        calculated_at = datetime.now(timezone.utc).isoformat()
        for protected in protected_domains:
            similarity = best_similarity_typo_to_protected(typo_domain, protected)
            similarity_percent = round(similarity * 100, 2)
            similarities.append({
                "protected_domain": protected,
                "similarity_percent": similarity_percent,
                "calculated_at": calculated_at
            })
        similarities.sort(key=lambda x: x["similarity_percent"], reverse=True)
        return similarities

    @staticmethod
    async def calculate_and_update_for_domain(typosquat_id: str, typo_domain: str, protected_domains: List[str]) -> bool:
        try:
            similarities = ProtectedDomainSimilarityService.calculate_similarities_for_domain(typo_domain, protected_domains)
            if not similarities:
                return True
            async with get_db_session() as db:
                domain_record = db.query(TyposquatDomain).filter(TyposquatDomain.id == typosquat_id).first()
                if domain_record:
                    domain_record.protected_domain_similarities = similarities
                    domain_record.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    max_sim = similarities[0]["similarity_percent"] if similarities else 0
                    logger.info(f"Updated similarities for {typo_domain}: max {max_sim}%")
                    # Update auto_resolve flag based on program settings
                    await TyposquatAutoResolveService.update_auto_resolve_for_domain(typosquat_id)
                    return True
                else:
                    logger.warning(f"Domain {typosquat_id} not found")
                    return False
        except Exception as e:
            logger.error(f"Error calculating similarities for {typo_domain}: {e}")
            return False

    @staticmethod
    async def recalculate_for_program(program_id: str, protected_domains: List[str], batch_size: int = 100) -> Dict[str, Any]:
        updated_count = 0
        failed_count = 0
        total_count = 0
        try:
            async with get_db_session() as db:
                total_count = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).count()
                if total_count == 0:
                    return {"status": "success", "total": 0, "updated": 0, "failed": 0}
                logger.info(f"Recalculating similarities for {total_count} domains in program {program_id}")
                offset = 0
                while offset < total_count:
                    domains = db.query(TyposquatDomain).filter(TyposquatDomain.program_id == program_id).offset(offset).limit(batch_size).all()
                    if not domains:
                        break
                    for domain in domains:
                        try:
                            sims = ProtectedDomainSimilarityService.calculate_similarities_for_domain(domain.typo_domain, protected_domains)
                            domain.protected_domain_similarities = sims
                            domain.updated_at = datetime.now(timezone.utc)
                            updated_count += 1
                        except Exception as e:
                            logger.error(f"Error for {domain.typo_domain}: {e}")
                            failed_count += 1
                    db.commit()
                    offset += batch_size
                    await asyncio.sleep(0.1)
                logger.info(f"Completed: {updated_count} updated, {failed_count} failed")
            # Recalculate auto_resolve for all domains in program
            await TyposquatAutoResolveService.recalculate_auto_resolve_for_program(program_id)
            return {"status": "success", "total": total_count, "updated": updated_count, "failed": failed_count}
        except Exception as e:
            logger.error(f"Error during bulk recalculation: {e}")
            return {"status": "error", "error": str(e), "total": total_count, "updated": updated_count, "failed": failed_count}

    @staticmethod
    async def recalculate_for_program_by_name(program_name: str, batch_size: int = 100) -> Dict[str, Any]:
        try:
            async with get_db_session() as db:
                program = db.query(Program).filter(Program.name == program_name).first()
                if not program:
                    return {"status": "error", "error": f"Program '{program_name}' not found"}
                protected_domains = program.protected_domains or []
                if not protected_domains:
                    return {"status": "warning", "message": "No protected domains configured", "total": 0, "updated": 0, "failed": 0}
                return await ProtectedDomainSimilarityService.recalculate_for_program(str(program.id), protected_domains, batch_size)
        except Exception as e:
            logger.error(f"Error looking up program {program_name}: {e}")
            return {"status": "error", "error": str(e)}


protected_domain_similarity_service = ProtectedDomainSimilarityService()
