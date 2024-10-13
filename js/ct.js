function dropPrefix(prefix, str) {
    if (str.startsWith(prefix)) {
        str = str.substring(prefix.length)
    }
    return str.trim()
}

function dropSuffix(suffix, str) {
    if (str.endsWith(suffix)) {
        str = str.substring(0, str.length - suffix.length)
    }
    return str.trim()
}

function normalizeDescription(operator, description) {
    let orig = description

    // Normalize 2022H1 vs 2022h2
    description = description.replace(/(20[0-9][0-9])H([12])/, "$1h$2")
    description = description.replace(/(20[0-9][0-9])A/, "$1a")
    description = description.replace(/(20[0-9][0-9])B/, "$1b")

    description = description.replace(/' log #2/, "-2")

    description = description.replace(/ (20[0-9][0-9])/g, "$1")
    // Operator names, including some mismatches:
    description = dropPrefix("Symantec", description)
    description = dropPrefix("Up In The Air", description)
    description = dropPrefix("Trust Asia", description)
    description = dropPrefix("Nordu", description)
    description = dropPrefix(operator, description)
    description = dropSuffix("CT Log", description)
    description = dropSuffix("CT log", description)
    description = dropSuffix("Log", description)
    description = dropSuffix("log", description)
    description = dropPrefix("'", description)
    description = dropSuffix("'", description)
    description = dropPrefix("Log", description)
    description = dropPrefix("log", description)
    description = dropPrefix("CT Log", description)

    // "StartCom log" etc goes to 0, so just return the original
    if (description.length === 0) {
        return orig
    }

    return description
}

function normalizeState(state) {
    let entries = Object.entries(state);
    if (entries.length !== 1) {
        console.log("Unexpected state length", entries, entries.length)
    }

    // The state is a map {"rejected": {"timestamp": "2022..."}}
    // Apple's has a version which we ignore
    // Instead, map as ["rejected", "2022..."]
    let [k, v] = entries[0]

    return [k, v["timestamp"]]
}

function normalizeTemporalInterval(interval) {
    if (interval === undefined) {
        return [undefined, undefined]
    }
    const start = interval["start_inclusive"]
    const end = interval["end_exclusive"]

    return [start, end]
}

function mergeLog(apple, google) {
    let merged = new Map();

    const operator = apple.get("operator") || google.get("operator")

    const keys = new Set(apple.keys()).union(new Set(google.keys()));
    for (let k of keys) {
        let av = apple.get(k)
        let gv = google.get(k)

        if (k === "description") {
            av = normalizeDescription(operator, av)
            gv = normalizeDescription(operator, gv)
        }

        if (k === "temporal_interval") {
            let [apple_start, apple_end] = normalizeTemporalInterval(av)
            let [google_start, google_end] = normalizeTemporalInterval(gv)

            if (apple_start === google_start) {
                merged.set("start", apple_start)
            } else {
                merged.set("apple_start", apple_start)
                merged.set("google_start", google_start)
            }

            if (apple_end === google_end) {
                merged.set("end", apple_end)
            } else {
                merged.set("apple_end", apple_end)
                merged.set("google_end", google_end)
            }

            continue;
        }

        if (k === "state") {
            let [apple_status, apple_timestamp] = normalizeState(av)
            let [google_status, google_timestamp] = normalizeState(gv)

            if (apple_status === google_status) {
                merged.set("status", apple_status)
            } else {
                merged.set("apple_status", apple_status)
                merged.set("google_status", google_status)
            }

            if (apple_timestamp === google_timestamp) {
                merged.set("timestamp", apple_timestamp)
            } else {
                merged.set("apple_timestamp", apple_timestamp)
                merged.set("google_timestamp", google_timestamp)
            }
            continue;
        }

        if (gv === av) {
            // Both the same
            merged.set(k, av);
        } else {
            merged.set(k + "_apple", av);
            merged.set(k + "_google", gv);
        }
    }

    return merged;
}

// for logs in one operator only:
function normalizeLog(log) {
    let merged = new Map();
    for (let [k, v] of log) {
        if (k === "description") {
            v = normalizeDescription(log.get("operator"), v);
        }

        if (k === "temporal_interval") {
            let [start, end] = normalizeTemporalInterval(v);
            merged.set("start", start);
            merged.set("end", end);

            continue;
        }

        if (k === "state") {
            let [status, timestamp] = normalizeState(v)
            merged.set("status", status)
            merged.set("timestamp", timestamp)

            continue;
        }

        merged.set(k, v);
    }

    return merged;
}

function mapData(input) {
    let data = new Map();
    for (const op of input["operators"]) {
        for (const log of op["logs"]) {
            let logMap = new Map(Object.entries(log));
            logMap.set("operator", op["name"]);
            data.set(log["url"], logMap);
        }
    }

    return data;
}

function dataMerge(apple, google) {
    let appleMap = mapData(apple);
    let googleMap = mapData(google);
    let data = new Map();

    for (const [k, v] of appleMap) {
        if (!googleMap.has(k)) {
            // apple only
            data.set(k, normalizeLog(v))
        }

        // Merge if in both:
        data.set(k, mergeLog(v, googleMap.get(k)));
    }

    for (const [k, v] of googleMap) {
        // google only
        if (!appleMap.has(k)) {
            data.set(k, normalizeLog(v));
        }
    }

    return data;
}

async function getLogs() {
    const appleURL = "data/apple/current_log_list.json"
    const appleResp = await fetch(appleURL);
    if (!appleResp.ok) {
        throw new Error(`Could not fetch logs for ${appleURL}: ${appleResp.status}`);
    }
    const googleURL = "data/google/all_log_list.json"
    const googleResp = await fetch(googleURL);
    if (!googleResp.ok) {
        throw new Error(`Could not fetch google resp for ${googleURL}: ${googleResp.status}`);
    }
    return dataMerge(await appleResp.json(), await googleResp.json());
}

function td(row, log, field) {
    let text = undefined;
    if(log.has(field)) {
        text = log.get(field);
    } else if (log.has(field + "_google") && log.has(field + "_apple")) {
        text = "a: " + log.get(field + "_apple") + " g: " + log.get(field + "_google");
    } else if (log.has(field + "_apple")) {
        text = "a: " + log.get(field + "_apple");
    } else if (log.has(field + "_google")) {
        text = "g: " + log.get(field + "_google");
    }

    let element = document.createElement('td');
    if(text !== undefined) {
        element.innerText = text;
    }
    element.classList.add(field);
    row.appendChild(element);
}

async function render() {
    const data = await getLogs();
    console.log("Loaded data", data);

    const logsTable = document.getElementById("logs");
    for (const [url, log] of data) {
        let row = document.createElement('tr');

        td(row, log, "status")
        td(row, log, "operator")
        td(row, log, "description")
        td(row, log, "start")
        td(row, log, "end")
        td(row, log, "url")
        td(row, log, "log_id")
        logsTable.appendChild(row);
    }
}

render();