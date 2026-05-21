import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export const LIST_RETURN_KEY = 'listReturn';

function normalizePathnames(defaultPath) {
  const paths = Array.isArray(defaultPath) ? defaultPath : [defaultPath];
  return paths.map((path) => path.split('?')[0]);
}

/** State to pass to navigate/Link when opening a detail from a filtered list. */
export function withListReturn(location, extraState = {}) {
  return {
    state: {
      ...extraState,
      [LIST_RETURN_KEY]: `${location.pathname}${location.search}`,
    },
  };
}

/** Resolve back target: saved list URL if pathname matches, else defaultPath. */
export function resolveListReturnPath(location, defaultPath) {
  const allowedPathnames = normalizePathnames(defaultPath);
  const fallback = allowedPathnames[0];
  const saved = location.state?.[LIST_RETURN_KEY];
  if (!saved || typeof saved !== 'string') {
    return fallback;
  }
  const savedPathname = saved.split('?')[0];
  if (!allowedPathnames.includes(savedPathname)) {
    return fallback;
  }
  return saved;
}

export function useListReturnPath(defaultPath) {
  const location = useLocation();
  return resolveListReturnPath(location, defaultPath);
}

export function useBackToList(defaultPath) {
  const navigate = useNavigate();
  const location = useLocation();
  return useCallback(
    () => navigate(resolveListReturnPath(location, defaultPath)),
    [navigate, location, defaultPath],
  );
}
