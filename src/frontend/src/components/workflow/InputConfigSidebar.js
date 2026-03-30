import React from 'react';
import { Form, Button, Badge, Card, ListGroup, Alert } from 'react-bootstrap';
import ProgramAssetSelector from './ProgramAssetSelector';
import './InputConfigSidebar.css';

function InputConfigSidebar({
  isOpen,
  onClose,
  currentInputs,
  setCurrentInputs,
  editingInput,
  setEditingInput,
  handleAddInput,
  handleUpdateInput,
  handleSaveEditingInput,
  handleRemoveInput,
  handleAssetTypeAndFilterChange,
  handleFindingTypeAndFilterChange,
  handleSaveInputs,
  eventHandlerMode,
}) {
  const getBadgeLabel = (config) => {
    if (config.type === 'direct') return `Direct: ${config.value_type}`;
    if (config.type === 'program_protected_domains') return 'Program Protected Domains';
    if (config.type === 'program_scope_domains') return 'Program Scope Domains';
    if (config.type === 'program_finding') {
      const base = config.filter_type
        ? `Program Finding: ${config.finding_type} (${config.filter_type === 'root' ? 'Root Only' : config.filter_type})`
        : `Program Finding: ${config.finding_type}`;
      return config.min_similarity_percent != null ? `${base} ≥${config.min_similarity_percent}%` : base;
    }
    if (config.filter_type) {
      return `Program Asset: ${config.asset_type} (${config.filter_type === 'resolved' ? 'Resolved' : config.filter_type === 'unresolved' ? 'Unresolved' : config.filter_type === 'root' ? 'Root Only' : config.filter_type})`;
    }
    return `Program Asset: ${config.asset_type}`;
  };

  return (
    <>
      <div className={`input-config-sidebar-overlay ${isOpen ? 'open' : ''}`} onClick={onClose} aria-hidden="true" />
      <div className={`input-config-sidebar ${isOpen ? 'open' : ''}`}>
        <div className="input-config-sidebar-header">
          <h6 className="mb-0">Configure Inputs</h6>
          <Button variant="link" size="sm" className="p-0 text-muted" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </div>
        <div className="input-config-sidebar-body">
          <Alert variant="info" className="small py-2">
            Define data sources for your workflow.
            {eventHandlerMode && (
              <><br />Use template variables for batched event data, e.g. {'{domain_list_array}'}, {'{ip_list_array}'}, or {'{url_list_array}'}.</>
            )}
          </Alert>

          {editingInput ? (
            <Card className="mb-3">
              <Card.Header className="py-2">
                <small>{editingInput.id.startsWith('new_') ? 'Add Input' : `Edit: ${editingInput.name}`}</small>
              </Card.Header>
              <Card.Body className="py-2">
                <Form.Group className="mb-2">
                  <Form.Label className="small">Name</Form.Label>
                  <Form.Control
                    size="sm"
                    type="text"
                    value={editingInput.name}
                    onChange={(e) => handleUpdateInput(editingInput.id, 'name', e.target.value.replace(/\s/g, '_'))}
                    placeholder="e.g., program_domains"
                  />
                </Form.Group>
                <Form.Group className="mb-2">
                  <Form.Label className="small">Type</Form.Label>
                  <Form.Select
                    size="sm"
                    value={eventHandlerMode ? 'direct' : (editingInput.type || 'program_asset')}
                    onChange={(e) => !eventHandlerMode && handleUpdateInput(editingInput.id, 'type', e.target.value)}
                    disabled={eventHandlerMode}
                  >
                    <option value="program_asset">Program Asset</option>
                    <option value="direct">Direct Input</option>
                    <option value="program_finding">Program Finding</option>
                    <option value="program_protected_domains">Program Protected Domains</option>
                    <option value="program_scope_domains">Program Scope Domains</option>
                  </Form.Select>
                  {!eventHandlerMode && (
                    <Form.Text className="text-muted small">
                      Switch between program data and direct input at any time.
                    </Form.Text>
                  )}
                </Form.Group>

                {editingInput.type === 'program_asset' && !eventHandlerMode && (
                  <div className="mt-2">
                    <ProgramAssetSelector
                      assetType={editingInput.asset_type || ''}
                      filter={editingInput.filter || ''}
                      filterType={editingInput.filter_type || ''}
                      limit={editingInput.limit || 100}
                      onAssetTypeChange={(assetType) => {
                        if (assetType === 'typosquat_url' || assetType === 'external_link') {
                          const updated = { ...editingInput, type: 'program_finding', finding_type: assetType };
                          delete updated.asset_type;
                          setEditingInput(updated);
                        } else {
                          handleUpdateInput(editingInput.id, 'asset_type', assetType);
                        }
                      }}
                      onFilterChange={(filter) => handleUpdateInput(editingInput.id, 'filter', filter)}
                      onFilterTypeChange={(filterType) => handleUpdateInput(editingInput.id, 'filter_type', filterType)}
                      onLimitChange={(limit) => handleUpdateInput(editingInput.id, 'limit', limit)}
                      onAssetAndFilterChange={handleAssetTypeAndFilterChange}
                    />
                  </div>
                )}

                {editingInput.type === 'program_protected_domains' && !eventHandlerMode && (
                  <Alert variant="info" className="small py-2 mt-2">Protected domains. No extra config.</Alert>
                )}
                {editingInput.type === 'program_scope_domains' && !eventHandlerMode && (
                  <Alert variant="info" className="small py-2 mt-2">Scope domains. No extra config.</Alert>
                )}

                {editingInput.type === 'program_finding' && !eventHandlerMode && (
                  <div className="mt-2">
                    <ProgramAssetSelector
                      assetType={editingInput.finding_type || 'typosquat_url'}
                      filter={editingInput.filter || ''}
                      filterType={editingInput.filter_type || ''}
                      limit={editingInput.limit || 100}
                      minSimilarityPercent={editingInput.min_similarity_percent != null ? editingInput.min_similarity_percent : ''}
                      onMinSimilarityPercentChange={(v) => handleUpdateInput(editingInput.id, 'min_similarity_percent', v === '' ? undefined : Number(v))}
                      onAssetTypeChange={(findingType) => handleUpdateInput(editingInput.id, 'finding_type', findingType)}
                      onFilterChange={(filter) => handleUpdateInput(editingInput.id, 'filter', filter)}
                      onFilterTypeChange={(filterType) => handleUpdateInput(editingInput.id, 'filter_type', filterType)}
                      onLimitChange={(limit) => handleUpdateInput(editingInput.id, 'limit', limit)}
                      onAssetAndFilterChange={handleFindingTypeAndFilterChange}
                    />
                  </div>
                )}

                {(editingInput.type === 'direct' || eventHandlerMode) && (
                  <>
                    <Form.Group className="mb-2">
                      <Form.Label className="small">Value Type</Form.Label>
                      <Form.Select
                        size="sm"
                        value={editingInput.value_type}
                        onChange={(e) => handleUpdateInput(editingInput.id, 'value_type', e.target.value)}
                      >
                        <option value="domains">Domains</option>
                        <option value="ips">IPs</option>
                        <option value="urls">URLs</option>
                        <option value="cidrs">CIDRs</option>
                        <option value="strings">Strings</option>
                      </Form.Select>
                    </Form.Group>
                    {(eventHandlerMode || typeof editingInput.values === 'string') ? (
                      <Form.Group className="mb-2">
                        <Form.Label className="small">Event Template</Form.Label>
                        <Form.Control
                          size="sm"
                          type="text"
                          value={typeof editingInput.values === 'string' ? editingInput.values : ''}
                          onChange={(e) => handleUpdateInput(editingInput.id, 'values', e.target.value)}
                          placeholder="{domain_list_array}"
                        />
                        {!eventHandlerMode && (
                          <Button variant="link" size="sm" className="p-0 mt-1" onClick={() => handleUpdateInput(editingInput.id, 'values', [])}>
                            Switch to literal values
                          </Button>
                        )}
                      </Form.Group>
                    ) : (
                      <Form.Group className="mb-2">
                        <Form.Label className="small">Values (one per line)</Form.Label>
                        <Form.Control
                          size="sm"
                          as="textarea"
                          rows={4}
                          value={Array.isArray(editingInput.values) ? editingInput.values.join('\n') : ''}
                          onChange={(e) => {
                            const lines = e.target.value.split('\n').map(v => v.trim());
                            handleUpdateInput(editingInput.id, 'values', lines);
                          }}
                          placeholder="example.com&#10;test.com"
                        />
                        <Button variant="link" size="sm" className="p-0 mt-1" onClick={() => handleUpdateInput(editingInput.id, 'values', '')}>
                          Switch to event template
                        </Button>
                      </Form.Group>
                    )}
                  </>
                )}

                <div className="d-flex justify-content-end gap-1 mt-2">
                  <Button variant="secondary" size="sm" onClick={() => setEditingInput(null)}>Cancel</Button>
                  <Button variant="primary" size="sm" onClick={handleSaveEditingInput}>Save</Button>
                </div>
              </Card.Body>
            </Card>
          ) : (
            <Button variant="success" size="sm" className="mb-3 w-100" onClick={handleAddInput}>
              + Add Input
            </Button>
          )}

          <ListGroup variant="flush">
            {Object.entries(currentInputs).map(([name, config]) => (
              <ListGroup.Item key={name} className="py-2 px-2">
                <div className="d-flex justify-content-between align-items-center">
                  <div className="small">
                    <strong>{name}</strong>
                    <Badge
                      bg={config.type === 'direct' ? 'warning' : config.type === 'program_finding' ? 'danger' : config.type === 'program_protected_domains' || config.type === 'program_scope_domains' ? 'secondary' : 'info'}
                      className="ms-1"
                      text={config.type === 'direct' ? 'dark' : 'white'}
                    >
                      {getBadgeLabel(config)}
                    </Badge>
                  </div>
                  <div>
                    <Button variant="outline-primary" size="sm" className="py-0 px-1 me-1" onClick={() => setEditingInput({ id: name, name, ...config })} title="Edit">✏️</Button>
                    <Button variant="outline-danger" size="sm" className="py-0 px-1" onClick={() => handleRemoveInput(name)} title="Remove">🗑️</Button>
                  </div>
                </div>
              </ListGroup.Item>
            ))}
          </ListGroup>
        </div>
        <div className="input-config-sidebar-footer">
          <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
          <Button variant="primary" size="sm" onClick={handleSaveInputs}>Apply</Button>
        </div>
      </div>
    </>
  );
}

export default InputConfigSidebar;
