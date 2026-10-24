"""mir_eval 기반 음표 단위 정확도(onset 50ms, 오프셋 무시, 음높이 ±50센트)."""
from __future__ import annotations

import numpy as np


def note_scores(ref: list[tuple[float, float, int]], est, onset_tol: float = 0.05) -> dict:
    import mir_eval

    def arr(items):
        if not items:
            return np.zeros((0, 2)), np.zeros(0)
        iv = np.array([[s, s + max(d, 0.01)] for s, d, _ in items])
        hz = np.array([440.0 * 2 ** ((m - 69) / 12) for *_, m in items])
        return iv, hz

    ri, rp = arr(ref)
    ei, ep = arr([(n.start, n.end - n.start, n.pitch) for n in est])
    if len(ep) == 0:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "ref": len(ref), "est": 0, "onset_mae_ms": None}
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ri, rp, ei, ep, onset_tolerance=onset_tol, offset_ratio=None
    )
    matches = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=onset_tol, offset_ratio=None)
    errs = [abs(ri[i][0] - ei[j][0]) * 1000 for i, j in matches]
    return {
        "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
        "ref": len(ref), "est": len(est),
        "onset_mae_ms": round(float(np.mean(errs)), 1) if errs else None,
    }
