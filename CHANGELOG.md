# Changelog

## 0.1.0 (unreleased)

First version of the installable app, for AMD Ryzen 7040 / 8040 laptops.

- Posture: slouch, lean-in and head-down against your own calibrated posture; alert after most of 30 seconds.
- Alerts: a soft glow on the screen edges, a small "Sit up" pill, one gentle chime at most once a minute.
- Hourly walk reminder that sees the empty chair ("Not done yet: 18 s left").
- Runs the pose model on the NPU (AMD Ryzen AI 1.6.1, 96.5% of operators); never on the CPU. Whole app ~0.8% CPU.
- `Sloucher - check my laptop` (doctor): checks NPU, driver, runtime, model and camera, and tests the NPU.
- Installer: 39 MB, no admin rights, checks for the NPU and AMD's software first.
