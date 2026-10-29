"""The webcam, read slowly: posture doesn't change 30 times a second, and 2 frames a second keeps the app near 1% CPU.

When another app (Camera, Teams, Meet) holds the camera, Windows can still hand out frames, but they're
black or noise. looks_dead() catches the black ones so the app can say so instead of seeing nobody.
"""
import cv2
import numpy as np


class CameraError(RuntimeError):
    pass


class Camera:
    def __init__(self, index=0):
        self.index = index
        self.cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    def open(self):
        self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            raise CameraError(f"Couldn't open camera {self.index}")
        return self

    def read(self):
        """-> HxWx3 BGR frame."""
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise CameraError("The camera stopped sending frames")
        return frame

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def looks_dead(frame):
    """A black frame: the lens is covered, or another app holds the camera."""
    small = frame[::8, ::8]
    return float(small.mean()) < 4 and float(small.std()) < 4


def to_model(frame, w, h):
    """BGR camera frame -> RGB at the model's input size (uint8)."""
    if frame.shape[1] != w or frame.shape[0] != h:
        frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(frame[:, :, ::-1])
