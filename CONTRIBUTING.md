# Contributing

Thanks for helping. Sloucher is small on purpose: a calm app, about 1% CPU, the model on the NPU only.

## The most useful help right now

**Testing on another NPU.** Sloucher runs on AMD Ryzen 7040 / 8040 today. If you have an AMD Ryzen AI 300, Intel Core
Ultra, Snapdragon X or Apple Silicon laptop, open an issue ("I can test on my laptop"). How a port fits together:
[docs/PORTING.md](docs/PORTING.md).

## Reporting a bug

Use the bug report template and paste the output of **Start menu → "Sloucher - check my laptop"**
(`python -m sloucher doctor` from source): it says which NPU, driver and runtime you have.

## Changing code

1. Pick or open an issue first, so we agree on the change.
2. A branch per issue; keep changes small.
3. `python -m pytest -q` must pass (the core tests need no NPU or camera; they run on every push).
4. If it touches the NPU path, run `python -m sloucher doctor` on a real laptop: it must show "Actually running on NPU".
5. Open a pull request that says `Fixes #<issue>`.

Ground rules: no CPU fallback for the model; nothing leaves the laptop (no network calls, no saved frames); measure CPU
for the whole app, not just inference time.

Versions follow [Semantic Versioning](https://semver.org) and changes are listed in [CHANGELOG.md](CHANGELOG.md).
