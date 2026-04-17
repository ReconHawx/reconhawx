import React, { useMemo } from 'react';
import { Table, Form, Button, OverlayTrigger, Tooltip } from 'react-bootstrap';

/**
 * Editable table for structured program scope rows: { pattern, wildcard }.
 *
 * `invalidPatterns` is an optional array of `{ pattern, reason }` entries
 * returned by the API when it rejects some patterns as invalid. Rows whose
 * pattern matches (case-insensitive, trimmed) are highlighted in red and show
 * the rejection reason on hover so the user can correct them in place.
 */
function ScopeDomainsEditor({
  rows,
  onChange,
  disabled = false,
  invalidPatterns = [],
}) {
  // Normalize invalid patterns to the same form we send to the API so we can
  // match rows reliably (`scopeRowsToEntries` calls `.trim().toLowerCase()`).
  const invalidByPattern = useMemo(() => {
    const map = new Map();
    (invalidPatterns || []).forEach((w) => {
      const key = String(w?.pattern ?? '').trim().toLowerCase();
      if (key) map.set(key, w?.reason || 'Invalid pattern');
    });
    return map;
  }, [invalidPatterns]);

  const getRowError = (row) => {
    const key = String(row?.pattern ?? '').trim().toLowerCase();
    if (!key) return null;
    return invalidByPattern.get(key) || null;
  };

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
              rows.map((row, index) => {
                const rowError = getRowError(row);
                const inputStyle = {
                  backgroundColor: 'var(--bs-input-bg)',
                  color: 'var(--bs-input-color)',
                  borderColor: rowError ? 'var(--bs-danger)' : 'var(--bs-border-color)',
                };
                if (rowError) {
                  inputStyle.boxShadow = '0 0 0 0.15rem rgba(220, 53, 69, 0.25)';
                }
                const control = (
                  <Form.Control
                    type="text"
                    value={row.pattern}
                    onChange={(e) => updateRow(index, 'pattern', e.target.value)}
                    disabled={disabled}
                    placeholder="e.g. example.com or *.example.com"
                    isInvalid={Boolean(rowError)}
                    style={inputStyle}
                  />
                );
                return (
                  <tr key={index} className={rowError ? 'table-danger' : undefined}>
                    <td className="align-middle">{index + 1}</td>
                    <td>
                      {rowError ? (
                        <OverlayTrigger
                          placement="top"
                          overlay={
                            <Tooltip id={`scope-invalid-${index}`}>{rowError}</Tooltip>
                          }
                        >
                          {control}
                        </OverlayTrigger>
                      ) : (
                        control
                      )}
                      {rowError && (
                        <Form.Text className="text-danger small">
                          {rowError}
                        </Form.Text>
                      )}
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
                );
              })
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
