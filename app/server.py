"""로컬 웹 서버 (FastAPI). 127.0.0.1에만 바인딩하며 파일을 외부로 보내지 않는다."""
from __future__ import annotations

import atexit
import logging
import os
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, audio, pipeline, postprocess, score, transcribe

log = logging.getLogger("mp3score")

STATIC = Path(__file__).parent / "static"
MAX_BYTES = int(os.environ.get("MP3SCORE_MAX_MB", "50")) * 1024 * 1024
MAX_SECONDS = float(os.environ.get("MP3SCORE_MAX_SECONDS", str(audio.DEFAULT_MAX_SECONDS)))
JOB_TTL = float(os.environ.get("MP3SCORE_JOB_TTL", "3600"))  # 결과 보관 시간(초)
MAX_JOBS = 20

ROOT = Path(tempfile.mkdtemp(prefix="mp3score_"))
_executor = ThreadPoolExecutor(max_workers=1)  # 메모리 보호: 한 번에 한 작업
_lock = threading.Lock()

DOWNLOAD_NAMES = {
    "musicxml": ("score.musicxml", "application/vnd.recordare.musicxml+xml"),
    "midi": ("score.mid", "audio/midi"),
    "raw_midi": ("performance.mid", "audio/midi"),
    "pdf": ("score.pdf", "application/pdf"),
    "notes": ("notes.json", "application/json"),
}


@dataclass
class Job:
    id: str
    dir: Path
    filename: str
    created: float = field(default_factory=time.time)
    status: str = "queued"  # queued | running | done | error
    stage: str = "대기 중"
    progress: float = 0.0
    error: str | None = None
    result: dict | None = None


JOBS: dict[str, Job] = {}


def cleanup(expired_only: bool = True) -> int:
    now = time.time()
    removed = 0
    with _lock:
        for jid in list(JOBS):
            job = JOBS[jid]
            if not expired_only or (now - job.created > JOB_TTL and job.status in ("done", "error")):
                audio.safe_remove_tree(job.dir)
                del JOBS[jid]
                removed += 1
    return removed


def _shutdown():
    cleanup(expired_only=False)
    audio.safe_remove_tree(ROOT)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def sweep_orphans() -> int:
    """비정상 종료(강제 종료 등)로 남은 이전 실행의 임시 폴더를 지운다."""
    removed = 0
    for d in Path(tempfile.gettempdir()).glob("mp3score_*"):
        if d == ROOT or not d.is_dir():
            continue
        pidfile = d / "server.pid"
        try:
            pid = int(pidfile.read_text())
        except (OSError, ValueError):
            continue  # 우리 서버가 만든 폴더인지 확실하지 않으면 건드리지 않는다
        if not _pid_alive(pid):
            audio.safe_remove_tree(d)
            removed += 1
    return removed


(ROOT / "server.pid").write_text(str(os.getpid()))
atexit.register(_shutdown)


def _run_job(job: Job, src: Path, opts: pipeline.PipelineOptions):
    def progress(stage: str, pct: float):
        job.stage, job.progress = stage, pct

    job.status = "running"
    try:
        res = pipeline.run(src, job.dir, opts, progress)
        job.result = res.to_dict()
        job.status = "done"
    except audio.AudioError as exc:
        job.status, job.error = "error", str(exc)
    except MemoryError:
        job.status, job.error = "error", "메모리가 부족합니다. 분석 길이를 줄여 다시 시도하세요."
    except Exception as exc:
        log.error("작업 실패: %s", traceback.format_exc())
        job.status, job.error = "error", f"처리 중 오류가 발생했습니다: {type(exc).__name__}: {exc}"
    finally:
        # 업로드 원본은 결과가 나오면 바로 지운다(재생은 브라우저에서 로컬 파일로 함)
        try:
            src.unlink(missing_ok=True)
            (job.dir / "input_22050_mono.wav").unlink(missing_ok=True)
        except OSError:
            pass


@asynccontextmanager
async def lifespan(_app):
    sweep_orphans()
    yield
    # uvicorn은 SIGTERM 처리 후 신호를 다시 발생시켜 atexit가 안 돌 수 있으므로 여기서 정리한다
    _shutdown()


app = FastAPI(title="MP3 → 피아노 악보", version=__version__, lifespan=lifespan)


@app.get("/api/info")
def info():
    return {
        "version": __version__,
        "engines": [e.__dict__ for e in transcribe.available_engines()],
        "musescore": score.find_musescore(),
        "max_mb": MAX_BYTES // 1024 // 1024,
        "max_seconds": MAX_SECONDS,
        "source_modes": postprocess.SOURCE_MODES,
    }


@app.post("/api/transcribe")
async def create_job(
    file: UploadFile = File(...),
    engine: str = Form("auto"),
    source_mode: str = Form("piano"),
    bpm: float = Form(0),
    time_signature: str = Form("4/4"),
    grid: int = Form(4),
    min_note_ms: float = Form(100),
    min_pitch: int = Form(21),
    max_pitch: int = Form(108),
    split_pitch: int = Form(60),
    onset_threshold: float = Form(0.5),
    frame_threshold: float = Form(0.3),
    start: float = Form(0),
    length: float = Form(0),
    make_pdf: bool = Form(True),
    suppress_harmonics: bool = Form(True),
):
    # ---- 파라미터 검증
    if engine not in ("auto", "basicpitch", "yin"):
        raise HTTPException(400, "엔진 값이 올바르지 않습니다.")
    if source_mode not in postprocess.SOURCE_MODES:
        raise HTTPException(400, "음원 종류 값이 올바르지 않습니다.")
    if time_signature not in ("2/4", "3/4", "4/4", "6/8", "12/8"):
        raise HTTPException(400, "지원하지 않는 박자표입니다.")
    if grid not in (1, 2, 3, 4):
        raise HTTPException(400, "양자화 단위가 올바르지 않습니다.")
    if not (0 <= min_pitch < max_pitch <= 127):
        raise HTTPException(400, "음역 범위가 올바르지 않습니다(최저음 < 최고음).")
    if bpm and not (30 <= bpm <= 260):
        raise HTTPException(400, "BPM은 30~260 사이로 입력하세요(0 = 자동).")
    if not (0.05 <= onset_threshold <= 0.95 and 0.05 <= frame_threshold <= 0.95):
        raise HTTPException(400, "임계값은 0.05~0.95 사이여야 합니다.")
    if not (10 <= min_note_ms <= 2000):
        raise HTTPException(400, "최소 음 길이는 10~2000ms 사이여야 합니다.")

    cleanup()
    with _lock:
        busy = sum(1 for j in JOBS.values() if j.status in ("queued", "running"))
        if len(JOBS) >= MAX_JOBS or busy >= 3:
            raise HTTPException(429, "작업이 너무 많습니다. 잠시 후 다시 시도하세요.")

    filename = os.path.basename(file.filename or "")
    ext = Path(filename).suffix.lower()
    if ext not in audio.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식입니다({ext or '확장자 없음'}). MP3, WAV, FLAC, OGG, M4A만 가능합니다.")

    jid = uuid.uuid4().hex[:12]
    jdir = ROOT / jid
    jdir.mkdir(parents=True)
    src = jdir / f"upload{ext}"
    size = 0
    try:
        with open(src, "wb") as fh:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise audio.AudioError(f"파일이 너무 큽니다. 최대 {MAX_BYTES // 1024 // 1024} MB까지 지원합니다.")
                fh.write(chunk)
        audio.check_upload(filename, size, MAX_BYTES)
    except audio.AudioError as exc:
        audio.safe_remove_tree(jdir)
        raise HTTPException(400, str(exc))

    opts = pipeline.PipelineOptions(
        engine=engine,
        start=start,
        length=length or None,
        max_seconds=MAX_SECONDS,
        make_pdf=make_pdf,
        transcribe=transcribe.TranscribeParams(
            onset_threshold=onset_threshold, frame_threshold=frame_threshold
        ),
        score=postprocess.ScoreParams(
            bpm=bpm or None,
            time_signature=time_signature,
            grid=grid,
            split_pitch=split_pitch,
            source_mode=source_mode,
            min_pitch=min_pitch,
            max_pitch=max_pitch,
            min_note_ms=min_note_ms,
            suppress_harmonics=suppress_harmonics,
            title=Path(filename).stem[:80] or "변환된 악보",
        ),
    )
    job = Job(jid, jdir, filename)
    with _lock:
        JOBS[jid] = job
    _executor.submit(_run_job, job, src, opts)
    return {"job_id": jid}


def _get(jid: str) -> Job:
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404, "작업을 찾을 수 없습니다(만료되었을 수 있습니다).")
    return job


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    j = _get(jid)
    return {
        "id": j.id, "filename": j.filename, "status": j.status, "stage": j.stage,
        "progress": j.progress, "error": j.error, "result": j.result,
    }


@app.get("/api/jobs/{jid}/files/{kind}")
def job_file(jid: str, kind: str):
    j = _get(jid)
    if kind not in DOWNLOAD_NAMES or not j.result or kind not in j.result["files"]:
        raise HTTPException(404, "파일이 없습니다.")
    name, media = DOWNLOAD_NAMES[kind]
    path = j.dir / name
    if not path.exists():
        raise HTTPException(404, "파일이 없습니다.")
    stem = Path(j.filename).stem or "score"
    download = f"{stem}_{name}"
    return FileResponse(path, media_type=media, filename=download)


@app.delete("/api/jobs/{jid}")
def job_delete(jid: str):
    j = _get(jid)
    with _lock:
        audio.safe_remove_tree(j.dir)
        JOBS.pop(jid, None)
    return {"deleted": jid}


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main():
    import argparse
    import webbrowser

    import uvicorn

    ap = argparse.ArgumentParser(description="MP3 → 피아노 악보 로컬 웹 UI")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  MP3 → 피아노 악보: {url}\n  (종료: Ctrl+C, 임시폴더: {ROOT})\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
