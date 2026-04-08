import React, { useState, useEffect } from 'react';
import AceEditor from 'react-ace';
import { Alert, Form } from 'react-bootstrap';

import 'ace-builds/src-noconflict/mode-json';
import 'ace-builds/src-noconflict/theme-github';
import 'ace-builds/src-noconflict/theme-monokai';
import 'ace-builds/src-noconflict/ext-language_tools';
import 'ace-builds/src-noconflict/ext-searchbox';

const JsonEditor = ({ 
  value, 
  onChange, 
  placeholder = '', 
  height = '300px',
  theme = 'github',
  readOnly = false,
  showValidation = true,
  className = ''
}) => {
  const [validationError, setValidationError] = useState(null);
  const [isValid, setIsValid] = useState(true);

  useEffect(() => {
    validateJson(value);
  }, [value]);

  const validateJson = (jsonString) => {
    if (!jsonString.trim()) {
      setValidationError(null);
      setIsValid(true);
      return;
    }

    try {
      JSON.parse(jsonString);
      setValidationError(null);
      setIsValid(true);
    } catch (error) {
      setValidationError(error.message);
      setIsValid(false);
    }
  };

  const handleChange = (newValue) => {
    onChange(newValue);
    validateJson(newValue);
  };

  const formatJson = () => {
    try {
      const parsed = JSON.parse(value);
      const formatted = JSON.stringify(parsed, null, 2);
      onChange(formatted);
    } catch (error) {
      // If JSON is invalid, don't format
    }
  };

  const minifyJson = () => {
    try {
      const parsed = JSON.parse(value);
      const minified = JSON.stringify(parsed);
      onChange(minified);
    } catch (error) {
      // If JSON is invalid, don't minify
    }
  };

  return (
    <div className={className}>
      <div className="d-flex justify-content-between align-items-center mb-2">
        <Form.Label className="mb-0">Workflow JSON Definition</Form.Label>
        <div>
          <button
            type="button"
            className="btn btn-sm btn-outline-secondary me-1"
            onClick={formatJson}
            disabled={!isValid || !value.trim()}
            title="Format JSON"
          >
            🎨 Format
          </button>
          <button
            type="button"
            className="btn btn-sm btn-outline-secondary"
            onClick={minifyJson}
            disabled={!isValid || !value.trim()}
            title="Minify JSON"
          >
            📦 Minify
          </button>
        </div>
      </div>

      <div className="position-relative">
        <AceEditor
          mode="json"
          theme={theme}
          value={value}
          onChange={handleChange}
          name="json-editor"
          width="100%"
          height={height}
          fontSize={14}
          showPrintMargin={false}
          showGutter={true}
          highlightActiveLine={true}
          readOnly={readOnly}
          placeholder={value ? '' : placeholder} // Only show placeholder if no value
          setOptions={{
            enableBasicAutocompletion: true,
            enableLiveAutocompletion: true,
            enableSnippets: true,
            showLineNumbers: true,
            tabSize: 2,
            useWorker: false, // Disable web worker for better compatibility
            wrap: true,
            autoScrollEditorIntoView: true,
            minLines: 12,
            maxLines: 30
          }}
          editorProps={{
            $blockScrolling: true
          }}
          style={{
            border: `1px solid ${isValid ? 'var(--bs-border-color)' : 'var(--bs-danger)'}`,
            borderRadius: '0.375rem'
          }}
        />
      </div>

      {showValidation && validationError && (
        <Alert variant="danger" className="mt-2 mb-0">
          <small>
            <strong>JSON Error:</strong> {validationError}
          </small>
        </Alert>
      )}

      {showValidation && isValid && value.trim() && (
        <div className="mt-2">
          <small className="text-success">
            ✅ Valid JSON format
          </small>
        </div>
      )}

      <Form.Text className="text-muted">
        Enter a valid JSON workflow definition. Use Tab for indentation, Ctrl+/ for comments toggle.
      </Form.Text>
    </div>
  );
};

export default JsonEditor;