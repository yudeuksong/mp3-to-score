"""음표 후처리: 음역/최소 길이 필터, 박자 양자화, 왼손/오른손 분리.

왼손/오른손 분리는 **음역(분할음) 기반 휴리스틱**이다. 실제 운지나 성부를 추론하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from .transcribe import NoteEvent

SOURCE_MODES = {
    "piano": "피아노/단일 악기 (다성음)",
    "melody": "단선율 (멜로디 한 줄)",
    "mixed": "보컬+반주 혼합곡 (실험적)",
}


@dataclass
class ScoreParams:
    bpm: float | None = None  # None이면 자동 추정
    time_signature: str = "4/4"
    grid: int = 4  # 4분음표당 분할 수 (1=4분, 2=8분, 3=셋잇단 8분, 4=16분)
    split_pitch: int = 60  # 이 음(MIDI) 이상은 오른손
    source_mode: str = "piano"
    align_first_note: bool = True
    min_pitch: int = 21
    max_pitch: int = 108
    min_note_ms: float = 100.0
    suppress_harmonics: bool = True
    title: str = "변환된 악보"


@dataclass
class ChordEvent:
    offset: Fraction  # 4분음표 단위
    duration: Fraction
    pitches: list[int]
    velocity: float = 0.7


@dataclass
class Arrangement:
    bpm: float
    bpm_estimated: bool
    right: list[ChordEvent] = field(default_factory=list)
    left: list[ChordEvent] = field(default_factory=list)
    notes_in: int = 0
    notes_kept: int = 0
    warnings: list[str] = field(default_factory=list)


def estimate_bpm(wav: Path) -> float | None:
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(wav), sr=None, mono=True)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        if not (30 <= bpm <= 260):
            return None
        # 비트 추적기는 절반/두 배 템포로 잡는 일이 잦다 → 흔한 범위(70~160)로 접는다
        while bpm >= 160:
            bpm /= 2
        while bpm < 70:
            bpm *= 2
        return bpm
    except Exception:
        return None


def filter_notes(notes: list[NoteEvent], p: ScoreParams) -> list[NoteEvent]:
    min_dur = p.min_note_ms / 1000.0
    kept = [
        n for n in notes
        if p.min_pitch <= n.pitch <= p.max_pitch and n.duration >= min_dur
    ]
    if p.suppress_harmonics:
        kept = suppress_harmonics(kept)
    return kept


# 기본음 위 배음 위치(반음): 2배(12), 3배(19), 4배(24), 5배(28), 6배(31), 7배(34), 8배(36)
HARMONIC_INTERVALS = {12, 19, 24, 28, 31, 34, 36}


def suppress_harmonics(
    notes: list[NoteEvent], ratio: float = 0.6, onset_tol: float = 0.06
) -> list[NoteEvent]:
    """아래 음과 같은 시점에 시작하고 배음 간격에 있으면서 훨씬 약한 음(배음 유령음)을 제거한다.

    휴리스틱이므로 실제로 약하게 친 옥타브 음도 지워질 수 있다(설정에서 끌 수 있음).
    """
    def is_ghost(n: NoteEvent) -> bool:
        return any(
            abs(n.start - f.start) <= onset_tol
            and (n.pitch - f.pitch) in HARMONIC_INTERVALS
            and n.velocity < ratio * f.velocity
            for f in notes
        )

    return [n for n in notes if not is_ghost(n)]


def skyline(notes: list[NoteEvent]) -> list[NoteEvent]:
    """동시에 울리는 음 중 가장 높은 음만 남겨 단선율로 만든다."""
    out: list[NoteEvent] = []
    for n in sorted(notes, key=lambda n: (n.start, -n.pitch)):
        if out and n.start < out[-1].end - 1e-3:
            prev = out[-1]
            if n.pitch > prev.pitch:
                # 더 높은 새 음이 들어오면 이전 음을 자르고 교체
                prev.end = n.start
                if prev.duration < 0.03:
                    out.pop()
                out.append(NoteEvent(n.start, n.end, n.pitch, n.velocity))
            continue
        out.append(NoteEvent(n.start, n.end, n.pitch, n.velocity))
    return out


def _q(x: float, grid: int) -> Fraction:
    return Fraction(round(x * grid), grid)


def to_chord_events(notes: list[NoteEvent], bpm: float, t0: float, grid: int) -> list[ChordEvent]:
    """한 손의 음표들을 겹치지 않는 화음 이벤트 열로 바꾼다."""
    beats_per_sec = bpm / 60.0
    step = Fraction(1, grid)
    groups: dict[Fraction, list[tuple[NoteEvent, Fraction]]] = {}
    for n in notes:
        on = _q((n.start - t0) * beats_per_sec, grid)
        off = _q((n.end - t0) * beats_per_sec, grid)
        if on < 0:
            on = Fraction(0)
        dur = max(off - on, step)
        groups.setdefault(on, []).append((n, dur))

    onsets = sorted(groups)
    events: list[ChordEvent] = []
    for i, on in enumerate(onsets):
        items = groups[on]
        dur = max(d for _, d in items)
        if i + 1 < len(onsets):
            gap = onsets[i + 1] - on - dur
            # 레가토 보정: 다음 음까지 틈이 짧으면(16분쉼표 수준) 메워서 읽기 쉬운 리듬으로
            if 0 < gap <= max(step, Fraction(1, 4)) and gap <= dur / 4:
                dur += gap
            dur = min(dur, onsets[i + 1] - on)
        elif 0 < (-(on + dur)) % 1 <= max(step, Fraction(1, 4)) and ((-(on + dur)) % 1) <= dur / 4:
            dur += (-(on + dur)) % 1  # 마지막 음은 다음 박까지 짧게 모자라면 채움
        pitches = sorted({n.pitch for n, _ in items})
        vel = max(n.velocity for n, _ in items)
        events.append(ChordEvent(on, max(dur, step), pitches, vel))
    return events


def arrange(notes: list[NoteEvent], wav: Path | None, p: ScoreParams) -> Arrangement:
    warnings: list[str] = []
    kept = filter_notes(notes, p)

    if p.source_mode == "melody":
        kept = skyline(kept)
    elif p.source_mode == "mixed":
        warnings.append(
            "혼합곡 모드는 실험적입니다. 보컬 선율을 정확히 분리하지 못하며, "
            "오른손은 '가장 높은 음' 추정치, 왼손은 분할음 아래 음들입니다."
        )
        upper = skyline([n for n in kept if n.pitch >= p.split_pitch])
        lower = [n for n in kept if n.pitch < p.split_pitch]
        kept = upper + lower

    bpm, estimated = p.bpm, False
    if not bpm:
        bpm = estimate_bpm(wav) if wav else None
        estimated = True
        if not bpm:
            bpm = 120.0
            warnings.append("템포를 추정하지 못해 120 BPM을 사용했습니다.")
        else:
            warnings.append(
                f"템포 {bpm:.0f} BPM은 자동 추정값입니다(절반/두 배로 틀릴 수 있음). "
                "곡의 BPM을 알면 직접 입력해야 박자가 정확해집니다."
            )
    t0 = min((n.start for n in kept), default=0.0) if p.align_first_note else 0.0

    if p.source_mode == "melody":
        right, left = kept, []
    else:
        right = [n for n in kept if n.pitch >= p.split_pitch]
        left = [n for n in kept if n.pitch < p.split_pitch]

    if not kept:
        warnings.append("검출된 음표가 없습니다. 임계값·음역·최소 음 길이를 조정해 보세요.")

    return Arrangement(
        bpm=round(float(bpm), 2),
        bpm_estimated=estimated,
        right=to_chord_events(right, bpm, t0, p.grid),
        left=to_chord_events(left, bpm, t0, p.grid),
        notes_in=len(notes),
        notes_kept=len(kept),
        warnings=warnings,
    )
