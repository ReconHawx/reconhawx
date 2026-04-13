import React from 'react';
import { Table, Form, Button } from 'react-bootstrap';

/**
 * Editable table for structured program scope rows: { pattern, wildcard }.
 */
function ScopeDomainsEditor({ rows, onChange, disabled = false }) {
  const updateRow = (index, field, value) => {
    const next = rows.map((r, i) => {
      if (i !== index) return { ...r };
      if (field === 'pattern') {
        const pattern = value;
        let wildcard = r.wildcard;
        if (pattern.includes('*')) wildcard = true;
        return { pattern, wildcard };
      }
      if (field === 'wildcard') {
        return { ...r, wildcard: value };
      }
      return { ...r };
    });
    onChange(next);
  };

  const removeRow = (index) => {
    onChange(rows.filter((_, i) => i !== index));
  };

  const addRow = () => {
    onChange([...rows, { pattern: '', wildcard: false }]);
  };

  return (
    <div>
      <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
        <Table striped bordered size="sm" className="mb-2">
          <thead>
            <tr>
              <th style={{ width: '48px' }}>#</th>
              <th>Pattern</th>
              <th style={{ width: '130px' }} className="text-center">
                Wildcard
              </th>
              <th style={{ width: '88px' }} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={4} className="text-muted text-center py-3">
                  No rows yet. Click &quot;Add pattern&quot; to add one.
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={index}>
                  <td className="align-middle">{index + 1}</td>
                  <td>
                    <Form.Control
                      type="text"
                      value={row.pattern}
                      onChange={(e) => updateRow(index, 'pattern', e.target.value)}
                      disabled={disabled}
                      placeholder="e.g. example.com or *.example.com"
                      style={{
                        backgroundColor: 'var(--bs-input-bg)',
                        color: 'var(--bs-input-color)',
                        borderColor: 'var(--bs-border-color)',
                      }}
                    />
                  </td>
                  <td className="align-middle text-center">
                    <Form.Check
                      type="switch"
                      id={`scope-domains-wildcard-${index}`}
                      checked={row.wildcard}
                      onChange={(e) => updateRow(index, 'wildcard', e.target.checked)}
                      disabled={disabled}
                      aria-label="Wildcard"
                      title="Wildcard"
                    />
                  </td>
                  <td className="align-middle">
                    <Button
                      variant="outline-danger"
                      size="sm"
                      onClick={() => removeRow(index)}
                      disabled={disabled}
                      type="button"
                    >
                      Remove
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </Table>
      </div>
      <Button
        variant="outline-primary"
        size="sm"
        onClick={addRow}
        disabled={disabled}
        type="button"
      >
        Add pattern
      </Button>
    </div>
  );
}

export default ScopeDomainsEditor;
