import numpy as np

from sloucher.npu import yolo_pose

W, H = 640, 480


def model_output(best_score=0.9, kp_score=0.8, n=6300, best=1234):
    out = np.zeros((1, 56, n), dtype=np.float32)
    out[0, 4, :] = 0.01
    out[0, 4, best] = best_score
    kps = np.zeros((17, 3), dtype=np.float32)
    kps[:, 0] = np.linspace(100, 540, 17)
    kps[:, 1] = np.linspace(60, 420, 17)
    kps[:, 2] = kp_score
    kps[3, 2] = 0.1                                   # one keypoint the model isn't sure about
    out[0, 5:, best] = kps.reshape(-1)
    return out, kps


def test_input_layout():
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    rgb[..., 0] = 255
    x = yolo_pose.to_input(rgb)
    assert x.shape == (1, 3, H, W) and x.dtype == np.float32
    assert x[0, 0].max() == 1.0 and x[0, 1].max() == 0.0


def test_decode_picks_the_person_and_normalises():
    out, kps = model_output()
    got = yolo_pose.decode(out, W, H)
    assert got.shape == (17, 3)
    assert np.allclose(got[0, :2], (kps[0, 0] / W, kps[0, 1] / H))
    assert tuple(got[3, :2]) == (-1, -1)              # low-confidence keypoint: not found
    assert (got[:, 0] >= 0).sum() == 16


def test_decode_nobody_there():
    out, _ = model_output(best_score=0.1)
    assert (yolo_pose.decode(out, W, H)[:, 0] < 0).all()
