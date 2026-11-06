"""The Sloucher window: Stats and Settings tabs, in smoked glass.

- Stats: today, the last 7 days, the trend, and a summary for an AI coach.
- Settings: calibration, sound, the walk reminder, start with Windows, your data; under Advanced
  (closed by default), how strict the posture check is. Changes apply at once and are saved.

No title bar (glass.py): drag the window by any empty spot; the glass x or Esc closes it. Every
tile, bar and control is a glass piece on one canvas (liquid.py). The window is created when
opened and destroyed when closed, so it costs nothing the rest of the time; Stats redraws once a
minute while it's open, or on Refresh.
"""
import datetime as dt
import logging
import os
import subprocess
import time
import tkinter as tk
from tkinter import filedialog

from . import __version__, glass, liquid, paths, posture, stats, winsys

log = logging.getLogger(__name__)

INK, MUTED, FAINT = "#F7F7F5", "#B9B9B4", "#5A5A57"
YELLOW, BLUE = "#FFD60A", "#64D2FF"
KNOB = (228, 228, 224)      # the bright glass you grab: slider knob, switch knob
W, M = 600, 28              # layout width and margin in 96-dpi pixels; scaled for the screen
TABS = ("Stats", "Settings")
SIT_CHOICES = (30, 45, 60, 90)          # minutes in the chair before the walk reminder
BREAK_CHOICES = (30, 60, 120)           # seconds away that count as a walk


def _num(v, suffix=""):
    return "–" if v is None else f"{v}{suffix}"


class Window:
    def __init__(self, root, recorder, settings, on_change, on_calibrate, tab="Stats"):
        """on_change(key, value) saves and applies one setting; on_calibrate() starts a calibration."""
        self.root, self.recorder, self.settings = root, recorder, settings
        self.on_change, self.on_calibrate = on_change, on_calibrate
        self.tab = tab
        self.win = tk.Toplevel(root)
        self.win.title("Sloucher")
        self.win.configure(bg=glass.BG)
        self.win.resizable(False, False)
        try:
            self.win.iconbitmap(paths.asset("icon.ico"))
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())
        self.k = self.win.winfo_fpixels("1i") / 96          # screen scale (1.0 at 100%, 1.5 at 150%)
        self.cv = tk.Canvas(self.win, bg=glass.BG, highlightthickness=0, width=self.px(W), height=10)
        self.cv.pack()
        self.cv.bind("<ButtonPress-1>", self.on_press)
        glass.frame(self.win, titlebar=False)
        self.note_text = None
        self.refresh_job = None
        self.advanced = False           # Settings: on the Advanced page (opened from its row)
        self.main_h = 0                 # height of the main Settings page, so Advanced doesn't shrink the window
        self.draw()
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        self.win.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{max(0, (root.winfo_screenheight() - h) // 4)}")
        self.win.focus_force()

    # -- window

    def px(self, v):
        return int(round(v * self.k))

    def font(self, size, weight=""):
        """Segoe UI for text, as on the website (headlines: see headline())."""
        return ("Segoe UI" + (f" {weight}" if weight else ""), size)

    @property
    def open(self):
        return self.win is not None

    def show(self, tab):
        self.tab = tab
        self.advanced = False
        self.note_text = None
        self.draw()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def refresh(self):
        """Redraw (Stats: from the files plus the minute in progress); also once a minute on its own."""
        if self.win is not None:
            self.draw()

    def close(self):
        if self.win is not None:
            if self.refresh_job:
                self.win.after_cancel(self.refresh_job)
            self.win.destroy()
            self.win = None

    def on_press(self, e):
        # Empty glass moves the window (there's no title bar); controls handle their own clicks
        if not self.cv.find_withtag("current"):
            glass.drag(self.win)

    # -- drawing helpers

    def text(self, x, y, s, size=11, colour=INK, weight="", anchor="nw", width=None):
        return self.cv.create_text(self.px(x), self.px(y), text=s, font=self.font(size, weight), fill=colour,
                                   anchor=anchor, width=self.px(width) if width else 0)

    def headline(self, x, base, s, size, colour=INK, anchor="sw"):
        """Text in the headline font, placed by its baseline (`base`); anchor sw, s or se."""
        font = glass.display(size)
        return self.cv.create_text(self.px(x), glass.baseline_y(font, self.px(base)), text=s, font=font,
                                   fill=colour, anchor=anchor)

    def tile(self, x, y, w, h, r, tint=None, level=1.0):
        img = liquid.piece(self.px(w), self.px(h), self.px(r), tint, level)
        return self.cv.create_image(self.px(x), self.px(y), image=img, anchor="nw")

    def button(self, x, y, label, command, tint=None, anchor="nw", h=40, size=11, pad=20, weight="Semibold"):
        return liquid.Button(self.cv, self.px(x), self.px(y), label, command, tint=tint,
                             font=self.font(size, weight), pad=self.px(pad), h=self.px(h), anchor=anchor)

    def clickable(self, items, command):
        for item in items:
            self.cv.tag_bind(item, "<ButtonRelease-1>", lambda e: command())
            self.cv.tag_bind(item, "<Enter>", lambda e: self.cv.configure(cursor="hand2"))
            self.cv.tag_bind(item, "<Leave>", lambda e: self.cv.configure(cursor=""))

    def draw(self):
        self.cv.delete("all")
        if self.refresh_job:
            self.win.after_cancel(self.refresh_job)
            self.refresh_job = None
        self.headline(M, 58, self.tab, 34)
        close = self.button(W - M, 24, "✕", self.close, anchor="ne", h=36, size=10, pad=13)
        right = W - M - close.w / self.k - 8
        if self.tab == "Stats":
            ref = self.button(right, 24, "↻  Refresh", self.refresh, anchor="ne", h=36, size=10)
            self.text(ref.x / self.k - 12, 34, f"Updated {time.strftime('%H:%M')}", 9, MUTED, anchor="ne")
        self.tabs(M, 76)
        y = self.draw_stats(128) if self.tab == "Stats" else self.draw_settings(128)
        self.cv.configure(height=self.px(y))
        if self.tab == "Stats":
            self.refresh_job = self.win.after(60_000, self.refresh)

    def tabs(self, x, y):
        """A glass segmented control: the open tab is the lit piece."""
        seg_w, h = 112, 36
        self.tile(x, y, seg_w * len(TABS) + 8, h + 8, (h + 8) / 2)
        for i, name in enumerate(TABS):
            sx = x + 4 + i * seg_w
            items = []
            if name == self.tab:
                items.append(self.tile(sx, y + 4, seg_w, h, h / 2, level=1.9))
            items.append(self.text(sx + seg_w / 2, y + 4 + h / 2, name, 10, INK if name == self.tab else MUTED,
                                   "Semibold", anchor="center"))
            if name != self.tab or self.advanced:
                self.clickable(items, lambda n=name: self.show(n))

    def section(self, y, title):
        self.text(M, y, title, 10, MUTED, "Semibold")
        return y + 26

    # -- Stats tab

    def rows(self):
        return stats.load(paths.stats_dir(), self.recorder.pending() if self.recorder else ())

    def draw_stats(self, y):
        rep = self.report = stats.report(self.rows())
        t = rep["today"]
        yellow = liquid.rgb(YELLOW)

        y = self.section(y, "Today")
        walks = f"{t['walks_done']}/{int(t['walks_due'])}" if t["walks_due"] else str(t["walks_done"])
        cells = [(_num(t["upright_pct"], "%"), "upright"), (stats.hours_text(t["bad_min"]), "slouched"),
                 (str(int(t["alerts"])), "alerts"), (_num(t["avg_correct_s"], " s"), "to sit up"),
                 (str(int(t["self_corrected"])), "fixed yourself"), (walks, "walks")]
        gap, tw, th = 10, (W - 2 * M - 20) / 3, 74
        for i, (value, caption) in enumerate(cells):
            x = M + (i % 3) * (tw + gap)
            ty = y + (i // 3) * (th + gap)
            self.tile(x, ty, tw, th, 18)
            self.headline(x + 16, ty + 40, value, 25, YELLOW if i == 0 else INK)
            self.text(x + 16, ty + 46, caption, 9, MUTED)
        y += 2 * th + gap + 14

        trend = []
        c = stats.change(t, rep["yesterday"])
        if c:
            trend.append(f"vs yesterday: {c}")
        trend.append(f"sitting {stats.hours_text(t['sitting_min'])}")
        self.text(M, y, "  ·  ".join(trend), 10, MUTED)
        y += 34

        w7 = rep["week"]
        head = "Last 7 days"
        if w7["upright_pct"] is not None:
            head += f": {w7['upright_pct']}% upright"
            c = stats.change(w7, rep["prev_week"])
            if c:
                head += f" ({c} vs the 7 days before)"
        y = self.section(y, head)
        ph = 196
        self.tile(M, y, W - 2 * M, ph, 24)
        self.chart(M, y, W - 2 * M, ph, rep["days"], yellow)
        y += ph + 14

        best, worst = rep["best_hour"], rep["worst_hour"]
        if best and worst:
            self.text(M, y, f"Best time of day {stats.hour_range(best[0])} ({best[1]['upright_pct']}%)  ·  "
                            f"hardest {stats.hour_range(worst[0])} ({worst[1]['upright_pct']}%)", 10, MUTED)
            y += 30

        b = self.button(M, y, "Copy for my AI coach", self.copy, tint=yellow, h=44)
        e = self.button(M + b.w / self.k + 10, y, "Export…", self.export, h=44)
        self.button(M + (b.w + e.w) / self.k + 20, y, "Open stats folder", self.folder, h=44)
        y += 60
        note = self.note_text or "Numbers only, kept on this laptop. Nothing is sent anywhere unless you paste or share it."
        self.note = self.text(M, y, note, 9, INK if self.note_text else MUTED, width=W - 2 * M)
        return y + 44

    def chart(self, x0, y0, w, h, days, tint):
        """Upright % per day as glass bars, each labelled; hover for the day's details."""
        cv = self.cv
        top, bottom = y0 + 34, y0 + h - 34
        slot = (w - 24) / len(days)
        bw = min(38, slot * 0.5)
        tip = self.text(x0 + w - 18, y0 + 12, "", 9, MUTED, anchor="ne")
        cv.create_line(self.px(x0 + 16), self.px(bottom), self.px(x0 + w - 16), self.px(bottom), fill=FAINT)
        today = dt.date.today()
        for i, (d, s) in enumerate(days):
            cx = x0 + 12 + slot * i + slot / 2
            self.text(cx, bottom + 8, "Today" if d == today else f"{d:%a}", 9, INK if d == today else MUTED,
                      "Semibold" if d == today else "", anchor="n")
            pct = s["upright_pct"] if s else None
            if pct is None:
                cv.create_line(self.px(cx - bw / 4), self.px(bottom - 3), self.px(cx + bw / 4), self.px(bottom - 3),
                               fill=FAINT, width=self.px(2))
                continue
            bh = max(10, (bottom - top) * pct / 100)
            bar = self.tile(cx - bw / 2, bottom - bh, bw, bh, 12, tint)
            self.headline(cx, bottom - bh - 7, f"{pct}%", 13, INK if d == today else MUTED, anchor="s")
            info = (f"{d:%a %b %d}: {pct}% upright, {stats.hours_text(s['sitting_min'])} sitting, "
                    f"{int(s['alerts'])} alerts, {s['walks_done']} walks")
            cv.tag_bind(bar, "<Enter>", lambda e, t=info: cv.itemconfigure(tip, text=t))
            cv.tag_bind(bar, "<Leave>", lambda e: cv.itemconfigure(tip, text=""))

    # -- Settings tab

    def set(self, key, value):
        self.on_change(key, value)
        self.draw()

    def draw_settings(self, y):
        """Everyday settings first; posture strictness sits under Advanced, closed by default.

        Each row: a name, one line of help, and its control on the right.
        """
        if self.advanced:
            return self.draw_advanced_page(y)
        st = self.settings
        blue = liquid.rgb(BLUE)

        y = self.group(y, "Posture", [
            ("Calibration", "Teach Sloucher your upright posture.",
             lambda r, m: self.button(r, m - 17, "Recalibrate", self.on_calibrate, anchor="ne", h=34, size=10,
                                      weight="")),
            ("Alert sound", "A soft chime when the screen edges glow.",
             lambda r, m: self.switch(r, m - 14, bool(st.get("sound")), lambda on: self.set("sound", on))),
        ])
        y = self.group(y, "Walk reminder", [
            ("Remind me after", "Time in the chair before the reminder.",
             lambda r, m: self.choices(r, m - 16, [f"{v} min" for v in SIT_CHOICES], SIT_CHOICES,
                                       st.get("sit_minutes"), lambda v: self.set("sit_minutes", v), blue)),
            ("Counts as a walk after", "Time away from the chair.",
             lambda r, m: self.choices(r, m - 16, ["30 s", "1 min", "2 min"], BREAK_CHOICES,
                                       st.get("break_seconds"), lambda v: self.set("break_seconds", v), blue)),
        ])
        y = self.group(y, "General", [
            ("Start with Windows", "Sloucher starts quietly in the tray.",
             lambda r, m: self.switch(r, m - 14, winsys.autostart_enabled(), lambda on: self.set("autostart", on))),
            ("Your data", "Kept on this laptop, nowhere else.",
             lambda r, m: self.button(r, m - 17, "Open folder",
                                      lambda: subprocess.Popen(["explorer", paths.data_dir()]),
                                      anchor="ne", h=34, size=10, weight="")),
        ])
        self.main_h = self.draw_advanced_row(y)
        return self.main_h

    def group(self, y, title, rows):
        """A titled glass panel of rows, with a hairline between them."""
        y = self.section(y, title)
        rh, pw = 68, W - 2 * M
        self.tile(M, y, pw, rh * len(rows), 22)
        for i, (name, helper, control) in enumerate(rows):
            ry = y + i * rh
            if i:
                self.cv.create_line(self.px(M + 22), self.px(ry), self.px(W - M - 22), self.px(ry), fill="#2C2C2A")
            self.text(M + 22, ry + 14, name, 11, INK)
            self.text(M + 22, ry + 36, helper, 9, MUTED, width=250)
            control(W - M - 20, ry + rh / 2)
        return y + rh * len(rows) + 22

    def draw_advanced_row(self, y):
        """The way into Advanced: one row, saying what's been changed there, if anything."""
        level = int(self.settings.get("strictness", posture.NORMAL))
        items = [self.tile(M, y, W - 2 * M, 56, 22)]
        items.append(self.text(M + 22, y + 9, "Advanced", 11, INK))
        items.append(self.text(M + 22, y + 31, "For power users: how strict the posture check is.", 9, MUTED))
        if level != posture.NORMAL:
            items.append(self.text(W - M - 48, y + 18, f"Strictness: {posture.STRICTNESS[level][0]}", 10, YELLOW,
                                   anchor="ne"))
        items.append(self.text(W - M - 22, y + 16, "\u203a", 13, MUTED, anchor="ne"))
        self.clickable(items, self.toggle_advanced)
        return y + 56 + 28

    def draw_advanced_page(self, y):
        """Settings > Advanced: the posture strictness, with what each step catches."""
        level = int(self.settings.get("strictness", posture.NORMAL))
        name, drop_th, face_th, meaning = posture.STRICTNESS[level]
        pw = W - 2 * M
        self.button(M, y - 6, "\u2039  Back", self.toggle_advanced, h=32, size=10, pad=14, weight="")
        y += 44
        y = self.section(y, "Advanced")
        ph = 236
        self.tile(M, y, pw, ph, 22)
        self.text(M + 22, y + 16, "Posture strictness", 11, INK)
        self.text(W - M - 22, y + 16, name, 11, YELLOW, "Semibold", anchor="ne")
        self.text(M + 22, y + 40, "Normal is the tested default. Change it only if alerts feel too frequent "
                                  "or too rare.", 9, MUTED, width=pw - 44)
        self.slider(M + 34, W - M - 34, y + 90, level)
        self.text(M + 22, y + 110, "Relaxed", 9, MUTED)
        self.text(W - M - 22, y + 110, "Strict", 9, MUTED, anchor="ne")
        self.text(M + 22, y + 136, f"{meaning} Alerts when your eyes drop {round(100 * (1 - drop_th))}% below "
                                   f"your calibration, or you lean in {round(100 * (face_th - 1))}%.",
                  10, INK, width=pw - 44)
        if level != posture.NORMAL:
            self.button(M + 22, y + 186, "Reset to Normal", lambda: self.set("strictness", posture.NORMAL),
                        h=32, size=10, weight="")
        y += ph + 18
        self.text(M, y, "Strictness only moves the line between good posture and a slouch. An alert still needs "
                        "a slouch for most of 30 seconds.", 9, MUTED, width=pw)
        return max(y + 50, self.main_h)

    def toggle_advanced(self):
        self.advanced = not self.advanced
        self.draw()

    def slider(self, x1, x2, y, level):
        """Five stops on a glass track; click or drag. The lit part runs up to the knob."""
        n = len(posture.STRICTNESS) - 1
        kx = x1 + (x2 - x1) * level / n
        track = self.tile(x1 - 6, y - 6, x2 - x1 + 12, 12, 6)
        fill = self.tile(x1 - 6, y - 6, kx - x1 + 12, 12, 6, liquid.rgb(YELLOW))
        dots = []
        for i in range(n + 1):
            dx = x1 + (x2 - x1) * i / n
            if dx > kx + 1:             # the stops still ahead of the knob
                dots.append(self.cv.create_oval(self.px(dx - 2), self.px(y - 2), self.px(dx + 2), self.px(y + 2),
                                                fill=MUTED, outline=""))
        knob = self.tile(kx - 15, y - 15, 30, 30, 15, KNOB)

        def pick(e):
            stop = round((e.x / self.k - x1) / (x2 - x1) * n)
            stop = max(0, min(n, stop))
            if stop != int(self.settings.get("strictness", posture.NORMAL)):
                self.set("strictness", stop)

        for item in [track, fill, knob] + dots:
            self.cv.tag_bind(item, "<ButtonPress-1>", pick)
            self.cv.tag_bind(item, "<B1-Motion>", pick)
            self.cv.tag_bind(item, "<Enter>", lambda e: self.cv.configure(cursor="hand2"))
            self.cv.tag_bind(item, "<Leave>", lambda e: self.cv.configure(cursor=""))

    def choices(self, right, y, labels, values, current, pick, tint):
        """A row of small glass capsules, right-aligned; the chosen one is tinted."""
        x = right
        for label, value in reversed(list(zip(labels, values))):
            chosen = value == current
            b = liquid.Button(self.cv, self.px(x), self.px(y), label, lambda v=value: pick(v),
                              tint=tint if chosen else None, font=self.font(10, "Semibold" if chosen else ""),
                              pad=self.px(13), h=self.px(32), anchor="ne")
            x = b.x / self.k - 6

    def switch(self, right, y, on, flip):
        """A glass on/off switch."""
        w, h = 50, 28
        x = right - w
        items = [self.tile(x, y, w, h, h / 2, liquid.rgb(YELLOW) if on else None)]
        kx = x + w - h + 3 if on else x + 3
        items.append(self.tile(kx, y + 3, h - 6, h - 6, (h - 6) / 2, KNOB))
        self.clickable(items, lambda: flip(not on))

    # -- Stats actions

    def say(self, text):
        self.note_text = text
        self.cv.itemconfigure(self.note, text=text, fill=INK)

    def copy(self):
        level = int(self.settings.get("strictness", posture.NORMAL))
        drop_th = posture.STRICTNESS[level][1]
        text = stats.coach_summary(self.report, drop_pct=round(100 * (1 - drop_th)), alert_s=posture.ALERT_S)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()
        self.say("Copied. Paste it into Gemini, ChatGPT, Claude or your coach app, and ask away.")

    def export(self):
        folder = filedialog.askdirectory(parent=self.win, title="Save my posture stats in…",
                                         initialdir=os.path.expanduser("~\\Documents"))
        if not folder:
            return
        try:
            csv_path, _ = stats.export(self.rows(), folder, __version__)
        except OSError as e:
            self.say(f"Couldn't save there: {e}")
            return
        self.say(f"Saved a CSV (opens in Excel) and a JSON file in {folder}")
        subprocess.Popen(["explorer", "/select,", csv_path])

    def folder(self):
        os.makedirs(paths.stats_dir(), exist_ok=True)
        subprocess.Popen(["explorer", paths.stats_dir()])
