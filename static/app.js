const $ = (id) => document.getElementById(id);

const fields = ["exam", "city", "center", "tech", "server_number"];

function setStatus(msg, isError=false) {
  const el = $("status");
  el.textContent = msg || "";
  // minimal: only subtle border change on error
  el.style.borderColor = isError ? "#ef4444" : "#e5e7eb";
}

function setBar(pct) {
  $("bar").style.width = `${pct}%`;
}

function bytesToHuman(n) {
  const units = ["B","KB","MB","GB"];
  let i = 0, x = n;
  while (x >= 1024 && i < units.length-1) { x /= 1024; i++; }
  return `${x.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function isTwoDigitServerNumber(s) {
  return /^\d{2}$/.test((s || "").trim());
}

function getDateFormat() {
  // OFF = DD-MM-YYYY, ON = MM-DD-YYYY
  return $("dateToggle").checked ? "MM-DD-YYYY" : "DD-MM-YYYY";
}

function updateDateLabel() {
  $("dateLabel").textContent = getDateFormat();
}

function loadRemembered() {
  for (const k of fields) {
    const v = localStorage.getItem("zipren_" + k);
    if (v !== null) $(k).value = v;
  }
  const dt = localStorage.getItem("zipren_dateToggle");
  if (dt !== null) $("dateToggle").checked = (dt === "1");
  updateDateLabel();
}

function remember() {
  for (const k of fields) {
    localStorage.setItem("zipren_" + k, $(k).value);
  }
  localStorage.setItem("zipren_dateToggle", $("dateToggle").checked ? "1" : "0");
}

function updateMeta() {
  const f = $("file").files?.[0];
  $("meta").textContent = f ? `Selected: ${f.name} (${bytesToHuman(f.size)})` : "";
}

function clearAll() {
  for (const k of fields) $(k).value = "";
  $("dateToggle").checked = false;
  updateDateLabel();

  $("file").value = "";
  $("meta").textContent = "";
  setStatus("Cleared.");
  setBar(0);

  for (const k of fields) localStorage.removeItem("zipren_" + k);
  localStorage.removeItem("zipren_dateToggle");
}

$("dateToggle").addEventListener("change", () => {
  updateDateLabel();
  remember();
});

$("clearBtn").addEventListener("click", clearAll);

// Drag/drop
const dz = $("dropzone");
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("dragover"); });
dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("dragover");
  if (e.dataTransfer.files?.length) $("file").files = e.dataTransfer.files;
  updateMeta();
});

$("file").addEventListener("change", updateMeta);

async function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "renamed.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

$("btn").addEventListener("click", async () => {
  remember();

  const file = $("file").files?.[0];
  if (!file) return setStatus("Please select a container ZIP file.", true);

  for (const k of ["exam", "city", "center", "tech", "server_number"]) {
    if (!$(k).value.trim()) return setStatus(`Missing field: ${k}`, true);
  }

  if (!isTwoDigitServerNumber($("server_number").value)) {
    return setStatus("Server Number must be exactly 2 digits (01..99).", true);
  }

  const fd = new FormData();
  fd.append("container_zip", file);
  fd.append("exam", $("exam").value);
  fd.append("city", $("city").value);
  fd.append("center", $("center").value);
  fd.append("tech", $("tech").value);
  fd.append("server_number", $("server_number").value);
  fd.append("date_format", getDateFormat());

  $("btn").disabled = true;
  setStatus("Uploading and processing...");
  setBar(20);

  try {
    const res = await fetch("/api/rename", { method: "POST", body: fd });
    setBar(60);

    if (!res.ok) {
      let detail = `Error (${res.status})`;
      try { const j = await res.json(); if (j?.detail) detail = j.detail; } catch {}
      setStatus(detail, true);
      setBar(0);
      return;
    }

    const processed = res.headers.get("X-Processed");
    const skipped = res.headers.get("X-Skipped");
    const warnings = res.headers.get("X-Warnings");

    const blob = await res.blob();
    setBar(95);

    const cd = res.headers.get("Content-Disposition") || "";
    const m = cd.match(/filename="?([^"]+)"?/i);
    const filename = m?.[1] || "renamed.zip";

    await downloadBlob(blob, filename);
    setBar(100);
    setStatus(`Done. Processed: ${processed || "?"}, Skipped: ${skipped || "?"}, Notes: ${warnings || "0"}.`);
  } catch {
    setStatus("Network error or upload interrupted.", true);
    setBar(0);
  } finally {
    $("btn").disabled = false;
    setTimeout(() => setBar(0), 1500);
  }
});

loadRemembered();
updateMeta();
setStatus("Ready.");