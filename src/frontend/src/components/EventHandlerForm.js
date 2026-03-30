/**
 * Form-based editor for event handler configuration.
 * Replaces raw JSON with user-friendly form fields.
 */

import React, { useState } from 'react';
import { Form, Row, Col, Button, Card, Badge } from 'react-bootstrap';
import EmbeddedWorkflowBuilderModal from './EmbeddedWorkflowBuilderModal';

// Parsed event_type values (see event-handler routing + API NATS subjects). Includes alternate
// subject shapes some repos still publish (e.g. events.findings.created.nuclei).
const EVENT_TYPES = [
  'typosquat.ct_alert',
  'assets.apex_domain.created',
  'assets.apex_domain.updated',
  'assets.certificate.created',
  'assets.domain.created',
  'assets.ip.created',
  'assets.ip.deleted',
  'assets.ip.updated',
  'assets.service.created',
  'assets.service.updated',
  'assets.subdomain.created',
  'assets.subdomain.resolved',
  'assets.subdomain.updated',
  'assets.url.created',
  'assets.url.updated',
  'findings.broken_link.created',
  'findings.created.broken_link',
  'findings.created.nuclei',
  'findings.created.wpscan',
  'findings.nuclei.created',
  'findings.nuclei.critical',
  'findings.nuclei.high',
  'findings.nuclei.info',
  'findings.nuclei.low',
  'findings.nuclei.medium',
  'findings.nuclei.typosquat',
  'findings.typosquat.created',
  'findings.typosquat_domain.created',
  'findings.wpscan.created',
  'test.workflow.trigger'
];

const CONDITION_OPERATORS = [
  'equals', 'not_equals', 'null_or_empty', 'not_exists', 'exists',
  'greater_than', 'less_than', 'not_empty', 'in'
];

const ACTION_TYPES = [
  { value: 'log', label: 'Log' },
  { value: 'discord_notification', label: 'Discord Notification' },
  { value: 'workflow_trigger', label: 'Trigger Workflow' },
  { value: 'phishlabs_batch_trigger', label: 'PhishLabs Batch' },
  { value: 'ai_analysis_batch_trigger', label: 'AI Analysis Batch' }
];

const emptyCondition = (type = 'field_value') => {
  if (type === 'field_exists') return { type: 'field_exists', field: '' };
  if (type === 'asset_filter') return { type: 'asset_filter', filter_field: '', filter_operator: 'exists', filter_value: '' };
  return { type: 'field_value', field: '', operator: 'equals', expected_value: '' };
};

const emptyAction = (type = 'log') => {
  const base = { type };
  if (type === 'log') {
    return { ...base, level: 'info', message_template: '', batch_message_template: '', batching: { max_events: 10, max_delay_seconds: 60 } };
  }
  if (type === 'discord_notification') {
    return {
      ...base,
      title_template: '',
      description_template: '',
      batch_title_template: '',
      batch_description_template: '',
      webhook_url: '{program_settings.discord_webhook_url}',
      color: 5763719,
      batch_color: 3066993,
      batching: { max_events: 10, max_delay_seconds: 60 }
    };
  }
  if (type === 'workflow_trigger') {
    return {
      ...base,
      api_url: '{api_base_url}',
      api_key: '{internal_api_key}',
      use_custom_payload: true,
      batching: { max_events: 50, max_delay_seconds: 300 },
      parameters: {
        workflow_name: '',
        program_name: '{program_name}',
        description: '',
        steps: [],
        inputs: {},
        variables: {}
      }
    };
  }
  if (type === 'phishlabs_batch_trigger') {
    return {
      ...base,
      finding_id_template: '{record_id}',
      api_url: '{api_base_url}',
      api_key: '{internal_api_key}',
      batching: { max_events: 10, max_delay_seconds: 120 }
    };
  }
  if (type === 'ai_analysis_batch_trigger') {
    return {
      ...base,
      finding_id_template: '{record_id}',
      api_url: '{api_base_url}',
      api_key: '{internal_api_key}',
      batching: { max_events: 10, max_delay_seconds: 120 }
    };
  }
  return base;
};

function ConditionEditor({ condition, onChange, onRemove }) {
  const type = condition.type || 'field_value';

  const update = (key, value) => onChange({ ...condition, [key]: value });

  return (
    <Card className="mb-2">
      <Card.Body className="py-2">
        <Row className="align-items-center g-2">
          <Col md="auto">
            <Form.Select size="sm" value={type} onChange={(e) => onChange({ ...emptyCondition(e.target.value), type: e.target.value })} style={{ width: 140 }}>
              <option value="field_value">Field Value</option>
              <option value="field_exists">Field Exists</option>
              <option value="asset_filter">Asset Filter</option>
            </Form.Select>
          </Col>
          {type === 'field_value' && (
            <>
              <Col md={2}>
                <Form.Control size="sm" placeholder="Field" value={condition.field || ''} onChange={(e) => update('field', e.target.value)} />
              </Col>
              <Col md={2}>
                <Form.Select size="sm" value={condition.operator || 'equals'} onChange={(e) => update('operator', e.target.value)}>
                  {CONDITION_OPERATORS.map(op => <option key={op} value={op}>{op}</option>)}
                </Form.Select>
              </Col>
              <Col md={2}>
                <Form.Control
                  size="sm"
                  placeholder="Value (or JSON)"
                  value={typeof condition.expected_value === 'string' ? condition.expected_value : JSON.stringify(condition.expected_value)}
                  onChange={(e) => {
                    const v = e.target.value;
                    try {
                      update('expected_value', v.startsWith('[') || v.startsWith('{') ? JSON.parse(v) : v);
                    } catch {
                      update('expected_value', v);
                    }
                  }}
                />
              </Col>
            </>
          )}
          {type === 'field_exists' && (
            <Col md={4}>
              <Form.Control size="sm" placeholder="Field name" value={condition.field || ''} onChange={(e) => update('field', e.target.value)} />
            </Col>
          )}
          {type === 'asset_filter' && (
            <>
              <Col md={2}>
                <Form.Control size="sm" placeholder="Filter field" value={condition.filter_field || ''} onChange={(e) => update('filter_field', e.target.value)} />
              </Col>
              <Col md={2}>
                <Form.Select size="sm" value={condition.filter_operator || 'exists'} onChange={(e) => update('filter_operator', e.target.value)}>
                  <option value="exists">exists</option>
                  <option value="not_exists">not_exists</option>
                  <option value="equals">equals</option>
                  <option value="not_equals">not_equals</option>
                </Form.Select>
              </Col>
              <Col md={2}>
                <Form.Control size="sm" placeholder="Value" value={condition.filter_value || ''} onChange={(e) => update('filter_value', e.target.value)} />
              </Col>
            </>
          )}
          <Col md="auto" className="ms-auto">
            <Button variant="outline-danger" size="sm" onClick={onRemove}>Remove</Button>
          </Col>
        </Row>
      </Card.Body>
    </Card>
  );
}

function BatchingFields({ batching, onChange }) {
  const b = batching || {};
  const update = (k, v) => onChange({ ...b, [k]: v });
  return (
    <Row className="g-2">
      <Col md={3}>
        <Form.Label className="small">Max events</Form.Label>
        <Form.Control type="number" size="sm" value={b.max_events ?? 10} onChange={(e) => update('max_events', parseInt(e.target.value) || 10)} />
      </Col>
      <Col md={3}>
        <Form.Label className="small">Max delay (sec)</Form.Label>
        <Form.Control type="number" size="sm" value={b.max_delay_seconds ?? 60} onChange={(e) => update('max_delay_seconds', parseInt(e.target.value) || 60)} />
      </Col>
    </Row>
  );
}

function ActionEditor({ action, onChange, onRemove, eventType }) {
  const type = action.type || 'log';
  const [showWorkflowBuilderModal, setShowWorkflowBuilderModal] = useState(false);

  const update = (key, value) => onChange({ ...action, [key]: value });

  return (
    <Card className="mb-3">
      <Card.Header className="py-2 d-flex justify-content-between align-items-center">
        <Badge bg="primary">{type.replace(/_/g, ' ')}</Badge>
        <Button variant="outline-danger" size="sm" onClick={onRemove}>Remove</Button>
      </Card.Header>
      <Card.Body>
        <Form.Select className="mb-2" size="sm" value={type} onChange={(e) => onChange(emptyAction(e.target.value))}>
          {ACTION_TYPES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
        </Form.Select>

        {type === 'log' && (
          <>
            <Form.Group className="mb-2">
              <Form.Label className="small">Level</Form.Label>
              <Form.Select size="sm" value={action.level || 'info'} onChange={(e) => update('level', e.target.value)}>
                <option value="debug">debug</option>
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="error">error</option>
              </Form.Select>
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Message template (use {'{field}'} for event data)</Form.Label>
              <Form.Control as="textarea" rows={2} size="sm" value={action.message_template || ''} onChange={(e) => update('message_template', e.target.value)} placeholder="Event: {event_type}" />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Batch message template</Form.Label>
              <Form.Control as="textarea" rows={2} size="sm" value={action.batch_message_template || ''} onChange={(e) => update('batch_message_template', e.target.value)} />
            </Form.Group>
            <Form.Group>
              <Form.Label className="small">Batching</Form.Label>
              <BatchingFields batching={action.batching} onChange={(b) => update('batching', b)} />
            </Form.Group>
          </>
        )}

        {type === 'discord_notification' && (
          <>
            <Form.Group className="mb-2">
              <Form.Label className="small">Title template</Form.Label>
              <Form.Control size="sm" value={action.title_template || ''} onChange={(e) => update('title_template', e.target.value)} placeholder="🎯 Event: {name}" />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Description template</Form.Label>
              <Form.Control as="textarea" rows={3} size="sm" value={action.description_template || ''} onChange={(e) => update('description_template', e.target.value)} />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Batch title template</Form.Label>
              <Form.Control size="sm" value={action.batch_title_template || ''} onChange={(e) => update('batch_title_template', e.target.value)} />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Batch description template</Form.Label>
              <Form.Control as="textarea" rows={2} size="sm" value={action.batch_description_template || ''} onChange={(e) => update('batch_description_template', e.target.value)} />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Webhook URL template</Form.Label>
              <Form.Control size="sm" value={action.webhook_url || ''} onChange={(e) => update('webhook_url', e.target.value)} placeholder="{program_settings.discord_webhook_url}" />
            </Form.Group>
            <Row className="g-2 mb-2">
              <Col md={3}>
                <Form.Label className="small">Color (decimal)</Form.Label>
                <Form.Control type="number" size="sm" value={action.color ?? 5763719} onChange={(e) => update('color', parseInt(e.target.value) || 5763719)} />
              </Col>
              <Col md={3}>
                <Form.Label className="small">Batch color</Form.Label>
                <Form.Control type="number" size="sm" value={action.batch_color ?? 3066993} onChange={(e) => update('batch_color', parseInt(e.target.value) || 3066993)} />
              </Col>
            </Row>
            <Form.Group>
              <Form.Label className="small">Batching</Form.Label>
              <BatchingFields batching={action.batching} onChange={(b) => update('batching', b)} />
            </Form.Group>
          </>
        )}

        {type === 'workflow_trigger' && (
          <>
            <Form.Group className="mb-2">
              <Form.Label className="small">Workflow name</Form.Label>
              <Form.Control size="sm" value={action.parameters?.workflow_name || ''} onChange={(e) => update('parameters', { ...(action.parameters || {}), workflow_name: e.target.value })} placeholder="subdomain_resolution" />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Program name template</Form.Label>
              <Form.Control size="sm" value={action.parameters?.program_name || ''} onChange={(e) => update('parameters', { ...(action.parameters || {}), program_name: e.target.value })} placeholder="{program_name}" />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">Description template</Form.Label>
              <Form.Control size="sm" value={action.parameters?.description || ''} onChange={(e) => update('parameters', { ...(action.parameters || {}), description: e.target.value })} placeholder="Batch: {event_count} items" />
            </Form.Group>
            <Form.Group className="mb-2">
              <Form.Label className="small">API URL template</Form.Label>
              <Form.Control size="sm" value={action.api_url || ''} onChange={(e) => update('api_url', e.target.value)} placeholder="{api_base_url}" />
            </Form.Group>
            <Form.Group>
              <Form.Label className="small">Batching</Form.Label>
              <BatchingFields batching={action.batching} onChange={(b) => update('batching', b)} />
            </Form.Group>
            <Form.Group className="mt-2">
              <Button variant="outline-primary" size="sm" onClick={() => setShowWorkflowBuilderModal(true)}>
                Build Workflow
              </Button>
            </Form.Group>
            <EmbeddedWorkflowBuilderModal
              show={showWorkflowBuilderModal}
              onHide={() => setShowWorkflowBuilderModal(false)}
              initialParameters={action.parameters || {}}
              eventType={eventType}
              onSave={(params) => {
                update('parameters', params);
                setShowWorkflowBuilderModal(false);
              }}
            />
          </>
        )}

        {type === 'phishlabs_batch_trigger' && (
          <>
            <Form.Group className="mb-2">
              <Form.Label className="small">Finding ID template</Form.Label>
              <Form.Control size="sm" value={action.finding_id_template || ''} onChange={(e) => update('finding_id_template', e.target.value)} placeholder="{record_id}" />
            </Form.Group>
            <Form.Group>
              <Form.Label className="small">Batching</Form.Label>
              <BatchingFields batching={action.batching} onChange={(b) => update('batching', b)} />
            </Form.Group>
          </>
        )}

        {type === 'ai_analysis_batch_trigger' && (
          <>
            <Form.Group className="mb-2">
              <Form.Label className="small">Finding ID template</Form.Label>
              <Form.Control size="sm" value={action.finding_id_template || ''} onChange={(e) => update('finding_id_template', e.target.value)} placeholder="{record_id}" />
            </Form.Group>
            <Form.Group>
              <Form.Label className="small">Batching</Form.Label>
              <BatchingFields batching={action.batching} onChange={(b) => update('batching', b)} />
            </Form.Group>
          </>
        )}
      </Card.Body>
    </Card>
  );
}

export default function EventHandlerForm({ handler, onChange }) {
  const h = handler || { id: '', event_type: '', description: '', conditions: [], actions: [] };
  const update = (key, value) => onChange({ ...h, [key]: value });

  const addCondition = () => update('conditions', [...(h.conditions || []), emptyCondition()]);
  const addAction = () => update('actions', [...(h.actions || []), emptyAction()]);

  return (
    <Form>
      <Card className="mb-3">
        <Card.Header>Basic Info</Card.Header>
        <Card.Body>
          <Row className="g-2">
            <Col md={4}>
              <Form.Label>Handler ID</Form.Label>
              <Form.Control value={h.id || ''} onChange={(e) => update('id', e.target.value)} placeholder="my_handler_id" />
            </Col>
            <Col md={4}>
              <Form.Label>Event Type</Form.Label>
              <Form.Select
                value={EVENT_TYPES.includes(h.event_type) ? h.event_type : '__custom__'}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === '__custom__') {
                    // Leaving a preset for custom: clear so the select stays on Custom and the text field appears.
                    // Already-custom values: keep the typed event_type.
                    const next = EVENT_TYPES.includes(h.event_type) ? '' : (h.event_type || '');
                    update('event_type', next);
                  } else {
                    update('event_type', v);
                  }
                }}
              >
                {EVENT_TYPES.map(et => <option key={et} value={et}>{et}</option>)}
                <option value="__custom__">Custom…</option>
              </Form.Select>
              {!EVENT_TYPES.includes(h.event_type) && (
                <Form.Control size="sm" className="mt-1" value={h.event_type || ''} onChange={(e) => update('event_type', e.target.value)} placeholder="e.g. assets.subdomain.created" />
              )}
            </Col>
          </Row>
          <Form.Group className="mt-2">
            <Form.Label>Description</Form.Label>
            <Form.Control as="textarea" rows={2} value={h.description || ''} onChange={(e) => update('description', e.target.value)} placeholder="What this handler does" />
          </Form.Group>
        </Card.Body>
      </Card>

      <Card className="mb-3">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <span>Conditions</span>
          <Button variant="outline-primary" size="sm" onClick={addCondition}>+ Add Condition</Button>
        </Card.Header>
        <Card.Body>
          {(h.conditions || []).length === 0 ? (
            <p className="text-muted small">No conditions. Events will match if the event type matches.</p>
          ) : (
            (h.conditions || []).map((c, i) => (
              <ConditionEditor
                key={i}
                condition={c}
                onChange={(nc) => {
                  const arr = [...(h.conditions || [])];
                  arr[i] = nc;
                  update('conditions', arr);
                }}
                onRemove={() => update('conditions', (h.conditions || []).filter((_, j) => j !== i))}
              />
            ))
          )}
        </Card.Body>
      </Card>

      <Card className="mb-3">
        <Card.Header className="d-flex justify-content-between align-items-center">
          <span>Actions</span>
          <Button variant="outline-primary" size="sm" onClick={addAction}>+ Add Action</Button>
        </Card.Header>
        <Card.Body>
          {(h.actions || []).length === 0 ? (
            <p className="text-muted small">Add at least one action.</p>
          ) : (
            (h.actions || []).map((a, i) => (
              <ActionEditor
                key={i}
                action={a}
                eventType={h.event_type}
                onChange={(na) => {
                  const arr = [...(h.actions || [])];
                  arr[i] = na;
                  update('actions', arr);
                }}
                onRemove={() => update('actions', (h.actions || []).filter((_, j) => j !== i))}
              />
            ))
          )}
        </Card.Body>
      </Card>
    </Form>
  );
}
