# Bringing Sloucher to another NPU

Every NPU vendor has its own runtime and needs its own converted model, but the app (camera, posture logic, walk
reminder, tray, alerts) stays the same. A new NPU is: an entry in `hardware.CHIPS`, a backend in `npu/`, a branch in
`engine.plan()`, a converted model with its checksum in `models/manifest.json`, and a tester with that laptop.

The rule for every backend: **prove the model runs on the NPU, or refuse to start.** No CPU fallback.

| Order | NPU | Runtime | Model | Proof it's on the NPU | Notes |
|---|---|---|---|---|---|
| 1 | AMD Ryzen 7040 / 8040 | Ryzen AI 1.6.1, Vitis AI EP (X1 target + xclbin) | INT8 QDQ ONNX (this repo) | "Actually running on NPU" in the provider's report | Done |
| 2 | AMD Ryzen AI 300 (Strix, Krackan) | Ryzen AI (XDNA 2) | same ONNX, re-checked | same report | Check which Ryzen AI version supports both NPU generations, and the session options for XDNA 2 |
| 3 | Intel Core Ultra | OpenVINO, device `NPU` | INT8 OpenVINO IR: Ultralytics export, NNCF quantization on desk frames | compile on `NPU` only (no AUTO), read the device back | OpenVINO is Apache-2.0, so the runtime can ship inside the installer: one-click |
| 4 | Snapdragon X | ONNX Runtime QNN EP (HTP) | QDQ ONNX quantized for QNN | session option to disable CPU fallback | Windows on ARM: needs ARM64 builds of Python, numpy and OpenCV |
| 5 | Apple Silicon | Core ML, Neural Engine | Core ML package (Ultralytics export) | request the Neural Engine; verify with `powermetrics` while testing (macOS has no API for it) | A separate, native menu-bar app; notarization |

## Steps for a new Windows NPU

1. **Find it.** Add its PCI vendor/device ID to `hardware.CHIPS` (Device Manager → the NPU → Details → Hardware Ids).
2. **Convert the model.** Same YOLOv8n-pose at 480×640, quantized on seated desk frames (never on someone's face in
   git: keep calibration frames local). Record its checksum and the measured operator split in the manifest.
3. **Backend.** `npu/<vendor>.py` with `open_session(model, ...)`; `host.load()` picks it by `--backend`.
4. **Plan.** In `engine.plan()`, find the runtime and list the options to try, best first.
5. **Prove it.** `sloucher doctor` must show the model on the NPU, and the whole app must stay near 1% CPU at 2 fps.
   Measure the full process tree, not just inference time: "on the NPU" isn't automatically "light on the CPU".
