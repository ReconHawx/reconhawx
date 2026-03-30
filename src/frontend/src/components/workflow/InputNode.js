import React from 'react';
import { Handle, Position } from 'reactflow';
import { Badge } from 'react-bootstrap';
import { useTheme } from '../../contexts/ThemeContext';

const InputNode = ({ data, selected }) => {
  const { isDark } = useTheme();

  // Handle empty state
  if (data.isEmpty) {
    return (
      <div
        style={{
          padding: '15px 20px',
          borderRadius: '8px',
          background: isDark
            ? 'linear-gradient(145deg, #121c2f 0%, #0d1422 100%)'
            : 'linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%)',
          border: `2px dashed ${selected ? (isDark ? '#00f2ff' : '#0d6efd') : isDark ? '#5c6d80' : '#6c757d'}`,
          minWidth: '250px',
          fontSize: '14px',
          boxShadow: selected
            ? (isDark ? '0 4px 20px rgba(0, 242, 255, 0.15)' : '0 4px 12px rgba(0,0,0,0.15)')
            : (isDark ? '0 2px 12px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.1)'),
          textAlign: 'center',
          color: isDark ? '#f0fbff' : '#212529',
        }}
      >
        <div className="d-flex align-items-center justify-content-center mb-2">
          <span className="me-2" style={{fontSize: '20px'}}>📥</span>
          <strong>Data Sources</strong>
        </div>
        <div style={{ fontSize: '12px', color: isDark ? '#9db4c4' : '#6c757d' }}>
          <small>Click "Configure Inputs" to add data sources</small>
        </div>
      </div>
    );
  }

  const dataType = data.type === 'direct' ? data.value_type :
                   data.type === 'program_finding' ? data.finding_type :
                   data.type === 'program_protected_domains' || data.type === 'program_scope_domains' ? 'domains' :
                   data.asset_type;

  const getAssetTypeDisplayName = (assetType) => {
    const displayNames = {
      'apex-domain': 'Apex Domain',
      'subdomain': 'Subdomain',
      'ip': 'IP Address',
      'cidr': 'CIDR Block',
      'url': 'URL',
      'typosquat_url': 'Typosquat URL',
      'typosquat_domain': 'Typosquat Domains',
      'typosquat_apex_domain': 'Typosquat Apex Domains',
      'external_link': 'External Link'
    };
    return displayNames[assetType] || assetType;
  };

  const showSimilarity = data.type === 'program_finding' &&
    (data.finding_type === 'typosquat_domain' || data.finding_type === 'typosquat_apex_domain') &&
    data.min_similarity_percent != null;

  const getFilterDisplayName = (filterType, assetType) => {
    if (!filterType) return '';

    if (assetType === 'subdomain') {
      return filterType === 'resolved' ? ' (with IP)' : ' (no IP)';
    } else if (assetType === 'ip') {
      return filterType === 'resolved' ? ' (with PTR)' : ' (no PTR)';
    } else if (assetType === 'url' || assetType === 'typosquat_url') {
      return filterType === 'root' ? ' (Root Only)' : '';
    }
    return '';
  };

  return (
    <div
      style={{
        padding: '15px 20px',
        borderRadius: '8px',
        background: isDark
          ? 'linear-gradient(145deg, #152a38 0%, #121c2f 100%)'
          : 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)',
        border: `2px solid ${selected ? (isDark ? '#00f2ff' : '#0d6efd') : isDark ? 'rgba(0, 242, 255, 0.45)' : '#1976d2'}`,
        minWidth: '250px',
        fontSize: '14px',
        boxShadow: selected
          ? (isDark ? '0 4px 20px rgba(0, 242, 255, 0.15)' : '0 4px 12px rgba(0,0,0,0.15)')
          : (isDark ? '0 2px 12px rgba(0,0,0,0.35)' : '0 2px 8px rgba(0,0,0,0.1)'),
        color: isDark ? '#f0fbff' : '#212529',
      }}
    >
      <div className="d-flex align-items-center mb-2">
        <span className="me-2" style={{fontSize: '20px'}}>📥</span>
        <strong>Input: {data.name}</strong>
      </div>
      <div style={{ fontSize: '12px', color: isDark ? '#9db4c4' : '#555', marginBottom: '10px' }}>
        <small>
          <strong>Type: </strong>
          <Badge
            bg={data.type === 'direct' ? 'warning' : data.type === 'program_finding' ? 'danger' : data.type === 'program_protected_domains' || data.type === 'program_scope_domains' ? 'secondary' : 'info'}
            text={data.type === 'direct' ? 'dark' : 'white'}
          >
            {data.type === 'direct' ? 'Direct' : data.type === 'program_finding' ? 'Program Finding' : data.type === 'program_protected_domains' ? 'Program Protected Domains' : data.type === 'program_scope_domains' ? 'Program Scope Domains' : 'Program Asset'}
          </Badge>
        </small>
        <br />
        <small>
          <strong>Data: </strong>
          <Badge bg="secondary">
            {data.type === 'program_protected_domains' ? 'Protected Domains' : data.type === 'program_scope_domains' ? 'Scope Domains' : getAssetTypeDisplayName(dataType)}{getFilterDisplayName(data.filter_type, dataType)}
            {showSimilarity ? ` ≥${data.min_similarity_percent}% similarity` : ''}
          </Badge>
        </small>
      </div>
      
      {/* Invisible output handle - edges connect to node edge, no visual misalignment */}
      <Handle
        type="source"
        position={Position.Right}
        id="output"
        className="workflow-node-handle-invisible"
      />
    </div>
  );
};

export default InputNode;