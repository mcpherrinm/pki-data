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

function normalizeOperator(operator) {
    // Shorten some of the longer names
    if (operator === "Beijing PuChuangSiDa Technology Ltd.") {
        return "PuChuangSiDa"; // This is the shorter name used in the log description
    }
    if (operator === "Up In The Air Consulting") {
        return "Up In The Air";
    }
    return operator
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

function merge(data, k, av, gv) {
    if (gv === av) {
        // Both the same
        data.set(k, av);
    } else {
        data.set("apple_" + k, av);
        data.set("google_" + k, gv);
    }
}

function mergeLog(apple, google) {
    let merged = new Map();

    const operator = apple.get("operator") || google.get("operator")

    const keys = new Set(apple.keys()).union(new Set(google.keys()));
    for (let k of keys) {
        let av = apple.get(k)
        let gv = google.get(k)

        if (k === "description") {
            merge(merged, "full_description", av, gv)
            av = normalizeDescription(operator, av)
            gv = normalizeDescription(operator, gv)
        }

        if (k === "operator") {
            av = normalizeOperator(operator, av)
            gv = normalizeOperator(operator, gv)
        }

        if (k === "temporal_interval") {
            let [apple_start, apple_end] = normalizeTemporalInterval(av)
            let [google_start, google_end] = normalizeTemporalInterval(gv)

            merge(merged, "start", apple_start, google_start)
            merge(merged, "end", apple_end, google_end)
            continue;
        }

        if (k === "state") {
            let [apple_status, apple_timestamp] = normalizeState(av)
            let [google_status, google_timestamp] = normalizeState(gv)

            merge(merged, "status", apple_status, google_status)
            merge(merged, "timestamp", apple_timestamp, google_timestamp)
            continue;
        }
        merge(merged, k, av, gv)
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

        if (k === "operator") {
            v = normalizeOperator(log.get("operator"), v);
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

    return new Map([...data.entries()].sort(
        ([ka, va], [kb, vb]) => {
            return va.get("operator").localeCompare(vb.get("operator")) ||
                va.get("description").localeCompare(vb.get("description")) ||
                ka.localeCompare(kb)
        },
    ));
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
    } else if (log.has("google_" + field) && log.has("apple_" + field)) {
        text = "a: " + log.get("apple_" + field) + " g: " + log.get("google_" + field);
    } else if (log.has("apple_" + field)) {
        text = "a: " + log.get("apple_" + field);
    } else if (log.has("google_" + field)) {
        text = "g: " + log.get("google_" + field);
    }

    let element = document.createElement('td');
    if(text !== undefined) {
        element.innerText = text;
    }
    element.classList.add(field);
    row.appendChild(element);
}

function isCurrent(log) {
    let status = log.get("status");
    let apple_status = log.get("apple_status");
    let google_status = log.get("google_status");

    // We define "current" logs as usable or qualified in either list
    return (status === "usable" ||
        apple_status === "usable" ||
        google_status === "usable" ||
        status === "qualified" ||
        apple_status === "qualified" ||
        google_status === "qualified"
    )
}

async function render() {
    const data = await getLogs();
    console.log("Loaded data", data);

    const logsTable = document.getElementById("logs");
    for (const [url, log] of data) {
        let row = document.createElement("tr");
        td(row, log, "status")
        td(row, log, "operator")
        td(row, log, "description")

        if (isCurrent(log)) {
           row.classList.add("current");
        }

        let data = document.createElement("td");

        let expandLabel = document.createElement("label");
        expandLabel.innerText = "expand";
        expandLabel.setAttribute("for", url);
        expandLabel.classList.add("expand");
        let expandCheck = document.createElement("input");
        expandCheck.setAttribute("type", "checkbox");
        expandCheck.setAttribute("id", url);
        expandCheck.classList.add("expand");

        data.appendChild(expandCheck);
        data.appendChild(expandLabel);

        row.appendChild(data);

        data.classList.add("data")
        data.colSpan = 4;

        const dataTable = document.createElement("table");

        for(const [k, v] of log) {
            if (k === "status" || k === "operator" || k === "description") {
                // These are in the main table
                // Deliberately leave apple_ and google_ versions in, though
                continue;
            }
            let row = document.createElement("tr");
            row.classList.add(k);
            let key = document.createElement("td");
            key.classList.add("key");
            key.innerText = k;
            row.appendChild(key);
            let value = document.createElement("td");
            value.classList.add("value");
            value.innerText = v;
            value.colSpan = 3;
            row.appendChild(value);
            dataTable.appendChild(row);
        }

        data.appendChild(dataTable);
        row.appendChild(data);
        logsTable.appendChild(row);
    }
}

render();
