/**
 * Default workflow inputs for event-handler workflow_trigger actions.
 * Aligns with src/event-handler/app/routing.py batch variables and global_default_event_handlers.yaml.
 */

export function getEventHandlerDirectInputDefaults(eventType) {
  const t = typeof eventType === 'string' ? eventType : '';
  if (t.startsWith('assets.ip')) {
    return { value_type: 'ips', values: '{ip_list_array}' };
  }
  if (t.startsWith('assets.url')) {
    return { value_type: 'urls', values: '{url_list_array}' };
  }
  return { value_type: 'domains', values: '{domain_list_array}' };
}

export function getDefaultEventHandlerInputs(eventType) {
  const t = typeof eventType === 'string' ? eventType : '';
  if (t.startsWith('assets.ip')) {
    return {
      ips: {
        type: 'direct',
        value_type: 'ips',
        values: '{ip_list_array}',
      },
    };
  }
  if (t.startsWith('assets.url')) {
    return {
      urls: {
        type: 'direct',
        value_type: 'urls',
        values: '{url_list_array}',
      },
    };
  }
  return {
    domains: {
      type: 'direct',
      value_type: 'domains',
      values: '{domain_list_array}',
    },
  };
}
