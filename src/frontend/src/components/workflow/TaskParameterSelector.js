import React from 'react';
import { Form, Card } from 'react-bootstrap';
import { TASK_TYPES } from './constants';
import NucleiTemplateSelector from './NucleiTemplateSelector';
import WordlistSelector from './WordlistSelector';

function TaskParameterSelector({
  taskType,
  taskParams = {},
  onParameterChange,
  // Nuclei template props
  selectedOfficialTemplates = new Set(),
  selectedCustomTemplates = [],
  onOfficialTemplatesChange,
  onCustomTemplatesChange,
  // Wordlist props
  selectedWordlist,
  customWordlistUrl,
  wordlistInputType,
  onWordlistChange,
  onCustomUrlChange,
  onInputTypeChange,
  // Output mode props
  outputMode,
  onOutputModeChange,
  // Node update callback for immediate updates
  selectedNode,
  updateNodeData
}) {
  const taskConfig = TASK_TYPES[taskType];
  const onParameterChangeRef = React.useRef(onParameterChange);
  onParameterChangeRef.current = onParameterChange;

  // Initialize taskParams with default values for parameters that haven't been explicitly set.
  // Only depend on taskType/taskParams so we don't re-run on every parent render (onParameterChange is inline and would reset wordlist state).
  React.useEffect(() => {
    if (!taskConfig || !taskConfig.params) {
      return;
    }

    const updatedParams = { ...taskParams };
    let hasChanges = false;

    Object.entries(taskConfig.params).forEach(([paramName, paramConfig]) => {
      // Skip auto-setting timeout - allow it to be optional
      if (paramName === 'timeout') {
        return; // Don't auto-set timeout default
      }
      if (updatedParams[paramName] === undefined && paramConfig.default !== undefined) {
        updatedParams[paramName] = paramConfig.default;
        hasChanges = true;
      }
    });

    if (hasChanges) {
      onParameterChangeRef.current(updatedParams);
    }
  }, [taskType, taskConfig, taskParams]);

  if (!taskConfig || !taskConfig.params) {
    return null;
  }

  const handleParamChange = (paramName, value) => {
    const updatedParams = { ...taskParams };
    updatedParams[paramName] = value;
    onParameterChange(updatedParams);
  };

  const handleArrayParamChange = (paramName, textareaValue) => {
    // Process the textarea value into an array
    const lines = textareaValue.split('\n');
    
    // For command arguments, preserve spaces within each argument
    // For other parameters, trim whitespace as before
    const processedLines = lines
      .map(line => {
        if (paramName === 'cmd_args' || paramName === 'command') {
          // Preserve spaces for command arguments and commands
          return line;
        } else {
          // Trim whitespace for other array parameters
          return line.trim();
        }
      })
      .filter(line => line.length > 0);

    handleParamChange(paramName, processedLines);
  };

  const renderParameterInput = (paramName, paramConfig) => {
    // For timeout, use empty string if not set (don't use default)
    const isTimeout = paramName === 'timeout';
    const currentValue = taskParams[paramName] !== undefined 
      ? taskParams[paramName] 
      : (isTimeout ? '' : paramConfig.default);

    switch (paramConfig.type) {
      case 'boolean':
        return (
          <Form.Check
            type="checkbox"
            checked={currentValue}
            onChange={(e) => handleParamChange(paramName, e.target.checked)}
          />
        );

      case 'number':
        return (
          <Form.Control
            type="number"
            value={isTimeout && (currentValue === undefined || currentValue === '') ? '' : currentValue}
            onChange={(e) => {
              const value = e.target.value.trim();
              if (isTimeout && value === '') {
                // Clear timeout - remove from params
                const updatedParams = { ...taskParams };
                delete updatedParams[paramName];
                onParameterChange(updatedParams);
              } else {
                const numValue = parseInt(value);
                if (!isNaN(numValue) && numValue > 0) {
                  handleParamChange(paramName, numValue);
                } else if (isTimeout) {
                  // Invalid timeout - remove from params
                  const updatedParams = { ...taskParams };
                  delete updatedParams[paramName];
                  onParameterChange(updatedParams);
                } else {
                  // For non-timeout numbers, fall back to default
                  handleParamChange(paramName, parseInt(value) || paramConfig.default);
                }
              }
            }}
            placeholder={isTimeout ? 'Use system default' : undefined}
          />
        );

      case 'array':
        const textareaValue = Array.isArray(currentValue) ? currentValue.join('\n') : '';
        return (
          <>
            <Form.Control
              as="textarea"
              rows={4}
              value={textareaValue}
              onChange={(e) => handleArrayParamChange(paramName, e.target.value)}
              placeholder={getPlaceholderText(paramName)}
            />
            <Form.Text className="text-muted">
              {getHelpText(paramName)}
            </Form.Text>
          </>
        );

      case 'string':
      default:
        return (
          <Form.Control
            type="text"
            value={currentValue}
            onChange={(e) => handleParamChange(paramName, e.target.value)}
            placeholder={paramConfig.description}
          />
        );
    }
  };

  const getPlaceholderText = (paramName) => {
    switch (paramName) {
      case 'cmd_args':
        return 'Enter each command argument on a separate line\nExample:\n-silent\n-rate-limit 100\n-severity high\n--header "Authorization: Bearer token"';
      case 'command':
        return 'Enter each command on a separate line\nExample:\necho "Hello World"\nls -la /tmp\ncat /etc/passwd';
      case 'fuzzers':
        return 'Enter each fuzzer on a separate line\nExample:\naddition\nbitsquatting\ndictionary';
      default:
        return `Enter each item on a separate line`;
    }
  };

  const getHelpText = (paramName) => {
    switch (paramName) {
      case 'cmd_args':
        return 'Enter each command argument on a separate line. Spaces within arguments are preserved.';
      case 'command':
        return 'Enter each command on a separate line. Commands will be executed in order. Spaces are preserved.';
      case 'fuzzers':
        return 'Enter each fuzzer on a separate line. Available fuzzers depend on dnstwist.';
      default:
        return 'Enter each item on a separate line. You can include spaces within each item.';
    }
  };

  // Special handling for nuclei_scan template parameter
  if (taskType === 'nuclei_scan' && taskConfig.params.template) {
    return (
      <Card>
        <Card.Header>
          <h6 className="mb-0">🔬 Nuclei Scan Parameters</h6>
        </Card.Header>
        <Card.Body>
          <NucleiTemplateSelector
            selectedOfficialTemplates={selectedOfficialTemplates}
            selectedCustomTemplates={selectedCustomTemplates}
            onOfficialTemplatesChange={onOfficialTemplatesChange}
            onCustomTemplatesChange={onCustomTemplatesChange}
          />

          {/* Render cmd_args parameter */}
          {Object.entries(taskConfig.params).map(([paramName, paramConfig]) => {
            if (paramName === 'template') return null; // Handled by NucleiTemplateSelector

            // Special handling for timeout
            if (paramName === 'timeout') {
              return (
                <Form.Group key={paramName} className="mb-3">
                  <Form.Label>{paramName}</Form.Label>
                  {renderParameterInput(paramName, paramConfig)}
                  <Form.Text className="text-muted">
                    Optional: Overrides system default timeout. Leave empty to use system default.
                  </Form.Text>
                </Form.Group>
              );
            }

            return (
              <Form.Group key={paramName} className="mb-3">
                <Form.Label>{paramName}</Form.Label>
                {renderParameterInput(paramName, paramConfig)}
                <Form.Text className="text-muted">
                  {paramConfig.description}
                </Form.Text>
              </Form.Group>
            );
          })}
        </Card.Body>
      </Card>
    );
  }

  // Special handling for subdomain_permutations permutation_list parameter
  if (taskType === 'subdomain_permutations' && taskConfig.params.permutation_list) {
    return (
      <Card>
        <Card.Header>
          <h6 className="mb-0">🔀 Subdomain Permutation Parameters</h6>
        </Card.Header>
        <Card.Body>
          <Form.Group className="mb-3">
            <Form.Label>
              <strong>Permutation List</strong>
            </Form.Label>
            <WordlistSelector
              selectedWordlist={selectedWordlist}
              customWordlistUrl={customWordlistUrl}
              wordlistInputType={wordlistInputType}
              onWordlistChange={(wordlist) => {
                // Update the permutation_list parameter when wordlist changes
                const newParams = { ...taskParams };
                if (wordlistInputType === 'url') {
                  newParams.permutation_list = customWordlistUrl;
                } else if (wordlist) {
                  newParams.permutation_list = wordlist.id;
                } else {
                  newParams.permutation_list = 'files/permutations.txt';
                }
                onParameterChange(newParams);
                if (onWordlistChange) onWordlistChange(wordlist);
              }}
              onCustomUrlChange={(url) => {
                // Update the permutation_list parameter when URL changes
                const newParams = { ...taskParams };
                newParams.permutation_list = url;
                onParameterChange(newParams);
                if (onCustomUrlChange) onCustomUrlChange(url);
              }}
              onInputTypeChange={onInputTypeChange}
            />
            <Form.Text className="text-muted">
              Select a wordlist from the database, provide a custom URL, or use the default permutation list.
              The permutation list contains words that will be combined with your domains.
            </Form.Text>
          </Form.Group>

          {/* Render other parameters */}
          {Object.entries(taskConfig.params).map(([paramName, paramConfig]) => {
            if (paramName === 'permutation_list') return null; // Handled by WordlistSelector

            // Special handling for timeout
            if (paramName === 'timeout') {
              return (
                <Form.Group key={paramName} className="mb-3">
                  <Form.Label>{paramName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</Form.Label>
                  {renderParameterInput(paramName, paramConfig)}
                  <Form.Text className="text-muted">
                    Optional: Overrides system default timeout. Leave empty to use system default.
                  </Form.Text>
                </Form.Group>
              );
            }

            return (
              <Form.Group key={paramName} className="mb-3">
                <Form.Label>{paramName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</Form.Label>
                {renderParameterInput(paramName, paramConfig)}
                <Form.Text className="text-muted">
                  {paramConfig.description}
                </Form.Text>
              </Form.Group>
            );
          })}
        </Card.Body>
      </Card>
    );
  }

  // Special handling for dns_bruteforce wordlist parameter
  if (taskType === 'dns_bruteforce' && taskConfig.params.wordlist) {
    return (
      <Card>
        <Card.Header>
          <h6 className="mb-0">🔨 DNS Bruteforce Parameters</h6>
        </Card.Header>
        <Card.Body>
          <Form.Group className="mb-3">
            <Form.Label>
              <strong>Subdomain Wordlist</strong>
            </Form.Label>
            <WordlistSelector
              selectedWordlist={selectedWordlist}
              customWordlistUrl={customWordlistUrl}
              wordlistInputType={wordlistInputType}
              onWordlistChange={(wordlist) => {
                // Update the wordlist parameter when wordlist changes
                const newParams = { ...taskParams };
                if (wordlistInputType === 'url') {
                  newParams.wordlist = customWordlistUrl;
                } else if (wordlist) {
                  newParams.wordlist = wordlist.id;
                } else {
                  newParams.wordlist = '/workspace/files/subdomains.txt';
                }
                onParameterChange(newParams);
                if (onWordlistChange) onWordlistChange(wordlist);
              }}
              onCustomUrlChange={(url) => {
                // Update the wordlist parameter when URL changes
                const newParams = { ...taskParams };
                newParams.wordlist = url;
                onParameterChange(newParams);
                if (onCustomUrlChange) onCustomUrlChange(url);
              }}
              onInputTypeChange={onInputTypeChange}
            />
            <Form.Text className="text-muted">
              Select a subdomain wordlist from the database, provide a custom URL, or use the default wordlist.
              The wordlist contains subdomain prefixes to test against the target domain.
            </Form.Text>
          </Form.Group>

          {/* Output Mode Selection */}
          <Form.Group className="mb-3">
            <Form.Label>
              <strong>Output Mode</strong>
            </Form.Label>
            <Form.Select
              value={outputMode || ''}
              onChange={(e) => {
                const newValue = e.target.value || '';
                if (onOutputModeChange) {
                  onOutputModeChange(newValue);
                }
              }}
            >
              <option value="">Assets (Default) - Produce subdomain and IP assets</option>
              <option value="typosquat_findings">Typosquat Findings - Produce typosquat domain findings</option>
            </Form.Select>
            <Form.Text className="text-muted">
              Choose whether this task should produce subdomain assets (normal mode) or typosquat domain findings (for typosquat detection workflows).
            </Form.Text>
          </Form.Group>

          {/* Render other parameters */}
          {Object.entries(taskConfig.params).map(([paramName, paramConfig]) => {
            if (paramName === 'wordlist') return null; // Handled by WordlistSelector

            // Special handling for timeout
            if (paramName === 'timeout') {
              return (
                <Form.Group key={paramName} className="mb-3">
                  <Form.Label>{paramName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</Form.Label>
                  {renderParameterInput(paramName, paramConfig)}
                  <Form.Text className="text-muted">
                    Optional: Overrides system default timeout. Leave empty to use system default.
                  </Form.Text>
                </Form.Group>
              );
            }

            return (
              <Form.Group key={paramName} className="mb-3">
                <Form.Label>{paramName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</Form.Label>
                {renderParameterInput(paramName, paramConfig)}
                <Form.Text className="text-muted">
                  {paramConfig.description}
                </Form.Text>
              </Form.Group>
            );
          })}
        </Card.Body>
      </Card>
    );
  }

  // Special handling for fuzz_website wordlist parameter
  if (taskType === 'fuzz_website' && taskConfig.params.wordlist) {
    return (
      <Card>
        <Card.Header>
          <h6 className="mb-0">🕷️ Website Fuzzing Parameters</h6>
        </Card.Header>
        <Card.Body>
          <WordlistSelector
            selectedWordlist={selectedWordlist}
            customWordlistUrl={customWordlistUrl}
            wordlistInputType={wordlistInputType}
            onWordlistChange={(wordlist) => {
              const newParams = { ...taskParams };
              if (wordlistInputType === 'url') {
                newParams.wordlist = customWordlistUrl;
              } else if (wordlist) {
                newParams.wordlist = wordlist.id;
              } else {
                newParams.wordlist = '/workspace/files/webcontent_test.txt';
              }
              onParameterChange(newParams);
              if (onWordlistChange) onWordlistChange(wordlist);
            }}
            onCustomUrlChange={(url) => {
              const newParams = { ...taskParams };
              newParams.wordlist = url;
              onParameterChange(newParams);
              if (onCustomUrlChange) onCustomUrlChange(url);
            }}
            onInputTypeChange={onInputTypeChange}
          />

          {/* Output Mode Selection */}
          <Form.Group className="mb-3 mt-4">
            <Form.Label>
              <strong>Output Mode</strong>
            </Form.Label>
            <Form.Select
              value={outputMode || ''}
              onChange={(e) => {
                const newValue = e.target.value || '';
                if (onOutputModeChange) {
                  onOutputModeChange(newValue);
                } else {
                  console.error('[TaskParameterSelector] onOutputModeChange is not defined!');
                }
              }}
            >
              <option value="">Assets (Default) - Produce URL assets</option>
              <option value="typosquat_findings">Typosquat Findings - Produce typosquat URL findings</option>
            </Form.Select>
            <Form.Text className="text-muted">
              Choose whether this task should produce URL assets (normal mode) or typosquat URL findings (for typosquat detection workflows).
              In typosquat findings mode, URLs are enriched with risk scoring and domain context.
            </Form.Text>
          </Form.Group>

          {/* Render other parameters */}
          {Object.entries(taskConfig.params).map(([paramName, paramConfig]) => {
            if (paramName === 'wordlist') return null; // Handled by WordlistSelector

            // Special handling for timeout
            if (paramName === 'timeout') {
              return (
                <Form.Group key={paramName} className="mb-3">
                  <Form.Label>{paramName}</Form.Label>
                  {renderParameterInput(paramName, paramConfig)}
                  <Form.Text className="text-muted">
                    Optional: Overrides system default timeout. Leave empty to use system default.
                  </Form.Text>
                </Form.Group>
              );
            }

            return (
              <Form.Group key={paramName} className="mb-3">
                <Form.Label>{paramName}</Form.Label>
                {renderParameterInput(paramName, paramConfig)}
                <Form.Text className="text-muted">
                  {paramConfig.description}
                </Form.Text>
              </Form.Group>
            );
          })}
        </Card.Body>
      </Card>
    );
  }

  // Default parameter rendering for other tasks
  const hasParams = Object.keys(taskConfig.params).length > 0;
  if (!hasParams) {
    return null;
  }

  return (
    <Card>
      <Card.Header>
        <h6 className="mb-0">⚙️ Task Parameters</h6>
      </Card.Header>
      <Card.Body>
        {Object.entries(taskConfig.params).map(([paramName, paramConfig]) => {
          // Special handling for timeout
          if (paramName === 'timeout') {
            return (
              <Form.Group key={paramName} className="mb-3">
                <Form.Label>{paramName}</Form.Label>
                {renderParameterInput(paramName, paramConfig)}
                <Form.Text className="text-muted">
                  Optional: Overrides system default timeout. Leave empty to use system default.
                </Form.Text>
              </Form.Group>
            );
          }
          return (
            <Form.Group key={paramName} className="mb-3">
              <Form.Label>{paramName}</Form.Label>
              {renderParameterInput(paramName, paramConfig)}
              <Form.Text className="text-muted">
                {paramConfig.description}
              </Form.Text>
            </Form.Group>
          );
        })}
      </Card.Body>
    </Card>
  );
}

export default TaskParameterSelector;
