import React, { useState, useEffect } from 'react';
import { Form, Button, Modal, Tree, ListGroup, Badge, Spinner, Alert } from 'react-bootstrap';
import { nucleiTemplatesAPI } from '../services/api';

const TemplateBrowser = ({ show, onHide, onSelectTemplates, selectedTemplates = [] }) => {
  const [tree, setTree] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [activeTab, setActiveTab] = useState('tree'); // 'tree' or 'search'
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [selectedItems, setSelectedItems] = useState(new Set(selectedTemplates.map(t => t.id || t.path)));

  useEffect(() => {
    if (show) {
      loadTree();
    }
  }, [show]);

  useEffect(() => {
    if (searchQuery.trim()) {
      const timeoutId = setTimeout(() => {
        performSearch();
      }, 300);
      return () => clearTimeout(timeoutId);
    } else {
      setSearchResults([]);
    }
  }, [searchQuery]);

  const loadTree = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await nucleiTemplatesAPI.getOfficialTemplatesTree();
      setTree(response.tree);
    } catch (err) {
      setError('Failed to load template tree: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const performSearch = async () => {
    if (!searchQuery.trim()) return;
    
    setSearching(true);
    try {
      const response = await nucleiTemplatesAPI.searchOfficialTemplates(searchQuery, 100);
      setSearchResults(response.templates || []);
    } catch (err) {
      setError('Search failed: ' + err.message);
    } finally {
      setSearching(false);
    }
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

  const toggleSelection = (item) => {
    const newSelected = new Set(selectedItems);
    const itemId = item.id || item.path;
    
    if (newSelected.has(itemId)) {
      newSelected.delete(itemId);
    } else {
      newSelected.add(itemId);
    }
    setSelectedItems(newSelected);
  };

  const renderTreeNode = (node, level = 0) => {
    const isExpanded = expandedNodes.has(node.path);
    const isSelected = selectedItems.has(node.id || node.path);
    
    if (node.type === 'folder') {
      return (
        <div key={node.path} style={{ marginLeft: level * 20 }}>
          <div 
            className="d-flex align-items-center p-1 cursor-pointer"
            onClick={() => toggleNode(node.path)}
            style={{ cursor: 'pointer' }}
          >
            <span className="me-2">
              {isExpanded ? '📂' : '📁'}
            </span>
            <span className="flex-grow-1">{node.name}</span>
            <Badge bg="secondary">{node.template_count}</Badge>
          </div>
          {isExpanded && node.children && (
            <div>
              {node.children.map(child => renderTreeNode(child, level + 1))}
            </div>
          )}
        </div>
      );
    } else if (node.type === 'file') {
      const template = node.template;
      return (
        <div key={node.path} style={{ marginLeft: level * 20 }}>
          <div 
            className={`d-flex align-items-center p-1 ${isSelected ? 'bg-primary text-white' : ''}`}
            onClick={() => toggleSelection(template)}
            style={{ cursor: 'pointer' }}
          >
            <Form.Check
              type="checkbox"
              checked={isSelected}
              onChange={() => toggleSelection(template)}
              onClick={(e) => e.stopPropagation()}
              className="me-2"
            />
            <span className="me-2">📄</span>
            <div className="flex-grow-1">
              <div className="fw-bold">{template.name}</div>
              <small className="text-muted">{template.description}</small>
            </div>
            <Badge bg={getSeverityColor(template.severity)}>{template.severity}</Badge>
          </div>
        </div>
      );
    }
    return null;
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

  const handleConfirm = () => {
    const selectedTemplatesList = [];
    
    // Get selected templates from tree
    const collectSelected = (node) => {
      if (node.type === 'file' && selectedItems.has(node.template.id || node.path)) {
        selectedTemplatesList.push({
          id: node.template.id,
          name: node.template.name,
          path: node.path,
          severity: node.template.severity,
          description: node.template.description,
          tags: node.template.tags || []
        });
      }
      if (node.children) {
        node.children.forEach(collectSelected);
      }
    };
    
    if (tree) {
      collectSelected(tree);
    }
    
    // Add selected templates from search results
    searchResults.forEach(template => {
      if (selectedItems.has(template.id || template.path)) {
        selectedTemplatesList.push({
          id: template.id,
          name: template.name,
          path: template.path,
          severity: template.severity,
          description: template.description,
          tags: template.tags || []
        });
      }
    });
    
    onSelectTemplates(selectedTemplatesList);
    onHide();
  };

  const handleSelectAll = () => {
    const allItems = new Set();
    
    // Collect all template IDs from tree
    const collectIds = (node) => {
      if (node.type === 'file') {
        allItems.add(node.template.id || node.path);
      }
      if (node.children) {
        node.children.forEach(collectIds);
      }
    };
    
    if (tree) {
      collectIds(tree);
    }
    
    // Add search result IDs
    searchResults.forEach(template => {
      allItems.add(template.id || template.path);
    });
    
    setSelectedItems(allItems);
  };

  const handleClearSelection = () => {
    setSelectedItems(new Set());
  };

  return (
    <Modal show={show} onHide={onHide} size="xl" dialogClassName="template-browser-modal">
      <Modal.Header closeButton>
        <Modal.Title>🎯 Nuclei Templates Browser</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        {error && (
          <Alert variant="danger" dismissible onClose={() => setError(null)}>
            {error}
          </Alert>
        )}
        
        <div className="mb-3">
          <div className="d-flex justify-content-between align-items-center mb-2">
            <div>
              <Button
                variant={activeTab === 'tree' ? 'primary' : 'outline-primary'}
                size="sm"
                onClick={() => setActiveTab('tree')}
                className="me-2"
              >
                📁 Folder Tree
              </Button>
              <Button
                variant={activeTab === 'search' ? 'primary' : 'outline-primary'}
                size="sm"
                onClick={() => setActiveTab('search')}
              >
                🔍 Search
              </Button>
            </div>
            <div>
              <Button variant="outline-secondary" size="sm" onClick={handleSelectAll} className="me-2">
                Select All
              </Button>
              <Button variant="outline-secondary" size="sm" onClick={handleClearSelection}>
                Clear
              </Button>
            </div>
          </div>
          
          {activeTab === 'search' && (
            <Form.Control
              type="text"
              placeholder="Search templates by name, description, or tags..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="mb-3"
            />
          )}
        </div>

        <div style={{ height: '400px', overflowY: 'auto' }}>
          {activeTab === 'tree' && (
            <div>
              {loading ? (
                <div className="text-center p-4">
                  <Spinner animation="border" />
                  <div className="mt-2">Loading template tree...</div>
                </div>
              ) : tree ? (
                <div>
                  {renderTreeNode(tree)}
                </div>
              ) : (
                <div className="text-center p-4 text-muted">
                  No template tree available
                </div>
              )}
            </div>
          )}
          
          {activeTab === 'search' && (
            <div>
              {searching ? (
                <div className="text-center p-4">
                  <Spinner animation="border" />
                  <div className="mt-2">Searching...</div>
                </div>
              ) : searchResults.length > 0 ? (
                <ListGroup>
                  {searchResults.map(template => {
                    const isSelected = selectedItems.has(template.id || template.path);
                    return (
                      <ListGroup.Item
                        key={template.id || template.path}
                        className={`d-flex align-items-center ${isSelected ? 'bg-primary text-white' : ''}`}
                        onClick={() => toggleSelection(template)}
                        style={{ cursor: 'pointer' }}
                      >
                        <Form.Check
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelection(template)}
                          onClick={(e) => e.stopPropagation()}
                          className="me-3"
                        />
                        <div className="flex-grow-1">
                          <div className="fw-bold">{template.name}</div>
                          <small className={isSelected ? 'text-light' : 'text-muted'}>
                            {template.description}
                          </small>
                          <div className="mt-1">
                            {template.tags?.map(tag => (
                              <Badge key={tag} bg="light" text="dark" className="me-1">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        </div>
                        <Badge bg={getSeverityColor(template.severity)}>
                          {template.severity}
                        </Badge>
                      </ListGroup.Item>
                    );
                  })}
                </ListGroup>
              ) : searchQuery ? (
                <div className="text-center p-4 text-muted">
                  No templates found for "{searchQuery}"
                </div>
              ) : (
                <div className="text-center p-4 text-muted">
                  Enter a search query to find templates
                </div>
              )}
            </div>
          )}
        </div>
        
        <div className="mt-3">
          <small className="text-muted">
            Selected: {selectedItems.size} templates
          </small>
        </div>
      </Modal.Body>
      <Modal.Footer>
        <Button variant="secondary" onClick={onHide}>
          Cancel
        </Button>
        <Button variant="primary" onClick={handleConfirm}>
          Add Selected Templates ({selectedItems.size})
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default TemplateBrowser; 