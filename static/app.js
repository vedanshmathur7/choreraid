// ChoreRaid frontend. Real file moves happen here, in the browser,
// through the File System Access API. Only file names/sizes/dates go to the server.

const AUTO_CONFIDENCE = 0.85;   // AI this sure => cleans itself in the background
const SPEED_WINDOW_MS = 5000;   // decide inside this window for a speed bonus
const ARCHIVE_ROOT = "_ChoreRaid_Archive";
const JOURNAL_FILE = "_ChoreRaid_journal.json";
const MAX_FILES = 3000;

const $ = (id) => document.getElementById(id);

const state = {
  root: null,            // FileSystemDirectoryHandle
  sandbox: false,
  files: new Map(),      // name -> {name,size,mtime}
  fight: [],             // groups the player decides
  auto: [],              // groups that clean themselves
  current: null,
  jobs: [],              // executor jobs
  journal: [],
  createdDirs: new Set(),
  cleaned: 0,
  total: 0,
  score: 0,
  combo: 1,
  bestCombo: 1,
  decisions: 0,
  bossIndex: 0,
  bossTotal: 0,
  startedAt: 0,
  cardShownAt: 0,
  clockTimer: null,
  speedRaf: null,
  workerRunning: false,
  busy: false,
};

// ---------- UI helpers ----------
function show(screen) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.remove("active"));
  $(`screen-${screen}`).classList.add("active");
  const step = { start: 1, loading: 1, game: 2, done: 3 }[screen];
  [1, 2, 3].forEach((n) => {
    const li = $(`step-${n}`);
    li.classList.toggle("active", n === step);
    li.classList.toggle("done", n < step);
  });
}
const say = (msg) => { $("sr").textContent = msg; };
const fmtTime = (ms) => { const s = Math.floor(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function logLine(text) {
  const li = document.createElement("li");
  li.textContent = text;
  const log = $("log");
  log.prepend(li);
  while (log.children.length > 60) log.lastChild.remove();
}
function planText(g) {
  return g.action === "archive" ? `Archive to ${ARCHIVE_ROOT}/${g.target_folder}` : `Move to ${g.target_folder}`;
}

// ---------- file system ----------
async function getDir(path, create = false) {
  let dir = state.root;
  for (const seg of path.split("/").filter(Boolean)) {
    dir = await dir.getDirectoryHandle(seg, { create });
  }
  return dir;
}
async function exists(dir, name) {
  try { await dir.getFileHandle(name); return true; } catch { return false; }
}
async function freeName(dir, name) {
  if (!(await exists(dir, name))) return name;
  const dot = name.lastIndexOf(".");
  const base = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  for (let i = 2; i < 1000; i++) {
    const n = `${base} (cr${i})${ext}`;
    if (!(await exists(dir, n))) return n;
  }
  throw new Error("No free name");
}
async function moveFile(fromPath, name, toPath, wantName = name) {
  const src = await getDir(fromPath);
  const fh = await src.getFileHandle(name);
  const dest = await getDir(toPath, true);
  const finalName = await freeName(dest, wantName);
  if (typeof fh.move === "function") {
    try { await fh.move(dest, finalName); return finalName; } catch { /* fall back to copy */ }
  }
  const file = await fh.getFile();
  const out = await dest.getFileHandle(finalName, { create: true });
  const w = await out.createWritable();
  await w.write(file);
  await w.close();
  const copied = await out.getFile();
  if (copied.size !== file.size) throw new Error(`Copy check failed for ${name}`);
  await src.removeEntry(name);
  return finalName;
}

async function scanTopLevel(dir) {
  const files = new Map();
  for await (const [name, handle] of dir.entries()) {
    if (handle.kind !== "file" || name.startsWith(".") || name === JOURNAL_FILE) continue;
    const f = await handle.getFile();
    files.set(name, { name, size: f.size, mtime: f.lastModified });
    if (files.size >= MAX_FILES) break;
  }
  return files;
}

// ---------- sample mess (sandbox inside the browser) ----------
const SAMPLE = {
  screenshots: () => `Screenshot 2026-${rand2(12)}-${rand2(28)} at ${rand2(23)}.${rand2(59)}.png`,
  invoices: () => pick(["invoice", "Invoice", "receipt", "Amazon_receipt", "electricity_bill", "payment_confirmation"]) + `_${rnd(9000) + 1000}.pdf`,
  resumes: () => pick(["resume", "Resume_Vedansh", "CV", "resume_final", "resume_FINAL_v"]) + `${rnd(9)}.docx`,
  installers: () => pick(["ChromeSetup", "vscode-installer", "zoom_x64", "python-3.12", "Discord_Setup", "node-v22"]) + pick([".exe", ".msi", ".dmg"]),
  duplicates: () => pick(["notes", "report", "lab_manual", "IMG_4421", "assignment"]) + pick([" (1)", " (2)", "_copy", " copy"]) + pick([".pdf", ".jpg", ".docx"]),
  images: () => `IMG_${rnd(9000) + 1000}.jpg`,
  pdfs: () => pick(["DBMS_unit", "lecture", "OS_notes", "paper", "syllabus", "ticket", "boarding_pass"]) + `_${rnd(99)}.pdf`,
  documents: () => pick(["notes", "todo", "ideas", "minutes", "draft"]) + `_${rnd(99)}.` + pick(["txt", "docx", "md"]),
  spreadsheets: () => pick(["marks", "budget", "attendance", "data"]) + `_${rnd(99)}.` + pick(["xlsx", "csv"]),
  archives: () => pick(["project", "dataset", "photos", "backup", "submission"]) + `_${rnd(99)}.zip`,
  code: () => pick(["main", "test", "solution", "scraper", "app"]) + `_${rnd(99)}.` + pick(["py", "js", "cpp", "ipynb"]),
  slides: () => pick(["pitch", "ppt_final", "seminar", "review"]) + `_${rnd(99)}.pptx`,
  videos: () => `VID_${rnd(9000) + 1000}.mp4`,
};
const SAMPLE_COUNTS = { screenshots: 90, invoices: 40, resumes: 14, installers: 22, duplicates: 35, images: 70, pdfs: 45, documents: 25, spreadsheets: 16, archives: 14, code: 12, slides: 9, videos: 8 };
function rnd(n) { return Math.floor(Math.random() * n); }
function rand2(n) { return String(rnd(n) + 1).padStart(2, "0"); }
function pick(a) { return a[rnd(a.length)]; }

async function makeSampleMess() {
  const opfs = await navigator.storage.getDirectory();
  try { await opfs.removeEntry("sample-mess", { recursive: true }); } catch { /* first run */ }
  const dir = await opfs.getDirectoryHandle("sample-mess", { create: true });
  const used = new Set();
  for (const [kind, count] of Object.entries(SAMPLE_COUNTS)) {
    for (let i = 0; i < count; i++) {
      let name = SAMPLE[kind]();
      if (used.has(name)) continue;
      used.add(name);
      const fh = await dir.getFileHandle(name, { create: true });
      const w = await fh.createWritable();
      await w.write(`ChoreRaid sample file: ${name}\n`);
      await w.close();
    }
  }
  return dir;
}

// ---------- API ----------
async function api(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`Server error ${res.status}`);
  return res.json();
}
async function checkHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("ai-chip").textContent = h.ai ? "🧠 Gemini is planning" : "⚙️ Rule mode (no AI key)";
    $("ai-chip").classList.add(h.ai ? "ok" : "low");
  } catch { $("ai-chip").textContent = "Offline"; }
}

// ---------- executor: one worker, fights jump the queue ----------
function addJob(group, priority, onProgress) {
  const target = group.action === "archive" ? `${ARCHIVE_ROOT}/${group.target_folder}` : group.target_folder;
  return new Promise((resolve) => {
    state.jobs.push({ group, target, remaining: [...group.files], done: 0, total: group.files.length, priority, onProgress, resolve });
    runWorker();
  });
}
async function runWorker() {
  if (state.workerRunning) return;
  state.workerRunning = true;
  try {
    while (true) {
      const job = state.jobs.find((j) => j.priority && j.remaining.length) || state.jobs.find((j) => j.remaining.length);
      if (!job) break;
      const name = job.remaining.shift();
      try {
        const newName = await moveFile("", name, job.target, name);
        state.journal.push({ from: "", name, to: job.target, newName, at: Date.now() });
        markDirs(job.target);
        state.files.delete(name);
        logLine(`✓ ${name} → ${job.target}`);
      } catch (e) {
        logLine(`✗ ${name}: ${e.message}`);
      }
      job.done++;
      state.cleaned++;
      updateTotals();
      job.onProgress?.(job);
      if (!job.remaining.length) job.resolve();
    }
  } finally {
    state.workerRunning = false;
  }
}
function markDirs(path) {
  const segs = path.split("/");
  for (let i = 1; i <= segs.length; i++) state.createdDirs.add(segs.slice(0, i).join("/"));
}
function updateTotals() {
  const pct = state.total ? (state.cleaned / state.total) * 100 : 0;
  $("total-bar").style.width = `${pct}%`;
  $("total-text").textContent = `${state.cleaned} / ${state.total}`;
}

// ---------- game flow ----------
async function start(rootHandle, sandbox) {
  Object.assign(state, {
    root: rootHandle, sandbox, fight: [], auto: [], jobs: [], journal: [], createdDirs: new Set(),
    cleaned: 0, score: 0, combo: 1, bestCombo: 1, decisions: 0, bossIndex: 0, busy: false,
  });
  show("loading");
  $("loading-text").textContent = "Reading file names…";
  state.files = await scanTopLevel(rootHandle);
  state.total = state.files.size;
  if (!state.total) {
    alert("No loose files found in this folder. Pick a folder with files directly inside it.");
    return show("start");
  }
  $("loading-text").textContent = `Planning ${state.total} files into boss fights…`;
  let data;
  try {
    data = await api("/api/cluster", { files: [...state.files.values()] });
  } catch (e) {
    alert(`Could not reach the planner: ${e.message}`);
    return show("start");
  }
  for (const g of data.groups) (g.confidence >= AUTO_CONFIDENCE ? state.auto : state.fight).push(g);
  state.fight.sort((a, b) => b.files.length - a.files.length);
  state.bossTotal = state.fight.length;

  $("log").innerHTML = "";
  renderAutoList();
  updateTotals();
  show("game");
  state.startedAt = Date.now();
  clearInterval(state.clockTimer);
  state.clockTimer = setInterval(() => { $("clock").textContent = fmtTime(Date.now() - state.startedAt); }, 500);

  // background jobs start right away
  const autoDone = Promise.all(state.auto.map((g, i) => addJob(g, false, (job) => {
    const pct = (job.done / job.total) * 100;
    const bar = document.querySelector(`#auto-${i} .fill`);
    if (bar) bar.style.width = `${pct}%`;
  })));
  state.autoDone = autoDone;
  nextBoss();
}

function renderAutoList() {
  const ul = $("auto-list");
  ul.innerHTML = state.auto.length ? "" : "<li class='muted'>Nothing here. You decide everything.</li>";
  state.auto.forEach((g, i) => {
    const li = document.createElement("li");
    li.id = `auto-${i}`;
    li.innerHTML = `<b>${esc(g.boss_name)}</b> · ${g.files.length} files<br><span class="muted tiny">${esc(planText(g))}</span><div class="bar"><div class="fill"></div></div>`;
    ul.append(li);
  });
}

function nextBoss() {
  state.current = state.fight.shift() || null;
  if (!state.current) return finish();
  state.bossIndex++;
  const g = state.current;
  $("boss").classList.remove("dead", "hit");
  $("boss-count").textContent = `Boss ${state.bossIndex} of ${state.bossTotal}`;
  const pct = Math.round(g.confidence * 100);
  $("boss-conf").textContent = `AI is ${pct}% sure`;
  $("boss-conf").className = `chip ${pct >= 70 ? "ok" : "low"}`;
  $("boss-name").textContent = g.boss_name;
  $("boss-hp").style.width = "100%";
  $("boss-hp-text").textContent = `${g.files.length} files`;
  $("boss-plan").textContent = planText(g);
  $("boss-reason").textContent = g.reason;
  $("accept-label").textContent = g.action === "archive" ? "Do it: archive" : `Do it: move to ${g.target_folder}`;
  $("boss-samples").innerHTML = g.samples.map((s) => `<li>${esc(s)}</li>`).join("") +
    (g.files.length > g.samples.length ? `<li class="muted">…and ${g.files.length - g.samples.length} more</li>` : "");
  setButtons(true);
  state.cardShownAt = performance.now();
  runSpeedBar();
  say(`${g.boss_name}. ${g.files.length} files. Plan: ${planText(g)}. Right arrow to accept.`);
  $("act-accept").focus();
}

function runSpeedBar() {
  cancelAnimationFrame(state.speedRaf);
  const tick = () => {
    const left = Math.max(0, 1 - (performance.now() - state.cardShownAt) / SPEED_WINDOW_MS);
    $("speed-bar").style.width = `${left * 100}%`;
    if (left > 0 && !state.busy) state.speedRaf = requestAnimationFrame(tick);
  };
  tick();
}

function setButtons(on) {
  ["act-accept", "act-archive", "act-retarget", "act-split"].forEach((id) => { $(id).disabled = !on; });
}

async function resolveBoss(group) {
  state.busy = true;
  setButtons(false);
  cancelAnimationFrame(state.speedRaf);
  const elapsed = performance.now() - state.cardShownAt;
  const fast = elapsed < SPEED_WINDOW_MS;
  state.combo = fast ? state.combo + 1 : 1;
  state.bestCombo = Math.max(state.bestCombo, state.combo);
  state.decisions++;
  const speedBonus = fast ? 1 + (SPEED_WINDOW_MS - elapsed) / SPEED_WINDOW_MS : 1;
  const points = Math.round(group.files.length * 10 * speedBonus * state.combo);
  $("combo").textContent = `x${state.combo}`;

  $("boss").classList.add("hit");
  await addJob(group, true, (job) => {
    const left = job.total - job.done;
    $("boss-hp").style.width = `${(left / job.total) * 100}%`;
    $("boss-hp-text").textContent = `${left} files left`;
  });
  state.score += points;
  $("score").textContent = state.score.toLocaleString();
  $("boss").classList.remove("hit");
  $("boss").classList.add("dead");
  $("boss-hp-text").textContent = `Defeated! +${points.toLocaleString()} points`;
  say(`Defeated. Plus ${points} points.`);
  await new Promise((r) => setTimeout(r, 650));
  state.busy = false;
  nextBoss();
}

async function onAccept() { if (state.current && !state.busy) await resolveBoss(state.current); }
async function onArchive() {
  if (!state.current || state.busy) return;
  await resolveBoss({ ...state.current, action: "archive" });
}
async function onRetarget() {
  if (!state.current || state.busy) return;
  const answer = prompt("Which folder should these files go to?\nExample: College/Semester 5", state.current.target_folder);
  if (!answer) return;
  const clean = answer.split(/[\\/]+/).map((s) => s.replace(/[^A-Za-z0-9 _-]/g, "").trim())
    .filter((s) => s && s !== "." && s !== "..").slice(0, 3).join("/");
  if (!clean) return alert("Please use letters, numbers, spaces, - or _.");
  await resolveBoss({ ...state.current, action: "move", target_folder: clean });
}
async function onSplit() {
  if (!state.current || state.busy) return;
  const g = state.current;
  setButtons(false);
  try {
    const files = g.files.map((n) => state.files.get(n)).filter(Boolean);
    const data = await api("/api/split", { parent_target: g.target_folder, files });
    if (data.groups.length < 2) { alert("This group can't be split further. Pick another action."); setButtons(true); return; }
    state.fight.unshift(...data.groups);
    state.bossTotal += data.groups.length - 1;
    state.bossIndex--;
    logLine(`✂ ${g.boss_name} split into ${data.groups.length}`);
    nextBoss();
  } catch (e) {
    alert(`Split failed: ${e.message}`);
    setButtons(true);
  }
}

async function finish() {
  setButtons(false);
  $("boss-name").textContent = "Finishing background cleanup…";
  $("boss-plan").textContent = "";
  $("boss-reason").textContent = "";
  $("boss-samples").innerHTML = "";
  await state.autoDone;
  clearInterval(state.clockTimer);
  const elapsed = Date.now() - state.startedAt;
  state.elapsed = elapsed;
  await writeJournal();
  $("r-files").textContent = state.cleaned.toLocaleString();
  $("r-time").textContent = fmtTime(elapsed);
  $("r-decisions").textContent = state.decisions;
  $("r-score").textContent = state.score.toLocaleString();
  $("r-leverage").textContent = `You made ${state.decisions} decisions and ${state.cleaned} files got sorted. ` +
    `That's about ${Math.round(state.cleaned / Math.max(1, state.decisions))} files per key press.` +
    (state.sandbox ? " (Sample mess: this ran in a sandbox inside your browser.)" : "");
  const counts = {};
  for (const j of state.journal) counts[j.to] = (counts[j.to] || 0) + 1;
  $("r-folders").innerHTML = Object.entries(counts).sort((a, b) => b[1] - a[1])
    .map(([dir, n]) => `<li>📁 <b>${esc(dir)}</b><br><span class="muted tiny">${n} files</span></li>`).join("");
  show("done");
  say(`Folder cleared. ${state.cleaned} files sorted.`);
}

async function writeJournal() {
  try {
    const fh = await state.root.getFileHandle(JOURNAL_FILE, { create: true });
    const w = await fh.createWritable();
    await w.write(JSON.stringify({ app: "ChoreRaid", created: new Date().toISOString(), moves: state.journal }, null, 2));
    await w.close();
  } catch (e) { console.warn("Journal write failed", e); }
}

async function undoAll() {
  if (!state.journal.length) return;
  if (!confirm(`Put all ${state.journal.length} files back where they were?`)) return;
  $("btn-undo").disabled = true;
  $("btn-undo").textContent = "Undoing…";
  let restored = 0;
  for (const m of [...state.journal].reverse()) {
    try { await moveFile(m.to, m.newName, m.from, m.name); restored++; } catch (e) { console.warn(e); }
  }
  // remove folders we created, deepest first, only if empty
  const dirs = [...state.createdDirs].sort((a, b) => b.split("/").length - a.split("/").length);
  for (const d of dirs) {
    const parts = d.split("/");
    const name = parts.pop();
    try { const parent = await getDir(parts.join("/")); await parent.removeEntry(name); } catch { /* not empty or gone */ }
  }
  try { await state.root.removeEntry(JOURNAL_FILE); } catch { /* ignore */ }
  state.journal = [];
  $("btn-undo").textContent = `↩️ Undone (${restored} files restored)`;
  say(`${restored} files restored.`);
}

function downloadCard() {
  const c = document.createElement("canvas");
  c.width = 1080; c.height = 1080;
  const x = c.getContext("2d");
  const grd = x.createLinearGradient(0, 0, 1080, 1080);
  grd.addColorStop(0, "#1b1440"); grd.addColorStop(1, "#0f1117");
  x.fillStyle = grd; x.fillRect(0, 0, 1080, 1080);
  x.fillStyle = "#9b84ff"; x.font = "bold 54px system-ui"; x.fillText("⚔️ ChoreRaid", 80, 140);
  x.fillStyle = "#ffffff"; x.font = "bold 150px system-ui"; x.fillText(state.cleaned.toLocaleString(), 80, 380);
  x.font = "48px system-ui"; x.fillText("files cleaned", 80, 450);
  x.fillStyle = "#3ddc97"; x.font = "bold 64px system-ui"; x.fillText(`in ${fmtTime(state.elapsed || 0)}`, 80, 560);
  x.fillStyle = "#cfd4e1"; x.font = "40px system-ui";
  x.fillText(`${state.decisions} decisions · best combo x${state.bestCombo}`, 80, 680);
  x.fillText(`Score ${state.score.toLocaleString()}`, 80, 750);
  x.fillStyle = "#a3a9b8"; x.font = "32px system-ui"; x.fillText("I played a game. My folder got cleaned.", 80, 960);
  const a = document.createElement("a");
  a.download = "choreraid-score.png";
  a.href = c.toDataURL("image/png");
  a.click();
}

// ---------- wiring ----------
$("btn-pick").addEventListener("click", async () => {
  try {
    const dir = await window.showDirectoryPicker({ mode: "readwrite", id: "choreraid" });
    await start(dir, false);
  } catch (e) { if (e.name !== "AbortError") alert(e.message); }
});
$("btn-sample").addEventListener("click", async () => {
  show("loading");
  $("loading-text").textContent = "Making a sample mess…";
  try { await start(await makeSampleMess(), true); } catch (e) { alert(`Sample mess failed: ${e.message}`); show("start"); }
});
$("act-accept").addEventListener("click", onAccept);
$("act-archive").addEventListener("click", onArchive);
$("act-retarget").addEventListener("click", onRetarget);
$("act-split").addEventListener("click", onSplit);
$("btn-undo").addEventListener("click", undoAll);
$("btn-card").addEventListener("click", downloadCard);
$("btn-again").addEventListener("click", () => { $("btn-undo").disabled = false; $("btn-undo").textContent = "↩️ Undo everything"; show("start"); });

document.addEventListener("keydown", (e) => {
  if (!$("screen-game").classList.contains("active") || e.target.tagName === "INPUT") return;
  const map = { ArrowRight: onAccept, d: onAccept, ArrowLeft: onArchive, a: onArchive, ArrowUp: onRetarget, w: onRetarget, ArrowDown: onSplit, s: onSplit };
  const fn = map[e.key];
  if (fn) { e.preventDefault(); fn(); }
});

if (!("showDirectoryPicker" in window)) {
  $("btn-pick").disabled = true;
  $("unsupported").hidden = false;
}
checkHealth();

// test hook (used by automated tests only)
window.__choreraid = { state };
