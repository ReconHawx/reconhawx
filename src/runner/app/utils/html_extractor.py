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


def extract_text_from_gowitness_jsonl(jsonl_path: str, url: Optional[str] = None) -> Optional[str]:
    """
    Parse gowitness JSONL file, find main HTML from network[].content, extract readable text.

    With --skip-html, the top-level html field is empty; HTML lives only in network[].content (base64).
    Main document: request_type 0, status_code 200, mime_type "text/html".

    Args:
        jsonl_path: Path to gowitness.jsonl file (one JSON object per line)
        url: Optional URL to match (for multi-entry JSONL); if None, uses first entry

    Returns:
        Extracted text or None if extraction fails
    """
    try:
        with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        if not lines:
            return None

        # Parse first line (gowitness scan single produces one JSON per URL)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Optional: match by url/final_url if provided (normalize to handle :443 vs implicit port)
            if url:
                entry_url = entry.get('final_url') or entry.get('url', '')
                if entry_url and not _urls_match(url, entry_url):
                    continue

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
            break  # Only process first matching entry

        return None
    except Exception as e:
        logger.debug(f"Failed to extract text from {jsonl_path}: {e}")
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
    except Exception as e:
        logger.debug(f"OCR failed: {e}")
        return None
