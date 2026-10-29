# Changelog

All notable changes to Sloucher are listed here. The format follows [Keep a Changelog](https://keepachangelog.com),
and versions follow [Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.1.0] - 2026-10-29

First public release, for Windows 11 laptops with an AMD Ryzen 7040 or 8040 (Phoenix, Hawk Point).

### Added
- Posture check: slouching, leaning in and looking down, against your own calibrated posture. The alert comes after
  most of 30 seconds, so a brief slump is ignored.
- Alerts: a soft glow on the screen edges, a small "Sit up" pill and a gentle chime. Sit up and they fade.
- Hourly walk reminder that sees the empty chair, and says "Not done yet: 18 s left" if you come back early.
- The pose model runs on the NPU (AMD Ryzen AI 1.6.1, 96.5% of operators), never on the CPU. The whole app uses
  about 0.8% of the CPU.
- First-run calibration window, tray menu (calibrate, pause, sound, start with Windows), one copy at a time.
- "Sloucher - check my laptop": checks the NPU, driver, runtime, model and camera, and tests the NPU.
- 39 MB installer, no admin rights; it checks for the NPU and AMD's software first.

### Known issues
- The chime plays at most once a minute, so a glow that comes back within a minute is silent
  ([#1](https://github.com/naraianlegrand/sloucher_ai/issues/1)).
- Pause → Resume restarts the "sitting for N min" clock for the walk reminder
  ([#3](https://github.com/naraianlegrand/sloucher_ai/issues/3)).
- Tip: calibrate while looking at your screen as you normally do, not at the camera; otherwise reading the lower part
  of the screen can count as slouching ([#2](https://github.com/naraianlegrand/sloucher_ai/issues/2)).

[Unreleased]: https://github.com/naraianlegrand/sloucher_ai/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/naraianlegrand/sloucher_ai/releases/tag/v0.1.0
