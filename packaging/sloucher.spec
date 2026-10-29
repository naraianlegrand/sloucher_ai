# PyInstaller build: one folder, two programs sharing it.
#   Sloucher.exe      the tray app (no console)
#   sloucher-cli.exe  the same app with a console, for `sloucher-cli doctor`
# No NPU runtime inside: the NPU host scripts ship as plain .py files and run in the
# NPU vendor's own Python (AMD: Ryzen AI Software), which the user installs once.
#
#   pyinstaller packaging/sloucher.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src", "sloucher")
MODEL = os.path.join(ROOT, "models", "yolov8n-pose_int8.onnx")
if not os.path.exists(MODEL):
    raise SystemExit(f"Put the model at {MODEL} first (see models/manifest.json)")

datas = [
    (os.path.join(SRC, "assets"), "sloucher/assets"),
    (os.path.join(ROOT, "models", "manifest.json"), "models"),
    (MODEL, "models"),
]
datas += [(os.path.join(SRC, "npu", f), "sloucher/npu") for f in os.listdir(os.path.join(SRC, "npu")) if f.endswith(".py")]

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[os.path.join(ROOT, "src")],
    datas=datas,
    hiddenimports=["pystray._win32"],
    excludes=["onnxruntime", "matplotlib", "scipy", "pandas", "IPython", "pytest", "ssl", "_ssl", "_hashlib"],
    noarchive=False,
)
# Not needed: the camera is read through DirectShow (no FFmpeg), no AVIF images, no TLS
# (hashlib falls back to its built-in SHA-256). Saves ~45 MB.
UNUSED = ("opencv_videoio_ffmpeg", "_avif", "libcrypto", "libssl")
a.binaries = [b for b in a.binaries if not any(u in os.path.basename(b[0]) for u in UNUSED)]
pyz = PYZ(a.pure)
icon = os.path.join(SRC, "assets", "icon.ico")
common = dict(debug=False, bootloader_ignore_signals=False, strip=False, upx=False, icon=icon,
              version=os.path.join(SPECPATH, "version.txt"))

app = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Sloucher", console=False, **common)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name="sloucher-cli", console=True, **common)
COLLECT(app, cli, a.binaries, a.datas, strip=False, upx=False, name="Sloucher")
