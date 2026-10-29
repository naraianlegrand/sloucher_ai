"""The messages between the app and the NPU host, over a localhost socket.

Each message: 1 byte type, 4 bytes payload length (little-endian), payload.
  F  app -> host   a frame: uint16 width, uint16 height, then height*width*3 bytes of RGB
  K  host -> app   keypoints: float32 inference ms, then 17 x (x, y, score) float32
  Q  app -> host   quit

stdlib + numpy only, so it runs in the app and in the NPU vendor's Python alike.
"""
import struct

import numpy as np

HEADER = struct.Struct("<cI")
SIZE = struct.Struct("<HH")


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return bytes(buf)


def send(sock, kind, payload=b""):
    sock.sendall(HEADER.pack(kind, len(payload)) + payload)


def recv(sock):
    kind, n = HEADER.unpack(recv_exact(sock, HEADER.size))
    return kind, recv_exact(sock, n)


def pack_frame(rgb):
    h, w = rgb.shape[:2]
    return SIZE.pack(w, h) + np.ascontiguousarray(rgb, dtype=np.uint8).tobytes()


def unpack_frame(payload):
    w, h = SIZE.unpack_from(payload)
    return np.frombuffer(payload, dtype=np.uint8, offset=SIZE.size).reshape(h, w, 3)


def pack_keypoints(kps, infer_ms):
    return np.concatenate([[infer_ms], np.asarray(kps, dtype=np.float32).reshape(-1)]).astype(np.float32).tobytes()


def unpack_keypoints(payload):
    v = np.frombuffer(payload, dtype=np.float32)
    return v[1:].reshape(17, 3).copy(), float(v[0])
