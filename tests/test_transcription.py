"""실제 Basic Pitch(ONNX) 추론부터 출력까지의 통합 테스트."""
import pytest
from music21 import converter

from app import pipeline, transcribe
from app.postprocess import ScoreParams, filter_notes
from metrics import note_scores

needs_bp = pytest.mark.skipif(not transcribe.basic_pitch_info().available, reason="Basic Pitch 미설치")


@needs_bp
@pytest.mark.parametrize("key", ["melody_wav", "melody_mp3"])
def test_basic_pitch_melody(media, key, tmp_path):
    raw = transcribe.transcribe_basic_pitch(media[key], transcribe.TranscribeParams())
    assert note_scores(media["melody_notes"], raw)["recall"] == 1.0
    s = note_scores(media["melody_notes"], filter_notes(raw, ScoreParams()))
    assert s["f1"] >= 0.95, s


@needs_bp
@pytest.mark.parametrize("key", ["chords_wav", "chords_mp3"])
def test_basic_pitch_chords(media, key):
    raw = transcribe.transcribe_basic_pitch(media[key], transcribe.TranscribeParams())
    s = note_scores(media["chord_notes"], filter_notes(raw, ScoreParams()))
    assert s["recall"] >= 0.9 and s["precision"] >= 0.9, s


def test_yin_melody_only(media):
    notes = transcribe.transcribe_yin(media["melody_wav"], transcribe.TranscribeParams())
    s = note_scores(media["melody_notes"], notes)
    assert s["f1"] >= 0.7, s


@needs_bp
def test_full_pipeline_mp3_to_score(media, tmp_path):
    opts = pipeline.PipelineOptions(score=ScoreParams(bpm=120, grid=4))
    res = pipeline.run(media["chords_mp3"], tmp_path, opts)
    assert res.engine == "basicpitch" and res.polyphonic
    assert {"musicxml", "midi", "raw_midi"} <= set(res.files)
    sc = converter.parse(str(tmp_path / "score.musicxml"))
    rh, lh = sc.parts
    # 첫 마디 오른손은 C장조 3화음(C4 E4 G4), 왼손은 C3
    first_rh = rh.getElementsByClass("Measure")[0].notes[0]
    assert sorted(p.midi for p in first_rh.pitches) == [60, 64, 67]
    first_lh = lh.getElementsByClass("Measure")[0].notes[0]
    assert 48 in [p.midi for p in first_lh.pitches]
    assert res.key and res.key.startswith("C")
