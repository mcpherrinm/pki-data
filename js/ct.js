function mergeLog(apple, google) {
    let merged = new Map();

    for (const [k, v] of apple) {
        if (google.has(k)) {
            if (google.get(k) === v) {
                // Both the same
                merged.set(k, v)
            } else {
                merged.set(k + "_apple", v)
                merged.set(k + "_google", google.get(k))
            }
        }
    }

    for (const [k, v] of google) {
        if (!apple.has(k)) {
            merged.set(k, v)
        }
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
        let value = mergeLog(v, googleMap.get(k));
        data.set(k, value);
    }

    for (const [k, v] of googleMap) {
        // google only
        if (!appleMap.has(k)) {
            data.set(k, v);
        }
    }

    console.log("Merged", data)

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

async function render() {
    const data = await getLogs();

    const logs = document.querySelector('#logs');

    for (const [url, value] of data) {
        let logTitle = document.createElement('h2');
        logTitle.innerHTML = url
        logs.appendChild(logTitle);

        let logTable = document.createElement('table');

        for (const [k, v] of value) {
            let label = document.createElement('td');
            label.innerText = k;
            let data = document.createElement('td');
            data.innerHTML = JSON.stringify(v);
            let row = document.createElement('tr');
            row.appendChild(label);
            row.appendChild(data);
            logTable.appendChild(row);
        }
        logs.appendChild(logTable);
    }

}

render();