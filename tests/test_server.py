import time

import pytest
from fastapi.testclient import TestClient

from app import server, transcribe


@pytest.fixture(scope="module")
def client():
    with TestClient(server.app) as c:
        yield c


def _wait(client, jid, timeout=120):
    t = time.time()
    while time.time() - t < timeout:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.3)
    raise TimeoutError


def test_index_and_info(client):
    r = client.get("/")
    assert r.status_code == 200 and "피아노 악보" in r.text
    info = client.get("/api/info").json()
    assert {e["name"] for e in info["engines"]} == {"basicpitch", "yin"}
    assert client.get("/vendor/opensheetmusicdisplay.min.js").status_code == 200


def test_upload_mp3_and_download(client, media):
    with open(media["melody_mp3"], "rb") as fh:
        r = client.post("/api/transcribe", files={"file": ("melody.mp3", fh, "audio/mpeg")},
                        data={"bpm": "120", "source_mode": "melody"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    j = _wait(client, jid)
    assert j["status"] == "done", j
    res = j["result"]
    assert res["notes_kept"] > 0
    x = client.get(f"/api/jobs/{jid}/files/musicxml")
    assert x.status_code == 200 and b"score-partwise" in x.content
    assert "melody_score.musicxml" in x.headers["content-disposition"]
    m = client.get(f"/api/jobs/{jid}/files/midi")
    assert m.status_code == 200 and m.content[:4] == b"MThd"
    assert client.get(f"/api/jobs/{jid}/files/pdf").status_code in (200, 404)
    # 업로드 원본은 처리 후 삭제
    assert not list(server.JOBS[jid].dir.glob("upload*"))
    jdir = server.JOBS[jid].dir
    assert client.delete(f"/api/jobs/{jid}").status_code == 200
    assert not jdir.exists()
    assert client.get(f"/api/jobs/{jid}").status_code == 404


def test_reject_bad_extension(client):
    r = client.post("/api/transcribe", files={"file": ("a.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and "형식" in r.json()["error"]


def test_reject_empty(client):
    r = client.post("/api/transcribe", files={"file": ("a.mp3", b"", "audio/mpeg")})
    assert r.status_code == 400 and "빈 파일" in r.json()["error"]


def test_corrupt_reports_error(client, media):
    with open(media["corrupt"], "rb") as fh:
        r = client.post("/api/transcribe", files={"file": ("bad.mp3", fh, "audio/mpeg")})
    j = _wait(client, r.json()["job_id"])
    assert j["status"] == "error" and j["error"]


def test_param_validation(client, media):
    with open(media["melody_wav"], "rb") as fh:
        r = client.post("/api/transcribe", files={"file": ("m.wav", fh)}, data={"min_pitch": "90", "max_pitch": "40"})
    assert r.status_code == 400 and "음역" in r.json()["error"]


def test_too_large(client, monkeypatch):
    monkeypatch.setattr(server, "MAX_BYTES", 1000)
    r = client.post("/api/transcribe", files={"file": ("big.mp3", b"x" * 5000, "audio/mpeg")})
    assert r.status_code == 400 and "너무 큽니다" in r.json()["error"]


def test_sweep_orphans_only_dead_pid_dirs(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    dead = tmp_path / "mp3score_dead"
    dead.mkdir()
    (dead / "server.pid").write_text("999999999")
    alive = tmp_path / "mp3score_alive"
    alive.mkdir()
    import os

    (alive / "server.pid").write_text(str(os.getpid()))
    unknown = tmp_path / "mp3score_unknown"  # pid 파일 없음 → 건드리지 않음
    unknown.mkdir()
    assert server.sweep_orphans() == 1
    assert not dead.exists() and alive.exists() and unknown.exists()


def test_expired_cleanup(client, media, monkeypatch):
    with open(media["melody_wav"], "rb") as fh:
        jid = client.post("/api/transcribe", files={"file": ("m.wav", fh)}, data={"bpm": "120"}).json()["job_id"]
    _wait(client, jid)
    jdir = server.JOBS[jid].dir
    monkeypatch.setattr(server, "JOB_TTL", -1)
    assert server.cleanup() >= 1
    assert not jdir.exists()
