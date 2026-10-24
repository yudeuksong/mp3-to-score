import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_outputs_clean_json(media, tmp_path):
    p = subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "app.cli", str(media["melody_mp3"]), "-o", str(tmp_path / "o"),
         "--bpm", "120", "--mode", "melody", "--no-pdf"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)  # stdout은 JSON만
    assert d["notes_kept"] == 16 and d["bpm"] == 120
    assert (tmp_path / "o" / "score.musicxml").exists()
    assert not (tmp_path / "o" / "input_22050_mono.wav").exists()


def test_cli_error_exit_code(media, tmp_path):
    p = subprocess.run(
        [sys.executable, "-W", "ignore", "-m", "app.cli", str(media["corrupt"]), "-o", str(tmp_path / "o")],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert p.returncode == 2 and "오류" in p.stderr
