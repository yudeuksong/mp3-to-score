"""테스트용 합성 음원 생성기(피아노 비슷한 배음+감쇠 톤). 정답 음표 목록도 함께 반환한다."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def tone(midi: int, dur: float, sr: int = SR, vel: float = 0.6) -> np.ndarray:
    f = 440.0 * 2 ** ((midi - 69) / 12)
    t = np.arange(int(dur * sr)) / sr
    env = np.exp(-3.0 * t) * np.minimum(1.0, t / 0.005)
    rel = int(0.03 * sr)
    if t.size > rel:
        env[-rel:] *= np.linspace(1, 0, rel)
    sig = sum((0.6 ** (h - 1)) * np.sin(2 * np.pi * f * h * t) for h in range(1, 6) if f * h < sr / 2)
    return vel * env * sig


def render(notes: list[tuple[float, float, int]], total: float | None = None, sr: int = SR) -> np.ndarray:
    total = total or max(s + d for s, d, _ in notes) + 0.5
    out = np.zeros(int(total * sr))
    for s, d, m in notes:
        x = tone(m, d, sr)
        i = int(s * sr)
        out[i:i + x.size] += x[: out.size - i]
    peak = np.max(np.abs(out)) or 1.0
    return 0.8 * out / peak


def melody(bpm: float = 120) -> list[tuple[float, float, int]]:
    """C장조 음계 + 되돌아오기: 4분음표 16개."""
    q = 60 / bpm
    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 72, 71, 69, 67, 65, 64, 62, 60]
    return [(i * q, q * 0.95, p) for i, p in enumerate(pitches)]


def chords(bpm: float = 120) -> list[tuple[float, float, int]]:
    """I-IV-V-I 3화음(2분음표) + 베이스음(왼손)."""
    h = 2 * 60 / bpm
    prog = [([60, 64, 67], 48), ([60, 65, 69], 53), ([62, 67, 71], 55), ([60, 64, 67], 48)]
    notes = []
    for i, (triad, bass) in enumerate(prog):
        for p in triad + [bass]:
            notes.append((i * h, h * 0.95, p))
    return notes


def write_wav(path: Path, notes, sr: int = SR) -> Path:
    sf.write(str(path), render(notes, sr=sr), sr)
    return path


def wav_to_mp3(wav: Path, mp3: Path) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k", str(mp3)],
        check=True,
    )
    return mp3
