import React from 'react';
import { Modal, Button, Form, ListGroup } from 'react-bootstrap';
import { WIDGET_LABELS } from './useDashboardPrefs';

export default function CustomizeDashboardModal({
  show,
  onHide,
  order,
  visible,
  toggleWidget,
  moveWidget,
  resetDefaults,
}) {
  return (
    <Modal show={show} onHide={onHide} centered size="md">
      <Modal.Header closeButton>
        <Modal.Title>Customize dashboard</Modal.Title>
      </Modal.Header>
      <Modal.Body>
        <p className="text-muted small">
          Show or hide sections and change their order. Preferences are stored in this browser.
        </p>
        <ListGroup variant="flush">
          {order.map((id) => (
            <ListGroup.Item
              key={id}
              className="d-flex align-items-center justify-content-between gap-2 px-0"
            >
              <Form.Check
                type="checkbox"
                id={`widget-${id}`}
                label={WIDGET_LABELS[id] || id}
                checked={!!visible[id]}
                onChange={() => toggleWidget(id)}
              />
              <div className="btn-group btn-group-sm">
                <Button variant="outline-secondary" size="sm" onClick={() => moveWidget(id, 'up')}>
                  Up
                </Button>
                <Button variant="outline-secondary" size="sm" onClick={() => moveWidget(id, 'down')}>
                  Down
                </Button>
              </div>
            </ListGroup.Item>
          ))}
        </ListGroup>
      </Modal.Body>
      <Modal.Footer className="justify-content-between">
        <Button variant="outline-secondary" onClick={resetDefaults}>
          Reset to default
        </Button>
        <Button variant="primary" onClick={onHide}>
          Done
        </Button>
      </Modal.Footer>
    </Modal>
  );
}
