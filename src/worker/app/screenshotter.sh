#!/bin/bash
set -e  # Exit on any error

# Debug logging - ALL to stderr
echo "screenshotter.sh: Starting screenshot process" >&2

# Create temporary directory
tmp="/tmp/screenshots"
mkdir -p $tmp
echo "screenshotter.sh: Created temp directory: $tmp" >&2

# Check if gowitness is available
if ! command -v gowitness &> /dev/null; then
    echo "screenshotter.sh: ERROR: gowitness not found in PATH" >&2
    echo "screenshotter.sh: Available tools:" >&2
    which gowitness || echo "gowitness: not found" >&2
    ls -la /usr/local/bin/ | grep -i witness || echo "No witness tools found in /usr/local/bin/" >&2
    ls -la /usr/bin/ | grep -i witness || echo "No witness tools found in /usr/bin/" >&2
    
    # Create a dummy output to prevent empty results
    echo "screenshotter.sh: Creating dummy output due to missing gowitness" >&2
    # Output to stdout (for NATS) - clean JSON
    echo '{"error": "gowitness not available", "urls_processed": []}' | base64 | tr -d '\n'
    exit 0
fi

echo "screenshotter.sh: gowitness found at $(which gowitness)" >&2

# Debug: Show what's coming from stdin
echo "screenshotter.sh: Reading from stdin..." >&2

# URL-to-filename encoding for deterministic screenshot-to-URL mapping.
# Format: :// -> ---, : -> -, / -> ---, trim trailing ---
# Example: https://example.com:443/ -> https---example.com-443
url_to_filename() {
    echo "$1" | sed 's|://|---|' | sed 's|:|-|g' | sed 's|/|---|g' | sed 's|---*$||'
}

# Process each URL one at a time with deterministic filenames.
# This ensures correct screenshot-to-URL mapping (gowitness auto-filenames are unreliable).
url_count=0
while IFS= read -r url; do
    # Skip empty lines
    if [[ -n "$url" ]]; then
        echo "screenshotter.sh: Processing URL: '$url'" >&2
        url_count=$((url_count + 1))
        
        # Use empty subdir so we get exactly one output file per URL
        subdir="$tmp/$$_$url_count"
        mkdir -p "$subdir"
        encoded=$(url_to_filename "$url")
        
        if gowitness scan single -u "$url" -s "$subdir" --quiet --screenshot-format png --save-content --write-jsonl --write-jsonl-file "$tmp/${encoded}.jsonl" --skip-html --screenshot-fullpage; then
            echo "screenshotter.sh: Successfully took screenshot for $url" >&2
            # Rename gowitness output to our deterministic filename
            png_file=$(find "$subdir" -maxdepth 1 -name "*.png" -type f | head -1)
            if [[ -n "$png_file" ]]; then
                mv "$png_file" "$tmp/${encoded}.png"
                echo "screenshotter.sh: Renamed to ${encoded}.png" >&2
            fi
        else
            echo "screenshotter.sh: Failed to take screenshot for $url" >&2
        fi
        rm -rf "$subdir"
    else
        echo "screenshotter.sh: Skipping empty line (length: ${#url})" >&2
    fi
done

echo "screenshotter.sh: Processed $url_count URLs" >&2
echo "screenshotter.sh: Contents of $tmp:" >&2
ls -la "$tmp" >&2

# Check if we have any PNG files
cd "$tmp"
png_count=$(ls -l *.png 2>/dev/null | wc -l || echo "0")
echo "screenshotter.sh: Found $png_count PNG files" >&2

if [ "$png_count" -gt 0 ]; then
    echo "screenshotter.sh: Creating tar.gz archive" >&2
    tar czf "$tmp/output.tar.gz" ./*.png ./*.jsonl 2>/dev/null || tar czf "$tmp/output.tar.gz" ./*.png
    echo "screenshotter.sh: Archive created, size: $(ls -lh "$tmp/output.tar.gz" | awk '{print $5}')" >&2
    
    # Output base64-encoded tar.gz to stdout (for NATS) - clean data only
    base64 "$tmp/output.tar.gz" | tr -d '\n'
    echo "screenshotter.sh: Base64 output sent to stdout" >&2
else
    echo "screenshotter.sh: No PNG files found, creating error output" >&2
    # Create a JSON error output when no screenshots are available
    # Output to stdout (for NATS) - clean JSON
    error_json="{\"error\": \"No screenshots generated\", \"urls_processed\": $url_count, \"png_count\": $png_count, \"tmp_dir\": \"$tmp\"}"
    echo "$error_json" | base64 | tr -d '\n'
    echo "screenshotter.sh: Error output sent to stdout" >&2
fi

echo "screenshotter.sh: Script completed successfully" >&2