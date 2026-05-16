import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Badge } from 'react-bootstrap';
import './SitemapTree.css';

const loadFontAwesome = () => {
  if (!document.querySelector('link[href*="fontawesome"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css';
    document.head.appendChild(link);
  }
};

/** Raw UUID / id string for API and routes (not pre-encoded). */
const getUrlRecordId = (urlRecord) => {
  if (!urlRecord) return null;
  const raw = urlRecord.id ?? urlRecord._id;
  if (raw == null || raw === '') return null;
  const s = String(raw).trim();
  return s || null;
};

const SitemapTree = ({ urls }) => {
  const [expandedNodes, setExpandedNodes] = useState(new Set());

  useEffect(() => {
    loadFontAwesome();
  }, []);

  const buildSitemapTree = (urls) => {
    const tree = {};

    urls.forEach((url) => {
      let path;
      try {
        const urlObj = new URL(url.url);
        path = urlObj.pathname;
      } catch (e) {
        path = url.path || '/';
      }

      const normalizedPath = path.replace(/^\/+|\/+$/g, '');
      if (!normalizedPath) {
        return;
      }

      const pathSegments = normalizedPath.split('/');
      let currentLevel = tree;

      pathSegments.forEach((segment, idx) => {
        const isLast = idx === pathSegments.length - 1;

        if (!currentLevel[segment]) {
          currentLevel[segment] = {
            name: segment,
            type: 'folder',
            children: {},
            urlObj: null,
            pageUrl: null,
          };
        }

        const node = currentLevel[segment];

        if (isLast) {
          const hasKids = Object.keys(node.children).length > 0;
          if (hasKids) {
            node.pageUrl = url;
            node.type = 'folder';
          } else {
            node.urlObj = url;
            node.type = 'file';
          }
        } else {
          if (node.type === 'file' && node.urlObj) {
            node.pageUrl = node.urlObj;
            node.urlObj = null;
          }
          node.type = 'folder';
          currentLevel = node.children;
        }
      });
    });

    return tree;
  };

  const toggleNode = (nodeKey) => {
    setExpandedNodes((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(nodeKey)) {
        newSet.delete(nodeKey);
      } else {
        newSet.add(nodeKey);
      }
      return newSet;
    });
  };

  const getStatusBadgeVariant = (statusCode) => {
    if (!statusCode) return 'secondary';
    if (statusCode < 300) return 'success';
    if (statusCode < 400) return 'info';
    if (statusCode < 500) return 'warning';
    return 'danger';
  };

  const renderUrlBadges = (urlRecord) => (
    <div className="d-flex align-items-center flex-shrink-0">
      <Badge bg={getStatusBadgeVariant(urlRecord.http_status_code)} className="me-1">
        {urlRecord.http_status_code || 'N/A'}
      </Badge>
      {urlRecord.content_type && (
        <Badge bg="info" className="me-1">
          {urlRecord.content_type}
        </Badge>
      )}
    </div>
  );

  const renderUrlLeaf = (urlRecord, keySuffix, label) => {
    const id = getUrlRecordId(urlRecord);
    const to = id ? `/assets/urls/details?id=${encodeURIComponent(id)}` : null;
    return (
      <div className="tree-leaf d-flex align-items-center mb-1" key={keySuffix}>
        <i className="fas fa-file text-muted me-2" aria-hidden />
        {to ? (
          <Link
            to={to}
            className="text-decoration-none me-2"
            title={urlRecord.url}
            onClick={(e) => e.stopPropagation()}
          >
            {label}
          </Link>
        ) : (
          <span className="me-2" title={urlRecord.url}>
            {label}
          </span>
        )}
        <div className="ms-auto">{renderUrlBadges(urlRecord)}</div>
      </div>
    );
  };

  const renderTreeNode = (key, node, level = 0, parentKey = '') => {
    const nodeKey = `${parentKey}/${key}`;
    const isExpanded = expandedNodes.has(nodeKey);
    const hasChildren = Object.keys(node.children).length > 0;

    if (node.type === 'file' && node.urlObj) {
      return (
        <li key={nodeKey} className="sitemap-tree-item">
          {renderUrlLeaf(node.urlObj, nodeKey, node.name)}
        </li>
      );
    }

    const pageAssetId = node.pageUrl ? getUrlRecordId(node.pageUrl) : null;
    const pageDetailTo = pageAssetId
      ? `/assets/urls/details?id=${encodeURIComponent(pageAssetId)}`
      : null;

    return (
      <li key={nodeKey} className="sitemap-tree-item">
        <div className="d-flex align-items-center mb-1 flex-wrap gap-2 sitemap-folder-row">
          <div
            className="tree-node d-flex align-items-center sitemap-folder flex-grow-1"
            onClick={() => hasChildren && toggleNode(nodeKey)}
            style={{ cursor: hasChildren ? 'pointer' : 'default', minWidth: 0 }}
          >
            <i
              className={`fas ${isExpanded ? 'fa-folder-open' : 'fa-folder'} text-warning me-2`}
              aria-hidden
            />
            <span className="fw-bold">{node.name}</span>
            {hasChildren && (
              <i
                className={`fas ${isExpanded ? 'fa-chevron-down' : 'fa-chevron-right'} ms-2 text-muted`}
                style={{ fontSize: '0.8rem' }}
                aria-hidden
              />
            )}
          </div>
          {node.pageUrl && (
            <div className="d-flex align-items-center ms-md-auto flex-shrink-0 gap-2">
              {pageDetailTo ? (
                <Link
                  to={pageDetailTo}
                  className="text-decoration-none sitemap-page-asset-link"
                  title={node.pageUrl.url}
                  aria-label={`Open URL asset for ${node.name}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <i className="fas fa-file-alt text-muted" aria-hidden />
                </Link>
              ) : (
                <i
                  className="fas fa-file-alt text-muted opacity-50"
                  title={node.pageUrl.url || undefined}
                  aria-hidden
                />
              )}
              {renderUrlBadges(node.pageUrl)}
            </div>
          )}
        </div>
        {hasChildren && isExpanded && (
          <ul className="sitemap-subtree list-unstyled ms-3">
            {Object.entries(node.children)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([childKey, childNode]) =>
                renderTreeNode(childKey, childNode, level + 1, nodeKey)
              )}
          </ul>
        )}
      </li>
    );
  };

  if (!urls || urls.length === 0) {
    return (
      <p className="text-muted mb-0">No other URLs found for this base path.</p>
    );
  }

  const sitemapTree = buildSitemapTree(urls);

  if (Object.keys(sitemapTree).length === 0) {
    return (
      <p className="text-muted mb-0">No other URLs found for this base path.</p>
    );
  }

  return (
    <div className="sitemap-tree">
      <ul className="list-unstyled">
        {Object.entries(sitemapTree)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([key, node]) => renderTreeNode(key, node))}
      </ul>
    </div>
  );
};

export default SitemapTree;
