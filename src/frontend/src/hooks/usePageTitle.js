import { useEffect } from 'react';

const BRAND = 'ReconHawx';
const SEP = ' · ';

/**
 * Join non-empty parts with middle separator, then append brand.
 * @param {...string|null|undefined} parts
 * @returns {string}
 */
export function formatPageTitle(...parts) {
  const head = parts
    .map((p) => (p == null ? '' : String(p).trim()))
    .filter(Boolean);
  if (head.length === 0) return BRAND;
  return `${head.join(SEP)}${SEP}${BRAND}`;
}

/**
 * Shorten long strings for browser tabs (middle ellipsis).
 * @param {string} str
 * @param {number} maxLen
 * @returns {string}
 */
export function truncateTitle(str, maxLen = 72) {
  if (str == null || str === '') return '';
  const s = String(str);
  if (s.length <= maxLen) return s;
  const keep = maxLen - 1;
  const left = Math.ceil(keep / 2);
  const right = Math.floor(keep / 2);
  return `${s.slice(0, left)}…${s.slice(s.length - right)}`;
}

/**
 * Sync document.title when titleString changes.
 * @param {string} titleString
 */
export function usePageTitle(titleString) {
  useEffect(() => {
    document.title = titleString;
  }, [titleString]);
}
