"""The eyes: camera -> NPU -> posture call, on a background thread, twice a second.

The model never runs here: each frame goes to the NPU host (engine.py), and only 17 keypoints come
back. Between frames the thread sleeps, which is most of why the whole app stays near 1% of the CPU.
While the screen is locked the camera is closed (its light goes off) and the NPU stays loaded.
"""
import logging
import threading
import time

from . import camera, engine, paths, posture

log = logging.getLogger(__name__)

FPS = 2                 # posture changes slowly; 2 fps keeps the whole app near 1% CPU
DEAD_FRAMES = 6         # black frames in a row before saying the camera is in use


class Vision(threading.Thread):
    """Camera -> NPU host -> posture, at FPS. Everything it learns goes to `events`, tagged with `session`.

    Pause stops it, Resume starts a new one: the app ignores anything still arriving from an old session.
    """

    def __init__(self, settings, events, session):
        super().__init__(daemon=True)
        self.settings, self.events, self.session = settings, events, session
        self.halt = threading.Event()
        self.want_calibration = threading.Event()
        self.camera_off = threading.Event()        # set while the screen is locked

    def emit(self, kind, *data):
        if not self.halt.is_set():
            self.events.put(("vision", self.session, kind, *data))

    def run(self):
        eng = engine.Engine(self.settings)
        try:
            # Pausing during the ~40 s load cancels it at once (halt), so a quick Resume doesn't load twice
            report = eng.open(progress=lambda text: self.emit("loading", text), cancel=self.halt)
            self.emit("ready", report)
            w, h = report.input_wh
            post = posture.Posture(paths.calibration_file(), FPS, self.settings.get("strictness", posture.NORMAL))
            self.emit("calibrated?", post.calibrated)
            with camera.Camera(self.settings.get("camera", 0)) as cam:
                self.loop(eng, cam, post, w, h)
        except engine.Cancelled:
            log.info("NPU loading cancelled")
        except engine.NpuError as e:
            self.emit("fatal", str(e))
        except camera.CameraError as e:
            self.emit("fatal", f"{e}. Close other apps that use the camera, then choose Resume.")
        except (ConnectionError, OSError) as e:
            if not self.halt.is_set():
                log.exception("NPU host connection lost")
                self.emit("fatal", f"The NPU host stopped ({e}). Choose Resume to start it again.")
        finally:
            eng.close()
            log.info("Camera and NPU released (session %s)", self.session)

    def loop(self, eng, cam, post, w, h):
        dead = 0
        next_t = time.monotonic()
        while not self.halt.is_set():
            # Sleeping between frames is the main CPU saving
            self.halt.wait(max(0.0, next_t - time.monotonic()))
            next_t = max(next_t + 1 / FPS, time.monotonic())
            if self.halt.is_set():
                break
            if self.camera_off.is_set():
                # Screen locked: the camera light goes off; the NPU stays loaded for a quick start on unlock
                cam.close()
                log.info("Camera off while the screen is locked")
                while self.camera_off.is_set() and not self.halt.is_set():
                    self.halt.wait(0.5)
                if self.halt.is_set():
                    break
                for attempt in range(5):
                    try:
                        cam.open()
                        break
                    except camera.CameraError:
                        if attempt == 4:
                            raise
                        self.halt.wait(1.0)
                log.info("Camera back on")
                next_t = time.monotonic()
                continue
            frame = cam.read()
            dead = dead + 1 if camera.looks_dead(frame) else 0
            if dead == DEAD_FRAMES:
                self.emit("camera_dead")
            if self.want_calibration.is_set():
                self.want_calibration.clear()
                post.calibrate()
            post.set_strictness(self.settings.get("strictness", posture.NORMAL))     # the slider, live
            kps, ms = eng.infer(camera.to_model(frame, w, h))
            state, alert = post.update(kps, (frame.shape[1], frame.shape[0]))
            self.emit("frame", int((kps[:, 0] >= 0).sum()), state, alert, ms)

    def stop(self):
        self.halt.set()
