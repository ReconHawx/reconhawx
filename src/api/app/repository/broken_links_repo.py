"""Broken links repository — delegates to unified ``FindingsRepository``."""

from utils.query_filters import ProgramAccessMixin

from .findings_repo import FindingsRepository


class BrokenLinksRepository(ProgramAccessMixin):
    """PostgreSQL repository for broken-link findings (unified ``findings`` table)."""

    create_or_update_broken_link = FindingsRepository.create_or_update_broken_link
    get_broken_link_by_id = FindingsRepository.get_broken_link_by_id
    search_broken_links = FindingsRepository.search_broken_links
    update_broken_link = FindingsRepository.update_broken_link
    delete_broken_link = FindingsRepository.delete_broken_link
    delete_broken_links_batch = FindingsRepository.delete_broken_links_batch
    get_broken_links_stats = FindingsRepository.get_broken_links_stats
