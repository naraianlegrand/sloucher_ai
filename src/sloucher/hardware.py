"""What NPU this laptop has, and where its runtime is.

NPUs are in Windows' ComputeAccelerator device class. Its registry entries name the
device, its hardware ID and the driver version, and reading them takes well under a
millisecond (the WMI query for the same thing takes about 3 s).
"""
import glob
import json
import os
import re
import subprocess
from dataclasses import dataclass

COMPUTE_ACCELERATOR = r"SYSTEM\CurrentControlSet\Control\Class\{f01a9d53-3ff6-48d2-9f97-c8a7004be10c}"


@dataclass(frozen=True)
class Chip:
    vendor: str         # amd / intel / qualcomm
    family: str         # what picks the NPU binary and model
    name: str
    supported: bool     # by this version of Sloucher


# PCI vendor and device IDs. Only Phoenix / Hawk Point is tested so far; the rest are on the roadmap.
CHIPS = {
    ("1022", "1502"): Chip("amd", "phoenix", "AMD Ryzen 7040 / 8040 (Phoenix, Hawk Point)", True),
    ("1022", "17F0"): Chip("amd", "strix", "AMD Ryzen AI 300 (Strix, Krackan)", False),
}
VENDORS = {"1022": "amd", "8086": "intel"}


@dataclass(frozen=True)
class Npu:
    name: str
    hardware_id: str
    driver_version: str
    provider: str
    chip: Chip

    @property
    def supported(self):
        return self.chip.supported


def _chip(hardware_id, name):
    m = re.search(r"VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})", hardware_id.upper())
    if m and (m.group(1), m.group(2)) in CHIPS:
        return CHIPS[(m.group(1), m.group(2))]
    vendor = VENDORS.get(m.group(1)) if m else None
    if vendor is None and re.search(r"qualcomm|hexagon|qcom", f"{name} {hardware_id}", re.I):
        vendor = "qualcomm"
    return Chip(vendor or "unknown", "unknown", name, False)


def find_npus():
    """Every NPU Windows knows about, from the ComputeAccelerator class."""
    try:
        import winreg
    except ImportError:          # not Windows
        return []
    npus = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, COMPUTE_ACCELERATOR)
    except OSError:
        return []
    with root:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, sub) as k:
                    def val(name):
                        try:
                            return str(winreg.QueryValueEx(k, name)[0])
                        except OSError:
                            return ""
                    name, hwid = val("DriverDesc"), val("MatchingDeviceId")
                    if name or hwid:
                        npus.append(Npu(name, hwid, val("DriverVersion"), val("ProviderName"), _chip(hwid, name)))
            except OSError:
                continue            # e.g. the "Properties" key, which needs admin rights
    return npus


def main_npu():
    """The NPU to use: a supported one if there is one, else the first one found, else None."""
    npus = find_npus()
    return next((n for n in npus if n.supported), npus[0] if npus else None)


# ---------------------------------------------------------------- AMD Ryzen AI

RYZEN_AI_VERSION = "1.6.1"      # 1.8 dropped Phoenix / Hawk Point


@dataclass(frozen=True)
class RyzenAI:
    version: str
    path: str

    def xclbin(self, family, columns):
        """The NPU binary: columns "4x4" (4 of the 5 NPU columns) or "1x4" (1 column)."""
        hits = glob.glob(os.path.join(self.path, "voe-*", "xclbins", family, f"{columns}.xclbin"))
        return hits[0] if hits else None


def find_ryzen_ai():
    """Installed Ryzen AI Software folders, the version Sloucher is built for first."""
    roots = {os.environ.get("RYZEN_AI_INSTALLATION_PATH"),
             os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "RyzenAI")}
    found = []
    for root in filter(None, roots):
        if os.path.isdir(os.path.join(root, "voe-4.0-win_amd64")):
            found.append(RyzenAI(os.path.basename(root.rstrip("\\/")), root))
        for path in glob.glob(os.path.join(root, "*")):
            if glob.glob(os.path.join(path, "voe-*")):
                found.append(RyzenAI(os.path.basename(path), path))
    found.sort(key=lambda r: (r.version != RYZEN_AI_VERSION, r.version))
    return found


def ryzen_ai_pythons():
    """Python interpreters of the conda environments the Ryzen AI installer creates (ryzen-ai-<version>)."""
    home = os.path.expanduser("~")
    bases = [os.path.join(home, d) for d in ("miniforge3", "miniconda3", "anaconda3", "mambaforge")]
    bases += [os.path.join(os.environ.get("LOCALAPPDATA", ""), d) for d in ("miniforge3", "miniconda3", "anaconda3")]
    bases += [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), d) for d in ("miniforge3", "miniconda3", "anaconda3")]
    hits = []
    for base in bases:
        hits += glob.glob(os.path.join(base, "envs", "ryzen-ai-*", "python.exe"))
    hits.sort(key=lambda p: (RYZEN_AI_VERSION not in p, p))
    return hits


def check_runtime(python, timeout=90):
    """Ask an NPU Python what it has: onnxruntime version and execution providers. -> dict or None."""
    code = ("import json, onnxruntime as o, numpy; "
            "print(json.dumps({'onnxruntime': o.__version__, 'numpy': numpy.__version__, "
            "'providers': o.get_available_providers()}))")
    try:
        r = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None
