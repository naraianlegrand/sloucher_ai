"""Sloucher: the tray app, plus `doctor` and `--demo`.

    sloucher                 run in the tray (the normal way)
    sloucher doctor          check the NPU, driver, runtime, model and camera
    sloucher --demo          preview the alerts for 8 s, no camera or NPU
    sloucher --sit-minutes 1 --break-seconds 10    try the walk reminder quickly
"""
import argparse
import ctypes
import logging
import logging.handlers
import os
import sys

from . import __version__, paths


def setup_logging(verbose=False):
    handler = logging.handlers.RotatingFileHandler(os.path.join(paths.log_dir(), "sloucher.log"),
                                                   maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handlers = [handler]
    if sys.stderr is not None and not paths.frozen():
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sloucher", description="An always-on posture coach that runs on your NPU.")
    ap.add_argument("command", nargs="?", choices=["doctor"], help="doctor: check that Sloucher can run here")
    ap.add_argument("--demo", action="store_true", help="preview the alerts for 8 s, no camera or NPU")
    ap.add_argument("--sit-minutes", type=float, help="sitting time before the walk reminder (default 60)")
    ap.add_argument("--break-seconds", type=float, help="time away that counts as a break (default 30)")
    ap.add_argument("--xclbin", choices=["auto", "4x4", "1x4"], help="AMD: NPU columns to use (default auto)")
    ap.add_argument("--no-camera", action="store_true", help="doctor: skip the camera check")
    ap.add_argument("--verbose", action="store_true", help="log everything, including the NPU host's output")
    ap.add_argument("--version", action="version", version=f"Sloucher {__version__}")
    args = ap.parse_args(argv)

    settings = paths.load_settings()
    for key in ("sit_minutes", "break_seconds", "xclbin"):
        if getattr(args, key) is not None:
            settings[key] = getattr(args, key)
    setup_logging(args.verbose)

    if args.command == "doctor":
        from . import doctor
        return doctor.run(settings, camera=not args.no_camera)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)      # real pixels on scaled displays
    except (AttributeError, OSError):
        pass
    from . import app
    if args.demo:
        return app.demo()
    return app.run(settings)


if __name__ == "__main__":
    sys.exit(main())
