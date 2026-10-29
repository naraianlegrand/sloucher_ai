"""Slouch logic: turn face and shoulder keypoints into good / slouch / lean-in calls.

Front-view metrics, each a ratio so it doesn't change with how far from the camera
you sit, compared with your own upright baseline:

- eye drop:   eyes to the shoulder line, / shoulder width. Shrinks when you
              slump or look down.
- face ratio: eye-to-eye distance / shoulder width. Grows when you crane
              toward the screen (the face gets closer than the shoulders).

Thresholds were tuned on nine recorded desk clips: every slouch, lean-in and
head-down clip alerts at 30 s, and no upright clip does. Pure numpy.
"""
import collections
import json
import os

import numpy as np

NOSE, L_EYE, R_EYE, L_EAR, R_EAR, L_SH, R_SH = range(7)

DROP_TH = 0.96        # slouch when eye drop < 96% of upright
FACE_TH = 1.15        # lean-in when face ratio > 115% of upright
SMOOTH_S = 0.5        # rolling median over about half a second
ALERT_S = 30          # alert after a sustained bad posture ...
ALERT_FRAC = 0.8      # ... bad for 80% of the last 30 s, so a brief sit-up doesn't reset the clock
CALIB_S = 3           # seconds of upright frames for a calibration ...
CALIB_MIN_FRAMES = 12  # ... and at least this many, so low frame rates still get a steady baseline


def metrics(kps, frame_wh):
    """(N, 17, 3) keypoints, x and y in 0..1 (-1 = not found) -> eye_drop, face_ratio (NaN when unknown)."""
    kps = np.asarray(kps, dtype=np.float64).reshape(-1, 17, 3)
    found = kps[:, :, 0] >= 0
    p = kps[:, :, :2] * np.asarray(frame_wh, dtype=np.float64)    # pixels, so x and y share a scale
    ok = found[:, L_EYE] & found[:, R_EYE] & found[:, L_SH] & found[:, R_SH]
    sw = np.linalg.norm(p[:, L_SH] - p[:, R_SH], axis=1)
    sw[~ok | (sw == 0)] = np.nan
    eye_drop = ((p[:, L_SH, 1] + p[:, R_SH, 1]) - (p[:, L_EYE, 1] + p[:, R_EYE, 1])) / 2 / sw
    face_ratio = np.linalg.norm(p[:, L_EYE] - p[:, R_EYE], axis=1) / sw
    return eye_drop, face_ratio


def calibrate(kps, frame_wh):
    """Baseline from frames of you sitting upright: the median of each metric."""
    eye_drop, face_ratio = metrics(kps, frame_wh)
    if np.isnan(eye_drop).all():
        raise ValueError("no frames with both eyes and both shoulders to calibrate on")
    return {"eye_drop": float(np.nanmedian(eye_drop)), "face_ratio": float(np.nanmedian(face_ratio)),
            "frames": int(np.isfinite(eye_drop).sum())}


class SlouchDetector:
    """Feed one frame of keypoints at a time; returns (state, drop, face) with the ratios vs baseline.

    state is "good", "slouch", "lean-in" or "unknown" (no eyes + shoulders in the window yet).
    """

    def __init__(self, baseline, frame_wh, window, drop_th=DROP_TH, face_th=FACE_TH):
        self.base = baseline
        self.frame_wh = frame_wh
        self.drop_th, self.face_th = drop_th, face_th
        self.drops = collections.deque(maxlen=window)
        self.faces = collections.deque(maxlen=window)

    def update(self, kps):
        eye_drop, face_ratio = (m[0] for m in metrics(kps, self.frame_wh))
        if np.isfinite(eye_drop):
            self.drops.append(eye_drop / self.base["eye_drop"])
            self.faces.append(face_ratio / self.base["face_ratio"])
        if not self.drops:
            return "unknown", float("nan"), float("nan")
        drop, face = float(np.median(self.drops)), float(np.median(self.faces))
        if face > self.face_th:
            state = "lean-in"
        elif drop < self.drop_th:
            state = "slouch"
        else:
            state = "good"
        return state, drop, face


class AlertTimer:
    """True once the posture has been bad for ALERT_FRAC of the last ALERT_S seconds."""

    def __init__(self, fps, seconds=ALERT_S, frac=ALERT_FRAC):
        self.frac = frac
        self.bad = collections.deque(maxlen=max(1, int(seconds * fps)))

    def update(self, state):
        self.bad.append(state in ("slouch", "lean-in"))
        full = len(self.bad) == self.bad.maxlen
        return full and sum(self.bad) >= self.frac * len(self.bad)

    def reset(self):
        self.bad.clear()


class Posture:
    """The live posture call against your saved upright baseline.

    calibrate() collects the next few seconds of frames as the new baseline and saves it.
    update() -> (state, alert); state is good / slouch / lean-in / unknown / calibrating / uncalibrated,
    or ("calibrated" | "calibration_failed") on the frame a calibration finishes.
    """

    def __init__(self, path, fps):
        self.path = path
        self.fps = fps
        self.base = self._load()
        self.det = None
        self.timer = AlertTimer(fps)
        self.collecting = None

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                base = json.load(f)
            return base if {"eye_drop", "face_ratio"} <= base.keys() else None
        except (OSError, ValueError):
            return None

    @property
    def calibrated(self):
        return self.base is not None

    def calibrate(self):
        self.collecting = []

    def update(self, kps, frame_wh):
        if self.collecting is not None:
            self.collecting.append(kps)
            if len(self.collecting) < max(CALIB_MIN_FRAMES, round(CALIB_S * self.fps)):
                return "calibrating", False
            frames, self.collecting = self.collecting, None
            self.det = None
            self.timer.reset()
            try:
                self.base = calibrate(np.stack(frames), frame_wh)
            except ValueError:
                return "calibration_failed", False
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.base, f, indent=2)
            return "calibrated", False
        if self.base is None:
            return "uncalibrated", False
        if self.det is None:
            self.det = SlouchDetector(self.base, frame_wh, window=max(3, round(SMOOTH_S * self.fps)))
        state, _, _ = self.det.update(kps)
        return state, self.timer.update(state)
