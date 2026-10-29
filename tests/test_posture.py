import json

import numpy as np
import pytest

from sloucher import posture

FRAME = (640, 480)
FPS = 2


def pose(eye_y=0.40, eye_half=0.05, shoulder_y=0.75):
    """Synthetic keypoints: eyes and shoulders only, everything else not found."""
    k = np.full((17, 3), -1.0)
    k[:, 2] = 0
    k[posture.L_EYE] = (0.50 + eye_half, eye_y, 0.9)
    k[posture.R_EYE] = (0.50 - eye_half, eye_y, 0.9)
    k[posture.L_SH] = (0.70, shoulder_y, 0.9)
    k[posture.R_SH] = (0.30, shoulder_y, 0.9)
    return k


UPRIGHT, SLOUCH, LEAN_IN, NOBODY = pose(), pose(eye_y=0.45), pose(eye_half=0.10), np.full((17, 3), -1.0)


def calibrated(tmp_path):
    p = posture.Posture(str(tmp_path / "calibration.json"), fps=FPS)
    p.calibrate()
    results = [p.update(UPRIGHT, FRAME)[0] for _ in range(posture.CALIB_MIN_FRAMES)]
    assert results[-1] == "calibrated" and set(results[:-1]) == {"calibrating"}
    return p


def test_metrics_scale_free():
    near = posture.metrics(UPRIGHT, FRAME)
    far = posture.metrics(UPRIGHT, (1280, 960))
    assert np.allclose(near, far)


def test_uncalibrated_until_calibrated(tmp_path):
    p = posture.Posture(str(tmp_path / "calibration.json"), fps=FPS)
    assert p.update(UPRIGHT, FRAME) == ("uncalibrated", False)


def test_calibration_is_saved_and_reloaded(tmp_path):
    calibrated(tmp_path)
    saved = json.loads((tmp_path / "calibration.json").read_text())
    assert saved["frames"] == posture.CALIB_MIN_FRAMES
    assert posture.Posture(str(tmp_path / "calibration.json"), fps=FPS).calibrated


def test_calibration_fails_without_a_person(tmp_path):
    p = posture.Posture(str(tmp_path / "calibration.json"), fps=FPS)
    p.calibrate()
    states = [p.update(NOBODY, FRAME)[0] for _ in range(posture.CALIB_MIN_FRAMES)]
    assert states[-1] == "calibration_failed" and not p.calibrated


@pytest.mark.parametrize("frame, state", [(UPRIGHT, "good"), (SLOUCH, "slouch"), (LEAN_IN, "lean-in")])
def test_calls(tmp_path, frame, state):
    p = calibrated(tmp_path)
    assert [p.update(frame, FRAME)[0] for _ in range(5)][-1] == state


def test_alert_after_most_of_30_seconds(tmp_path):
    p = calibrated(tmp_path)
    alerts = [p.update(SLOUCH, FRAME)[1] for _ in range(posture.ALERT_S * FPS)]
    assert alerts[-1] and not any(alerts[:-1])          # fires exactly when the 30 s window fills


def test_brief_slump_never_alerts(tmp_path):
    p = calibrated(tmp_path)
    for _ in range(10):                                  # 20 s slouched, then 10 s upright, twice over
        alerts = [p.update(SLOUCH, FRAME)[1] for _ in range(20 * FPS)]
        alerts += [p.update(UPRIGHT, FRAME)[1] for _ in range(10 * FPS)]
        assert not any(alerts)
