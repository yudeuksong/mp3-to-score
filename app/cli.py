"""명령줄 실행: python -m app.cli 입력.mp3 -o 출력폴더"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audio, pipeline, postprocess, transcribe


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="MP3/WAV → 피아노 악보(MusicXML/MIDI/PDF)")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("out"))
    ap.add_argument("--engine", choices=["auto", "basicpitch", "yin"], default="auto")
    ap.add_argument("--mode", choices=list(postprocess.SOURCE_MODES), default="piano")
    ap.add_argument("--bpm", type=float, default=0, help="0 = 자동 추정")
    ap.add_argument("--time-signature", default="4/4")
    ap.add_argument("--grid", type=int, choices=[1, 2, 3, 4], default=4)
    ap.add_argument("--min-note-ms", type=float, default=100)
    ap.add_argument("--min-pitch", type=int, default=21)
    ap.add_argument("--max-pitch", type=int, default=108)
    ap.add_argument("--split", type=int, default=60)
    ap.add_argument("--onset", type=float, default=0.5)
    ap.add_argument("--frame", type=float, default=0.3)
    ap.add_argument("--start", type=float, default=0)
    ap.add_argument("--length", type=float, default=0)
    ap.add_argument("--max-seconds", type=float, default=audio.DEFAULT_MAX_SECONDS)
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--keep-harmonics", action="store_true", help="배음 유령음 제거 끄기")
    a = ap.parse_args(argv)

    opts = pipeline.PipelineOptions(
        engine=a.engine, start=a.start, length=a.length or None, max_seconds=a.max_seconds,
        make_pdf=not a.no_pdf,
        transcribe=transcribe.TranscribeParams(onset_threshold=a.onset, frame_threshold=a.frame),
        score=postprocess.ScoreParams(
            bpm=a.bpm or None, time_signature=a.time_signature, grid=a.grid, split_pitch=a.split,
            source_mode=a.mode, min_pitch=a.min_pitch, max_pitch=a.max_pitch,
            min_note_ms=a.min_note_ms, suppress_harmonics=not a.keep_harmonics, title=a.input.stem,
        ),
    )
    try:
        res = pipeline.run(a.input, a.out, opts, lambda s, p: print(f"[{p:5.1f}%] {s}", file=sys.stderr))
    except audio.AudioError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    finally:
        (a.out / "input_22050_mono.wav").unlink(missing_ok=True)
    print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
