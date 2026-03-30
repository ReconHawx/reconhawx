"""
Protected-domain similarity for CT monitor (typosquat FQDN vs one protected domain).

Duplicated from src/api/app/services/protected_domain_similarity_service.py — keep in sync
when changing apex/collapsed/suffix logic in the API.
"""

from typing import List, Optional, Tuple

_MAX_LABELS_FOR_SUFFIX_SCAN = 32
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
    parts = domain.lower().split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return domain.lower()


def _collapse_hostname_alphanumeric(domain: str) -> str:
    if not domain:
        return ""
    s = domain.lower().strip().rstrip(".")
    return "".join(c for c in s if c.isalnum())


def _normalize_fqdn_literal(domain: str) -> str:
    return domain.lower().strip().rstrip(".")


def _typo_suffix_hostnames(typo_fqdn: str) -> List[str]:
    raw = typo_fqdn.lower().strip().rstrip(".")
    labels = [p for p in raw.split(".") if p]
    if not labels:
        return []
    if len(labels) > _MAX_LABELS_FOR_SUFFIX_SCAN:
        labels = labels[-_MAX_LABELS_FOR_SUFFIX_SCAN:]
    n = len(labels)
    if n < 2:
        return [raw]
    return [".".join(labels[i:]) for i in range(0, n - 1)]


def _pair_similarity(hostname_fragment: str, protected: str) -> float:
    cand_lit = _normalize_fqdn_literal(hostname_fragment)
    prot_lit = _normalize_fqdn_literal(protected)
    apex_sim = _levenshtein_similarity(
        _extract_apex_domain(hostname_fragment),
        _extract_apex_domain(protected),
    )
    ca = _collapse_hostname_alphanumeric(hostname_fragment)
    cb = _collapse_hostname_alphanumeric(protected)
    coll_sim = _levenshtein_similarity(ca, cb)
    if ca == cb and cand_lit != prot_lit:
        coll_sim = min(coll_sim, _COLLAPSED_MATCH_NON_LITERAL_CAP)
    return max(apex_sim, coll_sim)


def best_similarity_typo_to_protected(typo_fqdn: str, protected: str) -> float:
    if not typo_fqdn or not protected:
        return 0.0
    best = 0.0
    for cand in _typo_suffix_hostnames(typo_fqdn):
        best = max(best, _pair_similarity(cand, protected))
    return best


def best_match_among_protected(typo_fqdn: str, protected_domains: List[str]) -> Tuple[float, Optional[str]]:
    best_s = 0.0
    best_p: Optional[str] = None
    for p in protected_domains:
        s = best_similarity_typo_to_protected(typo_fqdn, p)
        if s > best_s:
            best_s = s
            best_p = p
    return best_s, best_p
