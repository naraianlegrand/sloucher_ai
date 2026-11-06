"""What you see on screen: the edge glow, the pill, the walk flash and card, the welcome window.

The glow, pill and flash are click-through and never take focus; the walk card takes clicks but
not the keyboard. Nothing here draws or wakes up unless something changes.
"""
import ctypes
import tkinter as tk

from . import APP_NAME, glass, liquid, paths

YELLOW = "#FFD60A"      # alerts
BLUE = "#64D2FF"        # the walk
GREEN = "#30D158"       # done, calibrated
RED = "#FF453A"         # problems
INK = "#111111"


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
        tk.Label(self.win, text="Sit up tall.", font=glass.display(30), fg="#F7F7F5", bg="#000000").pack(anchor="w")
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
    """The walk reminder: a smoked-glass card, bottom right, that stays until you walk, tick
    "I walked" or snooze. When the walk counts it turns green ("Break done. Nice!") and fades.

    Clickable, but it never takes the keyboard from the window you're typing in.
    """
    W, H = 372, 152            # 96-dpi pixels; scaled for the screen

    def __init__(self, root, on_walked, on_snooze):
        self.root, self.on_walked, self.on_snooze = root, on_walked, on_snooze
        self.win = None
        self.close_job = None

    @property
    def showing(self):
        return self.win is not None

    def _build(self):
        self.win = win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=glass.BG)
        self.k = win.winfo_fpixels("1i") / 96
        self.cv = tk.Canvas(win, bg=glass.BG, highlightthickness=0,
                            width=self.px(self.W), height=self.px(self.H))
        self.cv.pack()
        # No focus and no taskbar button, but (unlike the glow) clicks land on it
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80 | 0x08000000)    # TOOLWINDOW | NOACTIVATE
        glass.frame(win)
        self._place()

    def px(self, v):
        return int(round(v * self.k))

    def _draw(self, title, detail, colour, buttons):
        cv, px = self.cv, self.px
        cv.delete("all")
        h = self.H if buttons else 84          # no buttons: a shorter card
        cv.configure(height=px(h))
        cv.create_image(0, 0, image=liquid.piece(px(self.W), px(h), px(14)), anchor="nw")
        cv.create_oval(px(22), px(25), px(33), px(36), fill=colour, outline="")
        font = glass.display(19)
        cv.create_text(px(42), glass.baseline_y(font, px(38)), text=title, font=font, fill="#F7F7F5", anchor="sw")
        cv.create_text(px(22), px(48), text=detail, font=("Segoe UI", 10), fill="#B9B9B4", anchor="nw",
                       width=px(self.W - 44))
        if buttons:
            b = liquid.Button(cv, px(22), px(self.H - 56), "\u2713  I walked", self.on_walked,
                              tint=liquid.rgb(BLUE), pad=px(18), h=px(38))
            liquid.Button(cv, b.x + b.w + px(10), px(self.H - 56), "Snooze 10 min", self.on_snooze,
                          font=("Segoe UI", 11), pad=px(18), h=px(38))

    def show(self, title, detail):
        if self.close_job:
            self.root.after_cancel(self.close_job)
            self.close_job = None
        if self.win is None:
            self._build()
        self._draw(title, detail, BLUE, buttons=True)
        self._place()

    def done(self, text="Break done. Nice!"):
        """The walk counted: the card says so for a moment, then closes. Its own place, so a
        slouch alert at the same moment can't hide it."""
        if self.win is None:
            self._build()
        self._draw(text, "Your sitting clock starts again.", GREEN, buttons=False)
        self._place()
        if self.close_job:
            self.root.after_cancel(self.close_job)
        self.close_job = self.root.after(3500, self.hide)

    def _place(self):
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        area = work_area() or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        self.win.geometry(f"+{area[2] - w - 24}+{area[3] - h - 24}")

    def hide(self):
        self.close_job = None
        if self.win is not None:
            self.win.destroy()
            self.win = None
