import logging
from typing import Dict, List, Any, Optional
import base64
import tarfile
import tempfile
import os
import re
from .base import Task, AssetType
from utils import (
    get_valid_urls,
    normalize_url_for_storage,
)
from utils.html_extractor import extract_text_from_gowitness_jsonl, extract_text_from_image_ocr

logger = logging.getLogger(__name__)

class ScreenshotWebsite(Task):
    name = "screenshot_website"
    description = "Screenshot a website"
    input_type = AssetType.STRING
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
                
                # Process each PNG file
                for filename in os.listdir(temp_dir):
                    if filename.endswith('.png'):
                        # Convert filename back to URL
                        # The filename format depends on how the screenshotter encodes URLs
                        # We need to reverse the encoding process carefully
                        
                        url = filename[:-4]  # Remove .png extension
                        
                        # Replace URL encoding back to original format
                        # First, replace --- with :// for the protocol
                        url = url.replace('---', '://', 1)
                        
                        # Replace remaining --- with / for paths
                        url = url.replace('---', '/')
                        
                        # Handle port numbers more carefully
                        # Look for pattern like -PORT- or -PORT at the end
                        if ':' not in url.split('://')[1]:  # No port yet in the URL
                            # Look for port pattern: -digits- or -digits at end
                            port_match = re.search(r'-(\d+)-?$', url)
                            if port_match:
                                port = port_match.group(1)
                                # Remove the port pattern and add it properly
                                url = re.sub(r'-\d+-?$', f':{port}', url)
                        
                        # Clean up any trailing dashes that might have been left
                        url = url.rstrip('-')
                        
                        # If URL doesn't end with /, add it (since we sent normalized URLs)
                        if not url.endswith('/') and '/' not in url.split('://', 1)[1]:
                            url += '/'
                        
                        
                        # Don't normalize again since we should already have the correct format
                        # url = normalize_url_for_storage(url)
                        
                        # Read image data as bytes
                        image_path = os.path.join(temp_dir, filename)
                        with open(image_path, 'rb') as img_file:
                            image_data = img_file.read()
                        
                        # Extract text from matching JSONL (same encoded filename)
                        # Pass url=None: filename match is sufficient; gowitness URL format may differ (e.g. :443 vs implicit)
                        jsonl_filename = filename[:-4] + '.jsonl'
                        jsonl_path = os.path.join(temp_dir, jsonl_filename)
                        extracted_text = None
                        if os.path.exists(jsonl_path):
                            extracted_text = extract_text_from_gowitness_jsonl(jsonl_path, url=None)
                            if extracted_text:
                                logger.debug(f"Extracted {len(extracted_text)} chars from {jsonl_filename}")
                        else:
                            logger.debug(f"JSONL not found for {filename}: {jsonl_path}")
                        # OCR fallback when HTML yields no text
                        if not extracted_text or not extracted_text.strip():
                            extracted_text = extract_text_from_image_ocr(image_path)
                        # Create screenshot asset object
                        screenshot_asset = {
                            "url": url,
                            "image_data": base64.b64encode(image_data).decode(),
                            "filename": filename,
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
    