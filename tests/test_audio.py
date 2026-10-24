import numpy as np
import pytest
import soundfile as sf

from app import audio


def test_check_upload_rejects():
    with pytest.raises(audio.AudioError, match="형식"):
        audio.check_upload("a.txt", 10)
    with pytest.raises(audio.AudioError, match="빈 파일"):
        audio.check_upload("a.mp3", 0)
    with pytest.raises(audio.AudioError, match="너무 큽니다"):
        audio.check_upload("a.mp3", 100, max_bytes=50)
    assert audio.check_upload("A.MP3", 10) == ".mp3"


def test_empty_file(media, tmp_path):
    with pytest.raises(audio.AudioError, match="빈 파일"):
        audio.decode_to_wav(media["empty"], tmp_path / "o.wav")


def test_corrupt_file(media, tmp_path):
    with pytest.raises(audio.AudioError):
        audio.decode_to_wav(media["corrupt"], tmp_path / "o.wav")


def test_silent_file(media, tmp_path):
    with pytest.raises(audio.AudioError, match="무음"):
        audio.decode_to_wav(media["silent"], tmp_path / "o.wav")


def test_too_long(media, tmp_path):
    with pytest.raises(audio.AudioError, match="너무 깁니다"):
        audio.decode_to_wav(media["melody_wav"], tmp_path / "o.wav", max_seconds=3)
    # 구간을 줄이면 통과
    dec = audio.decode_to_wav(media["melody_wav"], tmp_path / "o.wav", start=1, length=2, max_seconds=3)
    assert abs(dec.duration - 2.0) < 0.05


def test_start_beyond_end(media, tmp_path):
    with pytest.raises(audio.AudioError, match="시작 위치"):
        audio.decode_to_wav(media["melody_wav"], tmp_path / "o.wav", start=999)


def test_mp3_decodes_to_22050_mono(media, tmp_path):
    dec = audio.decode_to_wav(media["melody_mp3"], tmp_path / "o.wav")
    info = sf.info(str(dec.path))
    assert info.samplerate == 22050 and info.channels == 1
    assert 8.0 < dec.duration < 9.2


def test_stereo_44k_downmix(tmp_path):
    sr = 44100
    t = np.arange(sr) / sr
    x = np.stack([0.3 * np.sin(2 * np.pi * 440 * t)] * 2, axis=1)
    p = tmp_path / "st.wav"
    sf.write(str(p), x, sr)
    dec = audio.decode_to_wav(p, tmp_path / "o.wav")
    assert sf.info(str(dec.path)).channels == 1
