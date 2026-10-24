from fractions import Fraction

from music21 import converter

from app import score
from app.postprocess import Arrangement, ChordEvent, ScoreParams
from app.transcribe import NoteEvent


def _arr():
    return Arrangement(
        bpm=100, bpm_estimated=False,
        right=[ChordEvent(Fraction(0), Fraction(1), [64, 67]), ChordEvent(Fraction(3), Fraction(2), [72])],
        left=[ChordEvent(Fraction(0), Fraction(4), [48])],
    )


def test_musicxml_roundtrip(tmp_path):
    sc, _ = score.build_score(_arr(), ScoreParams(title="테스트"))
    xml = score.write_musicxml(sc, tmp_path / "s.musicxml")
    back = converter.parse(str(xml))
    parts = back.parts
    assert len(parts) == 2
    m_r = len(parts[0].getElementsByClass("Measure"))
    m_l = len(parts[1].getElementsByClass("Measure"))
    assert m_r == m_l == 2  # 마지막 음이 마디를 넘어 붙임줄로 이어짐
    pitches = [p.midi for n in parts[0].flatten().notes for p in n.pitches]
    assert 72 in pitches and 64 in pitches
    ties = [n for n in parts[0].flatten().notes if n.tie is not None]
    assert ties, "마디를 넘는 음은 붙임줄이어야 함"
    assert back.metadata.bestTitle == "테스트"


def test_empty_score_is_valid(tmp_path):
    arr = Arrangement(bpm=120, bpm_estimated=True)
    sc, k = score.build_score(arr, ScoreParams())
    xml = score.write_musicxml(sc, tmp_path / "e.musicxml")
    assert k is None
    assert len(converter.parse(str(xml)).parts) == 2


def test_midi_outputs(tmp_path):
    import pretty_midi

    sc, _ = score.build_score(_arr(), ScoreParams(time_signature="3/4"))
    score.write_score_midi(sc, tmp_path / "s.mid")
    pm = pretty_midi.PrettyMIDI(str(tmp_path / "s.mid"))
    assert sum(len(i.notes) for i in pm.instruments) >= 4
    raw = score.write_raw_midi([NoteEvent(0.1, 0.6, 60, 0.5)], tmp_path / "r.mid")
    pm2 = pretty_midi.PrettyMIDI(str(raw))
    n = pm2.instruments[0].notes[0]
    assert n.pitch == 60 and abs(n.start - 0.1) < 0.01


def test_pdf_without_musescore(tmp_path, monkeypatch):
    monkeypatch.setattr(score, "find_musescore", lambda: None)
    ok, msg = score.write_pdf(tmp_path / "x.musicxml", tmp_path / "x.pdf")
    assert not ok and "브라우저" in msg
