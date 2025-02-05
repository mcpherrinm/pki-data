#!/usr/bin/env python3

"""
This script renders files in data/ into HTML files.

"""
from base64 import b64decode, b64encode
from datetime import datetime
from urllib import request
import hashlib
import jinja2
import json
import os


def load_log_lists(fetch):
    """Load the Google and Apple log lists. If fetch is true,
    try to fetch them from the network.
    """

    apple_log_file = "data/apple/current_log_list.json"
    apple_log_url = "https://valid.apple.com/ct/log_list/current_log_list.json"
    google_log_file = "data/google/all_log_list.json"
    google_log_url = "https://www.gstatic.com/ct/log_list/v3/all_logs_list.json"

    if fetch:
        resp = request.urlopen(apple_log_url)
        if resp.status != 200:
            raise Exception("didn't get a 200")
        apple_log_data = json.load(resp)

        with open(apple_log_file, 'w') as f:
            json.dump(apple_log_data, f, indent=2)
            f.write("\n")

        resp = request.urlopen(google_log_url)
        if resp.status != 200:
            raise Exception("didn't get a 200")
        google_log_data = json.load(resp)

        # These change daily, leading to extra churn:
        del google_log_data["version"]
        del google_log_data["log_list_timestamp"]

        with open(google_log_file, 'w') as f:
            json.dump(google_log_data, f, indent=2)
            f.write("\n")

    # Always re-read:
    with open(apple_log_file) as alf:
        apple_logs = json.load(alf)
    with open(google_log_file) as glf:
        google_logs = json.load(glf)


    return apple_logs, google_logs


def log_name(operator, description):
    """The log descriptions are a bit verbose. This extracts a concise log name from them"""
    orig = description

    for suffix in ["CT Log", "CT log", "Log", "log", " ", "'"]:
        description = description.removesuffix(suffix)
    for prefix in [operator, "Nordu", "Up In The Air", "Symantec", " ", "'"]:
        description = description.removeprefix(prefix)

    if len(description) == 0:
        return orig

    return description


def flatten_logs(logs):
    """Take the nested structure and flatten into a list of key-value log descriptions"""
    for operator in logs["operators"]:
        op_name = operator["name"]
        for log in operator["logs"] + operator.get("tiled_logs", []):
            log["operator"] = op_name
            log["name"] = log_name(op_name, log["description"])
            state = log.pop("state", None)
            if state is not None:
                log["state"] = list(state.keys())[0]
                log["state_timestamp"] = state[log["state"]]["timestamp"]
            temporal_interval = log.pop("temporal_interval", None)
            if temporal_interval is not None:
                log["start"] = temporal_interval["start_inclusive"]
                log["end"] = temporal_interval["end_exclusive"]
            yield log


def all_keys(a, b):
    if a is None:
        return set(b.keys())
    if b is None:
        return set(a.keys())
    return set(a.keys()).union(set(b.keys()))


def merge_state_conflict(apple, google):
    if google == "rejected" or apple == "rejected":
        return "rejected"
    if google == "pending" or apple == "pending":
        return "pending"
    if apple == "usable" and google != "usable":
        return google
    if google == "usable" and apple != "usable":
        return apple

    # jank for other potential cases:
    return apple + google


def merge_item(d, k, apple_value, google_value):
    if apple_value == None:
        d[k] = google_value
        return
    if google_value == None:
        d[k] = apple_value
        return
    if apple_value == google_value:
        d[k] = apple_value
        return
    if k == "name":
        # Only really want one of the names, so pick one
        d[k] = google_value
        return
    if k == "state":
        # Resolve state conflicts specially
        d[k] = merge_state_conflict(apple_value, google_value)
        # No return here, keep the originals too
    d["apple_" + k] = apple_value
    d["google_" + k] = google_value


def cond_get(m, k):
    if m is None:
        return None
    return m.get(k, None)


def merge_log(apple, google):
    """Merge the two entries into a single one"""
    merge = {"apple": apple is not None, "google": google is not None}
    for key in all_keys(apple, google):
        merge_item(merge, key, cond_get(apple, key), cond_get(google, key))
    return merge


def merge_log_lists(apple_logs, google_logs):
    """Merge the flattened apple & google lists into one shared structure"""
    apple_map = {log.get("url") or log.get("submission_url"): log for log in apple_logs}
    google_map = {log.get("url") or log.get("submission_url"): log for log in google_logs}

    for log in all_keys(apple_map, google_map):
        yield merge_log(apple_map.get(log, None), google_map.get(log, None))

def fetch_accepted_roots(log_list):
    """Fetch and store all the accepted roots from each log"""
    for log in log_list:
        end = log.get("end")
        if end:
            if datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ") < datetime.now():
                continue
        state = log.get("state")
        if state is None or state == "rejected":
            # TODO: I want roots from test logs too, which don't have a state
            continue

        url = log.get("url") or log.get("submission_url")

        try:
            resp = request.urlopen(url + "ct/v1/get-roots", timeout=5)
        except Exception as e:
            print(f"failed to fetch {url}: {e}")
            continue
        if resp.status != 200:
            print(f"error on {url}: {resp.status}")
            continue

        try:
            roots = json.loads(resp.read())
        except Exception as e:
            print(f"failed to read {url}: {e}")
            continue
        accepted_roots = []
        for root in roots["certificates"]:
            der = b64decode(root)
            accepted_roots.append(write_root(der))
        if url.startswith("https://"):
            url = url[len("https://"):]
        logdir = f"data/log/{url}"
        os.makedirs(logdir,exist_ok=True)
        with open(f"{logdir}/roots.json", "w") as f:
            json.dump({"fingerprints": sorted(accepted_roots)}, f, indent=2)

def write_root(der):
    """Write out a root certificate into data/roots. Returns fingerprint."""

    fingerprint = hashlib.sha256(der).hexdigest()

    filename = f"data/roots/{fingerprint}.crt"
    with open(filename, "wb") as f:
        f.write(b"-----BEGIN CERTIFICATE-----\n")
        b = b64encode(der)
        for i in range(0, len(b), 64):
            f.write(b[i:i+64])
            f.write(b"\n")
        f.write(b"-----END CERTIFICATE-----\n")

    return fingerprint

def main():
    a, g = load_log_lists(fetch=True)
    merged = list(merge_log_lists(flatten_logs(a), flatten_logs(g)))

    fetch_accepted_roots(merged)

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader("templates"),
        autoescape=jinja2.select_autoescape(),
    )
    template = env.get_template("ct-logs.html")

    with open("ct-logs.html", "w") as f:
        f.write(template.render(logs=merged))
        f.write("\n")


if __name__ == "__main__":
    main()
