# Sloucher

**Your laptop has an AI chip that sits idle. Let it fix your posture.**

Sloucher is an always-on posture coach for Windows laptops. It watches your face and shoulders through the
webcam and runs its AI on the **NPU**, the laptop's neural processing unit, not the CPU. The whole app uses about
1% of the CPU. When you've slouched, leaned in or looked down for most of 30 seconds, the edges of your screen
glow and a small "Sit up" appears. Sit up and it's gone. Once an hour it gets you out of the chair.

Your video never leaves your laptop: each frame becomes 17 body points on the NPU and is then discarded.

## Website

**[sloucher.karthikeyanumesh.com](https://sloucher.karthikeyanumesh.com)**: what Sloucher does, in English and French.

- [How it was built](https://sloucher.karthikeyanumesh.com/story/): the SDK that quietly ran on the CPU, the model
  that couldn't see me, and the NPU app that burned 7 CPU cores.
- [Extra resources](https://sloucher.karthikeyanumesh.com/extra/): every measurement, and a checklist for building
  your own app on the NPU.
- [Privacy](https://sloucher.karthikeyanumesh.com/privacy/)

## Supported laptops

| NPU | Status |
|---|---|
| AMD Ryzen 7040 / 8040 (Phoenix, Hawk Point) | v1 |
| AMD Ryzen AI 300 (Strix, Krackan) | next, needs a tester |
| Intel Core Ultra | planned (OpenVINO) |
| Snapdragon X | planned (QNN) |
| Apple Silicon | planned (separate Mac app) |

Sloucher is NPU-only by design: if the model can't run on the NPU, the app tells you and stops. It never falls
back to the CPU.

## Install

See [docs/INSTALL.md](docs/INSTALL.md).

## Run from source

```
pip install -e .[dev]
python -m sloucher doctor     # checks the NPU, driver, runtime and model
python -m sloucher            # the tray app
python -m sloucher --demo     # preview the alerts, no camera or NPU
pytest
```

How it fits together: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Adding another NPU: [docs/PORTING.md](docs/PORTING.md).

## Licence

AGPL-3.0. The pose model is Ultralytics YOLOv8n-pose (AGPL-3.0), quantized to INT8 for the NPU.

Made in Montréal, Canada, by [Karthikeyan Umesh](https://karthikeyanumesh.com).
