"""YOLOv8-pose input and output, shared by every NPU backend.

numpy only: this file also runs inside the NPU vendor's Python (see host.py).

- Input:  1x3xHxW float RGB 0..1 (NCHW).
- Output: 1x56xN, per candidate: box (4), person score (1), 17 keypoints x (x, y, score) in pixels.
"""
import numpy as np

PERSON_TH = 0.25   # Ultralytics' default person confidence
KP_TH = 0.5        # Ultralytics' default keypoint confidence

KEYPOINTS = ["nose", "l_eye", "r_eye", "l_ear", "r_ear", "l_shoulder", "r_shoulder",
             "l_elbow", "r_elbow", "l_wrist", "r_wrist", "l_hip", "r_hip",
             "l_knee", "r_knee", "l_ankle", "r_ankle"]


def to_input(rgb):
    """HxWx3 uint8 RGB, already at the model's size -> 1x3xHxW float32 0..1."""
    return (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]


def decode(out, w, h):
    """Model output (56, N) -> (17, 3): x, y in 0..1 (-1 = not found) and score.

    Single user: takes the most confident person. Below PERSON_TH, every keypoint is "not found".
    """
    out = np.asarray(out)
    if out.ndim == 3:
        out = out[0]
    i = int(out[4].argmax())
    kps = out[5:, i].reshape(17, 3).astype(np.float32)   # astype copies
    kps[:, 0] /= w
    kps[:, 1] /= h
    if out[4, i] < PERSON_TH:
        kps[:, 2] = 0
    kps[kps[:, 2] < KP_TH, :2] = -1
    return kps
