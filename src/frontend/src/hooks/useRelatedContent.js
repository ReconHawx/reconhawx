import { useState, useEffect, useCallback } from 'react';
import {
  domainAPI,
  urlAPI,
  serviceAPI,
  certificateAPI,
} from '../services/api/assets';
import { nucleiAPI, wpscanAPI } from '../services/api/findings';
import { subdomainColumns, urlColumns, serviceColumns } from '../components/RelatedAssetsSection';

const PAGE_SIZE = 10;

function paginated(data) {
  return {
    items: data?.items || [],
    total: data?.pagination?.total_items ?? data?.items?.length ?? 0,
  };
}

function buildFindingAssetLinks(finding) {
  const links = [];
  if (finding.hostname) {
    links.push({
      label: 'Domain',
      value: finding.hostname,
      detailPath: finding.domain_id
        ? `/assets/subdomains/details?id=${encodeURIComponent(finding.domain_id)}`
        : `/assets/subdomains?exact_match=${encodeURIComponent(finding.hostname)}`,
    });
  }
  if (finding.url) {
    links.push({
      label: 'URL',
      value: finding.url,
      detailPath: finding.url_id
        ? `/assets/urls/details?id=${encodeURIComponent(finding.url_id)}`
        : `/assets/urls?exact_match=${encodeURIComponent(finding.url)}`,
    });
  }
  if (finding.ip) {
    links.push({
      label: 'IP Address',
      value: finding.ip,
      detailPath: finding.ip_id
        ? `/assets/ips/details?id=${encodeURIComponent(finding.ip_id)}`
        : `/assets/ips?exact_match=${encodeURIComponent(finding.ip)}`,
    });
  }
  if (finding.ip && finding.port) {
    links.push({
      label: 'Service',
      value: `${finding.ip}:${finding.port}`,
      detailPath: finding.service_id
        ? `/assets/services/details?id=${encodeURIComponent(finding.service_id)}`
        : `/assets/services?exact_match=${encodeURIComponent(`${finding.ip}:${finding.port}`)}`,
    });
  }
  return links;
}

function findingFkFilters(finding) {
  if (finding.url_id) return { url_id: finding.url_id };
  if (finding.domain_id) return { subdomain_id: finding.domain_id };
  if (finding.service_id) return { service_id: finding.service_id };
  if (finding.ip_id) return { ip_id: finding.ip_id };
  return {};
}

async function fetchFindings(filters, excludeFindingId) {
  const base = { page: 1, page_size: PAGE_SIZE, ...filters };
  const [nucleiRes, wpscanRes] = await Promise.allSettled([
    nucleiAPI.search(base),
    wpscanAPI.search(base),
  ]);

  const nucleiData = nucleiRes.status === 'fulfilled' ? paginated(nucleiRes.value) : { items: [], total: 0 };
  const wpscanData = wpscanRes.status === 'fulfilled' ? paginated(wpscanRes.value) : { items: [], total: 0 };

  const filterOut = (items) =>
    excludeFindingId ? items.filter((f) => f.id !== excludeFindingId) : items;

  return {
    nucleiItems: filterOut(nucleiData.items),
    wpscanItems: filterOut(wpscanData.items),
    nucleiTotal: nucleiData.total,
    wpscanTotal: wpscanData.total,
  };
}

function buildFindingsViewAllPaths(filters) {
  const params = new URLSearchParams();
  if (filters.url_id) params.set('url_id', filters.url_id);
  if (filters.subdomain_id) params.set('subdomain_id', filters.subdomain_id);
  if (filters.ip_id) params.set('ip_id', filters.ip_id);
  if (filters.service_id) params.set('service_id', filters.service_id);
  if (filters.certificate_id) params.set('certificate_id', filters.certificate_id);
  if (filters.apex_domain) params.set('apex_domain', filters.apex_domain);
  const qs = params.toString();
  return {
    nucleiViewAllPath: qs ? `/findings/nuclei?${qs}` : '/findings/nuclei',
    wpscanViewAllPath: qs ? `/findings/wpscan?${qs}` : '/findings/wpscan',
  };
}

export function useRelatedContent({ entityType, entity, excludeFindingId = null, enabled = true }) {
  const [assetGroups, setAssetGroups] = useState([]);
  const [findings, setFindings] = useState({
    nucleiItems: [],
    wpscanItems: [],
    nucleiTotal: 0,
    wpscanTotal: 0,
    nucleiViewAllPath: '/findings/nuclei',
    wpscanViewAllPath: '/findings/wpscan',
  });
  const [loading, setLoading] = useState(false);
  const [findingsLoading, setFindingsLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!entity || !enabled) {
      setAssetGroups([]);
      setFindings({
        nucleiItems: [],
        wpscanItems: [],
        nucleiTotal: 0,
        wpscanTotal: 0,
        nucleiViewAllPath: '/findings/nuclei',
        wpscanViewAllPath: '/findings/wpscan',
      });
      return;
    }

    setLoading(true);
    setFindingsLoading(true);
    setError(null);

    try {
      const groups = [];
      let findingFilters = {};

      if (entityType === 'nuclei_finding' || entityType === 'wpscan_finding') {
        const links = buildFindingAssetLinks(entity);
        if (links.length > 0) {
          groups.push({
            key: 'assets',
            label: 'Linked Assets',
            links,
          });
        }
        findingFilters = findingFkFilters(entity);
      } else if (entityType === 'apex_domain') {
        const apexName = entity.name;
        findingFilters = { apex_domain: apexName };
        const subRes = await domainAPI.searchSubdomains({
          apex_domain: apexName,
          page: 1,
          page_size: PAGE_SIZE,
          sort_by: 'name',
          sort_dir: 'asc',
        });
        const { items, total } = paginated(subRes);
        groups.push({
          key: 'subdomains',
          label: 'Subdomains',
          items,
          totalCount: total,
          columns: subdomainColumns(),
          detailPath: (item) => `/assets/subdomains/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/subdomains?apex_domain=${encodeURIComponent(apexName)}`,
        });
      } else if (entityType === 'certificate') {
        findingFilters = { certificate_id: entity.id };
        const urlRes = await urlAPI.searchURLs({
          certificate_id: entity.id,
          page: 1,
          page_size: PAGE_SIZE,
        });
        const { items, total } = paginated(urlRes);
        groups.push({
          key: 'urls',
          label: 'URLs',
          items,
          totalCount: total,
          columns: urlColumns(),
          detailPath: (item) => `/assets/urls/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/urls?certificate_id=${encodeURIComponent(entity.id)}`,
        });
      } else if (entityType === 'ip') {
        findingFilters = { ip_id: entity.id };
        const ipAddr = entity.ip || entity.ip_address;
        const [subRes, svcRes] = await Promise.allSettled([
          domainAPI.getSubdomainsByIP(ipAddr, 1, PAGE_SIZE),
          serviceAPI.searchServices({
            exact_match_ip: ipAddr,
            page: 1,
            page_size: PAGE_SIZE,
          }),
        ]);
        const subData = subRes.status === 'fulfilled' ? paginated(subRes.value) : { items: [], total: 0 };
        const svcData = svcRes.status === 'fulfilled' ? paginated(svcRes.value) : { items: [], total: 0 };
        groups.push({
          key: 'subdomains',
          label: 'Subdomains',
          items: subData.items,
          totalCount: subData.total,
          columns: subdomainColumns(),
          detailPath: (item) => `/assets/subdomains/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/subdomains?ip=${encodeURIComponent(ipAddr)}`,
        });
        groups.push({
          key: 'services',
          label: 'Services',
          items: svcData.items,
          totalCount: svcData.total,
          columns: serviceColumns(),
          detailPath: (item) => `/assets/services/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/services?exact_match_ip=${encodeURIComponent(ipAddr)}`,
        });
      } else if (entityType === 'service') {
        findingFilters = { service_id: entity.id };
        const promises = [
          urlAPI.searchURLs({ service_id: entity.id, page: 1, page_size: PAGE_SIZE }),
        ];
        const [urlRes] = await Promise.allSettled(promises);
        const urlData = urlRes.status === 'fulfilled' ? paginated(urlRes.value) : { items: [], total: 0 };
        if (entity.ip_id && entity.ip) {
          groups.push({
            key: 'ip',
            label: 'IP Address',
            links: [
              {
                label: 'IP',
                value: entity.ip,
                detailPath: `/assets/ips/details?id=${encodeURIComponent(entity.ip_id)}`,
              },
            ],
          });
        }
        groups.push({
          key: 'urls',
          label: 'URLs',
          items: urlData.items,
          totalCount: urlData.total,
          columns: urlColumns(),
          detailPath: (item) => `/assets/urls/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/urls?service_id=${encodeURIComponent(entity.id)}`,
        });
      } else if (entityType === 'subdomain') {
        findingFilters = { subdomain_id: entity.id };
        const ipList = Array.isArray(entity.ip)
          ? entity.ip.map((entry) => (typeof entry === 'string' ? entry : entry?.ip)).filter(Boolean)
          : [];
        const urlRes = await urlAPI.searchURLs({
          subdomain_id: entity.id,
          page: 1,
          page_size: PAGE_SIZE,
        });
        const { items: urlItems, total: urlTotal } = paginated(urlRes);
        groups.push({
          key: 'urls',
          label: 'URLs',
          items: urlItems,
          totalCount: urlTotal,
          columns: urlColumns(),
          detailPath: (item) => `/assets/urls/details?id=${encodeURIComponent(item.id)}`,
          viewAllPath: `/assets/urls?hostname=${encodeURIComponent(entity.name)}`,
        });

        if (entity.apex_domain) {
          groups.push({
            key: 'apex',
            label: 'Apex Domain',
            links: [
              {
                label: 'Apex Domain',
                value: entity.apex_domain,
                detailPath: entity.apex_domain_id
                  ? `/assets/apex-domains/details?id=${encodeURIComponent(entity.apex_domain_id)}`
                  : `/assets/apex-domains?exact_match=${encodeURIComponent(entity.apex_domain)}`,
              },
            ],
          });
        }

        const serviceMap = new Map();
        await Promise.all(
          ipList.slice(0, 5).map(async (ipAddr) => {
            try {
              const res = await serviceAPI.searchServices({
                exact_match_ip: ipAddr,
                page: 1,
                page_size: PAGE_SIZE,
              });
              paginated(res).items.forEach((svc) => {
                if (svc.id) serviceMap.set(svc.id, svc);
              });
            } catch {
              /* ignore per-IP errors */
            }
          })
        );
        const services = [...serviceMap.values()].slice(0, PAGE_SIZE);
        if (services.length > 0) {
          groups.push({
            key: 'services',
            label: 'Services',
            items: services,
            totalCount: services.length,
            columns: serviceColumns(),
            detailPath: (item) => `/assets/services/details?id=${encodeURIComponent(item.id)}`,
          });
        }
      } else if (entityType === 'url') {
        findingFilters = { url_id: entity.id };
        const serviceIds = entity.service_ids || (entity.service_id ? [entity.service_id] : []);
        const fetchPromises = [];
        if (entity.certificate_id) {
          fetchPromises.push(
            certificateAPI.getById(entity.certificate_id).then((cert) => ({ type: 'cert', cert }))
          );
        }
        serviceIds.forEach((id) => {
          fetchPromises.push(serviceAPI.getById(id).then((svc) => ({ type: 'svc', svc })));
        });
        if (entity.subdomain_id) {
          fetchPromises.push(
            domainAPI.getById(entity.subdomain_id).then((sub) => ({ type: 'sub', sub }))
          );
        }
        const results = await Promise.allSettled(fetchPromises);
        const links = [];
        const fetchedServices = [];
        results.forEach((res) => {
          if (res.status !== 'fulfilled') return;
          const { type, cert, svc, sub } = res.value;
          if (type === 'cert' && cert) {
            links.push({
              label: 'Certificate',
              value: cert.subject_cn || cert.subject_dn || 'Certificate',
              detailPath: `/assets/certificates/details?id=${encodeURIComponent(entity.certificate_id)}`,
            });
          }
          if (type === 'svc' && svc) {
            fetchedServices.push(svc);
            links.push({
              label: 'Service',
              value: `${svc.ip}:${svc.port}`,
              detailPath: `/assets/services/details?id=${encodeURIComponent(svc.id)}`,
            });
          }
          if (type === 'sub' && sub) {
            links.push({
              label: 'Subdomain',
              value: sub.name,
              detailPath: `/assets/subdomains/details?id=${encodeURIComponent(sub.id)}`,
            });
          }
        });
        const seenIps = new Set();
        fetchedServices.forEach((svc) => {
          if (svc.ip_id && svc.ip && !seenIps.has(svc.ip_id)) {
            seenIps.add(svc.ip_id);
            links.push({
              label: 'IP Address',
              value: svc.ip,
              detailPath: `/assets/ips/details?id=${encodeURIComponent(svc.ip_id)}`,
            });
          }
        });
        if (links.length > 0) {
          groups.push({
            key: 'linked',
            label: 'Linked Assets',
            links,
          });
        }
      }

      setAssetGroups(groups);
      setLoading(false);

      if (Object.keys(findingFilters).length > 0) {
        const findingData = await fetchFindings(findingFilters, excludeFindingId);
        const viewAll = buildFindingsViewAllPaths(findingFilters);
        setFindings({ ...findingData, ...viewAll });
      } else {
        setFindings({
          nucleiItems: [],
          wpscanItems: [],
          nucleiTotal: 0,
          wpscanTotal: 0,
          nucleiViewAllPath: '/findings/nuclei',
          wpscanViewAllPath: '/findings/wpscan',
        });
      }
    } catch (err) {
      setError(err.message || 'Failed to load related content');
      setAssetGroups([]);
    } finally {
      setLoading(false);
      setFindingsLoading(false);
    }
  }, [entityType, entity, excludeFindingId, enabled]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    assetGroups,
    findings,
    loading,
    findingsLoading,
    error,
    reload: load,
  };
}

export default useRelatedContent;
