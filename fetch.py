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
import csv
import io
from collections import defaultdict


def fetch_json(url, description):
    """Fetch JSON data from a URL and return parsed JSON."""
    print(f"Fetching {description}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read().decode("utf-8")
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
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"Saved {description} to {filepath}")
    except IOError as e:
        print(f"Error saving {description}: {e}")
        sys.exit(1)


def fetch_csv_data(url):
    """Fetch CSV data from a URL and return it as a string."""
    print(f"Fetching {url}...")
    try:
        with urllib.request.urlopen(url) as response:
            data = response.read().decode("utf-8")
            return data
    except urllib.error.URLError as e:
        print(f"Error fetching {url}: {e}")
        sys.exit(1)
    except UnicodeDecodeError as e:
        print(f"Error decoding CSV data for {url}: {e}")
        sys.exit(1)


def convert_ccadb_csv_to_json(csv_data):
    """Convert CCADB CSV data to JSON format."""
    print("Converting CCADB CSV to JSON...")

    # Dictionary to group records by CA Owner
    ca_owners = defaultdict(list)
    all_records = []

    try:
        csvfile = io.StringIO(csv_data)
        reader = csv.DictReader(csvfile)

        for row in reader:
            # Clean up the row data and omit empty strings
            clean_row = {
                k.strip(): v.strip() for k, v in row.items() if v and v.strip()
            }
            all_records.append(clean_row)

            # Group by CA Owner
            ca_owner = clean_row.get("CA Owner", "").strip()
            if ca_owner:
                ca_owners[ca_owner].append(clean_row)

        # Create main JSON file with list of all CA owners
        ca_owners_list = []
        for ca_owner, records in ca_owners.items():
            # Collect countries (deduplicated)
            countries = set()

            for record in records:
                # Collect country
                country = record.get("Country", "").strip()
                if country:
                    countries.add(country)

            # Calculate aggregated counts for roots and intermediates
            trusted_roots = 0
            partially_trusted_roots = 0
            untrusted_roots = 0
            intermediates = 0

            for record in records:
                record_type = record.get("Certificate Record Type", "").strip()

                if record_type == "Intermediate Certificate":
                    intermediates += 1
                elif record_type == "Root Certificate":
                    # Get statuses for all four programs
                    apple_status = record.get("Apple Status", "").strip()
                    chrome_status = record.get("Chrome Status", "").strip()
                    microsoft_status = record.get("Microsoft Status", "").strip()
                    mozilla_status = record.get("Mozilla Status", "").strip()

                    # Define trusted statuses for each program
                    trusted_statuses = {
                        "apple": ["Included"],
                        "chrome": ["Included"],
                        "microsoft": ["Included", "Trusted"],
                        "mozilla": ["Included"],
                    }

                    # Count how many programs trust this root
                    trusted_count = 0
                    if apple_status in trusted_statuses["apple"]:
                        trusted_count += 1
                    if chrome_status in trusted_statuses["chrome"]:
                        trusted_count += 1
                    if microsoft_status in trusted_statuses["microsoft"]:
                        trusted_count += 1
                    if mozilla_status in trusted_statuses["mozilla"]:
                        trusted_count += 1

                    # Categorize based on trust level
                    if trusted_count == 4:
                        trusted_roots += 1
                    elif trusted_count > 0:
                        partially_trusted_roots += 1
                    else:
                        untrusted_roots += 1

            # Create enhanced CA owner entry
            ca_entry = {
                "ca_owner": ca_owner,
                "record_count": len(records),
                "countries": sorted(list(countries)),
                "aggregated_counts": {
                    "trusted_roots": trusted_roots,
                    "partially_trusted_roots": partially_trusted_roots,
                    "untrusted_roots": untrusted_roots,
                    "intermediates": intermediates,
                },
            }

            ca_owners_list.append(ca_entry)

        # Sort by CA owner name
        ca_owners_list.sort(key=lambda x: x["ca_owner"])

        # Create individual JSON files per CA Owner and update ca_owners_list with filenames
        os.makedirs("data/ccadb/ca", exist_ok=True)
        for i, (ca_owner, records) in enumerate(ca_owners.items()):
            # Create safe filename from CA owner name
            safe_filename = "".join(
                c for c in ca_owner if c.isalnum() or c in (" ", "-", "_")
            ).rstrip()
            safe_filename = safe_filename.replace(" ", "_")
            if not safe_filename:
                safe_filename = "unknown_ca"

            filepath = f"data/ccadb/ca/{safe_filename}.json"
            filename = f"{safe_filename}.json"

            # Add filename to the corresponding ca_owners_list entry
            for ca_entry in ca_owners_list:
                if ca_entry["ca_owner"] == ca_owner:
                    ca_entry["output_filename"] = filename
                    break

            save_json(records, filepath, f"CCADB records for {ca_owner}")

        # Save main JSON file after filenames have been added
        main_json = {
            "total_ca_owners": len(ca_owners_list),
            "total_records": len(all_records),
            "ca_owners": ca_owners_list,
        }
        save_json(main_json, "data/ccadb/ca_owners.json", "CCADB CA Owners list")

        print(
            f"Converted CCADB CSV to JSON: {len(ca_owners)} CA owners, {len(all_records)} total records"
        )

    except IOError as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error converting CSV to JSON: {e}")
        sys.exit(1)


def main():
    """Main function to fetch all CT log data."""

    # Fetch Google CT Log Schema
    google_schema_url = "https://www.gstatic.com/ct/log_list/v3/log_list_schema.json"
    google_schema = fetch_json(google_schema_url, "Google CT Log Schema")
    save_json(google_schema, "data/google/log_list_schema.json", "Google CT Log Schema")

    # Fetch Apple CT Log Schema
    apple_schema_url = (
        "https://valid.apple.com/ct/log_list/schema_versions/log_list_schema_v5.json"
    )
    apple_schema = fetch_json(apple_schema_url, "Apple CT Log Schema")
    save_json(apple_schema, "data/apple/log_list_schema_v5.json", "Apple CT Log Schema")

    # Fetch Apple CT Log List
    apple_list_url = "https://valid.apple.com/ct/log_list/current_log_list.json"
    apple_list = fetch_json(apple_list_url, "Apple CT Log List")
    save_json(apple_list, "data/apple/current_log_list.json", "Apple CT Log List")

    # Fetch Google CT Log List
    google_list_url = "https://www.gstatic.com/ct/log_list/v3/all_logs_list.json"
    google_list = fetch_json(google_list_url, "Google CT Log List")

    # Google has a version & log_list_timestamp that increment daily - ignore them
    if "version" in google_list:
        del google_list["version"]
    if "log_list_timestamp" in google_list:
        del google_list["log_list_timestamp"]

    save_json(google_list, "data/google/all_log_list.json", "Google CT Log List")

    # Fetch CCADB All Certificate Records CSV and convert to JSON
    ccadb_csv_url = (
        "https://ccadb.my.salesforce-sites.com/ccadb/AllCertificateRecordsCSVFormatv3"
    )
    ccadb_csv_data = fetch_csv_data(ccadb_csv_url)

    # Convert CCADB CSV to JSON
    convert_ccadb_csv_to_json(ccadb_csv_data)

    print("All CT log data and CCADB data fetched and processed successfully!")


if __name__ == "__main__":
    main()
