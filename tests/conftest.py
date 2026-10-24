import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
warnings.filterwarnings("ignore", category=UserWarning)

import synth  # noqa: E402


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("media")
    mel = synth.melody()
    ch = synth.chords()
    files = {
        "melody_notes": mel,
        "chord_notes": ch,
        "melody_wav": synth.write_wav(d / "melody.wav", mel),
        "chords_wav": synth.write_wav(d / "chords.wav", ch),
    }
    files["melody_mp3"] = synth.wav_to_mp3(files["melody_wav"], d / "melody.mp3")
    files["chords_mp3"] = synth.wav_to_mp3(files["chords_wav"], d / "chords.mp3")
    empty = d / "empty.mp3"
    empty.write_bytes(b"")
    corrupt = d / "corrupt.mp3"
    corrupt.write_bytes(b"ID3\x03\x00\x00\x00" + bytes(range(256)) * 40)
    files["empty"] = empty
    files["corrupt"] = corrupt
    import numpy as np
    import soundfile as sf

    silent = d / "silent.wav"
    sf.write(str(silent), np.zeros(22050), 22050)
    files["silent"] = silent
    return files
