"""music21로 피아노 대보표(오른손/왼손)를 만들고 MusicXML·MIDI·PDF로 내보낸다."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

from .postprocess import Arrangement, ChordEvent, ScoreParams
from .transcribe import NoteEvent


def spell(midi: int, sharps: int):
    """조표에 맞춘 음이름(내림표 조에서는 ♭, 그 외 ♯). 자연음에는 임시표를 붙이지 않는다."""
    from music21 import pitch

    p = pitch.Pitch(midi=midi)
    if p.accidental is not None and p.accidental.alter == 0:
        p.accidental = None
    elif p.accidental is not None and p.accidental.alter == 1 and sharps < 0:
        p = p.getEnharmonic()
    return p


def _events_to_part(part, events: list[ChordEvent], sharps: int = 0):
    from music21 import chord, note, volume

    for ev in events:
        if len(ev.pitches) == 1:
            el = note.Note(spell(ev.pitches[0], sharps))
        else:
            el = chord.Chord([spell(m, sharps) for m in ev.pitches])
        el.quarterLength = ev.duration
        el.volume = volume.Volume(velocity=int(round(ev.velocity * 127)))
        part.insert(ev.offset, el)


def build_score(arr: Arrangement, p: ScoreParams):
    from music21 import clef, instrument, key, layout, meter, metadata, note, stream, tempo

    ts = meter.TimeSignature(p.time_signature)
    bar = Fraction(ts.barDuration.quarterLength).limit_denominator(64)

    end = Fraction(0)
    for ev in arr.right + arr.left:
        end = max(end, ev.offset + ev.duration)
    total = max(bar, ((end + bar - Fraction(1, 64)) // bar) * bar)

    score = stream.Score()
    md = metadata.Metadata()
    md.movementName = p.title  # 제목은 movement-title 하나에만 넣어 중복 표시를 막는다
    md.composer = "자동 채보 (검토 필요)"
    score.insert(0, md)

    rh = stream.PartStaff(id="RH")
    lh = stream.PartStaff(id="LH")
    rh.partName, lh.partName = "Piano", ""
    rh.insert(0, instrument.Piano())
    lh.insert(0, instrument.Piano())
    rh.insert(0, clef.TrebleClef())
    lh.insert(0, clef.BassClef())

    k = estimate_key(arr)
    for part in (rh, lh):
        part.insert(0, key.KeySignature(k.sharps if k is not None else 0))
        part.insert(0, meter.TimeSignature(p.time_signature))
    rh.insert(0, tempo.MetronomeMark(number=round(arr.bpm)))

    sharps = k.sharps if k is not None else 0
    _events_to_part(rh, arr.right, sharps)
    _events_to_part(lh, arr.left, sharps)

    for part in (rh, lh):
        # 마지막 마디까지 길이를 맞춘다(양손 마디 수 일치)
        last = Fraction(0)
        for el in part.notes:
            last = max(last, Fraction(el.offset).limit_denominator(64) + Fraction(el.quarterLength).limit_denominator(64))
        if last < total:
            r = note.Rest(quarterLength=total - last)
            part.insert(last, r)
        part.makeRests(fillGaps=True, inPlace=True, hideRests=False)
        part.makeMeasures(inPlace=True)
        part.makeTies(inPlace=True)
        score.insert(0, part)

    score.insert(0, layout.StaffGroup([rh, lh], name="Piano", abbreviation="Pno.", symbol="brace", barTogether=True))
    return score, k


def estimate_key(arr: Arrangement):
    from music21 import chord, note, stream

    s = stream.Stream()
    for ev in arr.right + arr.left:
        for pch in ev.pitches:
            n = note.Note(pch)
            n.quarterLength = ev.duration
            s.append(n)
    if len(s.notes) < 4:
        return None
    try:
        return s.analyze("key")
    except Exception:
        return None


def write_musicxml(score, path: Path) -> Path:
    score.makeNotation(inPlace=True)
    score.write("musicxml", fp=str(path))
    return path


def write_score_midi(score, path: Path) -> Path:
    score.write("midi", fp=str(path))
    return path


def write_raw_midi(notes: list[NoteEvent], path: Path, bpm: float = 120.0) -> Path:
    """양자화하지 않은 원래 타이밍의 MIDI(연주 그대로)."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    inst = pretty_midi.Instrument(program=0, name="Piano")
    for n in notes:
        inst.notes.append(
            pretty_midi.Note(
                velocity=int(max(1, min(127, round(n.velocity * 127)))),
                pitch=int(n.pitch),
                start=float(n.start),
                end=float(max(n.end, n.start + 0.02)),
            )
        )
    pm.instruments.append(inst)
    pm.write(str(path))
    return path


# ---------------------------------------------------------------- PDF (MuseScore)
def find_musescore() -> str | None:
    env = os.environ.get("MUSESCORE_PATH")
    if env and Path(env).exists():
        return env
    for name in ("mscore4portable", "mscore4", "mscore", "musescore", "MuseScore4", "MuseScore3"):
        found = shutil.which(name)
        if found:
            return found
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates += [
                    Path(base) / "MuseScore 4" / "bin" / "MuseScore4.exe",
                    Path(base) / "MuseScore 3" / "bin" / "MuseScore3.exe",
                ]
    elif sys.platform == "darwin":
        candidates += [
            Path("/Applications/MuseScore 4.app/Contents/MacOS/mscore"),
            Path("/Applications/MuseScore 3.app/Contents/MacOS/mscore"),
        ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def write_pdf(musicxml: Path, pdf: Path, timeout: float = 120) -> tuple[bool, str]:
    exe = find_musescore()
    if not exe:
        return False, (
            "MuseScore가 설치되어 있지 않아 PDF를 서버에서 만들지 않았습니다. "
            "'브라우저로 인쇄(PDF 저장)' 버튼을 쓰거나, MuseScore 4를 설치한 뒤 "
            "MusicXML 파일을 열어 PDF로 내보내세요."
        )
    try:
        env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
        proc = subprocess.run(
            [exe, "-o", str(pdf), str(musicxml)],
            capture_output=True, timeout=timeout, env=env,
        )
        if proc.returncode == 0 and pdf.exists() and pdf.stat().st_size > 0:
            return True, f"MuseScore로 PDF를 만들었습니다 ({Path(exe).name})."
        return False, f"MuseScore PDF 변환 실패 (코드 {proc.returncode})."
    except subprocess.TimeoutExpired:
        return False, "MuseScore PDF 변환 시간이 초과되었습니다."
    except OSError as exc:
        return False, f"MuseScore 실행 실패: {exc}"
