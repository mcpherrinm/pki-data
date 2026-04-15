#!/usr/bin/env python3

"""
Script to fetch CT log schemas and lists
This script downloads the latest CT log data from Google and Apple
"""

import base64
import hashlib
import json
import os
import re
import urllib.request
import urllib.error
import sys
import csv
import io
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse


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
    ca_owner_mapping = {}  # Maps lowercase to original case
    all_records = []

    try:
        csvfile = io.StringIO(csv_data)
        reader = csv.DictReader(csvfile)

        for row in reader:
            # Clean up the row data and omit empty strings
            clean_row = {}
            for k, v in row.items():
                if v and v.strip():
                    key = k.strip()
                    value = v.strip()
                    
                    if "JSON Array" in key:
                        try:
                            parsed_value = json.loads(value)
                            if isinstance(parsed_value, list):
                                clean_row[key] = parsed_value
                            else:
                                clean_row[key] = value
                        except (json.JSONDecodeError, ValueError):
                            # If parsing fails, keep as string
                            clean_row[key] = value
                    elif "CP/CPS URL" in key or "(CP) URL" in key or "(CPS) URL" in key or "Certificate Practice & Policy Statement" in key:
                        clean_row[key] = sorted([url.strip() for url in re.split('[;\n]', value)])
                    else:
                        clean_row[key] = value
            
            all_records.append(clean_row)

            # Group by CA Owner (case-insensitive)
            ca_owner = clean_row.get("CA Owner", "").strip()
            if ca_owner:
                ca_owner_lower = ca_owner.lower()

                # Use the first occurrence's case as the canonical form
                if ca_owner_lower not in ca_owner_mapping:
                    ca_owner_mapping[ca_owner_lower] = ca_owner

                canonical_ca_owner = ca_owner_mapping[ca_owner_lower]
                ca_owners[canonical_ca_owner].append(clean_row)

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
        ca_owners_list.sort(key=lambda x: x["ca_owner"].casefold())

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

            # Sort the entries so the json files are consistent
            records.sort(key=lambda x: (x.get("Valid To (GMT)", ""), x.get("SHA-256 Fingerprint", "")))

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


def is_log_active(log):
    """Return True if the log has a temporal_interval that has not ended yet."""
    ti = log.get("temporal_interval")
    if not ti:
        return False
    end = ti.get("end_exclusive")
    if not end:
        return False
    try:
        dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return False
    return dt > datetime.now(timezone.utc)


def der_to_pem(der):
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def fetch_roots_for_log(log, seen_log_ids, accepted_by):
    """Fetch get-roots for a single log and write roots.json + PEM files."""
    log_id = log.get("log_id")
    if log_id and log_id in seen_log_ids:
        return
    if log_id:
        seen_log_ids.add(log_id)

    if not is_log_active(log):
        return

    base_url = log.get("submission_url") or log.get("url")
    if not base_url:
        return
    if not base_url.endswith("/"):
        base_url += "/"
    roots_url = base_url + "ct/v1/get-roots"

    description = log.get("description") or base_url
    print(f"Fetching roots for {description}...")
    try:
        with urllib.request.urlopen(roots_url, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError) as e:
        print(f"  Error fetching roots for {description}: {e}")
        return

    fingerprints = []
    os.makedirs("data/roots", exist_ok=True)
    for cert_b64 in data.get("certificates", []):
        try:
            der = base64.b64decode(cert_b64)
        except (ValueError, TypeError) as e:
            print(f"  Error decoding cert for {description}: {e}")
            continue
        fp = hashlib.sha256(der).hexdigest()
        fingerprints.append(fp)
        cert_path = f"data/roots/{fp}.crt"
        if not os.path.exists(cert_path):
            with open(cert_path, "w", encoding="utf-8") as f:
                f.write(der_to_pem(der))

    fingerprints = sorted(set(fingerprints))

    parsed = urlparse(base_url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    out_dir = os.path.join("data", "log", parsed.netloc, *path_parts)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "roots.json")
    save_json({"fingerprints": fingerprints}, out_path, f"roots for {description}")

    log_identifier = "/".join([parsed.netloc, *path_parts])
    for fp in fingerprints:
        accepted_by[fp].add(log_identifier)


def fetch_all_roots(*log_lists):
    """Fetch roots for every active log across the provided log lists."""
    seen = set()
    accepted_by = defaultdict(set)
    for source in log_lists:
        for op in source.get("operators", []):
            for log in op.get("logs", []):
                fetch_roots_for_log(log, seen, accepted_by)
            for log in op.get("tiled_logs", []):
                fetch_roots_for_log(log, seen, accepted_by)
    write_accepted_by(accepted_by)


def write_accepted_by(accepted_by):
    """Write the reverse mapping: for each root, which logs accept it."""
    out_dir = "data/acceptedby"
    os.makedirs(out_dir, exist_ok=True)
    desired = {f"{fp}.json" for fp in accepted_by}
    for existing in os.listdir(out_dir):
        if existing.endswith(".json") and existing not in desired:
            os.remove(os.path.join(out_dir, existing))
    for fp, logs in accepted_by.items():
        path = os.path.join(out_dir, f"{fp}.json")
        save_json({"logs": sorted(logs)}, path, f"accepted-by for {fp}")


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

    # Fetch roots for every log that is still within its temporal interval.
    fetch_all_roots(google_list, apple_list)

    # Fetch CCADB All Certificate Records CSV and convert to JSON.
    # As a temporary measure, CCADB has split this into two files.
    ccadb_csv_url_a = (
        "https://ccadb.my.salesforce-sites.com/ccadb/AllCertificateRecordsCSVFormatV4a"
    )
    ccadb_csv_url_b = (
        "https://ccadb.my.salesforce-sites.com/ccadb/AllCertificateRecordsCSVFormatV4b"
    )
    ccadb_csv_data_a = fetch_csv_data(ccadb_csv_url_a)
    ccadb_csv_data_b = fetch_csv_data(ccadb_csv_url_b)

    # Drop the header from the second file before concatenating.
    _, _, ccadb_csv_data_b_body = ccadb_csv_data_b.partition("\n")
    ccadb_csv_data = ccadb_csv_data_a
    if not ccadb_csv_data.endswith("\n"):
        ccadb_csv_data += "\n"
    ccadb_csv_data += ccadb_csv_data_b_body

    # Convert CCADB CSV to JSON
    convert_ccadb_csv_to_json(ccadb_csv_data)

    print("All CT log data and CCADB data fetched and processed successfully!")


if __name__ == "__main__":
    main()
