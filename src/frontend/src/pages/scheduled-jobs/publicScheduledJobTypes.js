/** Job types shown in scheduled-job create/filter UI (excludes hiddenJobTypes). */
export const PUBLIC_SCHEDULED_JOB_TYPE_OPTIONS = Object.freeze([
  {
    value: 'workflow',
    label: 'Workflow Job',
    description: 'Execute a predefined workflow',
  },
  {
    value: 'gather_api_findings',
    label: 'Gather API Findings',
    description: 'Gather typosquat findings from vendor APIs (ThreatStream, RecordedFuture)',
  },
  {
    value: 'refresh_vendor_intel',
    label: 'Refresh Vendor Intel',
    description:
      'Refresh Recorded Future or ThreatStream intel on existing typosquat findings (no status/assignment changes)',
  },
]);

export function mergePublicScheduledJobTypes(apiJobTypes, hiddenTypesSet) {
  const byValue = new Map(
    (apiJobTypes || [])
      .filter((t) => !hiddenTypesSet.has(t.value))
      .map((t) => [t.value, t])
  );
  for (const fallback of PUBLIC_SCHEDULED_JOB_TYPE_OPTIONS) {
    if (!hiddenTypesSet.has(fallback.value) && !byValue.has(fallback.value)) {
      byValue.set(fallback.value, fallback);
    }
  }
  return Array.from(byValue.values());
}
