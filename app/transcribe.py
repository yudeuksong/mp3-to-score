"""음표 추론 엔진.

- basicpitch: Spotify Basic Pitch(Apache-2.0) ONNX 모델. 다성음 지원, 한 악기 음원에서 가장 정확.
- yin: Basic Pitch를 쓸 수 없을 때의 대체 엔진. **단선율 실험용**이며 화음은 검출하지 못한다.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class NoteEvent:
    start: float  # 초
    end: float  # 초
    pitch: int  # MIDI 번호
    velocity: float = 0.7  # 0~1

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class TranscribeParams:
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    min_note_ms: float = 100.0
    min_pitch: int = 21  # A0
    max_pitch: int = 108  # C8
    melodia_trick: bool = True


@dataclass
class EngineInfo:
    name: str
    available: bool
    polyphonic: bool
    detail: str = ""
    extra: dict = field(default_factory=dict)


def midi_to_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# ---------------------------------------------------------------- Basic Pitch
_bp_lock = threading.Lock()
_bp_model = None
_bp_error: str | None = None


def _onnx_model_path() -> Path:
    from basic_pitch import ICASSP_2022_MODEL_PATH

    return Path(ICASSP_2022_MODEL_PATH).parent / "nmp.onnx"


def basic_pitch_info() -> EngineInfo:
    try:
        import basic_pitch  # noqa: F401
        import onnxruntime  # noqa: F401

        path = _onnx_model_path()
        if not path.exists():
            return EngineInfo("basicpitch", False, True, f"ONNX 모델 파일이 없습니다: {path}")
        from importlib.metadata import version

        return EngineInfo(
            "basicpitch",
            True,
            True,
            "Spotify Basic Pitch (ONNX)",
            {"basic_pitch": version("basic-pitch"), "onnxruntime": version("onnxruntime")},
        )
    except Exception as exc:
        return EngineInfo("basicpitch", False, True, f"설치되지 않음: {type(exc).__name__}: {exc}")


def _get_bp_model():
    global _bp_model, _bp_error
    with _bp_lock:
        if _bp_model is None:
            # basic_pitch는 TF/CoreML/TFLite 미설치 경고를 출력하므로 잠시 낮춘다.
            logging.getLogger().setLevel(logging.ERROR)
            try:
                from basic_pitch.inference import Model

                _bp_model = Model(_onnx_model_path())
            except Exception as exc:
                _bp_error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                logging.getLogger().setLevel(logging.INFO)
        return _bp_model


def transcribe_basic_pitch(wav: Path, p: TranscribeParams) -> list[NoteEvent]:
    from basic_pitch.inference import predict

    import contextlib
    import sys

    model = _get_bp_model()
    # basic_pitch는 진행 메시지를 stdout으로 출력하므로 CLI의 JSON 출력을 오염시키지 않게 돌린다
    with contextlib.redirect_stdout(sys.stderr):
        _, _, events = predict(
            str(wav),
            model,
            onset_threshold=p.onset_threshold,
            frame_threshold=p.frame_threshold,
            minimum_note_length=p.min_note_ms,
            minimum_frequency=midi_to_hz(p.min_pitch - 0.5),
            maximum_frequency=midi_to_hz(p.max_pitch + 0.5),
            melodia_trick=p.melodia_trick,
        )
    notes = [
        NoteEvent(float(s), float(e), int(pitch), float(min(1.0, max(0.05, amp))))
        for s, e, pitch, amp, *_ in events
    ]
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes


# ---------------------------------------------------------------- YIN (단선율 실험용)
def transcribe_yin(wav: Path, p: TranscribeParams) -> list[NoteEvent]:
    """YIN 기반 단선율 추정. 화음·혼합곡에는 부적합하다."""
    import librosa

    y, sr = librosa.load(str(wav), sr=None, mono=True)
    hop = 256
    fmin = max(midi_to_hz(p.min_pitch), 32.0)
    fmax = min(midi_to_hz(p.max_pitch), sr / 4)
    f0 = librosa.yin(y, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop, frame_length=2048)
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    n = min(len(f0), len(rms))
    f0, rms = f0[:n], rms[:n]
    gate = max(rms.max() * 0.1, 1e-4)
    midi = np.where(rms > gate, np.round(librosa.hz_to_midi(f0)), -1).astype(int)
    onsets = set(
        librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop, backtrack=True).tolist()
    )

    frame_t = hop / sr
    min_frames = max(1, int(round(p.min_note_ms / 1000 / frame_t)))
    notes: list[NoteEvent] = []
    i = 0
    while i < n:
        m = midi[i]
        if m < 0:
            i += 1
            continue
        j = i + 1
        while j < n and midi[j] == m and j not in onsets:
            j += 1
        if j - i >= min_frames and p.min_pitch <= m <= p.max_pitch:
            vel = float(np.clip(rms[i:j].mean() / rms.max(), 0.1, 1.0))
            notes.append(NoteEvent(i * frame_t, j * frame_t, int(m), vel))
        i = j
    return notes


def available_engines() -> list[EngineInfo]:
    return [
        basic_pitch_info(),
        EngineInfo("yin", True, False, "YIN 단선율 추정 (실험용, 화음 불가)"),
    ]


def transcribe(wav: Path, params: TranscribeParams, engine: str = "auto") -> tuple[list[NoteEvent], str]:
    if engine == "auto":
        engine = "basicpitch" if basic_pitch_info().available else "yin"
    if engine == "basicpitch":
        info = basic_pitch_info()
        if not info.available:
            raise RuntimeError(f"Basic Pitch를 사용할 수 없습니다: {info.detail}")
        return transcribe_basic_pitch(wav, params), engine
    if engine == "yin":
        return transcribe_yin(wav, params), engine
    raise ValueError(f"알 수 없는 엔진: {engine}")
