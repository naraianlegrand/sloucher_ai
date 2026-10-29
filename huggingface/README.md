---
license: agpl-3.0
library_name: onnxruntime
pipeline_tag: keypoint-detection
base_model: Ultralytics/YOLOv8
tags:
  - onnx
  - int8
  - pose-estimation
  - npu
  - ryzen-ai
  - amd
  - on-device
  - yolov8
---

# YOLOv8n-pose INT8 for the AMD Ryzen AI NPU

A pose model that actually runs on a laptop's **NPU**: Ultralytics YOLOv8n-pose, exported at 480×640 and quantized to
INT8 so that **96.5% of its operators run on the AMD Ryzen AI NPU** (Phoenix / Hawk Point), at 12-17 ms per frame.

It powers [Sloucher](https://github.com/naraianlegrand/sloucher_ai), an open-source posture coach that uses about 1% of
the CPU and keeps your video on your laptop. Website: [sloucher.karthikeyanumesh.com](https://sloucher.karthikeyanumesh.com).

## On the NPU

Measured on an AMD Ryzen 7040 laptop with Ryzen AI Software 1.6.1 (Vitis AI execution provider):

| | |
|---|---|
| Operators on the NPU | **1,042 of 1,080 (96.5%)**; 28 on CPU (ONNX Runtime), 10 on the Vitis AI EP's CPU path |
| Provider report | 1 subgraph, "Actually running on NPU" |
| Time per frame | ~12.4 ms (4x4 NPU binary, 4 columns); ~22 ms (1x4, 1 column, shares the NPU with Windows Studio Effects) |
| Whole posture app, camera included | 0.8% of 16 logical CPUs at 2 frames a second |

## Input and output

- **Input** `images`: `1×3×480×640` float32, RGB, values 0..1 (NCHW).
- **Output** `output0`: `1×56×6300`. For each of the 6,300 candidates: box (4), person score (1), then 17 COCO
  keypoints × (x, y, score), with x and y in pixels of the 640×480 input.

## How to run it

Needs an AMD Ryzen 7040 / 8040 laptop and [Ryzen AI Software 1.6.1](https://ryzenai.docs.amd.com/en/latest/inst.html)
(use that version: newer ones dropped these chips).

```python
import numpy as np
import onnxruntime as ort

so = ort.SessionOptions()
# Important: ONNX Runtime's thread pool busy-waits by default. Even with the model on the NPU,
# that kept ~7 CPU cores busy. Spinning off + 1 thread brings it near zero.
so.add_session_config_entry("session.intra_op.allow_spinning", "0")
so.add_session_config_entry("session.inter_op.allow_spinning", "0")
so.intra_op_num_threads = 1
so.inter_op_num_threads = 1

xclbin = r"C:\Program Files\RyzenAI\1.6.1\voe-4.0-win_amd64\xclbins\phoenix\4x4.xclbin"
session = ort.InferenceSession("yolov8n-pose_int8.onnx", so,
                               providers=["VitisAIExecutionProvider"],          # NPU only, no CPU fallback
                               provider_options=[{"target": "X1", "xclbin": xclbin}])

rgb = ...  # a 480x640x3 uint8 RGB frame
x = (rgb.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
out = session.run(None, {"images": x})[0][0]                    # (56, 6300)
best = int(out[4].argmax())                                      # the most confident person
keypoints = out[5:, best].reshape(17, 3)                         # x, y (pixels), score
```

Check the console when the session is created: the Vitis AI EP prints the operator split and
`Actually running on NPU`. If that line is missing, the model is running on the CPU.

## How it was made

1. Exported from Ultralytics YOLOv8n-pose at 480×640 (ONNX, opset 17).
2. Quantized with AMD Quark (XINT8), calibrated on frames of a person sitting at a desk, the situation the model is used
   for. The final decode step is kept in float, because it mixes box coordinates and scores in one tensor.
3. Checked on 9 recorded desk clips (upright, slouching, leaning in, head down, dim light, glasses on and off):
   both shoulders found, below the nose and plausibly wide in **100% of frames in every front-facing clip**. MoveNet,
   AMD's ready-made NPU pose model, managed about 0% in the same test: it's trained on full-body photos and drew a tiny
   skeleton on the face at a desk.

The calibration and test clips are not published: they show a person's face.

## Limitations

- Tested on AMD Phoenix / Hawk Point only. Ryzen AI 300 (XDNA 2) should work with a newer Ryzen AI release but hasn't
  been checked.
- Tuned for one person sitting in front of a laptop webcam. Accuracy drops for side views (88% in the sideways clip) and
  leaning far forward (61%).
- Attention-based successors (YOLO11-pose) compile for this NPU but hang at run time; this plain-convolution model is
  the one that works.

## Licence

AGPL-3.0, inherited from Ultralytics YOLOv8. Made in Montréal, Canada, by
[Karthikeyan Umesh](https://karthikeyanumesh.com).
