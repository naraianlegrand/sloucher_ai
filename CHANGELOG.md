# Changelog

All notable changes to Sloucher are listed here. The format follows [Keep a Changelog](https://keepachangelog.com),
and versions follow [Semantic Versioning](https://semver.org).

## [Unreleased]

### Added
- **Stats** (tray menu, or double-click the icon): today's upright %, time slouched, alerts, how fast you sat up,
  slouches you fixed yourself, and walks; the last 7 days with the change against the 7 before; your best and hardest
  hour of the day ([#4](https://github.com/naraianlegrand/sloucher_ai/issues/4)).
- **Copy for my AI coach** and **Export** (CSV + JSON) from the stats window
  ([#12](https://github.com/naraianlegrand/sloucher_ai/issues/12)). Stats are numbers only, kept on your laptop; see
  docs/STATS.md.
- **Walk card:** the hourly reminder flashes the screen blue twice, then a card stays until you walk, with
  **"I walked"** (if the camera missed it) and **Snooze 10 min**
  ([#10](https://github.com/naraianlegrand/sloucher_ai/issues/10)).
- Windows 11 look: Mica glass behind Stats, frosted Acrylic behind the walk card, dark title bar, rounded corners.
  Stats has a **Refresh** button (it also refreshes itself every minute).
- The camera turns off while the screen is locked, and back on when you unlock (the NPU stays ready).

### Fixed
- A walk taken with the screen locked (Win+L) wasn't seen. A locked screen now counts as away, and a lock of 30 s or
  more counts as a walk, also after the display turns off
  ([#11](https://github.com/naraianlegrand/sloucher_ai/issues/11)).
- Turning Sound on or off while running with `--sit-minutes` saved those test timings for good; now only Sound is
  saved.
- Every glow now chimes, not just one a minute ([#1](https://github.com/naraianlegrand/sloucher_ai/issues/1)).
- Pause -> Resume no longer restarts the sitting clock ([#3](https://github.com/naraianlegrand/sloucher_ai/issues/3)).

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
