import React, { useState, useEffect } from 'react';
import { Form, Card, Row, Col, Badge } from 'react-bootstrap';

const VariableInput = ({ variables, onVariableChange, values = {}, errors = {} }) => {
  // Initialize localValues with default values to prevent undefined values
  const initializeValues = () => {
    const initialized = { ...values };
    Object.entries(variables || {}).forEach(([varName, varDef]) => {
      if (initialized[varName] === undefined) {
        initialized[varName] = varDef.default || '';
      }
    });
    return initialized;
  };
  
  const [localValues, setLocalValues] = useState(initializeValues);
  const [arrayProcessingTimeouts, setArrayProcessingTimeouts] = useState({});

  useEffect(() => {
    // Initialize values with defaults if they're undefined
    const initialized = { ...values };
    Object.entries(variables || {}).forEach(([varName, varDef]) => {
      if (initialized[varName] === undefined) {
        initialized[varName] = varDef.default || '';
      }
    });
    setLocalValues(initialized);
  }, [values, variables]);

  const processArrayValue = (value) => {
    if (typeof value === 'string') {
      return value.split(',').map(item => item.trim()).filter(item => item !== '');
    }
    return value;
  };

  const handleInputChange = (varName, value, type) => {
    let processedValue = value;
    
    // Process value based on type
    switch (type) {
      case 'array':
        // For arrays, store the raw string first to allow typing
        processedValue = value;
        
        // Clear any existing timeout for this variable
        if (arrayProcessingTimeouts[varName]) {
          clearTimeout(arrayProcessingTimeouts[varName]);
        }
        
        // Set a timeout to process the array after the user stops typing
        const timeoutId = setTimeout(() => {
          const arrayValue = processArrayValue(value);
          const newValues = {
            ...localValues,
            [varName]: arrayValue
          };
          setLocalValues(newValues);
          onVariableChange(newValues);
        }, 1000); // Process after 1 second of inactivity
        
        setArrayProcessingTimeouts(prev => ({
          ...prev,
          [varName]: timeoutId
        }));
        break;
      case 'number':
        processedValue = value === '' ? '' : Number(value);
        break;
      case 'boolean':
        processedValue = value === 'true' || value === true;
        break;
      default:
        processedValue = value;
    }

    const newValues = {
      ...localValues,
      [varName]: processedValue
    };
    
    setLocalValues(newValues);
    // For non-array types, update immediately
    if (type !== 'array') {
      onVariableChange(newValues);
    }
  };

  // Clean up timeouts on unmount
  useEffect(() => {
    return () => {
      Object.values(arrayProcessingTimeouts).forEach(timeoutId => {
        clearTimeout(timeoutId);
      });
    };
  }, [arrayProcessingTimeouts]);

  const renderInput = (varName, varDef) => {
    const currentValue = localValues[varName] !== undefined ? localValues[varName] : varDef.default;
    const hasError = errors[varName];

    switch (varDef.type) {
      case 'array':
        return (
          <Form.Control
            type="text"
            value={Array.isArray(currentValue) ? currentValue.join(', ') : (currentValue || '')}
            onChange={(e) => handleInputChange(varName, e.target.value, 'array')}
            placeholder="Enter comma-separated values (e.g., domain.com, example.com)"
            isInvalid={hasError}
          />
        );
      
      case 'number':
        return (
          <Form.Control
            type="number"
            value={currentValue || ''}
            onChange={(e) => handleInputChange(varName, e.target.value, 'number')}
            placeholder="Enter number"
            isInvalid={hasError}
          />
        );
      
      case 'boolean':
        return (
          <Form.Select
            value={currentValue ? 'true' : 'false'}
            onChange={(e) => handleInputChange(varName, e.target.value, 'boolean')}
            isInvalid={hasError}
          >
            <option value="true">True</option>
            <option value="false">False</option>
          </Form.Select>
        );
      
      default:
        return (
          <Form.Control
            type="text"
            value={currentValue || ''}
            onChange={(e) => handleInputChange(varName, e.target.value, 'string')}
            placeholder="Enter value"
            isInvalid={hasError}
          />
        );
    }
  };

  const getTypeColor = (type) => {
    const colors = {
      string: 'primary',
      array: 'info',
      number: 'warning',
      boolean: 'success'
    };
    return colors[type] || 'secondary';
  };

  if (!variables || Object.keys(variables).length === 0) {
    return null;
  }

  return (
    <Card>
      <Card.Header>
        <h6 className="mb-0">
          📝 Workflow Variables
          <Badge bg="secondary" className="ms-2">
            {Object.keys(variables).length} variable{Object.keys(variables).length !== 1 ? 's' : ''}
          </Badge>
        </h6>
      </Card.Header>
      <Card.Body>
        <p className="text-muted mb-3">
          Configure the variables for this workflow template:
        </p>
        
        <Row>
          {Object.entries(variables).map(([varName, varDef]) => (
            <Col md={6} key={varName} className="mb-3">
              <Form.Group>
                <Form.Label>
                  <div className="d-flex align-items-center">
                    <span className="me-2">{varName}</span>
                    <Badge bg={getTypeColor(varDef.type)} className="me-2">
                      {varDef.type}
                    </Badge>
                    {varDef.required && (
                      <Badge bg="danger">required</Badge>
                    )}
                  </div>
                </Form.Label>
                {renderInput(varName, varDef)}
                {varDef.description && (
                  <Form.Text className="text-muted">
                    {varDef.description}
                  </Form.Text>
                )}
                {errors[varName] && (
                  <div className="invalid-feedback d-block">
                    {errors[varName]}
                  </div>
                )}
              </Form.Group>
            </Col>
          ))}
        </Row>
      </Card.Body>
    </Card>
  );
};

export default VariableInput; 