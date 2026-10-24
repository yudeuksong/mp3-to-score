"""오디오 입력 검증 및 디코딩.

모든 입력은 22050 Hz 모노 WAV로 정규화한다(Basic Pitch 모델의 입력 샘플레이트).
디코딩은 로컬에서만 이루어지며 외부로 전송하지 않는다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

TARGET_SR = 22050
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a"}

DEFAULT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_MAX_SECONDS = 600.0  # 10분


class AudioError(Exception):
    """사용자에게 그대로 보여줄 수 있는 한국어 메시지를 가진 오류."""


@dataclass
class DecodedAudio:
    path: Path  # 정규화된 WAV 경로
    duration: float  # 분석 구간 길이(초)
    source_duration: float | None  # 원본 전체 길이(알 수 있는 경우)
    peak: float


def check_upload(filename: str, size: int, max_bytes: int = DEFAULT_MAX_BYTES) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AudioError(
            f"지원하지 않는 파일 형식입니다({ext or '확장자 없음'}). "
            f"MP3, WAV, FLAC, OGG, M4A 파일을 올려 주세요."
        )
    if size <= 0:
        raise AudioError("빈 파일입니다. 다른 파일을 선택해 주세요.")
    if size > max_bytes:
        raise AudioError(
            f"파일이 너무 큽니다({size / 1024 / 1024:.1f} MB). "
            f"최대 {max_bytes // 1024 // 1024} MB까지 지원합니다."
        )
    return ext


def probe_duration(path: Path) -> float | None:
    try:
        import librosa

        return float(librosa.get_duration(path=str(path)))
    except Exception:
        return None


def decode_to_wav(
    src: Path,
    dst: Path,
    start: float = 0.0,
    length: float | None = None,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> DecodedAudio:
    """src를 디코딩해 22050 Hz 모노 WAV(dst)로 저장한다.

    분석 구간(start, length)이 max_seconds를 넘으면 오류를 낸다.
    """
    if not src.exists() or src.stat().st_size == 0:
        raise AudioError("빈 파일입니다. 다른 파일을 선택해 주세요.")
    if start < 0:
        raise AudioError("시작 위치는 0초 이상이어야 합니다.")

    source_duration = probe_duration(src)
    if source_duration is not None:
        if source_duration <= 0:
            raise AudioError("오디오 길이가 0초입니다. 손상된 파일일 수 있습니다.")
        if start >= source_duration:
            raise AudioError(
                f"시작 위치({start:.1f}초)가 곡 길이({source_duration:.1f}초)보다 깁니다."
            )
        effective = source_duration - start if length is None else min(length, source_duration - start)
        if effective > max_seconds:
            raise AudioError(
                f"분석 구간이 너무 깁니다({effective / 60:.1f}분). "
                f"최대 {max_seconds / 60:.0f}분까지 지원합니다. "
                f"'시작 위치'와 '분석 길이'로 구간을 줄여 주세요."
            )
    elif length is None or length > max_seconds:
        # 길이를 미리 알 수 없으면 상한만큼만 읽는다.
        length = max_seconds

    try:
        import librosa

        y, _ = librosa.load(
            str(src), sr=TARGET_SR, mono=True, offset=start, duration=length
        )
    except Exception as exc:  # audioread/soundfile 오류 등
        raise AudioError(
            "오디오를 읽을 수 없습니다. 파일이 손상되었거나 지원하지 않는 인코딩입니다. "
            f"(세부: {type(exc).__name__})"
        ) from exc

    if y.size == 0:
        raise AudioError("오디오 데이터가 비어 있습니다. 손상된 파일일 수 있습니다.")
    if not np.all(np.isfinite(y)):
        raise AudioError("오디오 데이터에 잘못된 값이 있습니다. 손상된 파일일 수 있습니다.")
    peak = float(np.max(np.abs(y)))
    if peak < 1e-4:
        raise AudioError("소리가 거의 없는(무음) 파일입니다.")

    duration = y.size / TARGET_SR
    if duration > max_seconds + 0.5:
        raise AudioError(f"분석 구간이 최대 {max_seconds / 60:.0f}분을 넘습니다.")

    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), y, TARGET_SR, subtype="PCM_16")
    return DecodedAudio(path=dst, duration=duration, source_duration=source_duration, peak=peak)


def safe_remove_tree(path: Path) -> None:
    import shutil

    if path and path.exists():
        shutil.rmtree(path, ignore_errors=True)


def file_size(path: os.PathLike) -> int:
    return os.stat(path).st_size
