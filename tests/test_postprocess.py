from fractions import Fraction

from app.postprocess import ScoreParams, arrange, filter_notes, skyline, to_chord_events
from app.transcribe import NoteEvent


def test_filter_range_and_length():
    notes = [NoteEvent(0, 0.5, 60), NoteEvent(0, 0.05, 62), NoteEvent(0, 0.5, 20), NoteEvent(0, 0.5, 109)]
    kept = filter_notes(notes, ScoreParams(min_note_ms=100))
    assert [n.pitch for n in kept] == [60]


def test_quantize_to_sixteenths_at_120bpm():
    # 120 BPM: 4분음표 = 0.5초. 0.26초 시작 → 0.5박(8분) 근처 → 16분 격자에서 0.5
    ev = to_chord_events([NoteEvent(0.26, 0.74, 60)], bpm=120, t0=0, grid=4)
    assert ev[0].offset == Fraction(1, 2)
    assert ev[0].duration == Fraction(1)


def test_chord_grouping_and_no_overlap():
    notes = [NoteEvent(0, 1.0, 60), NoteEvent(0.01, 1.0, 64), NoteEvent(0.5, 1.0, 67)]
    ev = to_chord_events(notes, bpm=120, t0=0, grid=4)
    assert ev[0].pitches == [60, 64]
    assert ev[0].duration == Fraction(1)  # 다음 onset까지 잘림
    assert ev[1].offset == Fraction(1)


def test_suppress_harmonic_ghosts_but_keep_strong_octaves():
    from app.postprocess import suppress_harmonics

    notes = [
        NoteEvent(0, 1, 60, 0.8),
        NoteEvent(0.02, 0.3, 88, 0.3),  # 5배음 유령음 → 제거
        NoteEvent(0.01, 0.5, 72, 0.3),  # 약한 옥타브 → 제거
        NoteEvent(1.0, 2, 48, 0.7),
        NoteEvent(1.0, 2, 60, 0.65),  # 세게 친 옥타브 → 유지
        NoteEvent(2.0, 2.5, 76, 0.2),  # 아래에 동시 시작 음이 없음 → 유지
    ]
    kept = suppress_harmonics(notes)
    assert [(n.start, n.pitch) for n in kept] == [(0, 60), (1.0, 48), (1.0, 60), (2.0, 76)]
    assert len(filter_notes(notes, ScoreParams(suppress_harmonics=False))) == 6


def test_legato_fill_short_gaps_only():
    # 2박 음이 1.75박만 검출 → 2박으로 채움, 분명한 쉼(1박)은 유지
    notes = [NoteEvent(0, 0.875, 48), NoteEvent(1.0, 1.875, 53), NoteEvent(2.0, 2.125, 55), NoteEvent(4.0, 4.5, 57)]
    ev = to_chord_events(notes, bpm=120, t0=0, grid=4)
    assert [e.duration for e in ev[:3]] == [Fraction(2), Fraction(2), Fraction(1, 4)]


def test_spelling_follows_key():
    from app.score import spell

    assert spell(60, 0).accidental is None
    assert spell(61, 2).name == "C#"
    assert spell(70, -2).name == "B-"


def test_skyline_keeps_top_voice():
    notes = [NoteEvent(0, 1, 48), NoteEvent(0, 1, 72), NoteEvent(0.5, 1.5, 60)]
    sk = skyline(notes)
    assert [n.pitch for n in sk] == [72]


def test_hand_split_heuristic():
    notes = [NoteEvent(0, 0.5, 48), NoteEvent(0, 0.5, 64), NoteEvent(0.5, 1.0, 59)]
    arr = arrange(notes, None, ScoreParams(bpm=120, split_pitch=60))
    assert [e.pitches for e in arr.right] == [[64]]
    assert [e.pitches for e in arr.left] == [[48], [59]]
    assert arr.bpm == 120 and not arr.bpm_estimated


def test_melody_mode_single_staff():
    notes = [NoteEvent(0, 0.5, 48), NoteEvent(0, 0.5, 64)]
    arr = arrange(notes, None, ScoreParams(bpm=100, source_mode="melody"))
    assert arr.left == [] and arr.right[0].pitches == [64]


def test_mixed_mode_warns():
    arr = arrange([NoteEvent(0, 0.5, 64)], None, ScoreParams(bpm=100, source_mode="mixed"))
    assert any("실험적" in w for w in arr.warnings)


def test_empty_notes_warns_and_defaults_bpm():
    arr = arrange([], None, ScoreParams())
    assert arr.bpm == 120 and arr.right == [] and arr.warnings
