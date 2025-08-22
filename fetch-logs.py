#!/usr/bin/env python3

"""
Script to fetch CT log schemas and lists
This script downloads the latest CT log data from Google and Apple
"""

import json
import os
import urllib.request
import urllib.error
import sys


def fetch_json(url, description):
    """Fetch JSON data from a URL and return parsed JSON."""
    print(f"Fetching {description}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except urllib.error.URLError as e:
        print(f"Error fetching {description}: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON for {description}: {e}")
        sys.exit(1)


def save_json(data, filepath, description):
    """Save JSON data to a file with pretty formatting."""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved {description} to {filepath}")
    except IOError as e:
        print(f"Error saving {description}: {e}")
        sys.exit(1)


def main():
    """Main function to fetch all CT log data."""
    
    # Fetch Google CT Log Schema
    google_schema_url = 'https://www.gstatic.com/ct/log_list/v3/log_list_schema.json'
    google_schema = fetch_json(google_schema_url, "Google CT Log Schema")
    save_json(google_schema, 'data/google/log_list_schema.json', "Google CT Log Schema")
    
    # Fetch Apple CT Log Schema
    apple_schema_url = 'https://valid.apple.com/ct/log_list/schema_versions/log_list_schema_v5.json'
    apple_schema = fetch_json(apple_schema_url, "Apple CT Log Schema")
    save_json(apple_schema, 'data/apple/log_list_schema_v5.json', "Apple CT Log Schema")
    
    # Fetch Apple CT Log List
    apple_list_url = 'https://valid.apple.com/ct/log_list/current_log_list.json'
    apple_list = fetch_json(apple_list_url, "Apple CT Log List")
    save_json(apple_list, 'data/apple/current_log_list.json', "Apple CT Log List")
    
    # Fetch Google CT Log List
    google_list_url = 'https://www.gstatic.com/ct/log_list/v3/all_logs_list.json'
    google_list = fetch_json(google_list_url, "Google CT Log List")
    
    # Google has a version & log_list_timestamp that increment daily - ignore them
    if 'version' in google_list:
        del google_list['version']
    if 'log_list_timestamp' in google_list:
        del google_list['log_list_timestamp']
    
    save_json(google_list, 'data/google/all_log_list.json', "Google CT Log List")
    
    print("All CT log data fetched successfully!")


if __name__ == '__main__':
    main()