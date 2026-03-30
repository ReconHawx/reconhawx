#!/usr/bin/env python3
"""
FFUF wrapper script that handles wordlist downloading before running ffuf commands.
This script is called by command_wrapper.py when ffuf commands are executed.
"""

import sys
import os
import subprocess
import requests
import tempfile
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def is_remote_wordlist(wordlist_path):
    """Check if the wordlist is a remote URL"""
    return wordlist_path.startswith(('http://', 'https://'))

def download_wordlist(url, timeout=30):
    """Download wordlist from URL and return local path"""
    try:
        logger.info(f"Downloading wordlist from: {url}")
        if url.startswith(os.getenv('API_URL')):
            response = requests.get(url, headers={"Authorization": f"Bearer {os.getenv('INTERNAL_SERVICE_API_KEY')}"}, timeout=timeout)
        else:
            response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        temp_file.write(response.text)
        temp_file.close()
        
        logger.info(f"Downloaded wordlist to: {temp_file.name}")
        return temp_file.name
        
    except Exception as e:
        logger.error(f"Failed to download wordlist {url}: {e}")
        raise

def parse_ffuf_command(command):
    """Parse ffuf command to extract wordlist path"""
    parts = command.split()
    wordlist_path = None
    
    for i, part in enumerate(parts):
        if part == '-w' and i + 1 < len(parts):
            wordlist_path = parts[i + 1]
            break
    
    return wordlist_path, parts

def replace_wordlist_in_command(parts, new_wordlist_path):
    """Replace wordlist path in command parts"""
    for i, part in enumerate(parts):
        if part == '-w' and i + 1 < len(parts):
            parts[i + 1] = new_wordlist_path
            break
    return parts

def run_ffuf_with_wordlist_download(command):
    """Run ffuf command with wordlist downloading if needed"""
    temp_files = []
    
    try:
        # Parse the command to find wordlist
        wordlist_path, command_parts = parse_ffuf_command(command)
        
        if wordlist_path and is_remote_wordlist(wordlist_path):
            logger.info(f"Detected remote wordlist: {wordlist_path}")
            
            # Download the wordlist
            local_wordlist_path = download_wordlist(wordlist_path)
            temp_files.append(local_wordlist_path)
            
            # Replace wordlist path in command
            command_parts = replace_wordlist_in_command(command_parts, local_wordlist_path)
            
            # Reconstruct command
            command = ' '.join(command_parts)
            logger.info(f"Updated command: {command}")
        
        # Run the ffuf command
        logger.info(f"Executing ffuf command: {command}")
        
        # Use subprocess to run the command and capture output
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True
        )
        
        # Capture output
        stdout, stderr = process.communicate()
        return_code = process.returncode
        
        # Print stderr for debugging
        if stderr:
            print(f"stderr: {stderr}", file=sys.stderr)
        
        # Print stdout (this will be captured by command_wrapper.py)
        if stdout:
            print(stdout)
        
        return return_code
        
    except Exception as e:
        logger.error(f"Error in ffuf wrapper: {e}")
        print(f"Error in ffuf wrapper: {e}", file=sys.stderr)
        return 1
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    logger.info(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.error(f"Failed to clean up {temp_file}: {e}")

def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: ffuf_wrapper.py <ffuf_command>", file=sys.stderr)
        sys.exit(1)
    command = "ffuf "
    # Reconstruct the command from arguments
    command += " ".join(sys.argv[1:])
    
    # Run ffuf with wordlist downloading
    return_code = run_ffuf_with_wordlist_download(command)
    sys.exit(return_code)

if __name__ == "__main__":
    main() 