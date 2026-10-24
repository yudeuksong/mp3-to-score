"""입력 파일 → 디코딩 → 음표 추론 → 후처리 → 악보 파일 전체 파이프라인."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from . import audio, postprocess, score, transcribe

ProgressFn = Callable[[str, float], None]


@dataclass
class PipelineOptions:
    engine: str = "auto"
    start: float = 0.0
    length: float | None = None
    max_seconds: float = audio.DEFAULT_MAX_SECONDS
    make_pdf: bool = True
    transcribe: transcribe.TranscribeParams = field(default_factory=transcribe.TranscribeParams)
    score: postprocess.ScoreParams = field(default_factory=postprocess.ScoreParams)


@dataclass
class PipelineResult:
    engine: str
    polyphonic: bool
    duration: float
    source_duration: float | None
    bpm: float
    bpm_estimated: bool
    key: str | None
    notes_detected: int
    notes_kept: int
    right_events: int
    left_events: int
    files: dict[str, str]
    pdf_message: str
    warnings: list[str]
    timings: dict[str, float]

    def to_dict(self) -> dict:
        return asdict(self)


def run(src: Path, workdir: Path, opts: PipelineOptions, progress: ProgressFn | None = None) -> PipelineResult:
    def step(msg: str, pct: float):
        if progress:
            progress(msg, pct)

    timings: dict[str, float] = {}
    t = time.perf_counter()
    workdir.mkdir(parents=True, exist_ok=True)

    step("오디오 디코딩 중", 5)
    wav = workdir / "input_22050_mono.wav"
    dec = audio.decode_to_wav(src, wav, opts.start, opts.length, opts.max_seconds)
    timings["decode"] = time.perf_counter() - t

    tp = opts.transcribe
    sp = opts.score
    tp.min_pitch, tp.max_pitch, tp.min_note_ms = sp.min_pitch, sp.max_pitch, sp.min_note_ms

    step("음표 추론 중 (Basic Pitch)" if opts.engine != "yin" else "음표 추론 중 (YIN 실험용)", 20)
    t = time.perf_counter()
    notes, engine = transcribe.transcribe(wav, tp, opts.engine)
    timings["transcribe"] = time.perf_counter() - t

    warnings: list[str] = []
    polyphonic = engine == "basicpitch"
    if engine == "yin":
        warnings.append(
            "YIN 대체 엔진으로 처리했습니다. 단선율 실험용이며 화음·다성음은 검출하지 못합니다."
        )
        if sp.source_mode != "melody":
            sp.source_mode = "melody"

    step("음표 정리·양자화 중", 70)
    t = time.perf_counter()
    arr = postprocess.arrange(notes, wav, sp)
    warnings += arr.warnings
    if sp.source_mode != "melody":
        warnings.append(
            f"왼손/오른손은 분할음(MIDI {sp.split_pitch}) 기준 음역 휴리스틱으로 나눴습니다. 실제 운지와 다를 수 있습니다."
        )
    timings["postprocess"] = time.perf_counter() - t

    step("악보 파일 생성 중", 80)
    t = time.perf_counter()
    files: dict[str, str] = {}
    sc, k = score.build_score(arr, sp)
    xml = score.write_musicxml(sc, workdir / "score.musicxml")
    files["musicxml"] = xml.name
    files["midi"] = score.write_score_midi(sc, workdir / "score.mid").name
    kept_notes = postprocess.filter_notes(notes, sp)
    files["raw_midi"] = score.write_raw_midi(kept_notes, workdir / "performance.mid", arr.bpm).name
    (workdir / "notes.json").write_text(
        json.dumps([asdict(n) for n in notes], ensure_ascii=False), encoding="utf-8"
    )
    files["notes"] = "notes.json"
    timings["score"] = time.perf_counter() - t

    pdf_msg = "PDF 생성을 건너뛰었습니다."
    if opts.make_pdf:
        step("PDF 생성 시도 중", 90)
        ok, pdf_msg = score.write_pdf(xml, workdir / "score.pdf")
        if ok:
            files["pdf"] = "score.pdf"

    step("완료", 100)
    return PipelineResult(
        engine=engine,
        polyphonic=polyphonic,
        duration=round(dec.duration, 3),
        source_duration=round(dec.source_duration, 3) if dec.source_duration else None,
        bpm=arr.bpm,
        bpm_estimated=arr.bpm_estimated,
        key=str(k) if k is not None else None,
        notes_detected=arr.notes_in,
        notes_kept=arr.notes_kept,
        right_events=len(arr.right),
        left_events=len(arr.left),
        files=files,
        pdf_message=pdf_msg,
        warnings=warnings,
        timings={k_: round(v, 3) for k_, v in timings.items()},
    )
