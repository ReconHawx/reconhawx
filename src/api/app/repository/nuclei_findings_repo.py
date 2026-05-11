"""Nuclei findings repository — delegates to unified ``FindingsRepository``."""

from utils.query_filters import ProgramAccessMixin

from .findings_repo import FindingsRepository


class NucleiFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for Nuclei findings (unified ``findings`` table)."""

    create_or_update_nuclei_finding = FindingsRepository.create_or_update_nuclei_finding
    get_nuclei_by_id = FindingsRepository.get_nuclei_by_id
    execute_nuclei_query = FindingsRepository.execute_nuclei_query
    get_nuclei_query_count = FindingsRepository.get_nuclei_query_count
    _apply_nuclei_filters = FindingsRepository._apply_nuclei_filters
    get_nuclei_stats_by_severity = FindingsRepository.get_nuclei_stats_by_severity
    get_distinct_nuclei_values_typed = FindingsRepository.get_distinct_nuclei_values_typed
    search_nuclei_typed = FindingsRepository.search_nuclei_typed
    update_nuclei_finding = FindingsRepository.update_nuclei_finding
    delete_nuclei_finding = FindingsRepository.delete_nuclei_finding
    delete_nuclei_findings_batch = FindingsRepository.delete_nuclei_findings_batch
