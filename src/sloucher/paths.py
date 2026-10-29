"""Where things live, for the installed app and for a source checkout alike.

- Your data (settings, calibration, logs): %LOCALAPPDATA%\\Sloucher. SLOUCHER_HOME overrides it (tests).
- The app's own files (model, NPU host scripts, assets): next to the .exe when installed,
  or in the repo when running from source.
"""
import json
import os
import sys

PACKAGE = os.path.dirname(os.path.abspath(__file__))


def frozen():
    return getattr(sys, "frozen", False)


def app_dir():
    """Folder of the installed app (the .exe), or the repo root when running from source."""
    if frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(PACKAGE))


def bundled(*parts):
    """A file shipped with the app: PyInstaller unpacks data under sys._MEIPASS."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(PACKAGE)
    return os.path.join(base, *parts)


def asset(name):
    return bundled("sloucher", "assets", name)


def npu_dir():
    """The NPU host scripts. They run in the NPU vendor's Python, so they ship as plain .py files."""
    return bundled("sloucher", "npu")


def data_dir():
    base = os.environ.get("SLOUCHER_HOME") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "Sloucher")
    os.makedirs(base, exist_ok=True)
    return base


def calibration_file():
    return os.path.join(data_dir(), "calibration.json")


def log_dir():
    path = os.path.join(data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def model_file(name):
    """First copy of the model found: next to the app, in the repo, or in the data folder."""
    for folder in (os.path.join(app_dir(), "models"), bundled("models"), os.path.join(data_dir(), "models")):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    return None


def manifest():
    for folder in (os.path.join(app_dir(), "models"), bundled("models")):
        path = os.path.join(folder, "manifest.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise FileNotFoundError("models/manifest.json is missing")


# ---------------------------------------------------------------- settings

DEFAULTS = {
    "sound": True,
    "sit_minutes": 60,
    "break_seconds": 30,
    "xclbin": "auto",       # AMD: auto (4 NPU columns, else 1), 4x4 or 1x4
    "npu_python": None,     # override the NPU runtime's Python if it isn't found automatically
    "camera": 0,
}


def settings_file():
    return os.path.join(data_dir(), "settings.json")


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(settings_file(), encoding="utf-8") as f:
            s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    with open(settings_file(), "w", encoding="utf-8") as f:
        json.dump({k: s[k] for k in DEFAULTS if k in s}, f, indent=2)
