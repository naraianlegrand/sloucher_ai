# How Sloucher fits together

```
Sloucher.exe (our Python, frozen)                         NPU host (the NPU vendor's Python)
┌──────────────────────────────────────────┐   frames   ┌────────────────────────────────────┐
│ camera.py    webcam at 2 fps             │ ─────────► │ host.py       socket server        │
│ posture.py   slouch / lean-in / alert    │            │ amd_vitisai   ONNX Runtime +       │
│ breaks.py    hourly walk                 │ ◄───────── │               Vitis AI EP → NPU    │
│ app.py       tray, glow, pill, chime     │ 17 points  │ yolo_pose     decode               │
│ engine.py    finds the runtime, starts   │            └────────────────────────────────────┘
│              and checks the host         │ ◄── stdout: "Actually running on NPU", @@ready
└──────────────────────────────────────────┘
```

**Why two processes.** AMD's licence doesn't let us ship its NPU runtime inside our installer, so the model runs in
AMD's own Python, which the user installs once with Ryzen AI Software. Everything else (camera, logic, UI) is ours and
ships frozen. The split has two more benefits found in the lab:

- The provider reports where the model runs ("Actually running on NPU") from native code, straight to stdout. A
  separate process lets the app read that report and refuse to run if the model isn't on the NPU.
- The NPU host must start with stdin closed: an open stdin pipe made NPU session creation hang.

**The messages** (`npu/wire.py`): a frame is 640×480 RGB (900 KB) and the answer is 17 keypoints (208 bytes), twice a
second over localhost.

**NPU-only.** The engine only accepts a host whose output shows the model actually running on the NPU. On AMD it tries
4 NPU columns first and then 1 (room for Windows Studio Effects), never the CPU.

**CPU budget.** Measured on a Ryzen 7 Phoenix laptop: the whole app uses 0.8% of 16 logical CPUs (~480 MB). The two
settings that matter: ONNX Runtime's thread spinning off with one thread (spinning burned ~7 cores), and 2 frames a
second (posture doesn't change faster).

**Where things live.** `paths.py`: your settings, calibration (three numbers) and logs are in `%LOCALAPPDATA%\Sloucher`.
No camera frames are ever written to disk.

| File | Runs in | Job |
|---|---|---|
| `__main__.py` | app | `sloucher`, `sloucher doctor`, `sloucher --demo` |
| `app.py` | app | tray, glow, pill, chime, first-run calibration, start with Windows |
| `camera.py` | app | webcam, black-frame check, resize for the model |
| `posture.py` | app | metrics vs your baseline, 30 s alert rule, calibration |
| `breaks.py` | app | hourly walk logic |
| `engine.py` | app | plans and starts the NPU host, checks the NPU report |
| `hardware.py` | app | NPU from the registry (ComputeAccelerator class), Ryzen AI install and Python |
| `doctor.py` | app | the checklist |
| `npu/host.py` | NPU Python | loads the model, serves frames |
| `npu/amd_vitisai.py` | NPU Python | AMD session settings |
| `npu/yolo_pose.py`, `npu/wire.py` | both | model input/output, messages |
