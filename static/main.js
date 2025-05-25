// Socket.IO setup and event handlers
const sock = io();

sock.on("sample", gotSample);
sock.on("ref_update", data => {
  currentRef = data.ref;
  document.getElementById("ref").value = currentRef;
});

sock.on("connect", () => console.log("Socket connected"));

// Global variables and UI state
let chart, gauge;
let currentRef = 512;
const MAX_POINTS = 200;
let currentMode = "live"; // "live" | "db" | "json"
let gaugeDrawn = false;
let commOpen   = false;   // UI state for Open / Close

// Helper functions for HTTP requests and UI
function post(url, data = {}) {
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
}

function sendRef() {
  const val = parseInt(document.getElementById("ref").value, 10);
  if (!isNaN(val)) {
    currentRef = val;
    post("/params", { ref: currentRef });
  }
}

function resetChart() {
  if (!chart) return;
  chart.data.labels.length = 0;
  chart.data.datasets.forEach(ds => (ds.data.length = 0));
  chart.update();
}

function clearTable() {
  const tbody = document.querySelector("#tbl tbody");
  while (tbody.firstChild) tbody.removeChild(tbody.firstChild);
}

function setCommUI(opened) {
  commOpen = opened;
  const btnOpen  = document.getElementById("btnOpen");
  const btnClose = document.getElementById("btnClose");
  btnOpen.disabled  = opened;
  btnClose.disabled = !opened;
  btnOpen.classList.toggle("active", opened);
  btnClose.classList.toggle("active", !opened);
}

function setCaptureUI(running) {
  //document.getElementById("btnStart").disabled = running;
  //document.getElementById("btnStop").disabled  = !running;
  const btnStop  = document.getElementById("btnStop");
  btnStop.disabled = !running;
  btnStop.classList.toggle("active", running);
}

// ===================== DOM ready ====================
document.addEventListener("DOMContentLoaded", () => {
  /* TAB switching */
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));
      const target = btn.dataset.target;
      document.getElementById(target).classList.add("active");
      if (target === "tab-graph" && chart) chart.resize();
      if (target === "tab-gauge" && gauge) {
        if (!gaugeDrawn) { gauge.draw(); gaugeDrawn = true; } else { gauge.draw(); }
      }
    });
  });

  /* Gauge */
  gauge = new RadialGauge({
    renderTo: "gauge",
    width: 300,
    height: 300,
    units: "LDR",
    title: "Light",
    minValue: 0,
    maxValue: 1023,
    majorTicks: [0, 200, 400, 600, 800, 1023],
    minorTicks: 4,
    strokeTicks: true,
    highlights: [
      { from: 0, to: 200, color: "rgba(0,255,0,.15)" },
      { from: 800, to: 1023, color: "rgba(255,0,0,.25)" }
    ],
    colorPlate: "#fff",
    borderShadowWidth: 0,
    borders: false,
    needleType: "arrow",
    needleWidth: 2,
    animationDuration: 50,
    animationRule: "linear",
    valueBox: true,
    value: 0
  });

  /* Chart */
  const ctx = document.getElementById("chart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: { labels: [], datasets: [
      { label: "LDR", data: [], borderWidth: 2, fill: false, tension: 0.1 },
      { label: "Ref", data: [], borderWidth: 2, fill: false, tension: 0.1 } ] },
    options: {
      animation: false,
      scales: {
        x: { type: "category", ticks: { autoSkip: true, maxTicksLimit: 10 } },
        y: { min: 0, max: 1023 }
      },
      plugins: { legend: { position: "top" } }
    }
  });

  /* Control buttons */
  document.getElementById("btnOpen").addEventListener("click", () => { post("/open");  setCommUI(true);  });
  document.getElementById("btnClose").addEventListener("click", () => { post("/close"); setCommUI(false); });

  document.getElementById("btnStart").addEventListener("click", () => { sendRef(); post("/start"); setCaptureUI(true);  });
  document.getElementById("btnStop").addEventListener("click",  () => { post("/stop");  setCaptureUI(false); });
	
  document.getElementById("ref").addEventListener("change", sendRef);

  /* Graph mode buttons */
  document.getElementById("sessionSelect").addEventListener("change", e => loadSessionData(currentMode, e.target.value));

  document.getElementById("btnLive").addEventListener("click", () => {
    currentMode = "live";
    document.getElementById("sessionSelect").style.display = "none";
    resetChart(); clearTable(); gauge.value = 0;
  });
  document.getElementById("btnDB").addEventListener("click",   () => { currentMode = "db";   loadSessionList("db");   });
  document.getElementById("btnJSON").addEventListener("click", () => { currentMode = "json"; loadSessionList("json"); });
});

// ===================== incoming samples ==================
function gotSample(d) {
  if (currentMode !== "live") return;
  gauge.value = d.ldr;
  const t = new Date(d.ts);
  const time = `${t.getHours().toString().padStart(2,"0")}:${t.getMinutes().toString().padStart(2,"0")}:${t.getSeconds().toString().padStart(2,"0")}.${t.getMilliseconds().toString().padStart(3,"0")}`;
  chart.data.labels.push(time);
  chart.data.datasets[0].data.push(d.ldr);
  chart.data.datasets[1].data.push(d.ref);
  if (chart.data.labels.length > MAX_POINTS) {
    chart.data.labels.shift();
    chart.data.datasets.forEach(ds => ds.data.shift());
  }
  chart.update();

  const tbody = document.querySelector("#tbl tbody");
  const tr = document.createElement("tr");
  tr.innerHTML = `<td>${time}</td><td>${d.ldr}</td><td>${d.pwm1}</td><td>${d.pwm2}</td><td>${d.ref}</td>`;
  tbody.prepend(tr);
  if (tbody.rows.length > MAX_POINTS) tbody.deleteRow(-1);
}

// ===================== session loading ==================
async function loadSessionList(type) {
  const select = document.getElementById("sessionSelect");
  select.innerHTML = "";
  select.style.display = "inline";
  try {
    const res = await fetch(`/sessions/${type}`);
    if (!res.ok) throw new Error(res.statusText);
    const ids = await res.json();
    ids.forEach(id => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = `Session ${id}`;
      select.appendChild(opt);
    });
    if (ids.length > 0) loadSessionData(type, ids[0]);
  } catch (err) {
    alert("Error loading list: " + err.message);
  }
}

async function loadSessionData(type, id) {
  const res = await fetch(`/session/${type}/${id}`);
  const data = await res.json();

  chart.data.labels = [];
  chart.data.datasets[0].data = [];
  chart.data.datasets[1].data = [];

  data.forEach(d => {
    const t = new Date(d.ts);
    const time = `${t.getHours().toString().padStart(2, '0')}:` +
                 `${t.getMinutes().toString().padStart(2, '0')}:` +
                 `${t.getSeconds().toString().padStart(2, '0')}.` +
                 `${t.getMilliseconds().toString().padStart(3, '0')}`;

    chart.data.labels.push(time);
    chart.data.datasets[0].data.push(d.ldr);
    chart.data.datasets[1].data.push(d.ref);
  });

  chart.update();
}
