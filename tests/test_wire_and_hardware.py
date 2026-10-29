import socket
import threading

import numpy as np

from sloucher import engine, hardware
from sloucher.npu import wire


def test_frame_and_keypoints_round_trip():
    a, b = socket.socketpair()
    rgb = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    kps = np.random.default_rng(1).random((17, 3)).astype(np.float32)
    try:
        sender = threading.Thread(target=wire.send, args=(a, b"F", wire.pack_frame(rgb)))
        sender.start()
        kind, payload = wire.recv(b)
        sender.join()
        assert kind == b"F" and np.array_equal(wire.unpack_frame(payload), rgb)

        wire.send(b, b"K", wire.pack_keypoints(kps, 12.5))
        kind, payload = wire.recv(a)
        got, ms = wire.unpack_keypoints(payload)
        assert kind == b"K" and ms == 12.5 and np.allclose(got, kps)
    finally:
        a.close()
        b.close()


def test_chip_ids():
    assert hardware._chip(r"PCI\VEN_1022&DEV_1502", "NPU Compute Accelerator Device").supported
    strix = hardware._chip(r"PCI\VEN_1022&DEV_17F0", "NPU Compute Accelerator Device")
    assert strix.vendor == "amd" and not strix.supported
    assert hardware._chip(r"PCI\VEN_8086&DEV_7D1D", "Intel(R) AI Boost").vendor == "intel"
    assert hardware._chip(r"ACPI\QCOM0D0A", "Qualcomm(R) Hexagon(TM) NPU").vendor == "qualcomm"


def test_provider_report_parsing():
    ops = engine.OPS_RE.search("[Vitis AI EP] No. of Operators :   CPU    28    NPU  1042 VITIS_EP_CPU    10 ")
    sub = engine.SUBGRAPH_RE.search("[Vitis AI EP] No. of Subgraphs :   NPU     1 Actually running on NPU      1")
    assert tuple(int(g) for g in ops.groups()) == (28, 1042, 10)
    assert int(sub.group(2)) == 1
