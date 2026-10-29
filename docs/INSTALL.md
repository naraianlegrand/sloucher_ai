# Install Sloucher

Sloucher 0.1 runs on Windows 11 laptops with an **AMD Ryzen 7040 or 8040** processor (Phoenix, Hawk Point),
the ones with "Ryzen AI" and an NPU. Not sure? Open Task Manager → Performance: if you see **NPU 0**, you have one.

## 1. AMD Ryzen AI Software (once)

Sloucher's AI runs on AMD's NPU runtime, which AMD distributes itself.

1. Make sure the NPU driver is installed: Device Manager → **Neural processors** (or "Compute accelerators")
   → **NPU Compute Accelerator Device**. Most laptops ship with it; otherwise get it from your laptop maker or AMD.
2. Install **Ryzen AI Software 1.6.1** from AMD: https://ryzenai.docs.amd.com/en/latest/inst.html
   Use version 1.6.1: newer versions dropped support for these chips. Keep the installer's default options; it
   sets up its own Python environment (`ryzen-ai-1.6.1`), which Sloucher uses.

## 2. Sloucher

1. Download `SloucherSetup-x.y.z.exe` from the [latest release](https://github.com/naraianlegrand/sloucher_ai/releases/latest) and run it. No admin rights
   needed; it installs in about 15 seconds. The installer isn't code-signed yet, so Windows may say "Windows protected
   your PC": click **More info → Run anyway**. You can check the download against the SHA-256 on the release page.
2. Sloucher starts in the tray (Windows may hide it under **^** next to the clock; drag it onto the taskbar).
3. The first start takes about 40 seconds while the model loads onto the NPU.
4. Sit up tall, look at your screen the way you normally do (not at the camera), and click **Calibrate**. That's it.

## If something's wrong

Start menu → **Sloucher - check my laptop**. It checks the NPU, driver, AMD's software, the model and the camera,
runs a test on the NPU, and says what to fix.

| You see | What it means |
|---|---|
| "Stopped: couldn't run on the NPU" | Usually a video call or the Camera app is using Windows Studio Effects, which share the NPU. Close it, then choose **Resume** in the tray menu. |
| "The camera picture is black" | Another app is using the camera, or the privacy shutter is closed. |
| "Needs calibration" | Sit up tall, tray menu → **Calibrate**. |

Sloucher never falls back to the CPU: if the NPU isn't available, it stops and tells you.

## Update

Tray → **Quit**, run the new installer (it installs over the old version), then start Sloucher. Your settings and
calibration are kept.

## Uninstall

Settings → Apps → Sloucher → Uninstall. It asks whether to keep your settings and calibration
(they're in `%LOCALAPPDATA%\Sloucher`).
