import { useEffect, useRef, useState } from 'react';
import { Overlay, Popover } from 'react-bootstrap';
import packageJson from '../../package.json';

const GITHUB_RELEASES_REPO =
  process.env.REACT_APP_GITHUB_RELEASES_REPO || 'ReconHawx/reconhawx';
const STORAGE_KEY = 'reconhawx_github_latest';
const CACHE_MS = 8 * 60 * 60 * 1000;
/** Delay before closing so the pointer can move from the icon onto the popover (and the link). */
const POPOVER_HIDE_DELAY_MS = 280;

function parseSemverTriple(raw) {
  if (raw == null || typeof raw !== 'string') return null;
  const t = raw.trim().replace(/^v/i, '');
  const m = t.match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function semverGreater(a, b) {
  for (let i = 0; i < 3; i += 1) {
    if (a[i] > b[i]) return true;
    if (a[i] < b[i]) return false;
  }
  return false;
}

async function resolveRunningVersion() {
  try {
    const r = await fetch('/api/status');
    if (r.ok) {
      const data = await r.json();
      if (data && typeof data.version === 'string' && data.version.length > 0) {
        return data.version;
      }
    }
  } catch {
    /* fall through */
  }

  try {
    const base = process.env.PUBLIC_URL || '';
    const r = await fetch(`${base}/status.json`);
    if (r.ok) {
      const data = await r.json();
      if (data && typeof data.version === 'string' && data.version.length > 0) {
        return data.version;
      }
    }
  } catch {
    /* fall through */
  }

  return packageJson.version || 'unknown';
}

function readCachedLatest() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (
      o &&
      typeof o.tag === 'string' &&
      typeof o.checkedAt === 'number' &&
      Date.now() - o.checkedAt < CACHE_MS
    ) {
      return o.tag;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writeCachedLatest(tag) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ tag, checkedAt: Date.now() }),
    );
  } catch {
    /* ignore */
  }
}

async function fetchLatestReleaseTag() {
  const cached = readCachedLatest();
  if (cached !== null) return cached;

  const url = `https://api.github.com/repos/${GITHUB_RELEASES_REPO}/releases/latest`;
  try {
    const r = await fetch(url, {
      headers: {
        Accept: 'application/vnd.github+json',
      },
    });
    if (!r.ok) return null;
    const data = await r.json();
    const tag = typeof data.tag_name === 'string' ? data.tag_name : null;
    if (tag) writeCachedLatest(tag);
    return tag;
  } catch {
    return null;
  }
}

function AppStatusBar() {
  const [version, setVersion] = useState(null);
  const [latestTag, setLatestTag] = useState(null);
  const [showUpdatePopover, setShowUpdatePopover] = useState(false);
  const updateIconRef = useRef(null);
  const hidePopoverTimeoutRef = useRef(null);

  const clearHidePopoverTimeout = () => {
    if (hidePopoverTimeoutRef.current != null) {
      clearTimeout(hidePopoverTimeoutRef.current);
      hidePopoverTimeoutRef.current = null;
    }
  };

  const scheduleHideUpdatePopover = () => {
    clearHidePopoverTimeout();
    hidePopoverTimeoutRef.current = window.setTimeout(() => {
      hidePopoverTimeoutRef.current = null;
      setShowUpdatePopover(false);
    }, POPOVER_HIDE_DELAY_MS);
  };

  const keepUpdatePopoverOpen = () => {
    clearHidePopoverTimeout();
    setShowUpdatePopover(true);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const v = await resolveRunningVersion();
      if (cancelled) return;
      setVersion(v);

      const currentTriple = parseSemverTriple(v);
      if (!currentTriple) {
        return;
      }

      const tag = await fetchLatestReleaseTag();
      if (cancelled || !tag) return;

      const latestTriple = parseSemverTriple(tag);
      if (!latestTriple) return;

      if (semverGreater(latestTriple, currentTriple)) {
        setLatestTag(tag);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => clearHidePopoverTimeout(), []);

  const releaseBase = `https://github.com/${GITHUB_RELEASES_REPO}/releases`;
  const releaseUrl = `${releaseBase}/latest`;
  const displayVersion = version ?? '…';
  const latestDisplay = latestTag ? latestTag.replace(/^v/i, '') : '';

  return (
    <footer
      className="border-top py-2 px-3 fixed-bottom bg-body"
      style={{ borderColor: 'var(--bs-border-color)' }}
    >
      <div className="d-flex flex-wrap justify-content-end align-items-center gap-2">
        <span className="text-muted small d-inline-flex align-items-center gap-1">
          ReconHawx v{displayVersion}
          {latestTag ? (
            <>
              <Overlay
                show={showUpdatePopover}
                target={updateIconRef}
                placement="top"
                rootClose
                flip
                onHide={() => {
                  clearHidePopoverTimeout();
                  setShowUpdatePopover(false);
                }}
              >
                {(overlayProps) => (
                  <Popover
                    {...overlayProps}
                    id="reconhawx-version-update-popover"
                    className="shadow"
                    style={{
                      ...overlayProps.style,
                      maxWidth: 'min(320px, 92vw)',
                      pointerEvents: 'auto',
                    }}
                    onMouseEnter={keepUpdatePopoverOpen}
                    onMouseLeave={scheduleHideUpdatePopover}
                  >
                    <Popover.Body className="small py-2 px-3">
                      <div className="mb-2">
                        A newer release is available: <strong>{latestDisplay}</strong>
                        {version ? (
                          <>
                            {' '}
                            (you are on <span className="text-muted">{displayVersion}</span>)
                          </>
                        ) : null}
                      </div>
                      <a href={releaseUrl} target="_blank" rel="noopener noreferrer">
                        Open release on GitHub
                      </a>
                    </Popover.Body>
                  </Popover>
                )}
              </Overlay>
              <span
                ref={updateIconRef}
                className="text-info d-inline-flex align-items-center"
                style={{ cursor: 'help' }}
                role="button"
                aria-label="Newer release available. Hover for details."
                tabIndex={0}
                aria-expanded={showUpdatePopover}
                aria-haspopup="true"
                onMouseEnter={keepUpdatePopoverOpen}
                onMouseLeave={scheduleHideUpdatePopover}
                onFocus={keepUpdatePopoverOpen}
                onBlur={() => {
                  window.setTimeout(() => {
                    const active = document.activeElement;
                    const pop = document.getElementById('reconhawx-version-update-popover');
                    if (pop && active && pop.contains(active)) return;
                    scheduleHideUpdatePopover();
                  }, 0);
                }}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="15"
                  height="15"
                  fill="currentColor"
                  viewBox="0 0 16 16"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zm-7.5 3.5a.5.5 0 0 1-1 0V5.707L5.354 7.854a.5.5 0 1 1-.708-.708l3-3a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1-.708.708L8.5 5.707V11.5z"
                  />
                </svg>
              </span>
            </>
          ) : null}
        </span>
      </div>
    </footer>
  );
}

export default AppStatusBar;
