"""Lowercase hostnames/FQDNs and URL hosts; merge case-only duplicates.

Revision ID: v012_lowercase_hostnames
Revises: v011_waf_settings_extend

Running twice against an already-clean database is effectively a no-op.
Downgrade is no-op (original casing cannot be restored).

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v012_lowercase_hostnames"
down_revision: Union[str, Sequence[str], None] = "v011_waf_settings_extend"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CREATE_FN = """
CREATE OR REPLACE FUNCTION migration_0013_lower_url_host(u text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  m text[];
  prefix_len int;
BEGIN
  IF u IS NULL THEN
    RETURN NULL;
  END IF;
  IF u = '' THEN
    RETURN u;
  END IF;
  m := regexp_match(u, '^([a-zA-Z][a-zA-Z0-9+.-]*://)([^/?#]*)');
  IF m IS NOT NULL THEN
    prefix_len := length(m[1]) + length(m[2]);
    RETURN m[1] || lower(m[2]) || substr(u, prefix_len + 1);
  END IF;
  m := regexp_match(u, '^(//)([^/?#]*)');
  IF m IS NOT NULL THEN
    prefix_len := length(m[1]) + length(m[2]);
    RETURN m[1] || lower(m[2]) || substr(u, prefix_len + 1);
  END IF;
  RETURN u;
END;
$$;
"""

_DROP_FN = "DROP FUNCTION IF EXISTS migration_0013_lower_url_host(text);"


def upgrade() -> None:
    op.execute(sa.text(_CREATE_FN))

    op.execute(
        sa.text(
            """
WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM apex_domains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT ad.id AS old_id,
    k.keep_id
  FROM apex_domains ad
  JOIN keepers k
    ON k.program_id = ad.program_id AND k.lk = lower(ad.name)
  WHERE ad.id <> k.keep_id
)
UPDATE subdomains s
SET apex_domain_id = d.keep_id
FROM dups d
WHERE s.apex_domain_id = d.old_id
  AND s.apex_domain_id <> d.keep_id;

WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM apex_domains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT ad.id AS old_id
  FROM apex_domains ad
  JOIN keepers k
    ON k.program_id = ad.program_id AND k.lk = lower(ad.name)
  WHERE ad.id <> k.keep_id
)
DELETE FROM apex_domains WHERE id IN (SELECT old_id FROM dups);

UPDATE apex_domains SET name = lower(name) WHERE name <> lower(name);
"""
        )
    )

    op.execute(
        sa.text(
            """
WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM subdomains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT s.id AS old_id,
    k.keep_id
  FROM subdomains s
  JOIN keepers k
    ON k.program_id = s.program_id AND k.lk = lower(s.name)
  WHERE s.id <> k.keep_id
)
INSERT INTO subdomain_ips (id, subdomain_id, ip_id, created_at)
SELECT gen_random_uuid(), d.keep_id, si.ip_id, si.created_at
FROM subdomain_ips si
JOIN dups d ON si.subdomain_id = d.old_id
ON CONFLICT ON CONSTRAINT subdomain_ips_subdomain_id_ip_id_key DO NOTHING;

WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM subdomains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT s.id AS old_id
  FROM subdomains s
  JOIN keepers k
    ON k.program_id = s.program_id AND k.lk = lower(s.name)
  WHERE s.id <> k.keep_id
)
DELETE FROM subdomain_ips WHERE subdomain_id IN (SELECT old_id FROM dups);

WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM subdomains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT s.id AS old_id,
    k.keep_id
  FROM subdomains s
  JOIN keepers k
    ON k.program_id = s.program_id AND k.lk = lower(s.name)
  WHERE s.id <> k.keep_id
)
UPDATE urls u
SET subdomain_id = d.keep_id
FROM dups d
WHERE u.subdomain_id = d.old_id
  AND u.subdomain_id IS NOT NULL;

WITH keepers AS (
  SELECT DISTINCT ON (program_id, lower(name))
    id AS keep_id,
    program_id,
    lower(name) AS lk
  FROM subdomains
  ORDER BY program_id, lower(name), created_at ASC, id ASC
),
dups AS (
  SELECT s.id AS old_id
  FROM subdomains s
  JOIN keepers k
    ON k.program_id = s.program_id AND k.lk = lower(s.name)
  WHERE s.id <> k.keep_id
)
DELETE FROM subdomains WHERE id IN (SELECT old_id FROM dups);

UPDATE subdomains
SET name = lower(name),
    cname_record = CASE
      WHEN cname_record IS NOT NULL THEN lower(cname_record)
      ELSE cname_record
    END
WHERE name <> lower(name)
   OR (cname_record IS NOT NULL AND cname_record <> lower(cname_record));
"""
        )
    )

    op.execute(
        sa.text(
            """
WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id,
    k.keep_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
INSERT INTO url_services (id, url_id, service_id, created_at)
SELECT gen_random_uuid(), d.keep_id, us.service_id, us.created_at
FROM url_services us
JOIN url_dups d ON us.url_id = d.old_id
ON CONFLICT ON CONSTRAINT url_services_url_id_service_id_key DO NOTHING;

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id,
    k.keep_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
INSERT INTO url_technologies (id, technology_id, url_id, created_at)
SELECT gen_random_uuid(), ut.technology_id, d.keep_id, ut.created_at
FROM url_technologies ut
JOIN url_dups d ON ut.url_id = d.old_id
ON CONFLICT (technology_id, url_id) DO NOTHING;

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id,
    k.keep_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
DELETE FROM extracted_link_sources els USING url_dups d
WHERE els.source_url_id = d.old_id
  AND EXISTS (
    SELECT 1 FROM extracted_link_sources x
    WHERE x.extracted_link_id = els.extracted_link_id
      AND x.source_url_id = d.keep_id);

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id,
    k.keep_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
UPDATE extracted_link_sources els
SET source_url_id = d.keep_id
FROM url_dups d
WHERE els.source_url_id = d.old_id;

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id,
    k.keep_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
UPDATE screenshots sc
SET url_id = d.keep_id
FROM url_dups d
WHERE sc.url_id = d.old_id;

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
DELETE FROM url_services WHERE url_id IN (SELECT old_id FROM url_dups);

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
DELETE FROM url_technologies WHERE url_id IN (SELECT old_id FROM url_dups);

WITH url_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM urls
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
url_dups AS (
  SELECT u.id AS old_id
  FROM urls u
  JOIN url_keepers k
    ON k.program_id = u.program_id AND k.nu = migration_0013_lower_url_host(u.url)
  WHERE u.id <> k.keep_id
)
DELETE FROM urls WHERE id IN (SELECT old_id FROM url_dups);

UPDATE urls
SET url = migration_0013_lower_url_host(url),
    hostname = lower(hostname),
    final_url = CASE
      WHEN final_url IS NOT NULL THEN migration_0013_lower_url_host(final_url)
      ELSE final_url END
WHERE url <> migration_0013_lower_url_host(url)
   OR hostname <> lower(hostname)
   OR (final_url IS NOT NULL AND final_url <> migration_0013_lower_url_host(final_url));
"""
        )
    )

    op.execute(
        sa.text(
            """
WITH lk_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(link_url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(link_url) AS nu
  FROM extracted_links
  ORDER BY program_id, migration_0013_lower_url_host(link_url), created_at ASC, id ASC
),
lk_dups AS (
  SELECT e.id AS old_id,
    k.keep_id
  FROM extracted_links e
  JOIN lk_keepers k
    ON k.program_id = e.program_id AND k.nu = migration_0013_lower_url_host(e.link_url)
  WHERE e.id <> k.keep_id
)
DELETE FROM extracted_link_sources els USING lk_dups d
WHERE els.extracted_link_id = d.old_id
  AND EXISTS (
    SELECT 1 FROM extracted_link_sources x
    WHERE x.source_url_id = els.source_url_id
      AND x.extracted_link_id = d.keep_id);

WITH lk_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(link_url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(link_url) AS nu
  FROM extracted_links
  ORDER BY program_id, migration_0013_lower_url_host(link_url), created_at ASC, id ASC
),
lk_dups AS (
  SELECT e.id AS old_id,
    k.keep_id
  FROM extracted_links e
  JOIN lk_keepers k
    ON k.program_id = e.program_id AND k.nu = migration_0013_lower_url_host(e.link_url)
  WHERE e.id <> k.keep_id
)
UPDATE extracted_link_sources els
SET extracted_link_id = d.keep_id
FROM lk_dups d
WHERE els.extracted_link_id = d.old_id;

WITH lk_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(link_url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(link_url) AS nu
  FROM extracted_links
  ORDER BY program_id, migration_0013_lower_url_host(link_url), created_at ASC, id ASC
),
lk_dups AS (
  SELECT e.id AS old_id
  FROM extracted_links e
  JOIN lk_keepers k
    ON k.program_id = e.program_id AND k.nu = migration_0013_lower_url_host(e.link_url)
  WHERE e.id <> k.keep_id
)
DELETE FROM extracted_links WHERE id IN (SELECT old_id FROM lk_dups);

UPDATE extracted_links
SET link_url = migration_0013_lower_url_host(link_url)
WHERE link_url <> migration_0013_lower_url_host(link_url);
"""
        )
    )

    op.execute(
        sa.text(
            """
UPDATE ips SET ptr_record = lower(ptr_record)
WHERE ptr_record IS NOT NULL AND ptr_record <> lower(ptr_record);

WITH typ_keep AS (
  SELECT DISTINCT ON (lower(typo_domain))
    id AS keep_id,
    lower(typo_domain) AS lk
  FROM typosquat_domains
  ORDER BY lower(typo_domain), detected_at ASC, id ASC
),
typ_dups AS (
  SELECT t.id AS old_id,
    k.keep_id
  FROM typosquat_domains t
  JOIN typ_keep k ON k.lk = lower(t.typo_domain)
  WHERE t.id <> k.keep_id
)
UPDATE typosquat_urls tu SET typosquat_domain_id = d.keep_id FROM typ_dups d
WHERE tu.typosquat_domain_id = d.old_id;

WITH typ_keep AS (
  SELECT DISTINCT ON (lower(typo_domain))
    id AS keep_id,
    lower(typo_domain) AS lk
  FROM typosquat_domains
  ORDER BY lower(typo_domain), detected_at ASC, id ASC
),
typ_dups AS (
  SELECT t.id AS old_id
  FROM typosquat_domains t
  JOIN typ_keep k ON k.lk = lower(t.typo_domain)
  WHERE t.id <> k.keep_id
)
DELETE FROM typosquat_domains WHERE id IN (SELECT old_id FROM typ_dups);

UPDATE typosquat_domains SET typo_domain = lower(typo_domain)
WHERE typo_domain <> lower(typo_domain);

WITH tu_keep AS (
  SELECT DISTINCT ON (migration_0013_lower_url_host(url))
    id AS keep_id,
    migration_0013_lower_url_host(url) AS nu
  FROM typosquat_urls
  ORDER BY migration_0013_lower_url_host(url), created_at ASC, id ASC
),
tu_dups AS (
  SELECT t.id AS old_id,
    k.keep_id
  FROM typosquat_urls t
  JOIN tu_keep k ON k.nu = migration_0013_lower_url_host(t.url)
  WHERE t.id <> k.keep_id
)
UPDATE typosquat_screenshots ts
SET url_id = d.keep_id
FROM tu_dups d
WHERE ts.url_id = d.old_id;

WITH tu_keep AS (
  SELECT DISTINCT ON (migration_0013_lower_url_host(url))
    id AS keep_id,
    migration_0013_lower_url_host(url) AS nu
  FROM typosquat_urls
  ORDER BY migration_0013_lower_url_host(url), created_at ASC, id ASC
),
tu_dups AS (
  SELECT t.id AS old_id
  FROM typosquat_urls t
  JOIN tu_keep k ON k.nu = migration_0013_lower_url_host(t.url)
  WHERE t.id <> k.keep_id
)
DELETE FROM typosquat_urls WHERE id IN (SELECT old_id FROM tu_dups);

UPDATE typosquat_urls SET
  url = migration_0013_lower_url_host(url),
  hostname = lower(hostname),
  scheme = CASE WHEN scheme IS NOT NULL THEN lower(scheme) ELSE scheme END,
  final_url = CASE
    WHEN final_url IS NOT NULL THEN migration_0013_lower_url_host(final_url)
    ELSE final_url END,
  favicon_url = CASE
    WHEN favicon_url IS NOT NULL THEN migration_0013_lower_url_host(favicon_url)
    ELSE favicon_url END
WHERE url <> migration_0013_lower_url_host(url)
   OR hostname <> lower(hostname)
   OR (scheme IS NOT NULL AND scheme <> lower(scheme))
   OR (final_url IS NOT NULL AND final_url <> migration_0013_lower_url_host(final_url))
   OR (favicon_url IS NOT NULL AND favicon_url <> migration_0013_lower_url_host(favicon_url));
"""
        )
    )

    op.execute(
        sa.text(
            """
UPDATE nuclei_findings
SET url = migration_0013_lower_url_host(url),
    template_url = CASE
      WHEN template_url IS NOT NULL
       AND template_url LIKE 'http%'
      THEN migration_0013_lower_url_host(template_url)
      ELSE template_url END,
    hostname = CASE WHEN hostname IS NOT NULL THEN lower(hostname) ELSE hostname END,
    scheme = CASE WHEN scheme IS NOT NULL THEN lower(scheme) ELSE scheme END;

DELETE FROM nuclei_findings n
WHERE EXISTS (
  SELECT 1
  FROM nuclei_findings k
  WHERE k.id <> n.id
    AND k.program_id = n.program_id
    AND k.url IS NOT DISTINCT FROM n.url
    AND k.template_id IS NOT DISTINCT FROM n.template_id
    AND k.matcher_name IS NOT DISTINCT FROM n.matcher_name
    AND k.matched_at IS NOT DISTINCT FROM n.matched_at
    AND (
      k.created_at < n.created_at
      OR (k.created_at = n.created_at AND k.id < n.id)
    )
);
"""
        )
    )

    op.execute(
        sa.text(
            """
UPDATE wpscan_findings SET
    url = migration_0013_lower_url_host(url),
    hostname = CASE WHEN hostname IS NOT NULL THEN lower(hostname) ELSE hostname END,
    scheme = CASE WHEN scheme IS NOT NULL THEN lower(scheme) ELSE scheme END
WHERE url <> migration_0013_lower_url_host(url)
   OR (hostname IS NOT NULL AND hostname <> lower(hostname))
   OR (scheme IS NOT NULL AND scheme <> lower(scheme));
"""
        )
    )

    op.execute(
        sa.text(
            """
WITH bl_keepers AS (
  SELECT DISTINCT ON (program_id, migration_0013_lower_url_host(url))
    id AS keep_id,
    program_id,
    migration_0013_lower_url_host(url) AS nu
  FROM broken_links
  WHERE url IS NOT NULL
  ORDER BY program_id, migration_0013_lower_url_host(url), created_at ASC, id ASC
),
bl_dups AS (
  SELECT b.id AS old_id
  FROM broken_links b
  JOIN bl_keepers k
    ON k.program_id = b.program_id AND k.nu = migration_0013_lower_url_host(b.url)
  WHERE b.url IS NOT NULL
    AND b.id <> k.keep_id
)
DELETE FROM broken_links bl
WHERE bl.id IN (SELECT old_id FROM bl_dups);

UPDATE broken_links SET
    url = CASE WHEN url IS NOT NULL THEN migration_0013_lower_url_host(url) ELSE url END,
    domain = CASE WHEN domain IS NOT NULL THEN lower(domain) ELSE domain END
WHERE url IS DISTINCT FROM CASE WHEN url IS NOT NULL THEN migration_0013_lower_url_host(url) ELSE url END
   OR domain IS DISTINCT FROM CASE WHEN domain IS NOT NULL THEN lower(domain) ELSE domain END;
"""
        )
    )

    op.execute(
        sa.text(
            """
UPDATE droopescan_findings SET
    url = migration_0013_lower_url_host(url),
    host = CASE WHEN host IS NOT NULL THEN lower(host) ELSE host END,
    hostname = CASE WHEN hostname IS NOT NULL THEN lower(hostname) ELSE hostname END,
    scheme = CASE WHEN scheme IS NOT NULL THEN lower(scheme) ELSE scheme END
WHERE url <> migration_0013_lower_url_host(url)
   OR (host IS NOT NULL AND host <> lower(host))
   OR (hostname IS NOT NULL AND hostname <> lower(hostname))
   OR (scheme IS NOT NULL AND scheme <> lower(scheme));
"""
        )
    )

    op.execute(sa.text(_DROP_FN))


def downgrade() -> None:
    pass
