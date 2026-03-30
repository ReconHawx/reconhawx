import React, { createContext, useContext, useReducer, useEffect, useCallback } from 'react';
import apiObject from '../services/api';

const AuthContext = createContext();

const authReducer = (state, action) => {
  switch (action.type) {
    case 'LOGIN_START':
      return {
        ...state,
        isLoading: true,
        error: null
      };
    case 'LOGIN_SUCCESS':
      return {
        ...state,
        isLoading: false,
        isAuthenticated: true,
        user: action.payload.user,
        accessToken: action.payload.accessToken,
        refreshToken: action.payload.refreshToken,
        expiresIn: action.payload.expiresIn,
        error: null
      };
    case 'TOKEN_REFRESHED':
      return {
        ...state,
        accessToken: action.payload.accessToken,
        expiresIn: action.payload.expiresIn
      };
    case 'LOGIN_FAILURE':
      return {
        ...state,
        isLoading: false,
        isAuthenticated: false,
        user: null,
        accessToken: null,
        refreshToken: null,
        expiresIn: null,
        error: action.payload
      };
    case 'LOGOUT':
      return {
        ...state,
        isAuthenticated: false,
        user: null,
        accessToken: null,
        refreshToken: null,
        expiresIn: null,
        error: null
      };
    case 'SET_LOADING':
      return {
        ...state,
        isLoading: action.payload
      };
    default:
      return state;
  }
};

const initialState = {
  isAuthenticated: false,
  user: null,
  accessToken: null,
  refreshToken: null,
  expiresIn: null,
  isLoading: true,
  error: null
};

export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // Define logout function first to avoid circular dependency
  const logout = useCallback(async () => {
    try {
      // Call backend logout to revoke refresh token
      if (state.refreshToken) {
        await apiObject.auth.logout(state.refreshToken);
      }
    } catch (error) {
      console.error('Logout API call failed:', error);
    } finally {
      // Clear local storage
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user_data');
      localStorage.removeItem('token_expires_at');

      dispatch({ type: 'LOGOUT' });
    }
  }, [state.refreshToken, dispatch]);

  // Token refresh logic
  const refreshAccessToken = useCallback(async () => {
    if (!state.refreshToken) {
      return false;
    }

    try {
      const response = await apiObject.auth.refreshToken(state.refreshToken);

      // Calculate the new expiration timestamp
      const newExpiresAt = Date.now() + (response.expires_in * 1000);

      dispatch({
        type: 'TOKEN_REFRESHED',
        payload: {
          accessToken: response.access_token,
          expiresIn: response.expires_in
        }
      });

      // Update localStorage with new token and expiration
      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('token_expires_at', newExpiresAt.toString());

      return true;
    } catch (error) {
      console.error('Token refresh failed:', error);
      // Refresh failed, force logout
      logout();
      return false;
    }
  }, [state.refreshToken, logout]);

  // Auto-refresh token
  useEffect(() => {
    if (!state.isAuthenticated || !state.refreshToken) return;

    // Calculate when the next refresh should happen
    const calculateNextRefresh = () => {
      const expiresAt = localStorage.getItem('token_expires_at');
      if (!expiresAt) return null;

      const now = Date.now();
      const expiresTime = parseInt(expiresAt);
      const timeUntilExpiry = expiresTime - now;

      // For short-lived tokens (less than 10 minutes), refresh at 1/3 of remaining time
      // For longer tokens, refresh 5 minutes before expiry
      let refreshThreshold;
      if (timeUntilExpiry < 600000) { // Less than 10 minutes
        refreshThreshold = Math.floor(timeUntilExpiry / 3); // Refresh at 1/3 remaining time
      } else {
        refreshThreshold = 300000; // 5 minutes for longer tokens
      }

      const refreshTime = timeUntilExpiry - refreshThreshold;

      if (refreshTime <= 0) {
        // Token expires soon, refresh immediately
        return 0;
      }

      return refreshTime;
    };

    const scheduleNextRefresh = () => {
      const nextRefresh = calculateNextRefresh();

      if (nextRefresh === null) return;

      if (nextRefresh <= 0) {
        // Refresh immediately
        refreshAccessToken();
      } else {
        // Schedule refresh for later
        setTimeout(() => {
          refreshAccessToken();
        }, nextRefresh);
      }
    };

    // Schedule the first refresh
    scheduleNextRefresh();

    // No fallback interval needed - the setTimeout handles the refresh timing
    // The interval was causing unnecessary refreshes every 5 minutes

    return () => {
      // Clean up any pending timeouts if component unmounts
      // Note: setTimeout cleanup would need to be tracked separately if needed
    };
  }, [state.isAuthenticated, state.refreshToken, refreshAccessToken]);

  useEffect(() => {
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');
    const user = localStorage.getItem('user_data');
    const expiresAt = localStorage.getItem('token_expires_at');

    if (accessToken && refreshToken && user) {
      try {
        const parsedUser = JSON.parse(user);
        const now = Date.now();
        const expiresTime = parseInt(expiresAt);

        // Check if token is expired or will expire soon
        if (expiresTime && now < expiresTime) {
          // Token is still valid
          const remainingTime = Math.floor((expiresTime - now) / 1000);

          // Only restore session if token has more than 1 minute left
          if (remainingTime > 60) {
            dispatch({
              type: 'LOGIN_SUCCESS',
              payload: {
                user: parsedUser,
                accessToken,
                refreshToken,
                expiresIn: remainingTime
              }
            });
          } else {
            // Token expires too soon, try to refresh
            if (refreshToken) {
              refreshAccessToken();
            } else {
              // Clear expired data
              localStorage.removeItem('access_token');
              localStorage.removeItem('refresh_token');
              localStorage.removeItem('user_data');
              localStorage.removeItem('token_expires_at');
            }
          }
        } else {
          // Token expired, try to refresh
          if (refreshToken) {
            refreshAccessToken();
          } else {
            // Clear expired data
            localStorage.removeItem('access_token');
            localStorage.removeItem('refresh_token');
            localStorage.removeItem('user_data');
            localStorage.removeItem('token_expires_at');
          }
        }
      } catch (error) {
        console.error('Error parsing stored user data:', error);
        // Clear corrupted data
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user_data');
        localStorage.removeItem('token_expires_at');
      }
    }

    dispatch({ type: 'SET_LOADING', payload: false });
  }, [refreshAccessToken]);

  const login = async (username, password) => {
    dispatch({ type: 'LOGIN_START' });

    try {
      const data = await apiObject.auth.login(username, password);

      // Calculate the actual expiration timestamp
      // data.expires_in is in seconds, so multiply by 1000 to get milliseconds
      const expiresAt = Date.now() + (data.expires_in * 1000);
      
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      localStorage.setItem('user_data', JSON.stringify(data.user));
      localStorage.setItem('token_expires_at', expiresAt.toString());

      dispatch({
        type: 'LOGIN_SUCCESS',
        payload: {
          user: data.user,
          accessToken: data.access_token,
          refreshToken: data.refresh_token,
          expiresIn: data.expires_in
        }
      });

      return { success: true };
    } catch (error) {
      dispatch({
        type: 'LOGIN_FAILURE',
        payload: error.message
      });
      return { success: false, error: error.message };
    }
  };

  const isAdmin = () => {
    return state.user && (state.user.is_superuser || state.user.roles?.includes('admin'));
  };

  const isSuperuser = () => {
    return state.user && state.user.is_superuser;
  };

  const hasRole = (role) => {
    if (!state.user) return false;
    if (state.user.is_superuser) return true;
    return state.user.roles && state.user.roles.includes(role);
  };

  const hasPermission = (permission) => {
    if (!state.user) return false;
    if (state.user.is_superuser) return true;
    // For backward compatibility, check both roles and permissions
    if (state.user.roles && state.user.roles.includes(permission)) return true;
    return state.user.permissions && state.user.permissions.includes(permission);
  };

  const hasProgramAccess = (programName) => {
    if (!state.user) return false;
    if (state.user.is_superuser || (state.user.roles && state.user.roles.includes('admin'))) return true;
    const programPermissions = state.user.program_permissions || {};
    return programPermissions[programName] !== undefined;
  };

  const getProgramPermissionLevel = (programName) => {
    if (!state.user) return null;
    if (state.user.is_superuser || (state.user.roles && state.user.roles.includes('admin'))) return 'manager';
    const programPermissions = state.user.program_permissions || {};
    return programPermissions[programName] || null;
  };

  const hasProgramPermission = (programName, requiredLevel = 'analyst') => {
    if (!state.user) return false;
    if (state.user.is_superuser || (state.user.roles && state.user.roles.includes('admin'))) return true;

    const programPermissions = state.user.program_permissions || {};
    const userLevel = programPermissions[programName];

    if (!userLevel) return false;

    // Permission hierarchy: manager > analyst
    if (requiredLevel === 'analyst') {
      return userLevel === 'analyst' || userLevel === 'manager';
    } else if (requiredLevel === 'manager') {
      return userLevel === 'manager';
    }

    return false;
  };

  const getTokenInfo = () => {
    const expiresAt = localStorage.getItem('token_expires_at');
    if (!expiresAt) return null;

    const now = Date.now();
    const expiresTime = parseInt(expiresAt);
    const timeUntilExpiry = expiresTime - now;

    return {
      expiresAt: new Date(expiresTime).toISOString(),
      timeUntilExpiry: Math.floor(timeUntilExpiry / 1000),
      isExpired: timeUntilExpiry <= 0,
      needsRefresh: timeUntilExpiry < 300, // 5 minutes
      formattedTime: new Date(timeUntilExpiry).toISOString().substr(11, 8) // HH:MM:SS
    };
  };

  const checkTokenStatus = () => {
    const tokenInfo = getTokenInfo();
    if (!tokenInfo) {
      return;
    }


    return tokenInfo;
  };

  const showRefreshSchedule = () => {
    const expiresAt = localStorage.getItem('token_expires_at');
    if (!expiresAt) {
      return;
    }

    const now = Date.now();
    const expiresTime = parseInt(expiresAt);
    const timeUntilExpiry = expiresTime - now;

    // Calculate refresh threshold using same logic as calculateNextRefresh
    let refreshThreshold;
    if (timeUntilExpiry < 600000) { // Less than 10 minutes
      refreshThreshold = Math.floor(timeUntilExpiry / 3); // Refresh at 1/3 remaining time
    } else {
      refreshThreshold = 300000; // 5 minutes for longer tokens
    }

    const refreshTime = timeUntilExpiry - refreshThreshold;

  };

  const value = {
    ...state,
    login,
    logout,
    refreshAccessToken,
    getTokenInfo,
    checkTokenStatus,
    showRefreshSchedule,
    isAdmin,
    isSuperuser,
    hasRole,
    hasPermission,
    hasProgramAccess,
    getProgramPermissionLevel,
    hasProgramPermission
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;