/**
 * Utility functions for user-related operations
 */

import React from 'react';
import apiObject from '../services/api';

// Simple in-memory cache for user ID to username mapping
let userCache = new Map();

// Cache for ongoing API requests to avoid duplicate calls
let pendingRequests = new Map();

// Subscribers for cache updates (React components can subscribe to get notified when user data loads)
let cacheUpdateSubscribers = new Set();

/**
 * Fetch username from API by user ID
 * @param {string} userId - User ID (UUID)
 * @returns {Promise<string|null>} - Username if found, null otherwise
 */
const fetchUsernameFromAPI = async (userId) => {
  // Check if there's already a pending request for this user
  if (pendingRequests.has(userId)) {
    return await pendingRequests.get(userId);
  }

  // Create a promise for this request
  const requestPromise = (async () => {
    try {
      // Use the correct endpoint: GET /auth/users/{user_id}
      const response = await apiObject.userManagement.getUser(userId);

      if (response && response.username) {
        return response.username;
      }

      return null;
    } catch (error) {
      // Log the error for debugging but don't throw
      console.warn(`Failed to fetch user data for ID ${userId}:`, error);
      return null;
    }
  })();

  // Store the promise to avoid duplicate requests
  pendingRequests.set(userId, requestPromise);

  try {
    const result = await requestPromise;
    return result;
  } finally {
    // Remove the promise from pending requests
    pendingRequests.delete(userId);
  }
};

/**
 * Notify all subscribers about cache updates
 */
const notifySubscribers = () => {
  cacheUpdateSubscribers.forEach(callback => {
    try {
      callback();
    } catch (error) {
      console.warn('Error in cache update subscriber:', error);
    }
  });
};

/**
 * Add a user to the cache
 * @param {string} userId - User ID (UUID)
 * @param {string} username - Username
 */
export const addUserToCache = (userId, username) => {
  if (userId && username) {
    const wasNewEntry = !userCache.has(userId);
    const oldValue = userCache.get(userId);
    userCache.set(userId, username);

    // Notify subscribers only if this was a new entry or changed value
    if (wasNewEntry || oldValue !== username) {
      notifySubscribers();
    }
  }
};

/**
 * Get username from user ID
 * @param {string} userId - User ID (UUID)
 * @returns {Promise<string|null>} - Username if found, userId as fallback
 */
export const getUsernameFromId = async (userId) => {
  if (!userId) return null;

  // Check cache first
  if (userCache.has(userId)) {
    return userCache.get(userId);
  }

  // If not in cache, try to fetch from API
  try {
    const username = await fetchUsernameFromAPI(userId);
    if (username) {
      addUserToCache(userId, username);
      return username;
    }
  } catch (error) {
    console.warn(`Failed to fetch username for user ID ${userId}:`, error);
  }

  // Fallback to user ID if API call fails
  return userId;
};

/**
 * Initialize user cache with current user
 * @param {Object} user - Current user object from AuthContext
 */
export const initializeUserCache = (user) => {
  if (user && user.id && user.username) {
    addUserToCache(user.id, user.username);
  }
};

/**
 * Check if a string looks like a UUID
 * @param {string} str - String to check
 * @returns {boolean} - True if looks like UUID
 */
export const isUUID = (str) => {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(str);
};

/**
 * Format assigned_to display value (synchronous version - uses cache only)
 * @param {string} assignedTo - assigned_to value (could be UUID or username)
 * @returns {string} - Formatted display value
 */
export const formatAssignedTo = (assignedTo) => {
  if (!assignedTo) return null;

  // If it looks like a UUID, try to resolve it from cache
  if (isUUID(assignedTo)) {
    // Check cache only (synchronous)
    if (userCache.has(assignedTo)) {
      return userCache.get(assignedTo);
    }
    // If not in cache, show a truncated version of the UUID for better UX
    return `User ${assignedTo.substring(0, 8)}...`;
  }

  // If it's not a UUID, assume it's already a username
  return assignedTo;
};

/**
 * Format assigned_to display value (async version - fetches from API if needed)
 * @param {string} assignedTo - assigned_to value (could be UUID or username)
 * @returns {Promise<string>} - Formatted display value
 */
export const formatAssignedToAsync = async (assignedTo) => {
  if (!assignedTo) return null;

  // If it looks like a UUID, try to resolve it
  if (isUUID(assignedTo)) {
    const username = await getUsernameFromId(assignedTo);
    // If we found a username, return it
    if (username && username !== assignedTo) {
      return username;
    }
    // If still not found, show a truncated version of the UUID for better UX
    return `User ${assignedTo.substring(0, 8)}...`;
  }

  // If it's not a UUID, assume it's already a username
  return assignedTo;
};

/**
 * Subscribe to user cache updates (for React components)
 * @param {Function} callback - Function to call when cache is updated
 * @returns {Function} - Unsubscribe function
 */
export const subscribeToUserCacheUpdates = (callback) => {
  cacheUpdateSubscribers.add(callback);
  return () => {
    cacheUpdateSubscribers.delete(callback);
  };
};

/**
 * Hook for React components to get a reactive user cache state
 * This will trigger re-renders when user data is loaded
 */
export const useUserCache = () => {
  const [cacheVersion, setCacheVersion] = React.useState(0);

  React.useEffect(() => {
    const unsubscribe = subscribeToUserCacheUpdates(() => {
      setCacheVersion(v => v + 1);
    });
    return unsubscribe;
  }, []);

  return cacheVersion; // This value changes when cache updates, triggering re-renders
};

/**
 * Format assigned_to display value (reactive version for React components)
 * @param {string} assignedTo - assigned_to value (could be UUID or username)
 * @param {number} cacheVersion - Current cache version (from useUserCache hook)
 * @returns {string} - Formatted display value
 */
export const formatAssignedToReactive = (assignedTo, cacheVersion) => {
  if (!assignedTo) return null;

  // If it looks like a UUID, try to resolve it from cache
  if (isUUID(assignedTo)) {
    // Check cache (this will be current due to cacheVersion dependency)
    if (userCache.has(assignedTo)) {
      return userCache.get(assignedTo);
    }
    // If not in cache, show a truncated version of the UUID for better UX
    return `User ${assignedTo.substring(0, 8)}...`;
  }

  // If it's not a UUID, assume it's already a username
  return assignedTo;
};

/**
 * Preload user data for multiple user IDs (useful for loading user data before rendering)
 * @param {string[]} userIds - Array of user IDs to preload
 * @returns {Promise<void>}
 */
export const preloadUsers = async (userIds) => {
  if (!userIds || userIds.length === 0) return;

  // Filter out user IDs that are already in cache or not UUIDs
  const idsToFetch = userIds.filter(id => id && isUUID(id) && !userCache.has(id));

  if (idsToFetch.length === 0) return;

  // Fetch usernames for all missing IDs
  const promises = idsToFetch.map(id => getUsernameFromId(id));
  await Promise.allSettled(promises);
};
