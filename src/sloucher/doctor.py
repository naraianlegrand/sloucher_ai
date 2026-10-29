"""`sloucher doctor`: checks everything Sloucher needs, in plain words, and what to do if something's missing."""
import hashlib
import platform
import sys

from . import __version__, engine, hardware, paths


class Checklist:
    def __init__(self):
        self.failed = False

    def line(self, tag, text, hint=None):
        print(f"  [{tag:4s}] {text}")
        if hint:
            print(f"          -> {hint}")
        if tag == "FAIL":
            self.failed = True

    def ok(self, text):
        self.line("ok", text)

    def warn(self, text, hint=None):
        self.line("WARN", text, hint)

    def fail(self, text, hint=None):
        self.line("FAIL", text, hint)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(settings, camera=True, npu_test=True):
    c = Checklist()
    print(f"Sloucher {__version__} doctor\n")

    print("Laptop")
    c.ok(f"{platform.system()} {platform.release()} ({platform.version()}), Python {platform.python_version()}")
    npus = hardware.find_npus()
    if not npus:
        c.fail("No NPU found", "Sloucher needs a laptop with an NPU (AMD Ryzen 7040 / 8040 for now).")
    for n in npus:
        if n.supported:
            c.ok(f"NPU: {n.chip.name}, driver {n.driver_version}")
        else:
            c.fail(f"NPU: {n.chip.name} ({n.hardware_id}) isn't supported yet",
                   "Supported now: AMD Ryzen 7040 / 8040 (Phoenix, Hawk Point).")

    print("\nNPU runtime")
    npu = hardware.main_npu()
    if npu and npu.chip.vendor == "amd":
        installs = hardware.find_ryzen_ai()
        if installs:
            c.ok(f"AMD Ryzen AI Software {installs[0].version}: {installs[0].path}")
            for cols in ("4x4", "1x4"):
                (c.ok if installs[0].xclbin(npu.chip.family, cols) else c.warn)(
                    f"NPU binary {cols} ({'4 NPU columns' if cols == '4x4' else '1 column, shares the NPU'})"
                    + ("" if installs[0].xclbin(npu.chip.family, cols) else ": missing"))
        else:
            c.fail(f"AMD Ryzen AI Software {hardware.RYZEN_AI_VERSION} not found",
                   "Install it once from AMD (docs/INSTALL.md), then run doctor again.")
        python = settings.get("npu_python") or next(iter(hardware.ryzen_ai_pythons()), None)
        if python:
            info = hardware.check_runtime(python)
            if info and "VitisAIExecutionProvider" in info["providers"]:
                c.ok(f"Ryzen AI Python: {python} (onnxruntime {info['onnxruntime']}, Vitis AI provider)")
            else:
                c.fail(f"Ryzen AI Python at {python} has no Vitis AI provider", "Reinstall Ryzen AI Software.")
        else:
            c.fail(f"No ryzen-ai-{hardware.RYZEN_AI_VERSION} Python environment found",
                   "The Ryzen AI installer creates it; or set npu_python in " + paths.settings_file())

    print("\nModel")
    spec = paths.manifest()["pose"]
    model = paths.model_file(spec["file"])
    if not model:
        c.fail(f"{spec['file']} is missing", "Reinstall Sloucher.")
    elif sha256(model) != spec["sha256"]:
        c.fail(f"{spec['file']} doesn't match its checksum (damaged or a different model)", "Reinstall Sloucher.")
    else:
        c.ok(f"{spec['file']}, checksum matches")

    if camera:
        print("\nCamera")
        from . import camera as cam
        try:
            with cam.Camera(settings.get("camera", 0)) as cap:
                frame = cap.read()
            if cam.looks_dead(frame):
                c.warn("The camera opened but the picture is black",
                       "Another app (Camera, Teams, Meet) may be using it, or the privacy shutter is closed.")
            else:
                c.ok(f"Camera {settings.get('camera', 0)}: {frame.shape[1]}x{frame.shape[0]}")
        except cam.CameraError as e:
            c.fail(str(e), "Close other apps that use the camera, and check Windows camera privacy settings.")

    if npu_test and not c.failed:
        print("\nNPU test (loading the model takes about 40 s)")
        try:
            host, r = engine.start(settings, selftest=True)
            share = f"{100 * r.npu_share:.1f}% of operators" if r.npu_share else "operators: no report"
            c.ok(f"Actually running on NPU ({r.on_npu} subgraph, {share}, {host.option[-1].rsplit(chr(92), 1)[-1]})")
            c.ok(f"{r.selftest_ms:.1f} ms per frame" if r.selftest_ms else "Ran, but no timing came back")
        except engine.NpuError as e:
            c.fail(str(e))

    print("\n" + ("Something needs fixing (see above)." if c.failed else "All good. Sloucher can run on this laptop."))
    print(f"Your settings and calibration: {paths.data_dir()}")
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(run(paths.load_settings()))
