"""
Protected-domain similarity for CT monitor (typosquat FQDN vs one protected domain).

Duplicated from src/api/app/services/protected_domain_similarity_service.py — keep in sync
when changing apex/collapsed/suffix logic in the API.

The CT hot path uses rapidfuzz (C++ Levenshtein, identical scores to the pure-Python
implementation kept below for parity tests) plus precomputed inputs:

- ``PreparedProtected``: static per-protected-domain data, built once per config refresh
  (see ``domain_config_builder``).
- ``PreparedTypo``: per-certificate-domain data, built once per SAN and reused across
  all programs.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Tuple

from rapidfuzz.distance import Levenshtein

from domain_labels import extract_apex_domain

_MAX_LABELS_FOR_SUFFIX_SCAN = 32
_COLLAPSED_MATCH_NON_LITERAL_CAP = 0.99


def _levenshtein_distance_py(s1: str, s2: str) -> int:
    """Pure-Python reference implementation (parity tests only; hot path uses rapidfuzz)."""
    if len(s1) < len(s2):
        return _levenshtein_distance_py(s2, s1)
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
    # 1 - distance / max(len) — rapidfuzz normalizes uniform-weight Levenshtein the same way.
    return Levenshtein.normalized_similarity(s1, s2)


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


@dataclass(frozen=True)
class PreparedProtected:
    """Static similarity inputs for one protected domain (built once per refresh)."""

    domain: str
    literal: str
    apex: str
    collapsed: str


def prepare_protected(protected: str) -> PreparedProtected:
    return PreparedProtected(
        domain=protected,
        literal=_normalize_fqdn_literal(protected),
        apex=extract_apex_domain(protected),
        collapsed=_collapse_hostname_alphanumeric(protected),
    )


@dataclass(frozen=True)
class PreparedFragment:
    """One suffix fragment of a typo FQDN with derived comparison inputs."""

    literal: str
    apex: str
    collapsed: str


@dataclass(frozen=True)
class PreparedTypo:
    """Per-certificate-domain similarity inputs (built once, shared across programs)."""

    fragments: Tuple[PreparedFragment, ...]


def prepare_typo(typo_fqdn: str) -> PreparedTypo:
    fragments = tuple(
        PreparedFragment(
            literal=cand,
            apex=extract_apex_domain(cand),
            collapsed=_collapse_hostname_alphanumeric(cand),
        )
        for cand in _typo_suffix_hostnames(typo_fqdn)
    )
    return PreparedTypo(fragments=fragments)


def _pair_similarity_prepared(
    frag: PreparedFragment,
    prot: PreparedProtected,
    score_cutoff: float = 0.0,
) -> float:
    apex_sim = Levenshtein.normalized_similarity(
        frag.apex, prot.apex, score_cutoff=score_cutoff
    )
    coll_sim = Levenshtein.normalized_similarity(
        frag.collapsed, prot.collapsed, score_cutoff=score_cutoff
    )
    if frag.collapsed == prot.collapsed and frag.literal != prot.literal:
        coll_sim = min(coll_sim, _COLLAPSED_MATCH_NON_LITERAL_CAP)
    return max(apex_sim, coll_sim)


def best_match_among_prepared(
    typo: PreparedTypo,
    protected: Sequence[PreparedProtected],
    score_cutoff: float = 0.0,
) -> Tuple[float, Optional[str]]:
    """
    Best (similarity, protected_domain) over all fragments x protected domains.

    ``score_cutoff`` lets rapidfuzz bail out early; pair scores below it come back
    as 0.0, which is fine because callers only act on scores >= their threshold.
    """
    best_s = 0.0
    best_p: Optional[str] = None
    for prot in protected:
        for frag in typo.fragments:
            s = _pair_similarity_prepared(frag, prot, score_cutoff)
            if s > best_s:
                best_s = s
                best_p = prot.domain
    return best_s, best_p


def _pair_similarity(hostname_fragment: str, protected: str) -> float:
    frag = PreparedFragment(
        literal=_normalize_fqdn_literal(hostname_fragment),
        apex=extract_apex_domain(hostname_fragment),
        collapsed=_collapse_hostname_alphanumeric(hostname_fragment),
    )
    return _pair_similarity_prepared(frag, prepare_protected(protected))


def best_similarity_typo_to_protected(typo_fqdn: str, protected: str) -> float:
    if not typo_fqdn or not protected:
        return 0.0
    typo = prepare_typo(typo_fqdn)
    prot = prepare_protected(protected)
    best = 0.0
    for frag in typo.fragments:
        best = max(best, _pair_similarity_prepared(frag, prot))
    return best


def best_match_among_protected(typo_fqdn: str, protected_domains: List[str]) -> Tuple[float, Optional[str]]:
    typo = prepare_typo(typo_fqdn)
    prepared = [prepare_protected(p) for p in protected_domains if p]
    return best_match_among_prepared(typo, prepared)


def similarity_impossible_by_length_prepared(
    typo: PreparedTypo,
    protected_collapsed_lengths: List[int],
    similarity_threshold: float,
) -> bool:
    """
    Return True when no protected domain can reach similarity_threshold.

    Safe to skip full Levenshtein: edit distance is at least |len(a)-len(b)|.
    Checks all typo suffix fragments (same as best_match_among_prepared).
    """
    if not protected_collapsed_lengths or similarity_threshold >= 1.0:
        return False

    max_edit_frac = 1.0 - similarity_threshold
    for frag in typo.fragments:
        ca = frag.collapsed
        if not ca:
            continue
        la = len(ca)
        for lb in protected_collapsed_lengths:
            if lb <= 0:
                continue
            mx = max(la, lb)
            if abs(la - lb) / mx <= max_edit_frac:
                return False
    return True


def similarity_impossible_by_length(
    typo_fqdn: str,
    protected_collapsed_lengths: List[int],
    similarity_threshold: float,
) -> bool:
    return similarity_impossible_by_length_prepared(
        prepare_typo(typo_fqdn),
        protected_collapsed_lengths,
        similarity_threshold,
    )
