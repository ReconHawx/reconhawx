"""WPScan findings repository — delegates to unified ``FindingsRepository``."""

from utils.query_filters import ProgramAccessMixin

from .findings_repo import FindingsRepository


class WPScanFindingsRepository(ProgramAccessMixin):
    """PostgreSQL repository for WPScan findings (unified ``findings`` table)."""

    create_or_update_wpscan_finding = FindingsRepository.create_or_update_wpscan_finding
    get_wpscan_by_id = FindingsRepository.get_wpscan_by_id
    get_wpscan_query_count = FindingsRepository.get_wpscan_query_count
    _apply_wpscan_filters = FindingsRepository._apply_wpscan_filters
    get_wpscan_stats_by_severity = FindingsRepository.get_wpscan_stats_by_severity
    get_distinct_wpscan_values_typed = FindingsRepository.get_distinct_wpscan_values_typed
    search_wpscan_typed = FindingsRepository.search_wpscan_typed
    update_wpscan_finding = FindingsRepository.update_wpscan_finding
    delete_wpscan_finding = FindingsRepository.delete_wpscan_finding
    delete_wpscan_findings_batch = FindingsRepository.delete_wpscan_findings_batch
    execute_wpscan_query = FindingsRepository.execute_wpscan_query
