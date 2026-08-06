#!/bin/bash
set -e  # Exit on any error

# Debug logging - ALL to stderr
echo "screenshotter.sh: Starting screenshot process" >&2

# Fresh per-invocation temp directory (avoid archiving stale files from a prior run).
tmp="/tmp/screenshots"
rm -rf "$tmp"
mkdir -p "$tmp"
echo "screenshotter.sh: Using temp directory: $tmp" >&2

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

# Concurrent scan threads (gowitness default is 6). Override with GOWITNESS_THREADS; keep it
# modest by default because each thread drives a headless Chrome doing full-page screenshots.
threads="${GOWITNESS_THREADS:-4}"

# Read URLs from stdin into a targets file (skip blank lines).
echo "screenshotter.sh: Reading from stdin..." >&2
urls_file="$tmp/urls.txt"
url_count=0
while IFS= read -r url; do
    if [[ -n "$url" ]]; then
        printf '%s\n' "$url" >> "$urls_file"
        url_count=$((url_count + 1))
    else
        echo "screenshotter.sh: Skipping empty line" >&2
    fi
done

echo "screenshotter.sh: Read $url_count URL(s) from stdin" >&2

if [[ "$url_count" -eq 0 ]]; then
    echo "screenshotter.sh: No URLs provided" >&2
    echo '{"error": "No URLs provided", "urls_processed": 0}' | base64 | tr -d '\n'
    exit 0
fi

# Single concurrent batch scan. gowitness names the screenshots itself and records the
# authoritative URL <-> file_name mapping (plus per-request HTML in network[].content via
# --save-content) in the JSONL, so no manual filename encoding / reverse-engineering is needed.
jsonl="$tmp/gowitness.jsonl"

# Guard against `set -e`: gowitness may exit non-zero when some targets fail, but we still
# want to archive whatever screenshots did succeed.
if gowitness scan file -f "$urls_file" -s "$tmp" --threads "$threads" \
    --quiet --screenshot-format png --save-content \
    --write-jsonl --write-jsonl-file "$jsonl" \
    --skip-html --screenshot-fullpage; then
    echo "screenshotter.sh: gowitness scan completed" >&2
else
    echo "screenshotter.sh: gowitness scan exited non-zero (partial results possible)" >&2
fi

echo "screenshotter.sh: Contents of $tmp:" >&2
ls -la "$tmp" >&2

# Check if we have any PNG files
cd "$tmp"
png_count=$(find . -maxdepth 1 -name '*.png' -type f | wc -l)
echo "screenshotter.sh: Found $png_count PNG file(s)" >&2

if [ "$png_count" -gt 0 ]; then
    echo "screenshotter.sh: Creating tar.gz archive" >&2
    # Include the single JSONL so the runner can map screenshots to URLs and extract text.
    if [[ -f "$jsonl" ]]; then
        tar czf "$tmp/output.tar.gz" ./*.png "$(basename "$jsonl")"
    else
        tar czf "$tmp/output.tar.gz" ./*.png
    fi
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
