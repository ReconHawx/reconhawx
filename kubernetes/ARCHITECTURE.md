# Recon Kubernetes Architecture

## Overview
This document describes the optimized Kubernetes architecture for the Recon project, implementing best practices for resource management, security, and configuration management.

## Architecture Changes Summary

### Phase 1: Namespace Consolidation ✅
- **Goal**: Standardize all services to use a single "recon" namespace
- **Impact**: Simplified networking, consistent resource management, reduced complexity
- **Changes**: 
  - Consolidated dev, local, prod, vrev namespaces → single "recon" namespace
  - Updated all service references and environment variables

### Phase 2: Overlay Consolidation ✅ 
- **Goal**: Reduce complexity while preserving meaningful environment differences
- **Impact**: Streamlined deployment process, easier maintenance
- **Changes**:
  - Core services (MongoDB, NATS, Redis, Kueue): Single consolidated overlay
  - Application services (API, Frontend): Keep dev/prod variants for registry/resource differences
  - Reduced from 28+ directories to 12 directories

### Phase 3: Configuration Cleanup ✅
- **Goal**: Standardize configurations and remove inconsistencies
- **Impact**: Improved reliability, consistent behavior across environments
- **Changes**:
  - Fixed environment labels and service connections
  - Removed redundant configurations
  - Corrected registry configurations

### Phase 4: Advanced Optimization & Standardization ✅
- **Goal**: Implement enterprise-grade standards for resource management, security, and monitoring
- **Impact**: Production-ready infrastructure with proper governance

## Current Architecture

### Service Categories

#### Persistent Services (Always Running)
```
Core Infrastructure:
├── nats        # Message broker
├── redis       # Caching and session storage
└── kueue       # Job scheduling

Application Services:
├── api         # Backend API service
└── frontend    # Web interface
```

#### On-Demand Resources
```
Job Templates:
├── runner      # Workflow orchestration (instantiated by API)
└── worker      # Task execution (started by runners)
```

### Directory Structure
```
kubernetes/
├── base/                           # Base configurations
│   ├── config/                     # Centralized configuration management
│   │   ├── service-config.yaml     # Service URLs and common config
│   │   ├── resource-quota.yaml     # Namespace resource limits
│   │   ├── monitoring.yaml         # Health check configurations
│   │   ├── resource-profiles.yaml  # Standardized resource templates
│   │   └── security-policies.yaml  # Network security policies
│   ├── nats/                       # Message broker base configs
│   ├── api/                        # API base configs
│   └── frontend/                   # Frontend base configs
│
└── overlays/                       # Environment-specific overlays
    ├── kustomization.yaml          # Default (dev) consolidated overlay
    ├── production/                 # Production consolidated overlay
    ├── nats/
    ├── redis/
    ├── kueue/
    ├── api/dev/ & api/prod/       # App services with variants
    ├── frontend/dev/ & frontend/prod/
    └── [worker/runner]             # Available as job templates
```

## Configuration Management

### Centralized Configuration
All common configuration values are now managed through ConfigMaps:

#### `recon-config` ConfigMap
- Service URLs and endpoints
- Database connection parameters
- Kubernetes namespace and service account references
- Common application settings

#### `resource-profiles` ConfigMap  
- Standardized resource allocation templates
- Different profiles for micro, standard, database, messaging, and job services
- Production multipliers for scaling resources

#### `monitoring-config` ConfigMap
- Health check endpoints and probe configurations
- Monitoring and metrics settings

### Environment-Specific Values
Services reference ConfigMap values using `valueFrom.configMapKeyRef`, allowing:
- Centralized configuration management
- Easy updates without redeployment
- Consistent values across services
- Environment-specific overrides when needed

## Resource Management

### Resource Quotas
The namespace enforces the following limits:
- **CPU**: 4 cores requests, 8 cores limits
- **Memory**: 8Gi requests, 16Gi limits  
- **Storage**: 50Gi total
- **Objects**: Reasonable limits on deployments, jobs, services

### Resource Profiles
Standardized resource allocation based on service type:

| Profile | CPU Request | Memory Request | CPU Limit | Memory Limit | Use Case |
|---------|-------------|----------------|-----------|--------------|----------|
| Micro | 100m | 128Mi | 500m | 512Mi | Lightweight services |
| Standard | 200m | 256Mi | 1000m | 1Gi | Most services |
| Database | 250m | 512Mi | 1000m | 2Gi | MongoDB, Redis |
| Messaging | 200m | 256Mi | 500m | 512Mi | NATS |
| Job | 100m | 128Mi | 2000m | 4Gi | Workers, Runners |

Production environments apply 2x multipliers for CPU and memory.

### LimitRange Enforcement
- **Container Defaults**: 500m CPU, 512Mi memory limits
- **Container Minimums**: 50m CPU, 64Mi memory
- **Pod Maximums**: 4 CPU, 8Gi memory

## Security Policies

### Network Policies
Implements zero-trust networking with explicit allowlists:

#### `default-deny-all`
- Blocks all ingress and egress traffic by default
- Requires explicit policies for communication

#### Service-Specific Policies
- **API**: Can receive from frontend and ingress, connect to MongoDB/NATS/Redis
- **Frontend**: Can receive from ingress, connect to API only
- **Database**: Only accepts connections from API

### Best Practices Implemented
- Principle of least privilege for network access
- Explicit ingress controller allowlists
- Service-to-service communication restrictions

## Monitoring and Health Checks

### Health Check Configuration
- Standardized probe settings (30s initial delay, 10s period, 5s timeout)
- Service-specific health endpoints
- Custom health check scripts for complex services

### Monitoring Ready
- Metrics port configuration (9090)
- Health endpoint standardization
- Ready for Prometheus/Grafana integration

## Deployment

### Simplified Deployment Process
```bash
# Development deployment
python scripts/deploy.py

# Production deployment  
python scripts/deploy.py --overlay production

# Specific service deployment
python scripts/deploy.py --services api,frontend
```

### Deployment Features
- Automatic namespace creation and management
- Resource validation before deployment
- Job template availability for on-demand execution
- Rollback capabilities

## Benefits Achieved

### Operational Benefits
- **Simplified Management**: Single namespace, standardized configs
- **Resource Efficiency**: Proper resource allocation and limits
- **Security**: Network policies and access controls
- **Monitoring Ready**: Health checks and metrics endpoints
- **Scalability**: Resource profiles for different service types

### Development Benefits
- **Consistency**: Standardized resource allocation and configuration
- **Maintainability**: Centralized configuration management
- **Debugging**: Clear service boundaries and communication paths
- **Testing**: Consistent environments across dev/prod

### Infrastructure Benefits
- **Cost Control**: Resource quotas and limits prevent waste
- **Security**: Network policies implement zero-trust
- **Reliability**: Health checks and proper resource allocation
- **Compliance**: Enterprise-grade resource and security standards

## Migration Notes

### Breaking Changes
- Services now reference ConfigMaps for common values
- Network policies may block previously allowed traffic
- Resource limits may be more restrictive than before

### Deployment Sequence
1. Apply base configurations (includes ConfigMaps and policies)
2. Deploy core infrastructure services (MongoDB, NATS, Redis, Kueue)
3. Deploy application services (API, Frontend)
4. Verify network connectivity and resource allocation

### Rollback Plan
Original configurations are preserved in git history. To rollback:
1. Revert to previous configuration files
2. Remove new ConfigMaps and policies
3. Redeploy using original configurations

## Future Enhancements

### Phase 5 Candidates
- **Service Mesh**: Istio integration for advanced traffic management
- **Observability**: Prometheus, Grafana, Jaeger for comprehensive monitoring
- **GitOps**: ArgoCD for automated deployment and configuration management
- **Backup/Recovery**: Automated backup strategies for persistent data
- **CI/CD Integration**: Enhanced automation and testing workflows 