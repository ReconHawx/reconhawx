import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Button,
  Spinner,
  ListGroup,
  Badge
} from 'react-bootstrap';
import { nucleiTemplatesAPI } from '../../services/api';

function NucleiTemplateSelector({
  selectedOfficialTemplates = new Set(),
  selectedCustomTemplates = [],
  onOfficialTemplatesChange,
  onCustomTemplatesChange
}) {
  // Nuclei templates state
  const [nucleiTemplates, setNucleiTemplates] = useState([]);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [treeSearchTerm, setTreeSearchTerm] = useState('');

  // Nuclei templates functions
  const loadNucleiTemplates = useCallback(async () => {
    try {
      const response = await nucleiTemplatesAPI.list(0, 100, true);
      if (response && response.templates && Array.isArray(response.templates)) {
        const templates = response.templates.map(template => ({
          id: template.id,
          name: template.name || template.id,
          severity: template.severity || 'info',
          category: template.tags && template.tags.includes('custom') ? 'custom' : 'builtin',
          description: template.description,
          tags: template.tags || []
        }));
        setNucleiTemplates(templates);
      }
    } catch (err) {
      console.error('Failed to load nuclei templates:', err);
    }
  }, []);

  // Load nuclei templates on component mount
  useEffect(() => {
    loadNucleiTemplates();
  }, [loadNucleiTemplates]);

  const loadTree = async () => {
    setTreeLoading(true);
    try {
      const response = await nucleiTemplatesAPI.getOfficialTemplatesTree();
      // The API returns the tree structure directly, not wrapped in a 'tree' property
      setTree(response.children || []);
    } catch (err) {
      console.error('Failed to load template tree:', err);
    } finally {
      setTreeLoading(false);
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity?.toLowerCase()) {
      case 'critical': return 'danger';
      case 'high': return 'warning';
      case 'medium': return 'info';
      case 'low': return 'secondary';
      default: return 'light';
    }
  };

  const filterTreeNode = (node, searchTerm) => {
    if (!searchTerm) return true;

    const searchLower = searchTerm.toLowerCase();

    if (node.name && node.name.toLowerCase().includes(searchLower)) {
      return true;
    }

    if (node.type === 'file' && node.template) {
      const template = node.template;
      if ((template.name && template.name.toLowerCase().includes(searchLower)) ||
          (template.description && template.description.toLowerCase().includes(searchLower)) ||
          (template.id && template.id.toLowerCase().includes(searchLower))) {
        return true;
      }
    }

    if (node.children) {
      return node.children.some(child => filterTreeNode(child, searchTerm));
    }

    return false;
  };

  const collectAllNodePaths = (node, pathSet, level = 0) => {
    if (node.type === 'directory') {
      const nodePath = node.path || `${node.name}-${level}`;
      pathSet.add(nodePath);
      if (node.children) {
        node.children.forEach(child => collectAllNodePaths(child, pathSet, level + 1));
      }
    }
  };

  const expandAllNodes = () => {
    const allPaths = new Set();
    if (tree) {
      if (Array.isArray(tree)) {
        tree.forEach(node => collectAllNodePaths(node, allPaths, 0));
      } else {
        collectAllNodePaths(tree, allPaths, 0);
      }
    }
    setExpandedNodes(allPaths);
  };

  const collapseAllNodes = () => {
    setExpandedNodes(new Set());
  };

  const toggleNode = (nodePath) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(nodePath)) {
      newExpanded.delete(nodePath);
    } else {
      newExpanded.add(nodePath);
    }
    setExpandedNodes(newExpanded);
  };

  const toggleTreeTemplateSelection = (node, fullPath = '') => {
    const newSelected = new Set(selectedOfficialTemplates);

    if (node.type === 'file') {
      // For files, use the full path to the template
      const templatePath = fullPath ? `${fullPath}/${node.name}` : node.name;

      if (newSelected.has(templatePath)) {
        newSelected.delete(templatePath);
      } else {
        newSelected.add(templatePath);
      }
    } else if (node.type === 'directory') {
      // For directories, toggle ONLY the directory path itself
      const directoryPath = fullPath ? `${fullPath}/${node.name}` : node.name;
      if (newSelected.has(directoryPath)) {
        newSelected.delete(directoryPath);
      } else {
        newSelected.add(directoryPath);
      }
    }

    onOfficialTemplatesChange(newSelected);
  };

  const renderTreeNode = (node, level = 0, fullPath = '') => {
    // Generate a path for the node based on its position in the tree
    const nodePath = node.path || `${node.name}-${level}`;
    const isExpanded = expandedNodes.has(nodePath);

    if (!filterTreeNode(node, treeSearchTerm)) {
      return null;
    }

    if (node.type === 'directory') {
      // Calculate template count for directories
      const templateCount = node.children ? node.children.filter(child => child.type === 'file').length : 0;

      // Folder selection logic: selecting a folder stores ONLY the folder path
      const directoryPath = fullPath ? `${fullPath}/${node.name}` : node.name;
      const isFolderSelected = selectedOfficialTemplates.has(directoryPath);

      // Determine if any descendant (file or folder) is selected
      const isAnyDescendantSelected = (dirNode, currentPath) => {
        if (!dirNode.children) return false;
        for (const child of dirNode.children) {
          if (child.type === 'file') {
            const childPath = `${currentPath}/${child.name}`;
            if (selectedOfficialTemplates.has(childPath)) return true;
          } else if (child.type === 'directory') {
            const childDirPath = `${currentPath}/${child.name}`;
            if (selectedOfficialTemplates.has(childDirPath)) return true;
            if (isAnyDescendantSelected(child, childDirPath)) return true;
          }
        }
        return false;
      };
      const descendantSelected = isAnyDescendantSelected(node, directoryPath);

      return (
        <div key={nodePath} style={{ marginLeft: level * 20 }}>
          <div
            className="d-flex align-items-center p-1"
            style={{ cursor: 'pointer' }}
          >
            <Form.Check
              type="checkbox"
              checked={isFolderSelected}
              ref={(el) => {
                if (el) {
                  el.indeterminate = !isFolderSelected && descendantSelected;
                }
              }}
              onChange={(e) => {
                e.stopPropagation();
                toggleTreeTemplateSelection(node, fullPath);
              }}
              className="me-2"
            />
            <div
              className="d-flex align-items-center flex-grow-1"
              onClick={() => toggleNode(nodePath)}
              style={{ cursor: 'pointer' }}
            >
              <span className="me-2">
                {isExpanded ? '📂' : '📁'}
              </span>
              <span className="flex-grow-1">{node.name}</span>
              <Badge bg="secondary">{templateCount}</Badge>
            </div>
          </div>
          {isExpanded && node.children && (
            <div>
              {node.children
                .filter(child => filterTreeNode(child, treeSearchTerm))
                .map(child => renderTreeNode(child, level + 1, directoryPath))}
            </div>
          )}
        </div>
      );
    } else if (node.type === 'file') {
      const template = node.template;
      const templatePath = fullPath ? `${fullPath}/${node.name}` : node.name;
      const isSelected = selectedOfficialTemplates.has(templatePath);

      return (
        <div key={nodePath} style={{ marginLeft: level * 20 }}>
          <div
            className="d-flex align-items-center p-1"
            style={{ cursor: 'pointer' }}
          >
            <Form.Check
              type="checkbox"
              checked={isSelected}
              onChange={(e) => {
                e.stopPropagation();
                toggleTreeTemplateSelection(node, fullPath);
              }}
              className="me-2"
            />
            <div
              className="d-flex align-items-center flex-grow-1"
              onClick={() => toggleTreeTemplateSelection(node, fullPath)}
              style={{ cursor: 'pointer' }}
            >
              <span className="me-2">📄</span>
              <div className="flex-grow-1">
                <div className="fw-bold">{template.name}</div>
                <div><small className="text-primary font-monospace">{template.id}</small></div>
                <small className="text-muted">{template.description}</small>
              </div>
              <Badge bg={getSeverityColor(template.severity)}>{template.severity}</Badge>
            </div>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <Card>
      <Card.Header>
        <h6 className="mb-0">🔬 Nuclei Template Configuration</h6>
      </Card.Header>
      <Card.Body>
        {/* Official Templates Section */}
        <Form.Group className="mb-3">
          <Form.Label>Official Templates</Form.Label>
          <div className="mb-2">
            <div className="d-flex gap-2 mb-2">
              <Button
                variant="outline-primary"
                size="sm"
                onClick={loadTree}
                disabled={treeLoading}
              >
                {treeLoading ? (
                  <>
                    <Spinner animation="border" size="sm" className="me-1" />
                    Loading...
                  </>
                ) : (
                  '🌳 Browse Official Templates'
                )}
              </Button>
              <Button
                variant="outline-info"
                size="sm"
                onClick={async () => {
                  try {
                    await nucleiTemplatesAPI.updateOfficialTemplates();
                    await loadTree();
                  } catch (err) {
                    console.error('Failed to update official templates:', err);
                  }
                }}
                disabled={treeLoading}
              >
                📥 Update Repository
              </Button>
            </div>

            {/* Tree Control Buttons */}
            {tree && (
              <div className="d-flex gap-2 mb-2">
                <Button
                  variant="outline-success"
                  size="sm"
                  onClick={() => expandAllNodes()}
                  disabled={treeLoading}
                >
                  📖 Expand All
                </Button>
                <Button
                  variant="outline-warning"
                  size="sm"
                  onClick={() => collapseAllNodes()}
                  disabled={treeLoading}
                >
                  📕 Collapse All
                </Button>
              </div>
            )}

            {/* Show selected official templates */}
            {selectedOfficialTemplates.size > 0 && (
              <div className="p-2 bg-light rounded">
                <small className="text-muted">
                  <strong>Selected Official Templates:</strong>
                </small>
                <div className="mt-1">
                  {Array.from(selectedOfficialTemplates).map(templatePath => (
                    <Badge key={templatePath} bg="info" className="me-1 mb-1">
                      {templatePath}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Search Field */}
            {tree && (
              <div className="mb-2">
                <Form.Control
                  type="text"
                  placeholder="🔍 Search templates and folders..."
                  value={treeSearchTerm}
                  onChange={(e) => setTreeSearchTerm(e.target.value)}
                  size="sm"
                />
                {treeSearchTerm && (
                  <small className="text-muted">
                    Filtering results for: "{treeSearchTerm}"
                  </small>
                )}
              </div>
            )}

            {/* Tree Browser */}
            <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid #dee2e6', borderRadius: '0.375rem', padding: '10px' }}>
              {treeLoading ? (
                <div className="text-center py-4">
                  <Spinner animation="border" size="sm" />
                  <p className="mt-2 text-muted">Loading template tree...</p>
                </div>
              ) : tree ? (
                <div>
                  {Array.isArray(tree)
                    ? tree.filter(child => filterTreeNode(child, treeSearchTerm)).map(child => renderTreeNode(child, 0, ''))
                    : tree && filterTreeNode(tree, treeSearchTerm) && renderTreeNode(tree, 0, '')
                  }
                </div>
              ) : (
                <div className="text-center py-3 text-muted">
                  Click "Browse Official Templates" to load the template tree
                </div>
              )}
            </div>
          </div>
        </Form.Group>

        {/* Custom Templates Section */}
        <Form.Group className="mb-3">
          <Form.Label>Custom Templates</Form.Label>
          <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid #dee2e6', borderRadius: '0.375rem' }}>
            <ListGroup variant="flush">
              {nucleiTemplates.map(template => (
                <ListGroup.Item key={template.id} className="d-flex justify-content-between align-items-center py-2">
                  <Form.Check
                    type="checkbox"
                    id={`template-${template.id}`}
                    label={template.name}
                    checked={selectedCustomTemplates.includes(template.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        onCustomTemplatesChange([...selectedCustomTemplates, template.id]);
                      } else {
                        onCustomTemplatesChange(selectedCustomTemplates.filter(t => t !== template.id));
                      }
                    }}
                  />
                  <Badge bg={template.severity === 'high' ? 'danger' : template.severity === 'medium' ? 'warning' : 'info'}>
                    {template.severity}
                  </Badge>
                </ListGroup.Item>
              ))}
            </ListGroup>
          </div>
        </Form.Group>
      </Card.Body>
    </Card>
  );
}

export default NucleiTemplateSelector;
