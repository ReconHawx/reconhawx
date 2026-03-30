import { format, formatDistanceToNow, isValid } from 'date-fns';

/**
 * Format a date to local datetime string for datetime-local input
 * @param {Date} date - Date object
 * @returns {string} Formatted date string (YYYY-MM-DDTHH:mm)
 */
export const formatLocalDateTime = (date) => {
  if (!date || !(date instanceof Date)) {
    return '';
  }
  
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

/**
 * Format a date string to a readable format with local timezone
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp (seconds or milliseconds)
 * @param {string} formatString - Format string (default: 'MMM dd, yyyy HH:mm:ss')
 * @param {boolean} skipTimezoneConversion - If true, assumes dateString is already in local timezone (default: false)
 * @returns {string} Formatted date string
 */
export const formatDate = (dateString, formatString = 'MMM dd, yyyy HH:mm:ss', skipTimezoneConversion = false) => {
  if (!dateString) return 'N/A';

  try {
    let date;
    if (typeof dateString === 'number') {
      // Handle Unix timestamps - if it's less than a certain threshold, treat as seconds, otherwise as milliseconds
      // Unix timestamps in seconds are typically 10 digits, in milliseconds are 13 digits
      // Threshold: 1e12 (1 trillion) - timestamps after year 2001 in milliseconds will be above this
      if (dateString < 1e12) {
        // Likely seconds since epoch, convert to milliseconds
        date = new Date(dateString * 1000);
      } else {
        // Likely milliseconds since epoch
        date = new Date(dateString);
      }
    } else if (typeof dateString === 'string') {
      // Check for Microsoft/JSON date format like /Date(1234567890000)/ or /Date(1234567890000-0700)/
      const microsoftDateMatch = dateString.match(/^\/Date\((\d+)([+-]\d{4})?\)\/$/);
      if (microsoftDateMatch) {
        const timestamp = parseInt(microsoftDateMatch[1]);
        date = new Date(timestamp);
      } else {
        // Check if it's a numeric string that should be treated as a timestamp
        const numericValue = parseFloat(dateString);
        if (!isNaN(numericValue) && dateString.match(/^\d+\.?\d*$/)) {
          // It's a numeric string, treat like a numeric timestamp
          if (numericValue < 1e12) {
            date = new Date(numericValue * 1000);
          } else {
            date = new Date(numericValue);
          }
        } else {
          // Handle regular date strings
          if (skipTimezoneConversion) {
            // If skipTimezoneConversion is true, parse as-is (assumes already in local timezone)
            date = new Date(dateString);
          } else {
            // If the string doesn't end with 'Z' or have timezone info, treat it as UTC
            if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
              // Add 'Z' to treat as UTC, then parse
              date = new Date(dateString + 'Z');
            } else {
              date = new Date(dateString);
            }
          }
        }
      }
    } else if (dateString instanceof Date) {
      date = dateString;
    } else if (dateString && typeof dateString === 'object' && dateString.$date) {
      // Handle MongoDB date format
      const dateStr = dateString.$date;
      if (skipTimezoneConversion) {
        // Parse as-is if skipping timezone conversion
        date = new Date(dateStr);
      } else {
        // Treat as UTC if no timezone info
        if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
          date = new Date(dateStr + 'Z');
        } else {
          date = new Date(dateStr);
        }
      }
    } else {
      date = new Date(dateString);
    }
    
    if (!isValid(date)) {
      return 'Invalid Date';
    }
    
    // Simple approach: just use toLocaleString directly
    if (formatString === 'MMM dd, yyyy HH:mm:ss') {
      const result = date.toLocaleString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });

      return result;
    } else if (formatString === 'MMM dd, yyyy') {
      const result = date.toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric'
      });

      return result;
    } else if (formatString === 'HH:mm:ss') {
      const result = date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });

      return result;
    } else if (formatString === 'MMM dd, HH:mm') {
      const result = date.toLocaleString('en-US', {
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      });

      return result;
    } else if (formatString === 'yyyy-MM-dd HH:mm:ss') {
      const result = date.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }).replace(/(\d+)\/(\d+)\/(\d+)/, '$3-$1-$2');

      return result;
    }
    
    // Fallback to date-fns for other formats
    const result = format(date, formatString);

    return result;
  } catch (e) {
    return 'Invalid Date';
  }
};

/**
 * Format a date string that is already in local timezone (no UTC conversion)
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp (already in local timezone)
 * @param {string} formatString - Format string (default: 'MMM dd, yyyy HH:mm:ss')
 * @returns {string} Formatted date string
 */
export const formatLocalDate = (dateString, formatString = 'MMM dd, yyyy HH:mm:ss') => {
  return formatDate(dateString, formatString, true);
};

/**
 * Format a date string to date only (no time) with local timezone
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {string} Formatted date string
 */
export const formatDateOnly = (dateString) => {
  return formatDate(dateString, 'MMM dd, yyyy');
};

/**
 * Format a date string to time only with local timezone
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {string} Formatted time string
 */
export const formatTimeOnly = (dateString) => {
  return formatDate(dateString, 'HH:mm:ss');
};

/**
 * Format a date string to a relative time (e.g., "2 hours ago")
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {string} Relative time string
 */
export const formatRelativeTime = (dateString) => {
  if (!dateString) return 'N/A';

  try {
    let date;
    if (typeof dateString === 'number') {
      // Handle Unix timestamps - if it's less than a certain threshold, treat as seconds, otherwise as milliseconds
      if (dateString < 1e12) {
        date = new Date(dateString * 1000);
      } else {
        date = new Date(dateString);
      }
    } else if (typeof dateString === 'string') {
      // Check for Microsoft/JSON date format
      const microsoftDateMatch = dateString.match(/^\/Date\((\d+)([+-]\d{4})?\)\/$/);
      if (microsoftDateMatch) {
        const timestamp = parseInt(microsoftDateMatch[1]);
        date = new Date(timestamp);
      } else {
        // Check if it's a numeric string that should be treated as a timestamp
        const numericValue = parseFloat(dateString);
        if (!isNaN(numericValue) && dateString.match(/^\d+\.?\d*$/)) {
          if (numericValue < 1e12) {
            date = new Date(numericValue * 1000);
          } else {
            date = new Date(numericValue);
          }
        } else {
          // If the string doesn't end with 'Z' or have timezone info, treat it as UTC
          if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
            // Add 'Z' to treat as UTC, then parse
            date = new Date(dateString + 'Z');
          } else {
            date = new Date(dateString);
          }
        }
      }
    } else if (dateString instanceof Date) {
      date = dateString;
    } else if (dateString && typeof dateString === 'object' && dateString.$date) {
      // Handle MongoDB date format - treat as UTC if no timezone info
      const dateStr = dateString.$date;
      if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        date = new Date(dateStr + 'Z');
      } else {
        date = new Date(dateStr);
      }
    } else {
      date = new Date(dateString);
    }
    
    if (!isValid(date)) {
      return 'Invalid Date';
    }
    
    return formatDistanceToNow(date, { addSuffix: true });
  } catch (e) {
    return 'Invalid Date';
  }
};

/**
 * Format a date string to a compact format with local timezone
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {string} Compact formatted date string
 */
export const formatCompactDate = (dateString) => {
  return formatDate(dateString, 'MMM dd, HH:mm');
};

/**
 * Format a date string to ISO format with local timezone
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {string} ISO formatted date string
 */
export const formatISODate = (dateString) => {
  return formatDate(dateString, 'yyyy-MM-dd HH:mm:ss');
};

/**
 * Check if a date is expired (in the past)
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @returns {boolean} True if date is in the past
 */
export const isExpired = (dateString) => {
  if (!dateString) return false;

  try {
    let date;
    if (typeof dateString === 'number') {
      // Handle Unix timestamps
      if (dateString < 1e12) {
        date = new Date(dateString * 1000);
      } else {
        date = new Date(dateString);
      }
    } else if (typeof dateString === 'string') {
      // Check for Microsoft/JSON date format
      const microsoftDateMatch = dateString.match(/^\/Date\((\d+)([+-]\d{4})?\)\/$/);
      if (microsoftDateMatch) {
        const timestamp = parseInt(microsoftDateMatch[1]);
        date = new Date(timestamp);
      } else {
        // Check if it's a numeric string that should be treated as a timestamp
        const numericValue = parseFloat(dateString);
        if (!isNaN(numericValue) && dateString.match(/^\d+\.?\d*$/)) {
          if (numericValue < 1e12) {
            date = new Date(numericValue * 1000);
          } else {
            date = new Date(numericValue);
          }
        } else {
          // If the string doesn't end with 'Z' or have timezone info, treat it as UTC
          if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
            // Add 'Z' to treat as UTC, then parse
            date = new Date(dateString + 'Z');
          } else {
            date = new Date(dateString);
          }
        }
      }
    } else if (dateString instanceof Date) {
      date = dateString;
    } else if (dateString && typeof dateString === 'object' && dateString.$date) {
      // Handle MongoDB date format - treat as UTC if no timezone info
      const dateStr = dateString.$date;
      if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        date = new Date(dateStr + 'Z');
      } else {
        date = new Date(dateStr);
      }
    } else {
      date = new Date(dateString);
    }
    
    if (!isValid(date)) {
      return false;
    }
    
    return date < new Date();
  } catch (e) {
    return false;
  }
};

/**
 * Check if a date is expiring soon (within 30 days)
 * @param {string|Date|number} dateString - Date string, Date object, or Unix timestamp
 * @param {number} daysThreshold - Number of days to consider "soon" (default: 30)
 * @returns {boolean} True if date is expiring soon
 */
export const isExpiringSoon = (dateString, daysThreshold = 30) => {
  if (!dateString) return false;

  try {
    let date;
    if (typeof dateString === 'number') {
      // Handle Unix timestamps
      if (dateString < 1e12) {
        date = new Date(dateString * 1000);
      } else {
        date = new Date(dateString);
      }
    } else if (typeof dateString === 'string') {
      // Check for Microsoft/JSON date format
      const microsoftDateMatch = dateString.match(/^\/Date\((\d+)([+-]\d{4})?\)\/$/);
      if (microsoftDateMatch) {
        const timestamp = parseInt(microsoftDateMatch[1]);
        date = new Date(timestamp);
      } else {
        // Check if it's a numeric string that should be treated as a timestamp
        const numericValue = parseFloat(dateString);
        if (!isNaN(numericValue) && dateString.match(/^\d+\.?\d*$/)) {
          if (numericValue < 1e12) {
            date = new Date(numericValue * 1000);
          } else {
            date = new Date(numericValue);
          }
        } else {
          // If the string doesn't end with 'Z' or have timezone info, treat it as UTC
          if (!dateString.includes('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
            // Add 'Z' to treat as UTC, then parse
            date = new Date(dateString + 'Z');
          } else {
            date = new Date(dateString);
          }
        }
      }
    } else if (dateString instanceof Date) {
      date = dateString;
    } else if (dateString && typeof dateString === 'object' && dateString.$date) {
      // Handle MongoDB date format - treat as UTC if no timezone info
      const dateStr = dateString.$date;
      if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        date = new Date(dateStr + 'Z');
      } else {
        date = new Date(dateStr);
      }
    } else {
      date = new Date(dateString);
    }
    
    if (!isValid(date)) {
      return false;
    }
    
    const now = new Date();
    const thresholdDate = new Date(now.getTime() + (daysThreshold * 24 * 60 * 60 * 1000));
    
    return date < thresholdDate && date > now;
  } catch (e) {
    return false;
  }
};

/**
 * Calculate duration between two dates
 * @param {string|Date|number} startDate - Start date
 * @param {string|Date|number} endDate - End date (optional, defaults to now)
 * @returns {string} Duration string
 */
export const calculateDuration = (startDate, endDate = null) => {
  if (!startDate) return 'Not started';

  try {
    let start;
    if (typeof startDate === 'number') {
      // Handle Unix timestamps
      if (startDate < 1e12) {
        start = new Date(startDate * 1000);
      } else {
        start = new Date(startDate);
      }
    } else if (typeof startDate === 'string') {
      // Check if it's a numeric string that should be treated as a timestamp
      const numericValue = parseFloat(startDate);
      if (!isNaN(numericValue) && startDate.match(/^\d+\.?\d*$/)) {
        if (numericValue < 1e12) {
          start = new Date(numericValue * 1000);
        } else {
          start = new Date(numericValue);
        }
      } else {
        // If the string doesn't end with 'Z' or have timezone info, treat it as UTC
        if (!startDate.includes('Z') && !startDate.includes('+') && !startDate.includes('-', 10)) {
          // Add 'Z' to treat as UTC, then parse
          start = new Date(startDate + 'Z');
        } else {
          start = new Date(startDate);
        }
      }
    } else if (startDate instanceof Date) {
      start = startDate;
    } else if (startDate && typeof startDate === 'object' && startDate.$date) {
      // Handle MongoDB date format - treat as UTC if no timezone info
      const dateStr = startDate.$date;
      if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
        start = new Date(dateStr + 'Z');
      } else {
        start = new Date(dateStr);
      }
    } else {
      start = new Date(startDate);
    }
    
    if (!isValid(start)) {
      return 'Invalid start date';
    }
    
    let end;
    if (endDate) {
      if (typeof endDate === 'number') {
        // Handle Unix timestamps
        if (endDate < 1e12) {
          end = new Date(endDate * 1000);
        } else {
          end = new Date(endDate);
        }
      } else if (typeof endDate === 'string') {
        // Check for Microsoft/JSON date format
        const microsoftDateMatch = endDate.match(/^\/Date\((\d+)([+-]\d{4})?\)\/$/);
        if (microsoftDateMatch) {
          const timestamp = parseInt(microsoftDateMatch[1]);
          end = new Date(timestamp);
        } else {
          // Check if it's a numeric string that should be treated as a timestamp
          const numericValue = parseFloat(endDate);
          if (!isNaN(numericValue) && endDate.match(/^\d+\.?\d*$/)) {
            if (numericValue < 1e12) {
              end = new Date(numericValue * 1000);
            } else {
              end = new Date(numericValue);
            }
          } else {
            if (!endDate.includes('Z') && !endDate.includes('+') && !endDate.includes('-', 10)) {
              end = new Date(endDate + 'Z');
            } else {
              end = new Date(endDate);
            }
          }
        }
      } else if (endDate instanceof Date) {
        end = endDate;
      } else if (endDate && typeof endDate === 'object' && endDate.$date) {
        const dateStr = endDate.$date;
        if (!dateStr.includes('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
          end = new Date(dateStr + 'Z');
        } else {
          end = new Date(dateStr);
        }
      } else {
        end = new Date(endDate);
      }
    } else {
      end = new Date();
    }
    
    if (!isValid(end)) {
      return 'Invalid end date';
    }
    
    const durationMs = end - start;
    const durationSeconds = Math.floor(durationMs / 1000);
    
    if (durationSeconds < 0) {
      return 'Invalid duration';
    }
    
    if (durationSeconds < 60) {
      return `${durationSeconds}s`;
    }
    
    const durationMinutes = Math.floor(durationSeconds / 60);
    const remainingSeconds = durationSeconds % 60;
    
    if (durationMinutes < 60) {
      return `${durationMinutes}m ${remainingSeconds}s`;
    }
    
    const durationHours = Math.floor(durationMinutes / 60);
    const remainingMinutes = durationMinutes % 60;
    
    if (durationHours < 24) {
      return `${durationHours}h ${remainingMinutes}m`;
    }
    
    const durationDays = Math.floor(durationHours / 24);
    const remainingHours = durationHours % 24;
    
    return `${durationDays}d ${remainingHours}h`;
  } catch (e) {
    return 'Unable to calculate';
  }
}; 