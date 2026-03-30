/**
 * Barrel export file for API modules
 * Re-exports all APIs from split modules for easy importing
 * Maintains backward compatibility with original api.js structure
 */

// Import for default export object
import { authAPI, userManagementAPI, adminAPI, nucleiTemplatesAPI, wordlistsAPI } from './admin';
import { assetAPI, domainAPI, apexDomainAPI, ipAPI, urlAPI, serviceAPI, certificateAPI } from './assets';
import { nucleiAPI, wpscanAPI, typosquatAPI, brokenLinksAPI, socialMediaCredentialsAPI, externalLinksAPI } from './findings';
import { programAPI } from './programs';
import { workflowAPI, queueAPI, jobAPI, scheduledJobsAPI } from './workflows';
import { commonStatsAPI } from './stats';
import { aiAPI } from './ai';

// Re-export client configuration
export { API_BASE_URL, api } from './client';

// Re-export all asset APIs
export {
    assetAPI,
    domainAPI,
    apexDomainAPI,
    ipAPI,
    urlAPI,
    serviceAPI,
    screenshotAPI,
    typosquatScreenshotAPI,
    technologyAPI,
    certificateAPI
} from './assets';

// Re-export all findings APIs
export {
    nucleiAPI,
    wpscanAPI,
    brokenLinksAPI,
    socialMediaCredentialsAPI,
    typosquatAPI,
    externalLinksAPI
} from './findings';

// Re-export workflow/job APIs
export {
    jobAPI,
    workflowAPI,
    queueAPI,
    scheduledJobsAPI
} from './workflows';

// Re-export admin/auth APIs
export {
    authAPI,
    userManagementAPI,
    adminAPI,
    nucleiTemplatesAPI,
    wordlistsAPI,
    ctMonitorAPI
} from './admin';

// Re-export program API
export { programAPI } from './programs';

// Re-export stats API
export { commonStatsAPI } from './stats';

// Re-export AI API
export { aiAPI } from './ai';

/**
 * Default export: Maintains backward compatibility with original api.js structure
 * Usage: import api from './services/api'; 
 * Then: api.auth.login(), api.assets.domains.searchSubdomains(), etc.
 */

const apiObject = {
    auth: authAPI,
    userManagement: userManagementAPI,
    admin: adminAPI,
    nucleiTemplates: nucleiTemplatesAPI,
    wordlists: wordlistsAPI,
    commonStats: commonStatsAPI,
    jobs: jobAPI,
    queue: queueAPI,
    workflows: workflowAPI,
    scheduledJobs: scheduledJobsAPI,
    programs: programAPI,
    socialMediaCredentials: socialMediaCredentialsAPI,
    assets: {
        generic: assetAPI,
        domains: domainAPI,
        apexDomains: apexDomainAPI,
        ips: ipAPI,
        urls: urlAPI,
        services: serviceAPI,
        certificates: certificateAPI
    },
    findings: {
        nuclei: nucleiAPI,
        wpscan: wpscanAPI,
        typosquat: typosquatAPI,
        brokenLinks: brokenLinksAPI,
        externalLinks: externalLinksAPI
    },
    ai: aiAPI
};

export default apiObject;
