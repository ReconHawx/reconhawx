import logging
import os
from typing import Dict, List, Any, Optional
import base64
import tarfile
import tempfile
from .base import Task, AssetType, FindingType
from models.findings import TyposquatScreenshot
from utils import (
    get_valid_urls,
    normalize_url_for_storage,
)
from utils.html_extractor import (
    extract_text_from_gowitness_entry,
    extract_text_from_image_ocr,
    load_gowitness_entries,
)

logger = logging.getLogger(__name__)

class ScreenshotWebsite(Task):
    name = "screenshot_website"
    description = "Screenshot a website"
    input_type = AssetType.URL
    output_types = [AssetType.SCREENSHOT]
    chunk_size = 10

    def __init__(self):
        super().__init__()

    def get_timestamp_hash(self, target: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        hash_dict = {
            "task": self.name,
            "target": target
        }
        # Create a reversible hash by using base64 encoding of the dict string
        hash_str = str(hash_dict)
        return base64.b64encode(hash_str.encode()).decode()
    
    def get_command(self, input_data: Any, params: Optional[Dict[Any, Any]] = None) -> str:
        """Generate command to use the worker crawl_website.py script"""
        try:
            targets_to_process = input_data if isinstance(input_data, list) else [input_data]
            
            # Filter valid URLs from the targets list
            urls_to_process = get_valid_urls(targets_to_process)
            
            # Normalize URLs before processing
            normalized_urls = [normalize_url_for_storage(url) for url in urls_to_process]
            
            if len(normalized_urls) > 0:
                # Join URLs with here document for proper newlines
                urls_text = '\n'.join(normalized_urls)
                command = f"cat << 'EOF' | bash screenshotter.sh\n{urls_text}\nEOF"
                return command
            return ""
        except Exception as e:
            logger.error(f"Error generating command: {e}")
            return ""   
    
    def parse_output(self, output, params: Optional[Dict[Any, Any]] = None) -> Dict[AssetType, List[Any]]:
        """Parse the output from the worker script and return screenshot assets"""
        screenshots = []

        try:
            # Use the base class helper to normalize output format
            normalized_output = self.normalize_output_for_parsing(output)

            # Skip if output is empty or just whitespace
            if not normalized_output or not normalized_output.strip():
                logger.warning("Empty output received from screenshotter")
                return {AssetType.SCREENSHOT: []}

            # Try to decode base64 output
            try:
                archive_data = base64.b64decode(normalized_output.strip())
            except Exception as decode_error:
                logger.error(f"Error decoding base64 output: {decode_error}")
                logger.error(f"Raw output preview: {normalized_output[:200]}...")
                return {AssetType.SCREENSHOT: []}
            
            # Check if the decoded data looks like a tar.gz archive
            if len(archive_data) < 10 or not archive_data.startswith(b'\x1f\x8b'):
                # This might be a JSON error message instead of a tar.gz
                try:
                    decoded_text = archive_data.decode('utf-8')
                    if decoded_text.startswith('{') and 'error' in decoded_text:
                        logger.warning(f"Screenshot task returned error: {decoded_text}")
                        return {AssetType.SCREENSHOT: []}
                except UnicodeDecodeError:
                    pass
                
                logger.warning(f"Decoded data doesn't look like a tar.gz archive (size: {len(archive_data)}, starts with: {archive_data[:10].hex()})")
                return {AssetType.SCREENSHOT: []}
            
            # Create temporary directory to extract files
            with tempfile.TemporaryDirectory() as temp_dir:
                # Write archive to temporary file
                archive_path = os.path.join(temp_dir, "screenshots.tar.gz")
                with open(archive_path, 'wb') as f:
                    f.write(archive_data)
                
                # Extract tar.gz archive
                with tarfile.open(archive_path, 'r:gz') as tar:
                    tar.extractall(temp_dir)

                # Locate the single gowitness JSONL: it is the authoritative source for the
                # URL <-> screenshot mapping (via each entry's `file_name` / `url`), replacing
                # the old lossy filename encoding round-trip.
                jsonl_path = None
                for fn in os.listdir(temp_dir):
                    if fn.endswith('.jsonl'):
                        jsonl_path = os.path.join(temp_dir, fn)
                        break

                if not jsonl_path:
                    logger.warning(
                        "No JSONL found in screenshot archive; cannot map screenshots to URLs"
                    )
                    return {AssetType.SCREENSHOT: []}

                seen_files: set = set()
                for entry in load_gowitness_entries(jsonl_path):
                    # Authoritative URL straight from gowitness (no reconstruction).
                    raw_url = entry.get('final_url') or entry.get('url') or ''
                    if not raw_url:
                        continue
                    url = normalize_url_for_storage(raw_url)

                    file_name = entry.get('file_name') or ''
                    if not file_name or entry.get('failed'):
                        logger.info(
                            "Skipping screenshot for %s (failed=%s, file_name=%r): %s",
                            url,
                            entry.get('failed'),
                            file_name,
                            entry.get('failed_reason') or "",
                        )
                        continue

                    image_path = os.path.join(temp_dir, os.path.basename(file_name))
                    if not os.path.exists(image_path):
                        logger.warning(
                            "Screenshot file missing for %s: %s", url, file_name
                        )
                        continue

                    if file_name in seen_files:
                        logger.warning(
                            "Duplicate screenshot file_name %s for %s; gowitness may have "
                            "overwritten an earlier capture",
                            file_name,
                            url,
                        )
                    seen_files.add(file_name)

                    # Read image data as bytes
                    with open(image_path, 'rb') as img_file:
                        image_data = img_file.read()

                    # Text from the same JSONL entry (HTML body); OCR fallback if empty.
                    extracted_text = extract_text_from_gowitness_entry(entry)
                    if extracted_text:
                        logger.debug(
                            "Extracted %d chars from JSONL for %s", len(extracted_text), url
                        )
                    if not extracted_text or not extracted_text.strip():
                        extracted_text = extract_text_from_image_ocr(image_path)

                    # Create screenshot asset object
                    screenshot_asset = {
                        "url": url,
                        "image_data": base64.b64encode(image_data).decode(),
                        "filename": os.path.basename(file_name),
                        "image_size": len(image_data),
                        "status": "captured"
                    }
                    if extracted_text is not None:
                        screenshot_asset["extracted_text"] = extracted_text
                    screenshots.append(screenshot_asset)


            logger.info(f"Successfully processed {len(screenshots)} screenshots")
            
        except Exception as e:
            logger.error(f"Error parsing screenshotter output: {e}")
            return {AssetType.SCREENSHOT: []}
        
        return {AssetType.SCREENSHOT: screenshots}

    def transform_to_findings(
        self, assets: Dict[AssetType, List[Any]], context: Dict[str, Any]
    ) -> Dict[Any, List[Any]]:
        """
        Transform screenshot assets to TyposquatScreenshot findings for typosquat workflows.

        Same dual-purpose pattern as fuzz_website: parse_output produces assets; this method
        produces findings when output_mode is typosquat_findings.
        """
        screenshots = assets.get(AssetType.SCREENSHOT, [])
        if not screenshots:
            logger.info("No screenshots to transform to findings")
            return {}

        program_name = context.get("program_name") or os.getenv("PROGRAM_NAME", "")
        workflow_id = context.get("workflow_id") or os.getenv("WORKFLOW_ID", "unknown")
        step_name = context.get("step_name") or "screenshot_website"

        logger.info(
            f"Transforming {len(screenshots)} screenshot assets to TyposquatScreenshot findings"
        )

        findings = []
        for shot in screenshots:
            try:
                if isinstance(shot, dict):
                    url = shot.get("url", "")
                    image_data = shot.get("image_data", "")
                    filename = shot.get("filename")
                    extracted_text = shot.get("extracted_text")
                else:
                    url = getattr(shot, "url", "")
                    image_data = getattr(shot, "image_data", "")
                    filename = getattr(shot, "filename", None)
                    extracted_text = getattr(shot, "extracted_text", None)

                if not url or not image_data:
                    logger.warning("Skipping screenshot finding with missing url or image_data")
                    continue

                finding = TyposquatScreenshot(
                    url=url,
                    image_data=image_data,
                    filename=filename,
                    extracted_text=extracted_text,
                    workflow_id=workflow_id,
                    step_name=step_name,
                    program_name=program_name,
                )
                findings.append(finding)
            except Exception as e:
                logger.error(f"Error transforming screenshot asset to finding: {e}")

        logger.info(f"Successfully transformed {len(findings)} screenshots to typosquat findings")
        return {FindingType.TYPOSQUAT_SCREENSHOT: findings}
