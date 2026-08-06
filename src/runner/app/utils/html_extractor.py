"""
Extract readable text from gowitness JSONL output.
Parses network[].content (base64 HTML) and uses BeautifulSoup to get visible text.
"""

import base64
import json
import logging
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Max extracted text size to avoid DB bloat (50KB)
MAX_EXTRACTED_TEXT_BYTES = 50 * 1024


def load_gowitness_entries(jsonl_path: str) -> list:
    """
    Load all valid JSON objects from a gowitness JSONL file (one object per line).

    ``gowitness scan file`` writes a single JSONL with one line per scanned URL, so callers
    iterate the returned entries to map each screenshot (via ``file_name``) back to its URL.

    Returns an empty list if the file is missing or unreadable; malformed lines are skipped.
    """
    entries: list = []
    try:
        with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Failed to load entries from {jsonl_path}: {e}")
    return entries


def extract_text_from_gowitness_entry(entry: dict, url: Optional[str] = None) -> Optional[str]:
    """
    Extract readable text from a single parsed gowitness JSONL entry.

    Primary source is the main document's response body in ``network[].content`` (base64),
    populated by ``--save-content``: request_type 0, status_code 200, mime_type "text/html".
    Falls back to the top-level ``html`` field when present (i.e. when ``--skip-html`` is not
    used), so extraction is robust to which field gowitness populates.

    Args:
        entry: Parsed JSON object for one URL.
        url: Optional URL to match against the entry (handles :443 vs implicit port); if the
            entry is for a different URL, returns None.

    Returns:
        Extracted text or None if no HTML body is available.
    """
    try:
        if url:
            entry_url = entry.get('final_url') or entry.get('url', '')
            if entry_url and not _urls_match(url, entry_url):
                return None

        network = entry.get('network') or []
        final_url = (entry.get('final_url') or entry.get('url') or '').rstrip('/')

        for req in network:
            if (req.get('request_type') == 0
                    and req.get('status_code') == 200
                    and (req.get('mime_type') or '').lower() == 'text/html'):
                req_url = (req.get('url') or '').rstrip('/')
                if not final_url or req_url == final_url or req_url.startswith(final_url.split('?')[0]):
                    content_b64 = req.get('content')
                    if not content_b64:
                        continue
                    try:
                        html_bytes = base64.b64decode(content_b64)
                        html_str = html_bytes.decode('utf-8', errors='replace')
                    except Exception as e:
                        logger.debug(f"Failed to decode base64 content: {e}")
                        continue

                    text = _extract_text_from_html(html_str)
                    if text:
                        return _truncate_text(text)

        # Fallback: top-level html field (populated when --skip-html is not set).
        top_html = entry.get('html')
        if top_html:
            text = _extract_text_from_html(top_html)
            if text:
                return _truncate_text(text)

        return None
    except Exception as e:
        logger.debug(f"Failed to extract text from gowitness entry: {e}")
        return None


def extract_text_from_gowitness_jsonl(jsonl_path: str, url: Optional[str] = None) -> Optional[str]:
    """
    Parse a gowitness JSONL file and extract readable text for the first (matching) entry.

    Thin wrapper over :func:`extract_text_from_gowitness_entry` kept for single-entry callers.
    When ``url`` is provided, non-matching lines are skipped; otherwise the first line is used.

    Args:
        jsonl_path: Path to gowitness.jsonl file (one JSON object per line)
        url: Optional URL to match (for multi-entry JSONL); if None, uses first entry

    Returns:
        Extracted text or None if extraction fails
    """
    for entry in load_gowitness_entries(jsonl_path):
        if url:
            entry_url = entry.get('final_url') or entry.get('url', '')
            if entry_url and not _urls_match(url, entry_url):
                continue
        return extract_text_from_gowitness_entry(entry)
    return None


def _urls_match(a: str, b: str) -> bool:
    """Compare URLs, normalizing default ports (e.g. https:443 == https)."""
    if not a or not b:
        return a == b
    a, b = a.rstrip('/'), b.rstrip('/')
    if a == b:
        return True
    try:
        pa, pb = urlparse(a), urlparse(b)
        # Normalize port: treat None as default for scheme (https=443, http=80)
        def norm_port(parsed):
            p = parsed.port
            if p is None:
                p = 443 if parsed.scheme == 'https' else (80 if parsed.scheme == 'http' else None)
            return p
        if pa.scheme != pb.scheme or pa.hostname != pb.hostname:
            return False
        if norm_port(pa) != norm_port(pb):
            return False
        return (pa.path or '/') == (pb.path or '/')
    except Exception:
        return a == b


def _extract_text_from_html(html: str) -> Optional[str]:
    """Parse HTML with BeautifulSoup and extract visible text."""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        # Remove script and style elements
        for tag in soup(['script', 'style']):
            tag.decompose()
        text = soup.get_text(separator=' ', strip=True)
        # Normalize whitespace
        return ' '.join(text.split()) if text else None
    except Exception as e:
        logger.debug(f"Failed to parse HTML: {e}")
        return None


def _truncate_text(text: str) -> str:
    """Truncate text to max size (bytes)."""
    encoded = text.encode('utf-8')
    if len(encoded) <= MAX_EXTRACTED_TEXT_BYTES:
        return text
    # Truncate and add ellipsis
    truncated = encoded[:MAX_EXTRACTED_TEXT_BYTES - 3].decode('utf-8', errors='ignore')
    return truncated.rstrip() + '...'


def extract_text_from_image_ocr(image_path_or_bytes) -> Optional[str]:
    """
    Run Tesseract OCR on screenshot image. Returns None if Tesseract unavailable or fails.

    Args:
        image_path_or_bytes: Path to image file (str) or image bytes

    Returns:
        Extracted text or None
    """
    try:
        import io
        import pytesseract
        from PIL import Image

        if isinstance(image_path_or_bytes, bytes):
            img = Image.open(io.BytesIO(image_path_or_bytes))
        else:
            img = Image.open(image_path_or_bytes)

        text = pytesseract.image_to_string(img)
        normalized = ' '.join(text.split()).strip()
        if not normalized:
            return None
        return _truncate_text(normalized)
    except ModuleNotFoundError as e:
        logger.warning("OCR skipped (missing Python dependency): %s", e)
        return None
    except Exception as e:
        if type(e).__name__ == "TesseractNotFoundError":
            logger.warning("OCR skipped (Tesseract binary not found on PATH): %s", e)
        else:
            logger.debug("OCR failed: %s", e)
        return None
