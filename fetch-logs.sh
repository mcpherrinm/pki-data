#!/bin/bash

# Script to fetch CT log schemas and lists
# This script downloads the latest CT log data from Google and Apple

set -e  # Exit on any error

echo "Fetching Google CT Log Schema..."
curl -sSL 'https://www.gstatic.com/ct/log_list/v3/log_list_schema.json' | jq . > data/google/log_list_schema.json

echo "Fetching Apple CT Log Schema..."
curl -sSL 'https://valid.apple.com/ct/log_list/schema_versions/log_list_schema_v5.json' | jq . > data/apple/log_list_schema_v5.json

echo "Fetching Apple CT Log List..."
curl -sSL 'https://valid.apple.com/ct/log_list/current_log_list.json' | jq . > data/apple/current_log_list.json

echo "Fetching Google CT Log List..."
curl -sSL 'https://www.gstatic.com/ct/log_list/v3/all_logs_list.json' | jq 'del(.version, .log_list_timestamp)' > data/google/all_log_list.json

echo "All CT log data fetched successfully!"