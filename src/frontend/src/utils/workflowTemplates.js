// Utility functions for handling workflow templates with variables

/**
 * Extract variables from workflow template
 * @param {object} workflowTemplate - The workflow template object
 * @returns {string[]} Array of variable names found in template
 */
export const extractVariables = (workflowTemplate) => {
  const variables = new Set();
  const variableRegex = /\{\{([^}]+)\}\}/g;
  
  const searchObject = (obj) => {
    if (typeof obj === 'string') {
      let match;
      while ((match = variableRegex.exec(obj)) !== null) {
        variables.add(match[1].trim());
      }
    } else if (Array.isArray(obj)) {
      obj.forEach(item => searchObject(item));
    } else if (obj && typeof obj === 'object') {
      Object.values(obj).forEach(value => searchObject(value));
    }
  };

  searchObject(workflowTemplate);
  return Array.from(variables);
};

/**
 * Validate that all required variables are provided
 * @param {object} workflowTemplate - The workflow template
 * @param {object} variables - Variable values provided by user
 * @returns {object} Validation result with success boolean and errors array
 */
export const validateVariables = (workflowTemplate, variables) => {
  const requiredVars = extractVariables(workflowTemplate);
  const errors = [];
  
  requiredVars.forEach(varName => {
    if (!variables.hasOwnProperty(varName) || variables[varName] === '' || variables[varName] == null) {
      errors.push(`Variable "${varName}" is required but not provided`);
    }
  });

  return {
    success: errors.length === 0,
    errors,
    requiredVariables: requiredVars
  };
};

/**
 * Process workflow template by replacing variables with actual values
 * @param {object} workflowTemplate - The workflow template object
 * @param {object} variables - Variable values to substitute
 * @returns {object} Processed workflow with variables replaced
 */
export const processTemplate = (workflowTemplate, variables) => {
  
  const processValue = (value) => {
    if (typeof value === 'string') {
      // Check if the entire string is just a single variable
      const singleVarMatch = value.trim().match(/^\{\{([^}]+)\}\}$/);
      if (singleVarMatch) {
        const trimmedVarName = singleVarMatch[1].trim();
        if (variables.hasOwnProperty(trimmedVarName)) {
          const varValue = variables[trimmedVarName];

          // For single variables, return the value directly (including arrays)
          return varValue;
        }
      }
      
      // Handle multiple variables or partial replacement
      return value.replace(/\{\{([^}]+)\}\}/g, (match, varName) => {
        const trimmedVarName = varName.trim();
        if (variables.hasOwnProperty(trimmedVarName)) {
          const varValue = variables[trimmedVarName];
          // For embedded variables, convert arrays to strings
          if (Array.isArray(varValue)) {
            return varValue.join(',');
          }
          return varValue;
        }
        return match; // Return original if variable not found
      });
    } else if (Array.isArray(value)) {
      // Handle array processing with flattening for single-variable arrays
      const processedItems = value.map(item => processValue(item));
      
      // If the original array has only one item and it's a single variable that resolves to an array,
      // return the resolved array directly (flatten it)
      if (value.length === 1 && typeof value[0] === 'string') {
        const singleVarMatch = value[0].trim().match(/^\{\{([^}]+)\}\}$/);
        if (singleVarMatch && Array.isArray(processedItems[0])) {
          return processedItems[0];
        }
      }
      
      return processedItems;
    } else if (value && typeof value === 'object') {
      const processed = {};
      Object.keys(value).forEach(key => {
        processed[key] = processValue(value[key]);
      });
      return processed;
    }
    return value;
  };

  const result = processValue(workflowTemplate);
  return result;
};

/**
 * Get variable type based on its default value or usage context
 * @param {string} varName - Variable name
 * @param {any} defaultValue - Default value if provided
 * @returns {string} Variable type (string, array, number, boolean)
 */
export const getVariableType = (varName, defaultValue) => {
  if (defaultValue !== undefined) {
    if (Array.isArray(defaultValue)) return 'array';
    if (typeof defaultValue === 'number') return 'number';
    if (typeof defaultValue === 'boolean') return 'boolean';
    return 'string';
  }
  
  // Infer type from variable name patterns
  if (varName.toLowerCase().includes('port') || varName.toLowerCase().includes('timeout')) {
    return 'number';
  }
  if (varName.toLowerCase().includes('domain') || varName.toLowerCase().includes('url')) {
    return 'array';
  }
  
  return 'string';
};

/**
 * Generate variable definitions from workflow template
 * @param {object} workflowTemplate - The workflow template
 * @param {object} existingVariables - Existing variable definitions
 * @returns {object} Variable definitions with inferred types and descriptions
 */
export const generateVariableDefinitions = (workflowTemplate, existingVariables = {}) => {
  const extractedVars = extractVariables(workflowTemplate);
  const definitions = {};
  
  extractedVars.forEach(varName => {
    if (existingVariables[varName]) {
      definitions[varName] = existingVariables[varName];
    } else {
      definitions[varName] = {
        type: getVariableType(varName),
        description: `Variable: ${varName}`,
        required: true,
        default: ''
      };
    }
  });
  
  return definitions;
};

/**
 * Default workflow templates with variables
 */
export const defaultTemplates = {
  subdomain_discovery: {
    workflow_name: "subdomain_discovery_template",
    variables: {
      target_domain: {
        type: "string",
        description: "Domain to discover subdomains for",
        required: true,
        default: "example.com"
      },
      scan_ports: {
        type: "string",
        description: "Ports to scan (comma separated)",
        required: false,
        default: "80,443,8080,8443"
      }
    },
    steps: [
      {
        name: "subdomain_discovery",
        tasks: [
          {
            name: "subdomain_finder",
            input: ["{{target_domain}}"],
            force: true
          }
        ]
      },
      {
        name: "dns_resolution",
        tasks: [
          {
            name: "resolve_domain",
            input_from: ["subdomain_discovery"],
            force: true
          }
        ]
      },
      {
        name: "port_scanning",
        tasks: [
          {
            name: "port_scan",
            input_from: ["dns_resolution"],
            params: {
              ports: "{{scan_ports}}"
            },
            force: true
          }
        ]
      }
    ]
  },
  nuclei_vulnerability_scan: {
    workflow_name: "nuclei_vulnerability_scan_template",
    variables: {
      target_urls: {
        type: "array",
        description: "URLs to scan for vulnerabilities",
        required: true,
        default: ["https://example.com"]
      },
      nuclei_base_templates: {
        type: "array",
        description: "Base nuclei template categories to use",
        required: false,
        default: ["http/technologies"]
      },
      nuclei_custom_templates: {
        type: "array",
        description: "Custom nuclei template IDs to use",
        required: false,
        default: []
      }
    },
    steps: [
      {
        name: "url_discovery",
        tasks: [
          {
            name: "test_http",
            input: "{{target_urls}}",
            force: true
          }
        ]
      },
      {
        name: "vulnerability_scan",
        tasks: [
          {
            name: "nuclei_scan",
            input_from: ["url_discovery"],
            params: {
              template: {
                base: "{{nuclei_base_templates}}",
                custom: "{{nuclei_custom_templates}}"
              }
            },
            force: true
          }
        ]
      }
    ]
  }
}; 