import React from 'react';
import { Form, Button } from 'react-bootstrap';
import { formatAssetSource } from '../../utils/assetSource';

export default function SourceMultiSelectFilter({
  idPrefix = 'source-filter',
  options = [],
  selected = [],
  loading = false,
  onChange,
  onClear,
}) {
  const toggle = (value, checked) => {
    const cur = selected || [];
    if (checked) {
      onChange([...cur, value]);
    } else {
      onChange(cur.filter((s) => s !== value));
    }
  };

  return (
    <div>
      <Form.Label className="mb-1">Source</Form.Label>
      {loading ? (
        <Form.Text className="text-muted d-block mb-2">Loading sources…</Form.Text>
      ) : options.length === 0 ? (
        <Form.Text className="text-muted d-block mb-2">No sources found</Form.Text>
      ) : (
        <div className="d-flex flex-column gap-1" style={{ maxHeight: 220, overflowY: 'auto' }}>
          {options.map((value) => (
            <Form.Check
              key={value}
              type="checkbox"
              id={`${idPrefix}-${value}`}
              label={formatAssetSource(value)}
              checked={(selected || []).includes(value)}
              onChange={(e) => toggle(value, e.target.checked)}
            />
          ))}
        </div>
      )}
      <div className="d-flex justify-content-end gap-2 mt-2">
        <Button size="sm" variant="secondary" onClick={onClear}>Clear</Button>
      </div>
    </div>
  );
}
