"""합성 음원으로 실제 엔진 정확도를 측정해 JSON/Markdown으로 저장한다.

사용: python tools/evaluate.py [출력폴더]
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import warnings
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
warnings.filterwarnings("ignore")

import synth  # noqa: E402
from metrics import note_scores  # noqa: E402

from app import audio, transcribe  # noqa: E402
from app.postprocess import ScoreParams, arrange, filter_notes  # noqa: E402


def two_hands(bpm=100):
    q = 60 / bpm
    rh = [72, 74, 76, 77, 79, 77, 76, 74, 72, 76, 79, 84, 79, 76, 74, 72]
    notes = [(i * q / 2, q / 2 * 0.9, p) for i, p in enumerate(rh)]  # 8분음표
    for i, b in enumerate([48, 43, 45, 41]):  # 2분음표 베이스
        notes.append((i * 2 * q, 2 * q * 0.95, b))
    return notes


def voice(midi, dur, sr=synth.SR):
    """비브라토 있는 사인파(보컬 대용)."""
    t = np.arange(int(dur * sr)) / sr
    f = 440 * 2 ** ((midi - 69) / 12) * (1 + 0.006 * np.sin(2 * np.pi * 5.5 * t))
    ph = 2 * np.pi * np.cumsum(f) / sr
    env = np.minimum(1, t / 0.04) * np.minimum(1, (dur - t) / 0.05)
    return env * (np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.1 * np.sin(3 * ph))


def mixed(path: Path, bpm=100):
    q = 60 / bpm
    mel = [67, 69, 71, 72, 74, 72, 71, 69, 67, 64, 65, 67]
    mel_notes = [(i * q, q * 0.95, p) for i, p in enumerate(mel)]
    acc = []
    for i, triad in enumerate([[48, 52, 55], [53, 57, 60], [55, 59, 62]]):
        for j in range(4):
            for p in triad:
                acc.append((i * 4 * q + j * q, q * 0.6, p))
    a = synth.render(acc, total=len(mel) * q + 0.5)
    v = np.zeros_like(a)
    for s, d, m in mel_notes:
        x = voice(m, d)
        i = int(s * synth.SR)
        v[i:i + x.size] += x[: v.size - i]
    y = 0.5 * a / np.abs(a).max() + 0.6 * v / np.abs(v).max()
    sf.write(str(path), 0.9 * y / np.abs(y).max(), synth.SR)
    return mel_notes, acc


def add_noise(src: Path, dst: Path, snr_db=20):
    y, sr = sf.read(str(src))
    rng = np.random.default_rng(0)
    n = rng.standard_normal(y.size)
    n *= np.sqrt(np.mean(y**2) / (10 ** (snr_db / 10)) / np.mean(n**2))
    sf.write(str(dst), y + n, sr)
    return dst


def score_alignment(ref, arr, bpm):
    """양자화된 악보 이벤트가 정답 박자 위치·음높이와 일치하는 비율."""
    want = {(Fraction(round(s * bpm / 60 * 4), 4), m) for s, _, m in ref}
    got = {(e.offset, p) for e in arr.right + arr.left for p in e.pitches}
    t0 = min(s for s, _, _ in ref)
    hit = len(want & got)
    return {"expected": len(want), "produced": len(got), "matched": hit,
            "precision": round(hit / len(got), 3) if got else 0.0,
            "recall": round(hit / len(want), 3), "t0": t0}


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="mp3score_eval_"))
    cases = {
        "단선율(C장조 16음, 120BPM)": (synth.melody(), 120),
        "화음(I-IV-V-I 3화음+베이스, 120BPM)": (synth.chords(), 120),
        "양손(8분음표 멜로디+2분음표 베이스, 100BPM)": (two_hands(), 100),
    }
    rows = []
    params = transcribe.TranscribeParams()
    for name, (ref, bpm) in cases.items():
        wav = synth.write_wav(tmp / f"{len(rows)}.wav", ref)
        mp3 = synth.wav_to_mp3(wav, tmp / f"{len(rows)}.mp3")
        noisy = add_noise(wav, tmp / f"{len(rows)}_noise.wav")
        for label, path in [("WAV", wav), ("MP3 192k", mp3), ("WAV+잡음 SNR20dB", noisy)]:
            dec = audio.decode_to_wav(path, tmp / "dec.wav")
            t = time.perf_counter()
            raw = transcribe.transcribe_basic_pitch(dec.path, params)
            dt = time.perf_counter() - t
            filt = filter_notes(raw, ScoreParams())
            arr = arrange(raw, dec.path, ScoreParams(bpm=bpm))
            arr_auto = arrange(raw, dec.path, ScoreParams(bpm=None))
            rows.append({
                "case": name, "input": label, "engine": "basicpitch",
                "raw": note_scores(ref, raw), "post": note_scores(ref, filt),
                "score_grid": score_alignment(ref, arr, bpm),
                "bpm_true": bpm, "bpm_auto": arr_auto.bpm,
                "infer_sec": round(dt, 2), "audio_sec": round(dec.duration, 2),
            })
        if "단선율" in name:
            dec = audio.decode_to_wav(mp3, tmp / "dec.wav")
            y = transcribe.transcribe_yin(dec.path, params)
            rows.append({"case": name, "input": "MP3 192k", "engine": "yin",
                         "raw": note_scores(ref, y), "post": note_scores(ref, filter_notes(y, ScoreParams())),
                         "bpm_true": bpm})
        if "화음" in name:
            dec = audio.decode_to_wav(wav, tmp / "dec.wav")
            y = transcribe.transcribe_yin(dec.path, params)
            rows.append({"case": name, "input": "WAV", "engine": "yin",
                         "raw": note_scores(ref, y), "post": note_scores(ref, filter_notes(y, ScoreParams())),
                         "bpm_true": bpm})

    # 혼합곡(보컬 대용 비브라토 사인 + 피아노 반주)
    mel, acc = mixed(tmp / "mixed.wav")
    dec = audio.decode_to_wav(tmp / "mixed.wav", tmp / "dec.wav")
    raw = transcribe.transcribe_basic_pitch(dec.path, params)
    arr = arrange(raw, dec.path, ScoreParams(bpm=100, source_mode="mixed", split_pitch=64))
    melody_est = [n for n in raw if n.pitch >= 64]
    from app.postprocess import skyline
    sk = skyline(filter_notes(melody_est, ScoreParams()))
    rows.append({"case": "혼합(비브라토 보컬 대용+피아노 반주, 100BPM)", "input": "WAV", "engine": "basicpitch",
                 "raw_all_vs_melody+acc": note_scores(mel + acc, raw),
                 "mixed_mode_melody": note_scores(mel, sk),
                 "score_grid_melody": score_alignment(mel, type(arr)(bpm=100, bpm_estimated=False, right=arr.right), 100)})

    (out / "evaluation.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["| 사례 | 입력 | 엔진 | 원본 P/R/F1 | 후처리 P/R/F1 | onset 오차(ms) | 악보 격자 일치(R) | 자동 BPM(정답) | 추론(초)/길이 |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if "raw" not in r:
            continue
        f = lambda s: f"{s['precision']:.2f}/{s['recall']:.2f}/{s['f1']:.2f} ({s['est']}/{s['ref']})"
        g = r.get("score_grid")
        md.append(
            f"| {r['case']} | {r['input']} | {r['engine']} | {f(r['raw'])} | {f(r['post'])} | "
            f"{r['post']['onset_mae_ms']} | {g['recall'] if g else '-'} | "
            f"{r.get('bpm_auto', '-')} ({r['bpm_true']}) | {r.get('infer_sec', '-')}/{r.get('audio_sec', '-')} |"
        )
    m = rows[-1]
    md.append("")
    md.append(f"혼합곡: 전체 음(선율+반주) 대비 원본 P/R/F1 = {m['raw_all_vs_melody+acc']['precision']}/"
              f"{m['raw_all_vs_melody+acc']['recall']}/{m['raw_all_vs_melody+acc']['f1']}, "
              f"혼합 모드 선율 추정 P/R/F1 = {m['mixed_mode_melody']['precision']}/{m['mixed_mode_melody']['recall']}/"
              f"{m['mixed_mode_melody']['f1']} (추정 {m['mixed_mode_melody']['est']}음 / 정답 {m['mixed_mode_melody']['ref']}음)")
    (out / "evaluation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    audio.safe_remove_tree(tmp)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "results")
