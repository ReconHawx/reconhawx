import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Button,
  Alert,
  Spinner,
  ListGroup
} from 'react-bootstrap';
import { wordlistsAPI } from '../../services/api';

function WordlistSelector({
  selectedWordlist = null,
  customWordlistUrl = '',
  wordlistInputType = 'database',
  onWordlistChange,
  onCustomUrlChange,
  onInputTypeChange
}) {
  // Wordlist selection state
  const [wordlists, setWordlists] = useState([]);
  const [wordlistLoading, setWordlistLoading] = useState(false);
  const [wordlistSearchTerm, setWordlistSearchTerm] = useState('');

  // Load wordlists on component mount and when search term changes
  const loadWordlists = useCallback(async () => {
    setWordlistLoading(true);
    try {
      const response = await wordlistsAPI.list(0, 100, true, null, null, wordlistSearchTerm);
      if (response && response.wordlists && Array.isArray(response.wordlists)) {
        setWordlists(response.wordlists);
      }
    } catch (err) {
      console.error('Failed to load wordlists:', err);
    } finally {
      setWordlistLoading(false);
    }
  }, [wordlistSearchTerm]);

  // Load wordlists on component mount
  useEffect(() => {
    loadWordlists();
  }, [loadWordlists]);

  // Reload wordlists when search term changes (with debouncing)
  useEffect(() => {
    if (wordlistSearchTerm !== '') {
      const timer = setTimeout(() => {
        loadWordlists();
      }, 500); // Debounce search

      return () => clearTimeout(timer);
    }
  }, [wordlistSearchTerm, loadWordlists]);

  const handleWordlistSelect = (wordlist) => {
    onWordlistChange(wordlist);
  };

  const isSelected = (wordlist) =>
    selectedWordlist != null && String(selectedWordlist.id) === String(wordlist.id);

  const handleInputTypeChange = (type) => {
    onInputTypeChange(type);
    // Reset selections when switching types
    if (type === 'url') {
      onWordlistChange(null);
    } else if (type === 'database') {
      onCustomUrlChange('');
    }
  };

  const handleSearchKeyPress = (e) => {
    if (e.key === 'Enter') {
      loadWordlists();
    }
  };

  return (
    <Card>
      <Card.Header>
        <h6 className="mb-0">📚 Wordlist Configuration</h6>
      </Card.Header>
      <Card.Body>
        <Form.Group className="mb-3">
          <Form.Label>Wordlist Source</Form.Label>
          <Form.Select
            value={wordlistInputType}
            onChange={(e) => handleInputTypeChange(e.target.value)}
          >
            <option value="database">Select from Database</option>
            <option value="url">Enter URL</option>
          </Form.Select>
        </Form.Group>

        {wordlistInputType === 'database' && (
          <Form.Group className="mb-3">
            <Form.Label>Select Wordlist</Form.Label>
            <div className="mb-2">
              <Form.Control
                type="text"
                placeholder="🔍 Search wordlists..."
                value={wordlistSearchTerm}
                onChange={(e) => setWordlistSearchTerm(e.target.value)}
                onKeyPress={handleSearchKeyPress}
              />
              <div className="d-flex gap-2 mt-2">
                <Button
                  variant="outline-primary"
                  size="sm"
                  onClick={loadWordlists}
                  disabled={wordlistLoading}
                >
                  {wordlistLoading ? (
                    <>
                      <Spinner animation="border" size="sm" className="me-1" />
                      Loading...
                    </>
                  ) : (
                    '🔍 Search'
                  )}
                </Button>
                <Button
                  variant="outline-secondary"
                  size="sm"
                  onClick={() => {
                    setWordlistSearchTerm('');
                    loadWordlists();
                  }}
                >
                  Clear
                </Button>
              </div>
            </div>

            <div style={{ maxHeight: '200px', overflowY: 'auto', border: '1px solid #dee2e6', borderRadius: '0.375rem' }}>
              {wordlistLoading ? (
                <div className="text-center py-3">
                  <Spinner animation="border" size="sm" />
                  <p className="mt-2 text-muted">Loading wordlists...</p>
                </div>
              ) : wordlists.length === 0 ? (
                <div className="text-center py-3 text-muted">
                  No wordlists found. <br/>
                  <small>
                    Upload wordlists in the{' '}
                    <a href="/admin/wordlists" target="_blank" rel="noopener noreferrer">
                      Admin section
                    </a>.
                  </small>
                </div>
              ) : (
                <ListGroup variant="flush">
                  {wordlists.map(wordlist => (
                    <ListGroup.Item
                      key={wordlist.id}
                      className={`d-flex justify-content-between align-items-center py-2 ${isSelected(wordlist) ? 'bg-primary text-white' : ''}`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => handleWordlistSelect(wordlist)}
                    >
                      <div>
                        <div className="fw-bold">{wordlist.name}</div>
                        <small className={isSelected(wordlist) ? 'text-white-50' : 'text-muted'}>
                          {wordlist.filename} • {wordlist.word_count} words
                        </small>
                        {wordlist.description && (
                          <div className={isSelected(wordlist) ? 'text-white-50' : 'text-muted'}>
                            <small>{wordlist.description}</small>
                          </div>
                        )}
                      </div>
                      {isSelected(wordlist) && (
                        <span>✓</span>
                      )}
                    </ListGroup.Item>
                  ))}
                </ListGroup>
              )}
            </div>

            {selectedWordlist && (
              <Alert variant="success" className="mt-2">
                <strong>Selected:</strong> {selectedWordlist.name} ({selectedWordlist.word_count} words)
              </Alert>
            )}
          </Form.Group>
        )}

        {wordlistInputType === 'url' && (
          <Form.Group className="mb-3">
            <Form.Label>Wordlist URL</Form.Label>
            <Form.Control
              type="url"
              value={customWordlistUrl}
              onChange={(e) => onCustomUrlChange(e.target.value)}
              placeholder="https://raw.githubusercontent.com/user/repo/main/wordlist.txt"
            />
            <Form.Text className="text-muted">
              Enter a direct URL to a wordlist file. The file will be downloaded automatically.
            </Form.Text>
          </Form.Group>
        )}
      </Card.Body>
    </Card>
  );
}

export default WordlistSelector;
