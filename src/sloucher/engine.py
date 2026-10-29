"""The app's side of the NPU: finds the runtime, starts the NPU host, sends frames, gets keypoints.

NPU-only: the host's output must show the model actually running on the NPU, or the
engine refuses to start. On AMD it tries 4 NPU columns first and then 1 (room for Windows
Studio Effects), never the CPU.
"""
import logging
import os
import re
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, field

from . import hardware, paths
from .npu import wire

log = logging.getLogger(__name__)

OPS_RE = re.compile(r"No\. of Operators :\s+CPU\s+(\d+)\s+NPU\s+(\d+)(?:\s+VITIS_EP_CPU\s+(\d+))?")
SUBGRAPH_RE = re.compile(r"No\. of Subgraphs :\s+NPU\s+(\d+)\s+Actually running on NPU\s+(\d+)")
LOAD_TIMEOUT = 180      # s; YOLOv8n-pose takes ~35-50 s to load on the NPU, every start


class NpuError(RuntimeError):
    """Something a person can act on; the message says what."""


@dataclass
class Plan:
    """How to run the model on this laptop's NPU."""
    npu: hardware.Npu
    python: str
    model: str
    backend: str
    options: list = field(default_factory=list)     # one entry per attempt, best first

    def command(self, option, *extra):
        return [self.python, "-u", os.path.join(paths.npu_dir(), "host.py"),
                "--backend", self.backend, "--model", self.model, *option, *extra]


def plan(settings):
    """Work out the NPU, runtime and model, or raise NpuError saying what's missing."""
    npu = hardware.main_npu()
    if npu is None:
        raise NpuError("No NPU found. Sloucher needs a laptop with an NPU (AMD Ryzen 7040 / 8040 for now).")
    if not npu.supported:
        raise NpuError(f"This laptop's NPU ({npu.chip.name}) isn't supported yet. "
                       "Sloucher supports AMD Ryzen 7040 / 8040 (Phoenix, Hawk Point) for now.")
    spec = paths.manifest()["pose"]
    model = paths.model_file(spec["file"])
    if model is None:
        raise NpuError(f"The pose model ({spec['file']}) is missing. Reinstall Sloucher.")

    if npu.chip.vendor == "amd":
        installs = hardware.find_ryzen_ai()
        if not installs:
            raise NpuError(f"AMD Ryzen AI Software {hardware.RYZEN_AI_VERSION} isn't installed. "
                           "Install it once, then start Sloucher again (see docs/INSTALL.md).")
        python = settings.get("npu_python") or next(iter(hardware.ryzen_ai_pythons()), None)
        if not python or not os.path.exists(python):
            raise NpuError(f"Can't find the Ryzen AI Python (the ryzen-ai-{hardware.RYZEN_AI_VERSION} environment). "
                           "Reinstall Ryzen AI Software, or set npu_python in settings.json.")
        columns = {"auto": ["4x4", "1x4"], "4x4": ["4x4"], "1x4": ["1x4"]}.get(settings.get("xclbin", "auto"), ["4x4", "1x4"])
        options = []
        for c in columns:
            xclbin = installs[0].xclbin(npu.chip.family, c)
            if xclbin:
                options.append(["--xclbin", xclbin])
        if not options:
            raise NpuError(f"Ryzen AI {installs[0].version} has no NPU binary for {npu.chip.name}.")
        return Plan(npu, python, model, "amd", options)
    raise NpuError(f"No backend for {npu.chip.vendor} NPUs yet.")


@dataclass
class Report:
    """What the host said while loading."""
    ready: bool = False
    on_npu: int = 0                 # subgraphs actually running on the NPU
    ops: tuple = None               # (cpu, npu, vitis_ep_cpu)
    input_wh: tuple = None
    error: str = None
    selftest_ms: float = None
    option: list = None

    @property
    def npu_share(self):
        return None if not self.ops else self.ops[1] / sum(self.ops)


class Host:
    """One NPU host process: start, check it's on the NPU, then infer frame by frame."""

    def __init__(self, plan_, option):
        self.plan, self.option = plan_, option
        self.proc = self.sock = None
        self.report = Report(option=option)
        self._ready = threading.Event()
        self._exited = threading.Event()

    def start(self, selftest=False):
        listener = None
        extra = ["--selftest"]
        if not selftest:
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            extra = ["--port", str(listener.getsockname()[1])]
        cmd = self.plan.command(self.option, *extra)
        log.info("NPU host: %s", subprocess.list2cmdline(cmd))
        # stdin closed on purpose: an open stdin pipe hangs NPU session creation
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=paths.data_dir(),
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        threading.Thread(target=self._read, daemon=True).start()
        if listener:
            threading.Thread(target=self._accept, args=(listener,), daemon=True).start()
        return self

    def _accept(self, listener):
        listener.settimeout(LOAD_TIMEOUT + 30)
        try:
            self.sock, _ = listener.accept()
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(10)
        except OSError:
            pass
        finally:
            listener.close()

    def _read(self):
        r = self.report
        for line in self.proc.stdout:
            line = line.rstrip()
            log.debug("host> %s", line)
            if m := OPS_RE.search(line):
                r.ops = tuple(int(g or 0) for g in m.groups())
            elif m := SUBGRAPH_RE.search(line):
                r.on_npu = int(m.group(2))
            elif line.startswith("@@input"):
                r.input_wh = tuple(int(v) for v in line.split()[1:3])
            elif line.startswith("@@ready"):
                r.ready = True
                self._ready.set()
            elif line.startswith("@@selftest"):
                r.selftest_ms = float(line.split()[1])
            elif line.startswith("@@error"):
                r.error = line.split(" ", 1)[1] if " " in line else "unknown error"
        self.proc.wait()
        log.info("NPU host exited with code %s", self.proc.returncode)
        self._exited.set()
        self._ready.set()

    def wait_ready(self, timeout=LOAD_TIMEOUT):
        self._ready.wait(timeout)
        if self.report.ready and not self.report.on_npu:
            time.sleep(2)           # the provider's report can trail the ready line by a moment
        return self.report

    def wait_exit(self, timeout=60):
        self._exited.wait(timeout)
        return self.report

    def connected(self, timeout=30):
        end = time.monotonic() + timeout
        while self.sock is None and time.monotonic() < end and not self._exited.is_set():
            time.sleep(0.05)
        return self.sock is not None

    def infer(self, rgb):
        """HxWx3 uint8 RGB at the model's size -> ((17, 3) keypoints, inference ms)."""
        wire.send(self.sock, b"F", wire.pack_frame(rgb))
        kind, payload = wire.recv(self.sock)
        if kind != b"K":
            raise ConnectionError(f"unexpected message {kind!r}")
        return wire.unpack_keypoints(payload)

    def stop(self):
        if self.sock:
            try:
                wire.send(self.sock, b"Q")
            except OSError:
                pass
            self.sock.close()
            self.sock = None
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def start(settings, selftest=False, progress=None):
    """Start an NPU host that is proven to run on the NPU. -> (Host, Report). Raises NpuError."""
    p = plan(settings)
    tried = []
    for option in p.options:
        name = os.path.splitext(os.path.basename(option[-1]))[0]
        if progress:
            progress(f"Warming up the NPU ({name}, about 40 s)")
        host = Host(p, option).start(selftest=selftest)
        report = host.wait_ready()
        if selftest:
            report = host.wait_exit()
        if report.ready and report.on_npu and (selftest or host.connected()):
            log.info("On the NPU with %s: ops %s", name, report.ops)
            return host, report
        host.stop()
        why = report.error or ("loaded, but not on the NPU" if report.ready else "no answer")
        log.warning("NPU host with %s failed: %s", name, why)
        tried.append(f"{name}: {why}")
    raise NpuError("The model couldn't run on the NPU (" + "; ".join(tried) + "). If a video call or the Camera "
                   "app is using Windows Studio Effects, close it and try again.")


class Engine:
    """Runs a Host in the background and keeps the latest result; safe to call from one worker thread."""

    def __init__(self, settings):
        self.settings = settings
        self.host = None
        self.report = None

    def open(self, progress=None):
        self.host, self.report = start(self.settings, progress=progress)
        return self.report

    def infer(self, rgb):
        return self.host.infer(rgb)

    def close(self):
        if self.host:
            self.host.stop()
            self.host = None
