import React, { useState } from 'react';
import { Card, Button, Form, Alert, Spinner } from 'react-bootstrap';

const NotesSection = ({ 
  assetType, 
  assetId, 
  currentNotes = '', 
  apiUpdateFunction,
  onNotesUpdate = null 
}) => {
  const [notes, setNotes] = useState(currentNotes);
  const [originalNotes, setOriginalNotes] = useState(currentNotes);
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ text: '', type: '' });

  const handleSave = async () => {
    if (!notes.trim() && !originalNotes.trim()) {
      setMessage({ text: 'No changes to save', type: 'info' });
      setTimeout(() => setMessage({ text: '', type: '' }), 3000);
      return;
    }

    try {
      setLoading(true);
      setMessage({ text: '', type: '' });

      const response = await apiUpdateFunction(assetId, notes.trim());
      
      if (response.status === 'success') {
        setOriginalNotes(notes.trim());
        setIsEditing(false);
        setMessage({ text: 'Notes updated successfully', type: 'success' });
        
        // Call parent update callback if provided
        if (onNotesUpdate) {
          onNotesUpdate(notes.trim());
        }
      } else {
        throw new Error(response.message || 'Failed to update notes');
      }
    } catch (err) {
      console.error('Error updating notes:', err);
      setMessage({ 
        text: err.message || 'Failed to update notes', 
        type: 'danger' 
      });
    } finally {
      setLoading(false);
      setTimeout(() => setMessage({ text: '', type: '' }), 5000);
    }
  };

  const handleCancel = () => {
    setNotes(originalNotes);
    setIsEditing(false);
    setMessage({ text: '', type: '' });
  };

  const hasChanges = notes.trim() !== originalNotes.trim();

  return (
    <Card className="mb-4">
      <Card.Header className="d-flex justify-content-between align-items-center">
        <h5 className="mb-0">📝 Investigation Notes</h5>
        <div>
          {!isEditing ? (
            <Button 
              variant="outline-primary" 
              size="sm"
              onClick={() => setIsEditing(true)}
              disabled={loading}
            >
              {originalNotes ? 'Edit Notes' : 'Add Notes'}
            </Button>
          ) : (
            <div className="d-flex gap-2">
              <Button 
                variant="success" 
                size="sm"
                onClick={handleSave}
                disabled={loading || !hasChanges}
              >
                {loading ? (
                  <>
                    <Spinner size="sm" className="me-1" />
                    Saving...
                  </>
                ) : (
                  'Save'
                )}
              </Button>
              <Button 
                variant="outline-secondary" 
                size="sm"
                onClick={handleCancel}
                disabled={loading}
              >
                Cancel
              </Button>
            </div>
          )}
        </div>
      </Card.Header>
      <Card.Body>
        {message.text && (
          <Alert variant={message.type} className="mb-3">
            {message.text}
          </Alert>
        )}
        
        {!isEditing ? (
          <div>
            {originalNotes ? (
              <div className="notes-content" style={{ whiteSpace: 'pre-wrap' }}>
                {originalNotes}
              </div>
            ) : (
              <p className="text-muted mb-0">
                No investigation notes available. Click "Add Notes" to add some.
              </p>
            )}
          </div>
        ) : (
          <Form>
            <Form.Group>
              <Form.Label>Investigation Notes</Form.Label>
              <Form.Control
                as="textarea"
                rows={6}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder={`Enter investigation notes for this ${assetType}...`}
                disabled={loading}
              />
              <Form.Text className="text-muted">
                Document your investigation findings, analysis results, and any relevant information about this {assetType}.
              </Form.Text>
            </Form.Group>
          </Form>
        )}
      </Card.Body>
    </Card>
  );
};

export default NotesSection;