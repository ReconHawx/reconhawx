import React, { useState, useEffect, useRef } from 'react';
import { Row, Col, Card, Badge, Button, Spinner, Alert, Modal, Image } from 'react-bootstrap';
import { typosquatScreenshotAPI, API_BASE_URL } from '../services/api';
import { formatDate } from '../utils/dateUtils';

// Lazy loading image component
const LazyImage = ({ src, alt, style, onClick, onError, placeholder }) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [isInView, setIsInView] = useState(false);
  const [hasError, setHasError] = useState(false);
  const imgRef = useRef();

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true);
          observer.disconnect();
        }
      },
      { threshold: 0.1, rootMargin: '50px' }
    );

    if (imgRef.current) {
      observer.observe(imgRef.current);
    }

    return () => observer.disconnect();
  }, []);

  const handleLoad = () => {
    setIsLoaded(true);
  };

  const handleError = (e) => {
    setHasError(true);
    if (onError) onError(e);
  };

  return (
    <div ref={imgRef} style={style} onClick={onClick}>
      {!isInView ? (
        // Placeholder while not in view
        <div
          style={{
            ...style,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'var(--bs-card-bg)',
            border: '1px solid var(--bs-border-color)'
          }}
        >
          <i className="fas fa-image text-muted"></i>
        </div>
      ) : hasError ? (
        // Error state
        <div
          style={{
            ...style,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'var(--bs-card-bg)'
          }}
        >
          <i className="fas fa-image text-muted" style={{ fontSize: '2rem' }}></i>
        </div>
      ) : (
        // Loading/loaded image
        <>
          {!isLoaded && (
            <div
              style={{
                ...style,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backgroundColor: 'var(--bs-card-bg)',
                position: 'absolute',
                zIndex: 1
              }}
            >
              <Spinner animation="border" size="sm" />
            </div>
          )}
          <Image
            src={src}
            alt={alt}
            style={{
              ...style,
              opacity: isLoaded ? 1 : 0,
              transition: 'opacity 0.3s ease'
            }}
            onLoad={handleLoad}
            onError={handleError}
          />
        </>
      )}
    </div>
  );
};

function ScreenshotsViewer({ url, programName }) {
  const [screenshots, setScreenshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [selectedScreenshot, setSelectedScreenshot] = useState(null);
  const [showFullscreen, setShowFullscreen] = useState(false);
  const [fullscreenImageError, setFullscreenImageError] = useState(false);

  useEffect(() => {
    const fetchScreenshots = async () => {
      if (!url) {
        setScreenshots([]);
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        
        // Fetch screenshots for this specific URL
        const params = {
          url_equals: url, // Use exact match for this specific URL
          page: 1,
          page_size: 50, // Get more screenshots for this URL
          sort_by: 'created_at',
          sort_dir: 'desc'
        };
        
        if (programName) {
          params.program = programName;
        }
        
        const data = await typosquatScreenshotAPI.searchTyposquatScreenshots(params);
        setScreenshots(data.items || []);
      } catch (err) {
        setError('Failed to fetch screenshots: ' + err.message);
        setScreenshots([]);
      } finally {
        setLoading(false);
      }
    };

    fetchScreenshots();
  }, [url, programName]);

  // Handle keyboard shortcuts for fullscreen
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && showFullscreen) {
        setShowFullscreen(false);
      }
      if (event.key === 'f' && showModal && !showFullscreen) {
        setFullscreenImageError(false);
        setShowFullscreen(true);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [showFullscreen, showModal]);

  const handleScreenshotClick = (screenshot) => {
    setSelectedScreenshot(screenshot);
    setShowModal(true);
    setFullscreenImageError(false);
  };

  const formatScreenshotDate = (dateString) => {
    if (!dateString) return 'N/A';
    return formatDate(dateString);
  };

  const formatFileSize = (bytes) => {
    if (!bytes) return 'N/A';
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
  };

  const getFirstCaptureDate = (screenshot) => {
    // Try to get from capture_timestamps array first
    if (screenshot.metadata?.capture_timestamps && screenshot.metadata.capture_timestamps.length > 0) {
      return screenshot.metadata.capture_timestamps[0];
    }
    // Fall back to upload_date
    return screenshot.upload_date;
  };

  const getLastCaptureDate = (screenshot) => {
    // Try to get from capture_timestamps array first
    if (screenshot.metadata?.capture_timestamps && screenshot.metadata.capture_timestamps.length > 0) {
      return screenshot.metadata.capture_timestamps[screenshot.metadata.capture_timestamps.length - 1];
    }
    // Fall back to last_captured_at or upload_date
    return screenshot.metadata?.last_captured_at || screenshot.upload_date;
  };

  const hasMultipleCaptures = (screenshot) => {
    // First priority: If capture_count is explicitly set, use that as the source of truth
    if (screenshot.metadata?.capture_count !== undefined) {
      return screenshot.metadata.capture_count > 1;
    }
    
    // Second priority: Check if there are actually multiple captures via timestamps array
    if (screenshot.metadata?.capture_timestamps && screenshot.metadata.capture_timestamps.length > 1) {
      return true;
    }
    
    // Third priority: Check if first and last capture dates are different (indicating multiple captures)
    const firstDate = getFirstCaptureDate(screenshot);
    const lastDate = getLastCaptureDate(screenshot);
    return firstDate && lastDate && firstDate !== lastDate;
  };

  const getScreenshotUrl = (screenshot, thumbnailSize = null) => {
    // Use the API base URL to construct the screenshot URL
    const baseUrl = `${API_BASE_URL}/findings/typosquat-screenshot/${screenshot.file_id}`;
    const token = localStorage.getItem('access_token');
    const params = new URLSearchParams();
    if (thumbnailSize) params.append('thumbnail', thumbnailSize);
    if (token) params.append('token', token);
    const qs = params.toString();
    return qs ? `${baseUrl}?${qs}` : baseUrl;
  };

  if (!url) {
    return (
      <Alert variant="info" className="py-2 mb-0">
        <i className="fas fa-info-circle me-2"></i>
        No URL available to display screenshots for.
      </Alert>
    );
  }

  if (loading) {
    return (
      <div className="text-center p-4">
        <Spinner animation="border" role="status">
          <span className="visually-hidden">Loading...</span>
        </Spinner>
        <p className="mt-2">Loading screenshots...</p>
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="danger" className="py-2 mb-0">
        <i className="fas fa-exclamation-triangle me-2"></i>
        {error}
      </Alert>
    );
  }

  if (screenshots.length === 0) {
    return (
      <Alert variant="info" className="py-2 mb-0">
        <i className="fas fa-info-circle me-2"></i>
        No screenshots found for this URL.
      </Alert>
    );
  }

  return (
    <>
      <div className="mb-3">
        <Badge bg="info" className="me-2">
          {screenshots.length} screenshot{screenshots.length !== 1 ? 's' : ''} found
        </Badge>
        <small className="text-muted">
          Click on any screenshot to view details and full-size image
        </small>
      </div>

      <Row>
        {screenshots.map((screenshot) => (
          <Col md={4} lg={3} key={screenshot.file_id} className="mb-4">
            <Card>
              <div style={{ position: 'relative' }}>
                <LazyImage
                  src={getScreenshotUrl(screenshot, 400)}
                  alt={`Screenshot of ${url}`}
                  style={{ 
                    height: '200px', 
                    width: '100%',
                    cursor: 'pointer',
                    objectFit: 'contain',
                    backgroundColor: 'var(--bs-card-bg)'
                  }}
                  onClick={() => handleScreenshotClick(screenshot)}
                />
                {hasMultipleCaptures(screenshot) && (
                  <Badge 
                    bg="info" 
                    style={{ 
                      position: 'absolute', 
                      top: '5px', 
                      right: '5px',
                      zIndex: 2
                    }}
                  >
                    {screenshot.metadata?.capture_count}x
                  </Badge>
                )}
              </div>
              <Card.Body>
                <Card.Text className="small text-muted">
                  <div>
                    <strong>Size:</strong> {formatFileSize(screenshot.file_size)}
                  </div>
                  <div>
                    <strong>First Captured:</strong> {formatScreenshotDate(getFirstCaptureDate(screenshot))}
                  </div>
                  {hasMultipleCaptures(screenshot) && getLastCaptureDate(screenshot) !== getFirstCaptureDate(screenshot) && (
                    <div>
                      <strong>Last Captured:</strong> {formatScreenshotDate(getLastCaptureDate(screenshot))}
                    </div>
                  )}
                  {hasMultipleCaptures(screenshot) && (
                    <div>
                      <strong>Captures:</strong> 
                      <Badge bg="info" className="ms-1 small">
                        {screenshot.metadata?.capture_count}x
                      </Badge>
                    </div>
                  )}
                  {screenshot.metadata?.program_name && (
                    <div>
                      <Badge bg="primary" className="mt-1">
                        {screenshot.metadata.program_name}
                      </Badge>
                    </div>
                  )}
                  {(screenshot.source || screenshot.metadata?.source) && (
                    <div>
                      <strong>Source:</strong>{' '}
                      <Badge bg="secondary" className="small">
                        {screenshot.source || screenshot.metadata?.source}
                      </Badge>
                    </div>
                  )}
                  {(screenshot.source_created_at || screenshot.metadata?.source_created_at) && (
                    <div>
                      <strong>Source Captured:</strong>{' '}
                      {formatScreenshotDate(screenshot.source_created_at || screenshot.metadata?.source_created_at)}
                    </div>
                  )}
                </Card.Text>
              </Card.Body>
            </Card>
          </Col>
        ))}
      </Row>

      {/* Screenshot Modal */}
      <Modal show={showModal} onHide={() => setShowModal(false)} size="xl" centered>
        <Modal.Header closeButton>
          <Modal.Title>Screenshot Details</Modal.Title>
        </Modal.Header>
        <Modal.Body style={{ maxHeight: '80vh', overflowY: 'auto' }}>
          {selectedScreenshot && (
            <div>
              <div className="text-center mb-3" style={{ position: 'relative' }}>
                <div 
                  style={{ 
                    maxHeight: '600px', 
                    overflow: 'auto',
                    border: '1px solid var(--bs-border-color)',
                    borderRadius: '8px',
                    backgroundColor: 'var(--bs-card-bg)',
                    position: 'relative'
                  }}
                >
                  <Image
                    src={getScreenshotUrl(selectedScreenshot)}
                    alt={`Screenshot of ${url}`}
                    style={{ 
                      width: '100%', 
                      height: 'auto',
                      cursor: 'pointer'
                    }}
                    onClick={() => {
                      setFullscreenImageError(false);
                      setShowFullscreen(true);
                    }}
                    onError={(e) => {
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'block';
                    }}
                  />
                  <div style={{ display: 'none' }} className="text-muted p-4">
                    <i className="fas fa-image" style={{ fontSize: '3rem' }}></i>
                    <p>Image could not be loaded</p>
                  </div>
                  
                  {/* Fullscreen button overlay */}
                  <Button
                    variant="dark"
                    size="sm"
                    style={{
                      position: 'absolute',
                      top: '10px',
                      right: '10px',
                      opacity: 0.8,
                      zIndex: 2
                    }}
                    onClick={() => {
                      setFullscreenImageError(false);
                      setShowFullscreen(true);
                    }}
                    title="View fullscreen"
                  >
                    <i className="fas fa-expand"></i>
                  </Button>
                </div>
                <div className="mt-2 text-muted small">
                  <i className="fas fa-search-plus me-1"></i>
                  Click image, fullscreen button, or press 'F' to view at full size
                </div>
              </div>
              <div className="row">
                <div className="col-md-6">
                  <h6>Screenshot Information</h6>
                  <table className="table table-sm">
                    <tbody>
                      <tr>
                        <td><strong>URL:</strong></td>
                        <td><code className="text-break">{url}</code></td>
                      </tr>
                      <tr>
                        <td><strong>Upload Date:</strong></td>
                        <td>{formatScreenshotDate(selectedScreenshot.upload_date)}</td>
                      </tr>
                      <tr>
                        <td><strong>File Size:</strong></td>
                        <td>{formatFileSize(selectedScreenshot.file_size)}</td>
                      </tr>
                      {selectedScreenshot.metadata?.program_name && (
                        <tr>
                          <td><strong>Program:</strong></td>
                          <td><Badge bg="primary">{selectedScreenshot.metadata.program_name}</Badge></td>
                        </tr>
                      )}
                      {selectedScreenshot.metadata?.workflow_id && (
                        <tr>
                          <td><strong>Workflow ID:</strong></td>
                          <td><code>{selectedScreenshot.metadata.workflow_id}</code></td>
                        </tr>
                      )}
                      {selectedScreenshot.metadata?.capture_count && (
                        <tr>
                          <td><strong>Capture Count:</strong></td>
                          <td>
                            <Badge bg={hasMultipleCaptures(selectedScreenshot) ? "info" : "secondary"}>
                              {selectedScreenshot.metadata?.capture_count}x
                            </Badge>
                          </td>
                        </tr>
                      )}
                      {selectedScreenshot.metadata?.image_hash && (
                        <tr>
                          <td><strong>Image Hash:</strong></td>
                          <td><code className="small">{selectedScreenshot.metadata.image_hash}</code></td>
                        </tr>
                      )}
                      {(selectedScreenshot.extracted_text || selectedScreenshot.metadata?.extracted_text) && (
                        <tr>
                          <td><strong>Extracted Text:</strong></td>
                          <td>
                            <div
                              className="small p-2 rounded"
                              style={{
                                maxHeight: '200px',
                                overflowY: 'auto',
                                backgroundColor: 'var(--bs-pre-bg)',
                                color: 'var(--bs-pre-color)',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word'
                              }}
                            >
                              {selectedScreenshot.extracted_text || selectedScreenshot.metadata?.extracted_text}
                            </div>
                          </td>
                        </tr>
                      )}
                      {(selectedScreenshot.source || selectedScreenshot.metadata?.source) && (
                        <tr>
                          <td><strong>Source:</strong></td>
                          <td>
                            <Badge bg="secondary">
                              {selectedScreenshot.source || selectedScreenshot.metadata?.source}
                            </Badge>
                          </td>
                        </tr>
                      )}
                      {(selectedScreenshot.source_created_at || selectedScreenshot.metadata?.source_created_at) && (
                        <tr>
                          <td><strong>Source Captured:</strong></td>
                          <td>{formatScreenshotDate(selectedScreenshot.source_created_at || selectedScreenshot.metadata?.source_created_at)}</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="col-md-6">
                  <h6>Capture History</h6>
                  <div className="small" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    {hasMultipleCaptures(selectedScreenshot) && selectedScreenshot.metadata?.capture_timestamps && selectedScreenshot.metadata.capture_timestamps.length > 1 ? (
                      selectedScreenshot.metadata.capture_timestamps.map((timestamp, idx) => (
                        <div key={idx} className="text-muted mb-2">
                          <Badge bg={idx === 0 ? "success" : "info"} className="me-2 small">
                            {idx + 1}
                          </Badge>
                          {formatScreenshotDate(timestamp)}
                          {idx === 0 && <span className="ms-2 small text-success">(First)</span>}
                          {idx === selectedScreenshot.metadata.capture_timestamps.length - 1 && idx > 0 && (
                            <span className="ms-2 small text-warning">(Latest)</span>
                          )}
                        </div>
                      ))
                    ) : (
                      <div className="text-muted">
                        <Badge bg="success" className="me-2 small">1</Badge>
                        {formatScreenshotDate(selectedScreenshot.upload_date)}
                        <span className="ms-2 small text-success">(Single capture)</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button variant="secondary" onClick={() => setShowModal(false)}>
            Close
          </Button>
          {selectedScreenshot && (
            <Button 
              variant="primary" 
              href={getScreenshotUrl(selectedScreenshot)} 
              download
            >
              <i className="fas fa-download"></i> Download
            </Button>
          )}
        </Modal.Footer>
      </Modal>

      {/* Fullscreen Modal */}
      <Modal 
        show={showFullscreen} 
        onHide={() => setShowFullscreen(false)} 
        fullscreen={true}
        className="fullscreen-modal"
      >
        <Modal.Header closeButton className="bg-dark text-white">
          <Modal.Title>
            <i className="fas fa-expand me-2"></i>
            Fullscreen View
          </Modal.Title>
        </Modal.Header>
        <Modal.Body 
          className="p-0 d-flex align-items-center justify-content-center bg-dark"
          style={{ minHeight: '90vh' }}
        >
          {selectedScreenshot && (
            <div className="w-100 h-100 d-flex align-items-center justify-content-center">
              {!fullscreenImageError ? (
                <Image
                  src={getScreenshotUrl(selectedScreenshot)}
                  alt={`Screenshot of ${url}`}
                  style={{ 
                    maxWidth: '100%', 
                    maxHeight: '90vh',
                    objectFit: 'contain'
                  }}
                  onError={() => setFullscreenImageError(true)}
                />
              ) : (
                <div className="text-white d-flex flex-column align-items-center justify-content-center">
                  <i className="fas fa-image" style={{ fontSize: '5rem' }}></i>
                  <p className="mt-3">Image could not be loaded</p>
                </div>
              )}
            </div>
          )}
        </Modal.Body>
        <Modal.Footer className="bg-dark border-top-0">
          <div className="d-flex justify-content-between w-100 align-items-center">
            <div className="text-white">
              <small>
                <i className="fas fa-link me-1"></i>
                {url}
              </small>
            </div>
            <div>
              <Button variant="outline-light" onClick={() => setShowFullscreen(false)} className="me-2">
                <i className="fas fa-compress me-1"></i>
                Exit Fullscreen
              </Button>
              {selectedScreenshot && (
                <Button 
                  variant="primary" 
                  href={getScreenshotUrl(selectedScreenshot)} 
                  download
                >
                  <i className="fas fa-download me-1"></i>
                  Download
                </Button>
              )}
            </div>
          </div>
        </Modal.Footer>
      </Modal>
    </>
  );
}

export default ScreenshotsViewer;
