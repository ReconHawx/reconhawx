import React, { useState } from 'react';
import { Badge } from 'react-bootstrap';
import './SitemapTree.css';

const SitemapTree = ({ urls }) => {
  const [expandedNodes, setExpandedNodes] = useState(new Set());

  const buildSitemapTree = (urls) => {
    const tree = {};
    
    urls.forEach(url => {
      // Parse the URL to get the path
      let path;
      try {
        const urlObj = new URL(url.url);
        path = urlObj.pathname;
      } catch (e) {
        path = url.path || '/';
      }
      
      // Normalize path: remove leading/trailing slashes
      const normalizedPath = path.replace(/^\/+|\/+$/g, '');
      if (!normalizedPath) {
        // Skip root path
        return;
      }

      const pathSegments = normalizedPath.split('/');
      let currentLevel = tree;
      
      pathSegments.forEach((segment, idx) => {
        const isLast = idx === pathSegments.length - 1;
        const nodeType = isLast ? 'file' : 'folder';

        if (!currentLevel[segment]) {
          currentLevel[segment] = {
            name: segment,
            type: nodeType,
            children: {},
            urlObj: null
          };
        }
        
        if (isLast) {
          currentLevel[segment].urlObj = url;
          currentLevel[segment].type = 'file';
        } else {
          currentLevel[segment].type = 'folder';
          currentLevel = currentLevel[segment].children;
        }
      });
    });
    
    return tree;
  };

  const toggleNode = (nodeKey) => {
    setExpandedNodes(prev => {
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

  const renderTreeNode = (key, node, level = 0, parentKey = '') => {
    const nodeKey = `${parentKey}/${key}`;
    const isExpanded = expandedNodes.has(nodeKey);
    const hasChildren = Object.keys(node.children).length > 0;

    return (
      <li key={nodeKey} className="sitemap-tree-item">
        {node.type === 'file' && node.urlObj ? (
          // File node
          <div className="tree-leaf d-flex align-items-center mb-1">
            <i className="fas fa-file text-muted me-2"></i>
            <a 
              href={`/assets/urls/details?id=${encodeURIComponent(node.urlObj.id)}`} 
              className="text-decoration-none me-2"
              title={node.urlObj.url}
            >
              {node.name}
            </a>
            <div className="ms-auto">
              <Badge 
                bg={getStatusBadgeVariant(node.urlObj.http_status_code)} 
                className="me-1"
              >
                {node.urlObj.http_status_code || 'N/A'}
              </Badge>
              {node.urlObj.content_type && (
                <Badge bg="info" className="me-1">
                  {node.urlObj.content_type}
                </Badge>
              )}
            </div>
          </div>
        ) : (
          // Folder node
          <div 
            className="tree-node d-flex align-items-center mb-1 sitemap-folder" 
            onClick={() => hasChildren && toggleNode(nodeKey)}
            style={{ cursor: hasChildren ? 'pointer' : 'default' }}
          >
            <i 
              className={`fas ${isExpanded ? 'fa-folder-open' : 'fa-folder'} text-warning me-2`}
            ></i>
            <span className="fw-bold">{node.name}</span>
            {hasChildren && (
              <i 
                className={`fas ${isExpanded ? 'fa-chevron-down' : 'fa-chevron-right'} ms-2 text-muted`}
                style={{ fontSize: '0.8rem' }}
              ></i>
            )}
          </div>
        )}
        
        {/* Render children if expanded */}
        {hasChildren && (isExpanded || node.type === 'file') && (
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
          .map(([key, node]) => renderTreeNode(key, node))
        }
      </ul>
    </div>
  );
};

export default SitemapTree;