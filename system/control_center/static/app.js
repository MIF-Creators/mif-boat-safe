/* Control Center – interactive map, mission builder, live telemetry */

(() => {
"use strict";

const POLL_MS = 300;
const CANVAS_PX = 600;

let mapData = null;      // {width, height, obstacles, reference_markers}
let positions = {};       // vehicle_id -> {x, y, rotation}
let statuses = {};        // vehicle_id -> heartbeat
let missions = {};        // vehicle_id -> mission info
let waypoints = [];       // [{x, y, action, params}]
let selectedVehicle = "vehicle_0";

const $ = (s) => document.querySelector(s);
const canvas = $("#mapCanvas");
const ctx = canvas.getContext("2d");

canvas.width = CANVAS_PX;
canvas.height = CANVAS_PX;

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

async function fetchJson(url) {
    try { const r = await fetch(url); if (r.ok) return r.json(); } catch(_) {}
    return null;
}

async function poll() {
    const [pos, sts, mis, mp] = await Promise.all([
        fetchJson("/api/positions"),
        fetchJson("/api/statuses"),
        fetchJson("/api/missions"),
        mapData ? null : fetchJson("/api/map"),
    ]);
    if (pos) positions = pos;
    if (sts) statuses = sts;
    if (mis) missions = mis;
    if (mp && !mp.error) mapData = mp;

    render();
    updateSidebar();
}

setInterval(poll, POLL_MS);
poll();

// ---------------------------------------------------------------------------
// Map drawing
// ---------------------------------------------------------------------------

function toCanvas(mx, my) {
    const w = mapData ? mapData.width : 100;
    const h = mapData ? mapData.height : 100;
    const pad = 30;
    const area = CANVAS_PX - pad * 2;
    return [pad + (mx / w) * area, CANVAS_PX - pad - (my / h) * area];
}

function fromCanvas(cx, cy) {
    const w = mapData ? mapData.width : 100;
    const h = mapData ? mapData.height : 100;
    const pad = 30;
    const area = CANVAS_PX - pad * 2;
    const mx = ((cx - pad) / area) * w;
    const my = ((CANVAS_PX - pad - cy) / area) * h;
    return [Math.round(mx * 10) / 10, Math.round(my * 10) / 10];
}

function render() {
    ctx.clearRect(0, 0, CANVAS_PX, CANVAS_PX);

    // grid
    ctx.strokeStyle = "rgba(255,255,255,0.04)";
    ctx.lineWidth = 1;
    const step = 10;
    const w = mapData ? mapData.width : 100;
    const h = mapData ? mapData.height : 100;
    for (let i = 0; i <= w; i += step) {
        const [x1, y1] = toCanvas(i, 0);
        const [x2, y2] = toCanvas(i, h);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }
    for (let j = 0; j <= h; j += step) {
        const [x1, y1] = toCanvas(0, j);
        const [x2, y2] = toCanvas(w, j);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    }

    // reference markers
    if (mapData && mapData.reference_markers) {
        ctx.fillStyle = "#00e676";
        ctx.font = "11px sans-serif";
        for (const [id, coords] of Object.entries(mapData.reference_markers)) {
            const [cx, cy] = toCanvas(coords[0], coords[1]);
            ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
            ctx.fillText("M" + id, cx + 7, cy - 4);
        }
    }

    // obstacles
    if (mapData && mapData.obstacles) {
        ctx.fillStyle = "rgba(233,69,96,0.35)";
        ctx.strokeStyle = "#e94560";
        ctx.lineWidth = 1.5;
        for (const ob of mapData.obstacles) {
            if (ob.type === "rectangle") {
                const [ox, oy] = toCanvas(ob.x, ob.y + ob.height);
                const [ox2, oy2] = toCanvas(ob.x + ob.width, ob.y);
                const rw = ox2 - ox; const rh = oy2 - oy;
                ctx.fillRect(ox, oy, rw, rh);
                ctx.strokeRect(ox, oy, rw, rh);
            } else if (ob.type === "circle") {
                const [cx, cy] = toCanvas(ob.x, ob.y);
                const rPx = (ob.radius / w) * (CANVAS_PX - 60);
                ctx.beginPath(); ctx.arc(cx, cy, rPx, 0, Math.PI * 2);
                ctx.fill(); ctx.stroke();
            }
        }
    }

    // waypoints (planned)
    drawWaypoints();

    // active mission path
    drawActiveMission();

    // vehicles
    for (const [vid, pos] of Object.entries(positions)) {
        drawVehicle(vid, pos);
    }
}

function drawVehicle(vid, pos) {
    const [cx, cy] = toCanvas(pos.x, pos.y);
    const r = 10;
    const rot = pos.rotation || 0;

    ctx.save();
    ctx.translate(cx, cy);
    // canvas Y is inverted relative to map Y
    ctx.rotate(-rot);

    ctx.fillStyle = vid === selectedVehicle ? "#00d2ff" : "#ffffff";
    ctx.beginPath(); ctx.arc(0, 0, r, 0, Math.PI * 2); ctx.fill();

    // heading arrow
    ctx.strokeStyle = "#111";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(r + 6, 0); ctx.stroke();

    ctx.restore();

    ctx.fillStyle = "rgba(255,255,255,0.7)";
    ctx.font = "10px sans-serif";
    ctx.fillText(vid, cx + 14, cy - 4);
    ctx.fillText(`(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})`, cx + 14, cy + 8);
}

function drawWaypoints() {
    if (waypoints.length === 0) return;
    ctx.strokeStyle = "rgba(0,210,255,0.5)";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    for (let i = 0; i < waypoints.length; i++) {
        const [cx, cy] = toCanvas(waypoints[i].x, waypoints[i].y);
        if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    for (let i = 0; i < waypoints.length; i++) {
        const [cx, cy] = toCanvas(waypoints[i].x, waypoints[i].y);
        ctx.fillStyle = "#00d2ff";
        ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#fff";
        ctx.font = "bold 9px sans-serif";
        ctx.fillText(String(i + 1), cx - 3, cy + 3);
    }
}

function drawActiveMission() {
    const m = missions[selectedVehicle];
    if (!m || !m.waypoints || m.waypoints.length === 0) return;
    if (m.status === "completed" || m.status === "cancelled") return;

    ctx.strokeStyle = "rgba(233,69,96,0.5)";
    ctx.lineWidth = 2;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    for (let i = 0; i < m.waypoints.length; i++) {
        const wp = m.waypoints[i];
        const [cx, cy] = toCanvas(wp.x, wp.y);
        if (i === 0) ctx.moveTo(cx, cy); else ctx.lineTo(cx, cy);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    const curIdx = m.current_waypoint_idx || 0;
    for (let i = 0; i < m.waypoints.length; i++) {
        const wp = m.waypoints[i];
        const [cx, cy] = toCanvas(wp.x, wp.y);
        ctx.fillStyle = i < curIdx ? "rgba(0,230,118,0.6)" : (i === curIdx ? "#e94560" : "rgba(233,69,96,0.4)");
        ctx.beginPath(); ctx.arc(cx, cy, 4, 0, Math.PI * 2); ctx.fill();
    }
}

// ---------------------------------------------------------------------------
// Map click -> add waypoint
// ---------------------------------------------------------------------------

canvas.addEventListener("click", (e) => {
    const rect = canvas.getBoundingClientRect();
    const scaleX = CANVAS_PX / rect.width;
    const scaleY = CANVAS_PX / rect.height;
    const cx = (e.clientX - rect.left) * scaleX;
    const cy = (e.clientY - rect.top) * scaleY;
    const [mx, my] = fromCanvas(cx, cy);

    const w = mapData ? mapData.width : 100;
    const h = mapData ? mapData.height : 100;
    if (mx < 0 || mx > w || my < 0 || my > h) return;

    waypoints.push({ x: mx, y: my, action: "none", params: {} });
    render();
    updateWaypointList();
});

// ---------------------------------------------------------------------------
// Sidebar updates
// ---------------------------------------------------------------------------

function updateSidebar() {
    // auto-select first available vehicle if current selection is gone
    const vehicleIds = Object.keys(positions);
    if (vehicleIds.length > 0 && !positions[selectedVehicle]) {
        selectedVehicle = vehicleIds[0];
    }

    // vehicles
    const vList = $("#vehicleList");
    let html = "";
    for (const [vid, pos] of Object.entries(positions)) {
        const st = statuses[vid];
        const state = st ? st.state : "unknown";
        const dotColor = state === "executing" ? "var(--accent2)" :
                         state === "idle" ? "var(--success)" :
                         state === "paused" ? "var(--warning)" : "var(--text-dim)";
        html += `<div class="vehicle-item${vid === selectedVehicle ? ' selected' : ''}" onclick="window._selectVehicle('${vid}')">
            <span class="dot" style="background:${dotColor}"></span>
            <span class="vid">${vid}</span>
            <span class="coords">(${pos.x.toFixed(1)}, ${pos.y.toFixed(1)})</span>
        </div>`;
    }
    if (!html) html = '<div class="vehicle-item"><span style="color:var(--text-dim)">No vehicles</span></div>';
    vList.innerHTML = html;

    // mission status
    const m = missions[selectedVehicle];
    const mStatus = $("#missionStatus");
    if (m) {
        const cls = m.status || "idle";
        mStatus.innerHTML = `
            <div><span class="label">Status: </span><span class="value ${cls}">${cls}</span></div>
            <div><span class="label">Waypoint: </span><span class="value">${m.current_waypoint_idx + 1} / ${m.waypoints ? m.waypoints.length : 0}</span></div>
            <div><span class="label">ID: </span><span class="value" style="font-size:.7rem">${m.mission_id || '-'}</span></div>
        `;
    } else {
        mStatus.innerHTML = '<span class="label">No active mission</span>';
    }

    // selected vehicle label
    $("#selectedVehicle").textContent = selectedVehicle;
}

window._selectVehicle = function(vid) {
    selectedVehicle = vid;
    render();
    updateSidebar();
};

// ---------------------------------------------------------------------------
// Waypoint list management
// ---------------------------------------------------------------------------

function updateWaypointList() {
    const ul = $("#wpList");
    ul.innerHTML = "";
    waypoints.forEach((wp, i) => {
        const li = document.createElement("li");
        li.innerHTML = `
            <span class="idx">${i + 1}</span>
            <span class="wp-coords">(${wp.x}, ${wp.y})</span>
            <select onchange="window._setWpAction(${i}, this.value)" style="width:80px;margin-left:4px">
                <option value="none" ${wp.action === 'none' ? 'selected' : ''}>none</option>
                <option value="wait" ${wp.action === 'wait' ? 'selected' : ''}>wait</option>
                <option value="stop" ${wp.action === 'stop' ? 'selected' : ''}>stop</option>
            </select>
            <button class="remove-wp" onclick="window._removeWp(${i})">x</button>
        `;
        ul.appendChild(li);
    });
}

window._setWpAction = function(idx, action) {
    if (waypoints[idx]) {
        waypoints[idx].action = action;
        if (action === "wait") waypoints[idx].params = { duration: 3 };
        else waypoints[idx].params = {};
    }
};

window._removeWp = function(idx) {
    waypoints.splice(idx, 1);
    render();
    updateWaypointList();
};

// ---------------------------------------------------------------------------
// Buttons
// ---------------------------------------------------------------------------

$("#btnSend").addEventListener("click", async () => {
    if (waypoints.length === 0) return;
    await fetch("/api/mission/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vehicle_id: selectedVehicle, waypoints }),
    });
    waypoints = [];
    updateWaypointList();
    render();
});

$("#btnClear").addEventListener("click", () => {
    waypoints = [];
    updateWaypointList();
    render();
});

$("#btnCancel").addEventListener("click", () => sendControl("cancel"));
$("#btnPause").addEventListener("click", () => sendControl("pause"));
$("#btnResume").addEventListener("click", () => sendControl("resume"));

async function sendControl(cmd) {
    await fetch("/api/mission/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vehicle_id: selectedVehicle, command: cmd }),
    });
}

$("#btnRefreshMap").addEventListener("click", async () => {
    mapData = null;
    await fetch("/api/map/refresh", { method: "POST" });
});

// initial render
render();
updateWaypointList();

})();
