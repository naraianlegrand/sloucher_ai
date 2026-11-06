"""The tray app: it decides what to show, from what the NPU sees.

- vision.py reads the camera twice a second; the pose model runs on the NPU, never the CPU.
- posture.py turns keypoints into good / slouch / lean-in; breaks.py counts the time in the chair;
  stats.py keeps numbers per minute. All three are pure logic, tested without a camera or NPU.
- overlays.py shows the result: slouch for most of 30 s and the screen edges glow, a "Sit up" pill
  appears and it chimes once; sit up and it fades. Once an hour: a blue flash and the walk card.
- window.py is the one window: Stats and Settings. winsys.py is the Windows plumbing (lock, autostart).
- Tray menu: Stats, Settings, Calibrate, Pause (camera and NPU off), Quit.
"""
import ctypes
import logging
import queue
import time
import tkinter as tk
import winsound

import pystray

from . import APP_NAME, breaks, glass, icon, paths, stats, window
from .overlays import BLUE, GREEN, RED, YELLOW, CalibrateWindow, Flash, Glow, Pill, WalkCard
from .vision import Vision
from .winsys import already_running, screen_locked, set_autostart

log = logging.getLogger(__name__)

PRESENT_KPS = 4         # keypoints needed to count as someone in the chair
CHIME_GAP = 10          # s between two chimes, so a flickering alert never chimes twice for one slouch
SNOOZE_S = 10 * 60      # "Snooze" on the walk card
LOCK_CHECK_S = 2        # how often to check whether the screen is locked


class App:
    def __init__(self, settings):
        self.settings = settings
        self.events = queue.Queue()        # from the vision thread and the tray thread
        glass.load_fonts()
        self.root = tk.Tk()
        self.root.withdraw()
        self.glow = Glow(self.root)
        self.pill = Pill(self.root)
        self.flash = Flash(self.root)
        self.card = WalkCard(self.root, on_walked=lambda: self.on_menu("walked"),
                             on_snooze=lambda: self.on_menu("snooze"))
        self.stats = stats.Recorder(paths.stats_dir())
        self.window = None
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
            pystray.MenuItem("Stats", lambda: self.events.put(("menu", "Stats")), default=True),
            pystray.MenuItem("Settings", lambda: self.events.put(("menu", "Settings"))),
            pystray.MenuItem("Calibrate (sit up tall first)", lambda: self.events.put(("menu", "calibrate"))),
            pystray.MenuItem(lambda _: "Resume" if self.paused else "Pause",
                             lambda: self.events.put(("menu", "pause"))),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self.events.put(("menu", "quit"))),
        ))

    def change_setting(self, key, value):
        """From the Settings tab: save it and use it at once (no restart)."""
        log.info("setting %s = %s", key, value)
        if key == "autostart":
            set_autostart(value)
            return
        self.settings[key] = value
        paths.save_setting(key, value)
        # The vision thread reads "strictness" from this same dict on every frame
        if key == "sit_minutes":
            self.coach.sit_limit = value * 60
        elif key == "break_seconds":
            self.coach.break_s = value

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
        if self.walk_due:
            self.walk_due = False
            self.card.done()
        else:
            self.card.hide()

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
        elif item in ("Stats", "Settings"):
            if self.window and self.window.open:
                self.window.show(item)
            else:
                self.window = window.Window(self.root, self.stats, self.settings, self.change_setting,
                                            lambda: self.on_menu("calibrate"), tab=item)
        elif item == "quit":
            self.quitting = True
            self.stats.flush()
            if self.window:
                self.window.close()
            self.stop_vision()
            self.tray.stop()
            self.root.destroy()


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
    glass.load_fonts()
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
             (9000, lambda: card.done()),
             (10500, root.destroy)]
    for ms, fn in steps:
        root.after(ms, fn)
    root.mainloop()
    return 0
