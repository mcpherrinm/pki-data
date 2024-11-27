#!/usr/bin/env python3

"""
This script renders files in data/ into HTML files.

"""

import jinja2
import json


def load_files():
    with open("data/apple/current_log_list.json") as alf:
        apple_logs = json.load(alf)
    with open("data/google/all_log_list.json") as glf:
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
    merge = {}
    for key in all_keys(apple, google):
        merge_item(merge, key, cond_get(apple, key), cond_get(google, key))
    return merge


def merge_log_lists(apple_logs, google_logs):
    """Merge the flattened apple & google lists into one shared structure"""
    apple_map = {log.get("url") or log.get("submission_url"): log for log in apple_logs}
    google_map = {log.get("url") or log.get("submission_url"): log for log in google_logs}

    for log in all_keys(apple_map, google_map):
        yield merge_log(apple_map.get(log, None), google_map.get(log, None))


def main():
    a, g = load_files()
    merged = list(merge_log_lists(flatten_logs(a), flatten_logs(g)))

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader("templates"),
        autoescape=jinja2.select_autoescape(),
    )
    template = env.get_template("ct-logs.html")

    print(template.render(logs=merged))


if __name__ == "__main__":
    main()
