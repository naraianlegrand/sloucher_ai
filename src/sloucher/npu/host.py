"""The NPU host: loads the pose model on the NPU and turns frames into keypoints.

It runs in the NPU vendor's own Python (AMD: the Ryzen AI conda env), started by the app:

    <ryzen-ai python> -u host.py --backend amd --model M.onnx --xclbin X.xclbin --port P
    <ryzen-ai python> -u host.py --backend amd --model M.onnx --xclbin X.xclbin --selftest

Status goes to stdout as @@ lines, next to the provider's own report of where the model
runs; the app reads both. Frames and keypoints go over the socket (wire.py).
Start it with stdin closed (DEVNULL): an open stdin pipe made NPU session creation hang.

Only the standard library, numpy and the vendor's onnxruntime: no imports from the app.
"""
import argparse
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import wire  # noqa: E402
import yolo_pose  # noqa: E402


def say(*parts):
    print("@@" + " ".join(str(p) for p in parts), flush=True)


def load(args):
    if args.backend == "amd":
        import amd_vitisai
        session = amd_vitisai.open_session(args.model, args.xclbin)
    else:
        raise ValueError(f"unknown backend {args.backend}")
    inp = session.get_inputs()[0]
    _, _, h, w = inp.shape
    return session, inp.name, w, h


def infer(session, name, rgb, w, h):
    t0 = time.perf_counter()
    out = session.run(None, {name: yolo_pose.to_input(rgb)})[0]
    ms = 1000 * (time.perf_counter() - t0)
    return yolo_pose.decode(out, w, h), ms


def serve(sock, session, name, w, h):
    while True:
        try:
            kind, payload = wire.recv(sock)
        except (ConnectionError, OSError):
            return 0                            # the app went away: stop too
        if kind == b"Q":
            return 0
        if kind == b"F":
            rgb = wire.unpack_frame(payload)
            if rgb.shape[:2] != (h, w):
                say("error", f"frame is {rgb.shape[1]}x{rgb.shape[0]}, the model needs {w}x{h}")
                return 2
            kps, ms = infer(session, name, rgb, w, h)
            wire.send(sock, b"K", wire.pack_keypoints(kps, ms))


def main():
    ap = argparse.ArgumentParser(description="Sloucher NPU host")
    ap.add_argument("--backend", default="amd")
    ap.add_argument("--model", required=True)
    ap.add_argument("--xclbin", help="AMD: the NPU binary")
    ap.add_argument("--port", type=int)
    ap.add_argument("--selftest", action="store_true", help="load, run a few frames, report, exit")
    args = ap.parse_args()

    say("loading", os.path.basename(args.model))
    try:
        session, name, w, h = load(args)
    except Exception as e:                      # the NPU has no free columns, a missing file, ...
        say("error", f"{type(e).__name__}: {e}".replace("\n", " ")[:400])
        return 3
    say("input", w, h)
    say("ready")

    if args.selftest:
        blank = np.zeros((h, w, 3), dtype=np.uint8)
        times = [infer(session, name, blank, w, h)[1] for _ in range(5)]
        say("selftest", f"{sorted(times)[2]:.1f}")
        return 0

    sock = socket.create_connection(("127.0.0.1", args.port))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    try:
        return serve(sock, session, name, w, h)
    finally:
        sock.close()


if __name__ == "__main__":
    sys.exit(main())
