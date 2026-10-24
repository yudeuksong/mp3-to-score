"use strict";
const $ = (id) => document.getElementById(id);
const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const midiName = (m) => `${NAMES[m % 12]}${Math.floor(m / 12) - 1}`;
const ENGINE_LABEL = { basicpitch: "Basic Pitch (다성음)", yin: "YIN (단선율 실험용)" };

let file = null;
let osmd = null;
let zoom = 1.0;
let currentJob = null;
let objectUrl = null;

function showError(msg) {
  const box = $("error");
  box.textContent = msg;
  box.hidden = !msg;
}

function setProgress(pct, stage) {
  $("progress").hidden = false;
  $("bar-fill").style.width = `${pct}%`;
  $("stage").textContent = `${stage} (${Math.round(pct)}%)`;
}

for (const id of ["min_pitch", "max_pitch", "split_pitch"]) {
  const update = () => { const v = +$(id).value; $(`${id}_name`).textContent = Number.isFinite(v) ? midiName(v) : ""; };
  $(id).addEventListener("input", update);
  update();
}

async function loadInfo() {
  try {
    const r = await fetch("api/info");
    const info = await r.json();
    const bp = info.engines.find((e) => e.name === "basicpitch");
    $("engine-status").textContent = bp && bp.available
      ? `Basic Pitch 사용 가능 (${bp.extra.basic_pitch})`
      : "Basic Pitch 없음 → YIN 단선율 실험용으로 동작";
    if (!(bp && bp.available)) {
      $("engine").querySelector('option[value="basicpitch"]').disabled = true;
    }
    $("max-mb").textContent = info.max_mb;
    $("max-min").textContent = Math.round(info.max_seconds / 60);
    window.__info = info;
  } catch (e) {
    $("engine-status").textContent = "서버 연결 실패";
  }
}

function pickFile(f) {
  showError("");
  if (!f) return;
  const ok = /\.(mp3|wav|flac|ogg|m4a)$/i.test(f.name);
  if (!ok) { showError("MP3, WAV, FLAC, OGG, M4A 파일만 선택할 수 있습니다."); return; }
  if (f.size === 0) { showError("빈 파일입니다."); return; }
  const maxMb = (window.__info && window.__info.max_mb) || 50;
  if (f.size > maxMb * 1024 * 1024) { showError(`파일이 너무 큽니다. 최대 ${maxMb}MB까지 지원합니다.`); return; }
  file = f;
  $("drop-text").textContent = `${f.name} (${(f.size / 1024 / 1024).toFixed(2)} MB)`;
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(f); // 원음 재생은 브라우저 안에서만
  $("player").src = objectUrl;
  $("player").hidden = false;
  $("go").disabled = false;
}

$("file").addEventListener("change", (e) => pickFile(e.target.files[0]));
const drop = $("drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => pickFile(e.dataTransfer.files[0]));

$("go").addEventListener("click", async () => {
  if (!file) return;
  showError("");
  $("result").hidden = true;
  $("go").disabled = true;
  setProgress(1, "업로드 중");
  if (currentJob) { fetch(`api/jobs/${currentJob}`, { method: "DELETE" }).catch(() => {}); currentJob = null; }

  const fd = new FormData();
  fd.append("file", file);
  fd.append("source_mode", document.querySelector('input[name="source_mode"]:checked').value);
  for (const id of ["engine", "bpm", "time_signature", "grid", "min_note_ms", "min_pitch", "max_pitch",
                    "split_pitch", "onset_threshold", "frame_threshold", "start", "length"]) {
    fd.append(id, $(id).value);
  }
  fd.append("suppress_harmonics", $("suppress_harmonics").checked ? "true" : "false");
  try {
    const r = await fetch("api/transcribe", { method: "POST", body: fd });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || `요청 실패 (${r.status})`);
    currentJob = data.job_id;
    await poll(data.job_id);
  } catch (e) {
    showError(e.message || String(e));
    $("progress").hidden = true;
  } finally {
    $("go").disabled = false;
  }
});

async function poll(jid) {
  for (;;) {
    const r = await fetch(`api/jobs/${jid}`);
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "상태 확인 실패");
    setProgress(j.progress, j.stage);
    if (j.status === "done") return showResult(jid, j.result);
    if (j.status === "error") throw new Error(j.error);
    await new Promise((res) => setTimeout(res, 700));
  }
}

async function showResult(jid, res) {
  $("result").hidden = false;
  const rows = [
    ["엔진", ENGINE_LABEL[res.engine] || res.engine],
    ["분석 길이", `${res.duration.toFixed(1)}초` + (res.source_duration ? ` / 원본 ${res.source_duration.toFixed(1)}초` : "")],
    ["템포", `${res.bpm} BPM${res.bpm_estimated ? " (자동 추정)" : ""}`],
    ["조성 추정", res.key || "판단 불가"],
    ["검출 음표", `${res.notes_detected}개 → 정리 후 ${res.notes_kept}개`],
    ["악보 이벤트", `오른손 ${res.right_events} · 왼손 ${res.left_events}`],
    ["처리 시간", Object.entries(res.timings).map(([k, v]) => `${k} ${v}s`).join(" · ")],
  ];
  $("summary").innerHTML = "";
  for (const [k, v] of rows) {
    const dt = document.createElement("dt"); dt.textContent = k;
    const dd = document.createElement("dd"); dd.textContent = v;
    $("summary").append(dt, dd);
  }
  $("warnings").innerHTML = "";
  for (const w of res.warnings) {
    const li = document.createElement("li"); li.textContent = w; $("warnings").append(li);
  }

  const labels = { musicxml: "MusicXML", midi: "MIDI (악보)", raw_midi: "MIDI (원래 타이밍)", pdf: "PDF", notes: "음표 데이터(JSON)" };
  const dl = $("downloads");
  dl.innerHTML = "";
  for (const kind of ["pdf", "musicxml", "midi", "raw_midi", "notes"]) {
    if (!res.files[kind]) continue;
    const a = document.createElement("a");
    a.href = `api/jobs/${jid}/files/${kind}`;
    a.textContent = `${labels[kind]} 저장`;
    a.setAttribute("download", "");
    a.dataset.kind = kind;
    dl.append(a);
  }
  const pb = document.createElement("button");
  pb.type = "button";
  pb.id = "print";
  pb.textContent = "브라우저로 인쇄 (PDF 저장)";
  pb.onclick = () => window.print();
  dl.append(pb);
  $("pdf-msg").textContent = res.pdf_message +
    (res.files.pdf ? "" : " 인쇄 창에서 대상: 'PDF로 저장'을 고르면 PDF 파일로 저장됩니다.");

  const xml = await (await fetch(`api/jobs/${jid}/files/musicxml`)).text();
  await renderScore(xml);
  setProgress(100, "완료");
}

async function renderScore(xml) {
  const el = $("score");
  el.innerHTML = "";
  if (!window.opensheetmusicdisplay) {
    el.textContent = "악보 미리보기 라이브러리를 불러오지 못했습니다. MusicXML 파일을 내려받아 확인하세요.";
    return;
  }
  try {
    osmd = new opensheetmusicdisplay.OpenSheetMusicDisplay(el, {
      autoResize: true, backend: "svg", drawTitle: true, drawComposer: true,
    });
    await osmd.load(xml);
    osmd.zoom = zoom;
    osmd.render();
  } catch (e) {
    el.textContent = `악보 미리보기 실패: ${e.message || e}. MusicXML 파일은 정상 저장되었습니다.`;
  }
}

document.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
  if (!osmd) return;
  zoom = Math.min(2, Math.max(0.4, zoom + parseFloat(b.dataset.zoom)));
  osmd.zoom = zoom;
  osmd.render();
}));

loadInfo();
