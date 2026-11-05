"""The tray app: a soft screen-edge glow, a small pill and a gentle chime when you've slouched.

- A background thread reads the camera at 2 fps, sends each frame to the NPU host and turns
  the keypoints into a posture call. The UI thread only draws, and stays idle between frames.
- Slouch, lean in or look down for most of 30 s: the screen edges glow and a "Sit up" pill
  appears; sit up and it fades. One soft chime each time the glow comes on.
- Once an hour in the chair: the screen flashes blue and a card says "Time for a 30 s walk",
  with "I walked" and "Snooze". Back too early: "Not done yet: 18 s left". Locking the screen
  for 30 s or more counts as a walk.
- Every minute in the chair adds a row to your stats (numbers only): see stats.py and the Stats window.
- Tray menu: my stats, calibrate, pause (camera and NPU off), sound, start with Windows, quit.
"""
import ctypes
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import winsound

import pystray

from . import APP_NAME, breaks, camera, engine, glass, icon, paths, posture, stats, statswindow

log = logging.getLogger(__name__)

FPS = 2                 # posture changes slowly; 2 fps keeps the whole app near 1% CPU
PRESENT_KPS = 4         # keypoints needed to count as someone in the chair
CHIME_GAP = 10          # s between two chimes, so a flickering alert never chimes twice for one slouch
SNOOZE_S = 10 * 60      # "Snooze" on the walk card
LOCK_CHECK_S = 2        # how often to check whether the screen is locked
DEAD_FRAMES = 6         # black frames in a row before saying the camera is in use

YELLOW = "#FFD60A"      # alerts
BLUE = "#64D2FF"        # the walk
GREEN = "#30D158"       # done, calibrated
RED = "#FF453A"         # problems
INK = "#111111"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


# ---------------------------------------------------------------- the eyes (background thread)

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
            post = posture.Posture(paths.calibration_file(), FPS)
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
            kps, ms = eng.infer(camera.to_model(frame, w, h))
            state, alert = post.update(kps, (frame.shape[1], frame.shape[0]))
            self.emit("frame", int((kps[:, 0] >= 0).sum()), state, alert, ms)

    def stop(self):
        self.halt.set()


# ---------------------------------------------------------------- on-screen bits

def click_through(win):
    """No focus, no taskbar button, and clicks pass through to the window below."""
    GWL_EXSTYLE = -20
    flags = 0x80000 | 0x20 | 0x80 | 0x08000000     # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
    win.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | flags)


def overlay(root, x, y, w, h, bg):
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.0)
    win.configure(bg=bg)
    win.geometry(f"{w}x{h}+{x}+{y}")
    click_through(win)
    return win


class Glow:
    """A soft glow around the screen edges: 3 layers of edge strips, fading in and out."""
    LAYERS = ((3, 0.60), (9, 0.30), (18, 0.12))   # thickness px, alpha at full strength

    def __init__(self, root):
        self.root = root
        self.level, self.target = 0.0, 0.0
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.strips = []
        for t, a in self.LAYERS:
            for x, y, w, h in ((0, 0, sw, t), (0, sh - t, sw, t), (0, 0, t, sh), (sw - t, 0, t, sh)):
                self.strips.append((overlay(root, x, y, w, h, YELLOW), a))
        self.animating = False

    def show(self):
        self._go(1.0)

    def hide(self):
        self._go(0.0)

    def _go(self, target):
        self.target = target
        if not self.animating:
            self.animating = True
            self._step()

    def _step(self):
        # ~0.6 s fade; timers run only while fading, so an idle glow costs nothing
        self.level += max(-0.08, min(0.08, self.target - self.level))
        for win, a in self.strips:
            win.attributes("-alpha", a * self.level)
        if abs(self.level - self.target) > 1e-3:
            self.root.after(40, self._step)
        else:
            self.animating = False


class Pill:
    """A small rounded label at the top centre of the screen."""
    KEY = "#010203"   # transparent colour around the rounded shape

    def __init__(self, root):
        self.root = root
        self.win = overlay(root, 0, 0, 10, 10, self.KEY)
        self.win.attributes("-transparentcolor", self.KEY)
        self.canvas = tk.Canvas(self.win, bg=self.KEY, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.hide_job = None

    def show(self, text, colour, seconds=None):
        font = ("Segoe UI Semibold", 12)
        probe = self.canvas.create_text(0, 0, text=text, font=font, anchor="nw")
        x0, _, x1, _ = self.canvas.bbox(probe)
        self.canvas.delete("all")
        w, h = (x1 - x0) + 64, 40
        r = h // 2
        self.canvas.configure(width=w, height=h)
        c = self.canvas
        c.create_oval(0, 0, h, h, fill=INK, outline="")
        c.create_oval(w - h, 0, w, h, fill=INK, outline="")
        c.create_rectangle(r, 0, w - r, h, fill=INK, outline="")
        c.create_oval(18, h / 2 - 5, 28, h / 2 + 5, fill=colour, outline="")
        c.create_text(40, h / 2, text=text, font=font, fill="#F7F7F5", anchor="w")
        self.win.geometry(f"{w}x{h}+{(self.root.winfo_screenwidth() - w) // 2}+28")
        self.win.attributes("-alpha", 0.94)
        if self.hide_job:
            self.root.after_cancel(self.hide_job)
            self.hide_job = None
        if seconds:
            self.hide_job = self.root.after(int(seconds * 1000), self.hide)

    def hide(self):
        self.win.attributes("-alpha", 0.0)
        self.hide_job = None


class CalibrateWindow:
    """The one-time welcome: sit tall, click Calibrate."""

    def __init__(self, root, on_calibrate):
        self.win = tk.Toplevel(root)
        self.win.title(f"Welcome to {APP_NAME}")
        self.win.configure(bg="#000000", padx=36, pady=30)
        self.win.resizable(False, False)
        self.win.attributes("-topmost", True)
        try:
            self.win.iconbitmap(paths.asset("icon.ico"))
        except tk.TclError:
            pass
        tk.Label(self.win, text="Sit up tall.", font=("Segoe UI Black", 22), fg="#F7F7F5", bg="#000000").pack(anchor="w")
        tk.Label(self.win, text="Look at your screen as you normally would, then click Calibrate.\n"
                                "It takes 3 seconds, and it's how Sloucher learns your good posture.",
                 font=("Segoe UI", 11), fg="#A3A3A0", bg="#000000", justify="left").pack(anchor="w", pady=(8, 22))
        row = tk.Frame(self.win, bg="#000000")
        row.pack(anchor="w")
        tk.Button(row, text="Calibrate", font=("Segoe UI Semibold", 11), bg=YELLOW, fg="#000000", relief="flat",
                  activebackground="#FFE45C", padx=18, pady=6, cursor="hand2",
                  command=lambda: (on_calibrate(), self.close())).pack(side="left")
        tk.Button(row, text="Later", font=("Segoe UI", 11), bg="#000000", fg="#A3A3A0", relief="flat",
                  activebackground="#1C1C1C", padx=14, pady=6, cursor="hand2", command=self.close).pack(side="left", padx=8)
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        self.win.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
        self.win.focus_force()

    def close(self):
        self.win.destroy()


class _WtsInfoLevel1(ctypes.Structure):
    _fields_ = [("SessionId", ctypes.c_ulong), ("SessionState", ctypes.c_int), ("SessionFlags", ctypes.c_long),
                ("WinStationName", ctypes.c_wchar * 33), ("UserName", ctypes.c_wchar * 21),
                ("DomainName", ctypes.c_wchar * 18), ("LogonTime", ctypes.c_longlong),
                ("ConnectTime", ctypes.c_longlong), ("DisconnectTime", ctypes.c_longlong),
                ("LastInputTime", ctypes.c_longlong), ("CurrentTime", ctypes.c_longlong),
                ("Counters", ctypes.c_ulong * 6)]


class _WtsInfoEx(ctypes.Structure):
    _fields_ = [("Level", ctypes.c_ulong), ("Data", _WtsInfoLevel1)]


def screen_locked():
    """True while this Windows session is locked (Win+L), also once the display has turned off.

    Asks the session itself (WTSSessionInfoEx). Checking the input desktop instead only works while
    the lock screen is showing: once the screen goes black it reads "unlocked" again (seen in testing).
    """
    wts = ctypes.windll.wtsapi32
    buf, size = ctypes.c_void_p(), ctypes.c_ulong()
    if not wts.WTSQuerySessionInformationW(None, ctypes.c_ulong(0xFFFFFFFF), 25, ctypes.byref(buf), ctypes.byref(size)):
        return False                    # can't tell: assume unlocked, the camera still decides
    try:
        info = ctypes.cast(buf, ctypes.POINTER(_WtsInfoEx)).contents
        return info.Level == 1 and info.Data.SessionFlags == 0          # WTS_SESSIONSTATE_LOCK
    finally:
        wts.WTSFreeMemory(buf)


def work_area():
    """(left, top, right, bottom) of the primary screen without the taskbar."""
    r = (ctypes.c_long * 4)()
    if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, r, 0):     # SPI_GETWORKAREA
        return tuple(r)
    return None


class Flash:
    """Two soft blue pulses over the whole screen, click-through, then gone (about 1.2 s)."""
    PEAK = 0.28
    FRAMES = [0.33, 0.66, 1.0, 0.66, 0.33, 0.0, 0.0, 0.33, 0.66, 1.0, 0.66, 0.33, 0.0]

    def __init__(self, root):
        self.root = root
        self.win = None

    def play(self):
        if self.win is not None:
            return
        self.win = overlay(self.root, 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight(), BLUE)
        self._step(0)

    def _step(self, i):
        if i >= len(self.FRAMES):
            self.win.destroy()
            self.win = None
            return
        self.win.attributes("-alpha", self.PEAK * self.FRAMES[i])
        self.root.after(90, self._step, i + 1)


class WalkCard:
    """The walk reminder: bottom right, stays until you walk, tick "I walked" or snooze.

    Clickable, but it never takes the keyboard from the window you're typing in.
    """

    def __init__(self, root, on_walked, on_snooze):
        self.root, self.on_walked, self.on_snooze = root, on_walked, on_snooze
        self.win = None

    @property
    def showing(self):
        return self.win is not None

    def show(self, title, detail):
        if self.win is None:
            self._build()
        self.title.configure(text=title)
        self.detail.configure(text=detail)
        self._place()

    def _build(self):
        self.win = win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=glass.GLASS, padx=22, pady=18)
        head = tk.Frame(win, bg=glass.GLASS)
        head.pack(anchor="w")
        dot = tk.Canvas(head, width=12, height=12, bg=glass.GLASS, highlightthickness=0)
        dot.create_oval(1, 1, 11, 11, fill=BLUE, outline="")
        dot.pack(side="left", padx=(0, 10))
        self.title = tk.Label(head, font=("Segoe UI Semibold", 13), fg="#F7F7F5", bg=glass.GLASS)
        self.title.pack(side="left")
        self.detail = tk.Label(win, font=("Segoe UI", 10), fg="#C8C8C4", bg=glass.GLASS, justify="left")
        self.detail.pack(anchor="w", pady=(4, 12))
        row = tk.Frame(win, bg=glass.GLASS)
        row.pack(anchor="w")
        self.walked_btn = tk.Button(row, text="\u2713  I walked", font=("Segoe UI Semibold", 11), bg=BLUE,
                                    fg="#000000", relief="flat", activebackground="#9BE3FF", padx=14, pady=5,
                                    cursor="hand2", command=self.on_walked)
        self.walked_btn.pack(side="left")
        self.snooze_btn = tk.Button(row, text="Snooze 10 min", font=("Segoe UI", 11), bg=glass.TILE, fg="#F7F7F5",
                                    relief="flat", activebackground="#3A3A38", activeforeground="#F7F7F5",
                                    padx=12, pady=5, cursor="hand2", command=self.on_snooze)
        self.snooze_btn.pack(side="left", padx=(8, 0))
        # No focus and no taskbar button, but (unlike the glow) clicks land on it
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80 | 0x08000000)    # TOOLWINDOW | NOACTIVATE
        if glass.apply(win, "acrylic"):           # frosted glass and rounded corners (Windows 11)
            self.walked_btn.configure(bg=glass.tint(BLUE, 0x50))      # Acrylic is lighter than Mica
            dot.itemconfigure(1, fill=glass.tint(BLUE, 0x50))

    def _place(self):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        area = work_area() or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.win.geometry(f"+{area[2] - w - 24}+{area[3] - h - 24}")

    def hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None


# ---------------------------------------------------------------- start with Windows

def autostart_command():
    if paths.frozen():
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw if os.path.exists(pythonw) else sys.executable}" -m sloucher'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


# ---------------------------------------------------------------- the app

class App:
    def __init__(self, settings):
        self.settings = settings
        self.events = queue.Queue()        # from the vision thread and the tray thread
        self.root = tk.Tk()
        self.root.withdraw()
        self.glow = Glow(self.root)
        self.pill = Pill(self.root)
        self.flash = Flash(self.root)
        self.card = WalkCard(self.root, on_walked=lambda: self.on_menu("walked"),
                             on_snooze=lambda: self.on_menu("snooze"))
        self.stats = stats.Recorder(paths.stats_dir())
        self.stats_window = None
        self.vision = None
        self.session = 0                   # which Vision's events count; older ones are ignored
        self.coach = self.new_coach()
        self.paused = False
        self.alerting = False
        self.last_chime = -1e9
        self.walk_due = False
        self.locked_since = None           # monotonic time the screen was locked, while it is
        self.last_lock_s = 0.0             # how long the last lock lasted
        self.last_lock_check = 0.0
        self.present = None                # last presence, to log comings and goings
        self.welcome = None
        self.quitting = False
        self.status = "Starting..."
        self.icons = {}
        self.tray_key = None
        self.tray = pystray.Icon(APP_NAME, self.tray_image("away", False), APP_NAME, menu=pystray.Menu(
            pystray.MenuItem(lambda _: self.status, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Stats",lambda: self.events.put(("menu", "stats")), default=True),
            pystray.MenuItem("Calibrate (sit up tall first)", lambda: self.events.put(("menu", "calibrate"))),
            pystray.MenuItem(lambda _: "Resume" if self.paused else "Pause",
                             lambda: self.events.put(("menu", "pause"))),
            pystray.MenuItem("Sound", lambda: self.events.put(("menu", "sound")),
                             checked=lambda _: self.settings["sound"]),
            pystray.MenuItem("Start with Windows", lambda: self.events.put(("menu", "autostart")),
                             checked=lambda _: autostart_enabled()),
            pystray.MenuItem("Open settings folder", lambda: self.events.put(("menu", "folder"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.events.put(("menu", "quit"))),
        ))

    def new_coach(self):
        return breaks.BreakCoach(sit_limit=self.settings["sit_minutes"] * 60, break_s=self.settings["break_seconds"])

    # -- tray and sound

    def tray_image(self, state, slouched):
        key = (state, slouched)
        if key not in self.icons:
            self.icons[key] = icon.draw(64, icon.STATES[state], slouched)
        return self.icons[key]

    def set_tray(self, state, slouched=False, status=None):
        if status:
            self.status = status
        key = (state, slouched, self.status)
        if key == self.tray_key:
            return          # nothing changed: leave the tray alone
        self.tray_key = key
        self.tray.icon = self.tray_image(state, slouched)
        self.tray.title = f"{APP_NAME}: {self.status}"
        self.tray.update_menu()

    def chime(self, force=False):
        now = time.monotonic()
        if self.settings["sound"] and (force or now - self.last_chime >= CHIME_GAP):
            self.last_chime = now
            winsound.PlaySound(paths.asset("chime.wav"), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def notify(self, title, message):
        try:
            self.tray.notify(message, title)
        except Exception:
            log.debug("notification failed", exc_info=True)

    # -- lifecycle

    def run(self):
        self.tray.run_detached()
        self.start_vision()
        self.root.after(200, self.poll)
        self.root.mainloop()

    def start_vision(self):
        self.session += 1
        self.vision = Vision(self.settings, self.events, self.session)
        if self.locked_since is not None:
            self.vision.camera_off.set()
        self.vision.start()
        self.set_tray("away", status="Warming up the NPU...")

    def stop_vision(self):
        if self.vision:
            self.vision.stop()
            self.vision = None

    def poll(self):
        while not self.events.empty():
            self.handle(*self.events.get())
        if self.quitting:
            return
        now = time.monotonic()
        if now - self.last_lock_check >= LOCK_CHECK_S:
            self.last_lock_check = now
            self.check_lock(now)
        self.root.after(250, self.poll)

    def check_lock(self, now):
        locked = screen_locked()
        if locked and self.locked_since is None:
            self.locked_since = now
            self.stats.gap()
            if self.vision:
                self.vision.camera_off.set()
            log.info("Screen locked")
        elif not locked and self.locked_since is not None:
            self.last_lock_s = now - self.locked_since
            self.locked_since = None
            self.stats.gap()
            if self.vision:
                self.vision.camera_off.clear()
            log.info("Screen unlocked after %.0f s", self.last_lock_s)

    def handle(self, kind, *data):
        if kind == "vision":
            session, kind, *data = data
            if self.vision is None or session != self.session:
                return          # from a session that was paused or replaced: ignore
        if kind != "frame":
            log.info("event %s %s", kind, data)
        if kind == "frame":
            self.on_frame(*data)
        elif kind == "loading":
            self.pill.show(data[0], BLUE)
        elif kind == "ready":
            r = data[0]
            self.pill.show("Watching your posture, on the NPU", GREEN, 4)
            self.set_tray("good", status=f"Watching (on the NPU, {100 * (r.npu_share or 0):.0f}% of the model)")
        elif kind == "calibrated?":
            if not data[0]:
                self.welcome = CalibrateWindow(self.root, lambda: self.on_menu("calibrate"))
        elif kind == "camera_dead":
            self.notify("The camera picture is black", "Another app may be using the camera, or the lens is covered.")
        elif kind == "fatal":
            self.stop_vision()
            self.alerting = False
            self.glow.hide()
            self.pill.show("Sloucher stopped: see the tray", RED, 8)
            self.set_tray("away", status="Stopped")
            self.paused = True
            self.notify(f"{APP_NAME} stopped", data[0])
        elif kind == "menu":
            self.on_menu(data[0])

    def on_frame(self, visible, state, alert, ms):
        now = time.monotonic()
        # While locked the camera may be blocked or see junk: you count as away
        present = visible >= PRESENT_KPS and self.locked_since is None
        if present != self.present:
            if self.present is not None:
                log.info("%s (%s)", "Back in the chair" if present else "Left the chair", state)
            self.present = present
        event = self.coach.update(now, present)
        if event:
            self.on_break_event(event)

        if state == "calibrating":
            self.pill.show("Calibrating: sit up tall, hold still", GREEN)
        elif state == "calibrated":
            self.pill.show("Calibrated. Your good posture is saved.", GREEN, 4)
            return
        elif state == "calibration_failed":
            self.pill.show("Calibration failed: face and shoulders in view?", RED, 6)
            return

        bad = state in ("slouch", "lean-in")
        if alert and bad and not self.alerting:
            self.alerting = True
            self.glow.show()
            self.pill.show("Sit up" if state == "slouch" else "Lean back a little", YELLOW)
            self.chime()
        elif self.alerting and not bad:
            # Sitting up clears it at once: quick, rewarding feedback
            self.alerting = False
            self.glow.hide()
            self.pill.hide()
        if state != "calibrating":
            self.stats.frame(now, present, state, self.alerting)

        if not present:
            self.set_tray("away", status="Away from the desk")
        elif self.walk_due:
            self.set_tray("walk", status="Time for a 30 s walk")
        elif self.alerting:
            self.set_tray("alert", True, status="Sit up")
        elif bad:
            self.set_tray("slouch", True, status="Slouching" if state == "slouch" else "Leaning in")
        elif state == "uncalibrated":
            self.set_tray("away", status="Needs calibration (tray menu)")
        elif state == "calibrating":
            self.set_tray("away", status="Calibrating")
        else:
            mins = int(self.coach.sitting(time.monotonic()) // 60)
            self.set_tray("good", status=f"Good posture · sitting {mins} min")

    def on_break_event(self, event):
        kind = event[0]
        log.info("walk event %s", event)
        if kind in ("walk_due", "walk_nudge"):
            self.walk_due = True
            if kind == "walk_due":
                self.stats.walk_due()
            self.flash.play()
            self.card.show("Time for a 30 s walk",
                           f"Sitting {int(self.coach.sitting(time.monotonic()) // 60)} min. "
                           "I'll see you leave the chair,\nor tick it if you walked and I missed it.")
            self.chime(force=True)
        elif kind == "not_done":
            self.card.show(f"Not done yet: {event[1]} s left", "Get up again and walk a little longer.")
            self.pill.show(f"Not done yet: {event[1]} s left", BLUE, 8)
            self.chime(force=True)
        elif kind in ("break_done", "break_taken"):
            # Away 30 s or more, reminded or on your own. A lock that long is why you were away.
            self.walk_done("locked" if self.last_lock_s >= self.coach.break_s else "seen", event[1])

    def walk_done(self, how, sat_s):
        """A break, however it was noticed. Only a reminder that was due gets the "Nice!"."""
        self.stats.walk_done(how, sat_s)
        self.last_lock_s = 0.0
        self.card.hide()
        if self.walk_due:
            self.walk_due = False
            self.pill.show("Break done. Nice!", GREEN, 4)

    def on_menu(self, item):
        if item == "calibrate":
            if self.paused:
                self.on_menu("pause")
            if self.vision:
                self.vision.want_calibration.set()
                self.pill.show("Calibrating soon: sit up tall", GREEN)
        elif item == "pause":
            self.paused = not self.paused
            if self.paused:
                self.stop_vision()
                self.alerting = False
                self.glow.hide()
                self.pill.hide()
                self.stats.gap()
                self.stats.flush()
                self.set_tray("away", status="Paused (camera and NPU off)")
            else:
                # A pause isn't a break (#3): the sitting clock carries on
                self.coach.resume()
                self.start_vision()
        elif item == "walked":
            now = time.monotonic()
            sat = self.coach.sitting(now)
            self.coach.walked(now)
            log.info("walk ticked (I walked) after %.0f s sitting", sat)
            self.walk_done("ticked", sat)
        elif item == "snooze":
            self.coach.snooze(time.monotonic(), SNOOZE_S)
            log.info("walk snoozed for %d min", SNOOZE_S // 60)
            self.stats.snoozed()
            self.card.hide()
            self.pill.show("OK, I'll remind you in 10 min", BLUE, 4)
        elif item == "stats":
            if self.stats_window and self.stats_window.open:
                self.stats_window.lift()
            else:
                self.stats_window = statswindow.StatsWindow(self.root, self.stats)
        elif item == "sound":
            self.settings["sound"] = not self.settings["sound"]
            paths.save_setting("sound", self.settings["sound"])
            self.tray.update_menu()
        elif item == "autostart":
            set_autostart(not autostart_enabled())
            self.tray.update_menu()
        elif item == "folder":
            subprocess.Popen(["explorer", paths.data_dir()])
        elif item == "quit":
            self.quitting = True
            self.stats.flush()
            self.stop_vision()
            self.tray.stop()
            self.root.destroy()


# ---------------------------------------------------------------- entry points

def already_running():
    """One Sloucher at a time: two would fight over the camera and the NPU."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\Sloucher.App")
    return ctypes.windll.kernel32.GetLastError() == 183        # ERROR_ALREADY_EXISTS


def run(settings):
    if already_running():
        ctypes.windll.user32.MessageBoxW(None, "Sloucher is already running. Look for its icon in the tray "
                                               "(the ^ next to the clock).", APP_NAME, 0x40)
        return 0
    log.info("Sloucher starting; data in %s", paths.data_dir())
    App(settings).run()
    return 0


def demo():
    """Preview the alerts without the camera or the NPU, then exit."""
    root = tk.Tk()
    root.withdraw()
    glow, pill, flash = Glow(root), Pill(root), Flash(root)
    card = WalkCard(root, on_walked=lambda: card.hide(), on_snooze=lambda: card.hide())
    steps = [(0, lambda: (glow.show(), pill.show("Sit up", YELLOW),
                          winsound.PlaySound(paths.asset("chime.wav"), winsound.SND_FILENAME | winsound.SND_ASYNC))),
             (3500, lambda: (glow.hide(), pill.hide(), flash.play(),
                             card.show("Time for a 30 s walk", "Sitting 60 min. I'll see you leave the chair,\n"
                                                               "or tick it if you walked and I missed it."))),
             (7000, lambda: card.show("Not done yet: 18 s left", "Get up again and walk a little longer.")),
             (9000, lambda: (card.hide(), pill.show("Break done. Nice!", GREEN))),
             (10500, root.destroy)]
    for ms, fn in steps:
        root.after(ms, fn)
    root.mainloop()
    return 0
