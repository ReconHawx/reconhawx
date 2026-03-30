import React from 'react';
import {
  Card,
  Form,
  Alert
} from 'react-bootstrap';

function ProgramAssetSelector({
  assetType = '',
  filter = '',
  filterType = '',
  limit = 100,
  minSimilarityPercent = '',
  onMinSimilarityPercentChange,
  onAssetTypeChange,
  onFilterChange,
  onFilterTypeChange,
  onLimitChange,
  onAssetAndFilterChange
}) {
  // Base asset type (without :filter suffix) for conditional UI
  const baseAssetType = assetType && typeof assetType === 'string' && assetType.includes(':')
    ? assetType.split(':')[0]
    : assetType;
  const isTyposquatDomainInput = baseAssetType === 'typosquat_domain' || baseAssetType === 'typosquat_apex_domain';

  // Calculate the current dropdown value based on assetType and filterType
  const getCurrentValue = () => {
    if (!assetType) return '';
    if (filterType) {
      return `${assetType}:${filterType}`;
    }
    return assetType;
  };

  // Filter validation function (same as in VisualWorkflowBuilder)
  const isValidFilterExpression = (filterExpression) => {
    if (!filterExpression || !filterExpression.trim()) {
      return true; // Empty is valid (no filter)
    }

    // Split by operators (case-insensitive, with spaces)
    // Pattern matches ' and ' or ' or ' (case-insensitive, with spaces)
    const operatorPattern = /\s+(and|or)\s+/gi;
    const parts = filterExpression.split(operatorPattern);
    
    // Filter out empty strings and operators
    const filters = parts.filter(part => part && part.trim() && !/^(and|or)$/i.test(part.trim()));
    const operators = parts.filter(part => part && /^(and|or)$/i.test(part.trim()));
    
    // Validate that we have filters and proper operator placement
    if (filters.length === 0) {
      return false; // No filters found
    }
    
    // With N filters, we should have N-1 operators
    if (filters.length > 1 && operators.length !== filters.length - 1) {
      return false; // Mismatch between filters and operators
    }
    
    // Validate each individual filter condition
    for (const filter of filters) {
      const trimmedFilter = filter.trim();
      
      // Check basic syntax: property.operation:value
      const parts = trimmedFilter.split(':');
      if (parts.length !== 2) {
        return false;
      }

      const propertyOperation = parts[0].trim();
      const value = parts[1].trim();

      if (!propertyOperation || !value) {
        return false;
      }

      // Check property.operation format
      const propParts = propertyOperation.split('.');
      if (propParts.length !== 2) {
        return false;
      }

      const property = propParts[0].trim();
      const operation = propParts[1].trim();

      if (!property || !operation) {
        return false;
      }

      // Check if operation is valid
      const validOperations = [
        'contains', 'startswith', 'endswith', 'equals',
        'regex', 'in', 'not_contains', 'not_equals'
      ];

      if (!validOperations.includes(operation)) {
        return false;
      }
    }

    return true;
  };

  const getFilterExamples = (selectedAssetType) => {
    switch (selectedAssetType) {
      case 'apex-domain':
        return [
          { example: 'name.contains:example', description: 'Apex domains containing "example"' },
          { example: 'name.equals:example.com', description: 'Specific apex domain' },
          { example: 'name.endswith:.com', description: '.com domains only' }
        ];
      case 'subdomain':
        return [
          { example: 'name.contains:admin', description: 'Subdomains containing "admin"' },
          { example: 'name.startswith:www', description: 'Subdomains starting with "www"' },
          { example: 'name.regex:^api\\.', description: 'Subdomains starting with "api."' },
          { example: 'apex_domain.equals:example.com', description: 'Specific apex domain' }
        ];
      case 'ip':
        return [
          { example: 'ip.startswith:192.168', description: 'IPs in 192.168.x.x range' },
          { example: 'ptr.contains:example.com', description: 'IPs with PTR records containing domain' },
          { example: 'service_provider.equals:AWS', description: 'IPs from specific provider' }
        ];
      case 'cidr':
        return [
          { example: 'cidr.startswith:10.0', description: 'CIDR blocks starting with "10.0"' },
          { example: 'cidr.contains:/24', description: '/24 subnet masks' }
        ];
      case 'url':
        return [
          { example: 'port.equals:443', description: 'HTTPS URLs (port 443)' },
          { example: 'scheme.equals:https', description: 'HTTPS URLs only' },
          { example: 'http_status_code.equals:200', description: 'Successful responses' },
          { example: 'title.contains:login', description: 'Pages with "login" in title' },
          { example: 'content_type.contains:json', description: 'JSON API endpoints' }
        ];
      case 'typosquat_url':
        return [
          { example: 'url.contains:login', description: 'URLs containing "login"' },
          { example: 'http_status_code.equals:200', description: 'Active typosquat URLs (HTTP 200)' },
          { example: 'protocol.equals:https', description: 'HTTPS typosquat URLs only' },
          { example: 'technologies.contains:WordPress', description: 'Sites running WordPress' },
          { example: 'hostname.startswith:www', description: 'URLs starting with "www"' }
        ];
      case 'typosquat_domain':
        return [
          { example: 'typo_domain.contains:example', description: 'Domains containing "example"' },
          { example: 'typo_domain.startswith:www', description: 'Domains starting with "www"' },
          { example: 'status.equals:new', description: 'New typosquat domains only' },
          { example: 'risk_score.gte:60', description: 'High risk domains (score >= 60)' },
          { example: 'domain_registered.equals:true', description: 'Registered domains only' },
          { example: 'typo_domain.equals:example.com', description: 'Domains matching typo domain' }
        ];
      case 'typosquat_apex_domain':
        return [
          { example: 'typo_domain.contains:example', description: 'Apex domains containing "example"' },
          { example: 'typo_domain.startswith:www', description: 'Apex domains starting with "www"' },
          { example: 'status.equals:new', description: 'New typosquat apex domains only' },
          { example: 'risk_score.gte:60', description: 'High risk apex domains (score >= 60)' },
          { example: 'domain_registered.equals:true', description: 'Registered apex domains only' }
        ];
      case 'external_link':
        return [
          { example: 'url.contains:google', description: 'External links containing "google"' },
          { example: 'url.startswith:https://', description: 'HTTPS external links only' },
          { example: 'url.endswith:.com', description: '.com external links only' },
          { example: 'url.regex:.*example.*', description: 'External links matching regex pattern' },
          { example: 'source_url.contains:admin', description: 'Links found on pages containing "admin"' },
          { example: 'url.contains:facebook and source_url.contains:dummy', description: 'Multiple filters with AND operator' }
        ];
      default:
        return [];
    }
  };

  return (
    <Card>
      <Card.Header>
        <h6 className="mb-0">🏢 Program Asset Configuration</h6>
      </Card.Header>
      <Card.Body>
        <Alert variant="info" className="mb-3">
          <small>
            Select a program asset type and optionally apply filters to limit the input data.
          </small>
        </Alert>

        <Form.Group className="mb-3">
          <Form.Label>Asset Type *</Form.Label>
          <Form.Select
            value={getCurrentValue()}
            onChange={(e) => {
              const selectedValue = e.target.value;
              if (selectedValue.includes(':')) {
                // Handle combined asset type and filter type
                const [type, filter] = selectedValue.split(':');

                // Use atomic update if available, otherwise fall back to separate calls
                if (onAssetAndFilterChange) {
                  onAssetAndFilterChange(type, filter);
                } else {
                  onAssetTypeChange(type);
                  if (onFilterTypeChange) {
                    onFilterTypeChange(filter);
                  }
                }
              } else {
                // Handle regular asset type
                if (onAssetAndFilterChange) {
                  onAssetAndFilterChange(selectedValue, '');
                } else {
                  onAssetTypeChange(selectedValue);
                  if (onFilterTypeChange) {
                    onFilterTypeChange('');
                  }
                }
              }
            }}
            required
          >
            <option value="">Choose asset type...</option>
            <optgroup label="Program Assets">
              <option value="apex-domain">Apex Domain</option>
              <option value="subdomain">Subdomains (All)</option>
              <option value="subdomain:resolved">Subdomains (Resolved)</option>
              <option value="subdomain:unresolved">Subdomains (Unresolved)</option>
              <option value="ip">IP Addresses (All)</option>
              <option value="ip:resolved">IP Addresses (Resolved)</option>
              <option value="ip:unresolved">IP Addresses (Unresolved)</option>
              <option value="cidr">CIDR Block</option>
              <option value="url">URLs (All)</option>
              <option value="url:root">URLs (Root Only)</option>
            </optgroup>
            <optgroup label="Program Findings">
              <option value="typosquat_url">Typosquat URLs (All)</option>
              <option value="typosquat_url:root">Typosquat URLs (Root Only)</option>
              <option value="typosquat_domain">Typosquat Domains</option>
              <option value="typosquat_apex_domain">Typosquat Apex Domains</option>
              <option value="external_link">External Links</option>
            </optgroup>
          </Form.Select>
        </Form.Group>

        {assetType && (
          <>
            <Form.Group className="mb-3">
              <Form.Label>Filter Expression (Optional)</Form.Label>
              <Form.Control
                type="text"
                value={filter}
                onChange={(e) => onFilterChange(e.target.value)}
                placeholder="e.g., port.equals:443"
                isInvalid={filter && !isValidFilterExpression(filter)}
              />
              {filter && !isValidFilterExpression(filter) && (
                <Form.Control.Feedback type="invalid">
                  Invalid filter syntax. Expected format: property.operation:value (use 'and' or 'or' to combine multiple filters)
                </Form.Control.Feedback>
              )}
              {filter && isValidFilterExpression(filter) && (
                <Form.Control.Feedback type="valid">
                  ✓ Valid filter expression
                </Form.Control.Feedback>
              )}
              <Form.Text className="text-muted">
                <div className="mt-2">
                  <strong>Syntax:</strong> <code>property.operation:value</code>
                </div>
                <div className="mt-1">
                  <strong>Operations:</strong> contains, startswith, endswith, equals, regex, in, not_contains, not_equals
                </div>
                <div className="mt-1">
                  <strong>Multiple filters:</strong> Use <code> and </code> or <code> or </code> to combine filters (e.g., <code>url.contains:facebook and source_url.contains:dummy</code>)
                </div>
                {getFilterExamples(assetType).length > 0 && (
                  <div className="mt-2">
                    <strong>Examples for {assetType}:</strong>
                    <div className="mt-1">
                      {getFilterExamples(assetType).map((example, index) => (
                        <div key={index}>
                          <small>• <code>{example.example}</code> - {example.description}</small>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Form.Text>
            </Form.Group>

            <Form.Group className="mb-3">
              <Form.Label>Limit *</Form.Label>
              <Form.Control
                type="number"
                value={limit}
                onChange={(e) => onLimitChange(parseInt(e.target.value) || 100)}
                min="1"
                max="10000"
                required
              />
              <Form.Text className="text-muted">
                Maximum number of assets to include (1-10000)
              </Form.Text>
            </Form.Group>

            {isTyposquatDomainInput && onMinSimilarityPercentChange && (
              <Form.Group className="mb-3">
                <Form.Label>Minimum similarity with protected domain (%)</Form.Label>
                <Form.Control
                  type="number"
                  value={minSimilarityPercent}
                  onChange={(e) => {
                    const v = e.target.value;
                    onMinSimilarityPercentChange(v === '' ? '' : v);
                  }}
                  placeholder="e.g. 90"
                  min="0"
                  max="100"
                />
                <Form.Text className="text-muted">
                  Only include typosquat domains with at least this similarity to a protected domain (0-100). Leave empty for no filter.
                </Form.Text>
              </Form.Group>
            )}

            {assetType && (
              <Alert variant="success">
                <strong>Configuration Summary:</strong>
                <br />
                <strong>Asset Type:</strong> {assetType}
                {filterType && (
                  <>
                    <br />
                    <strong>Filter:</strong> {filterType === 'resolved' ? 'Resolved only' : 
                                            filterType === 'unresolved' ? 'Unresolved only' : 
                                            filterType === 'root' ? 'Root URLs only' : filterType}
                  </>
                )}
                {filter && (
                  <>
                    <br />
                    <strong>Custom Filter:</strong> {filter}
                  </>
                )}
                {isTyposquatDomainInput && minSimilarityPercent !== '' && minSimilarityPercent != null && (
                  <>
                    <br />
                    <strong>Min. similarity:</strong> {minSimilarityPercent}%
                  </>
                )}
                <br />
                <strong>Limit:</strong> {limit} items
              </Alert>
            )}
          </>
        )}
      </Card.Body>
    </Card>
  );
}

export default ProgramAssetSelector;
