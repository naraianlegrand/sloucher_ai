"""The Stats window: today, the last 7 days, the trend, and a summary for an AI coach.

Smoked-glass look: a dark window with no title bar (glass.py), and every tile, bar and button
drawn as a dark glass piece on one canvas (liquid.py).
Drag it by any empty spot; the glass x or Esc closes it.

Created when opened and destroyed when closed, so it costs nothing the rest of the time.
It redraws every minute, or on Refresh.
"""
import datetime as dt
import logging
import os
import subprocess
import time
import tkinter as tk
from tkinter import filedialog

from . import __version__, glass, liquid, paths, posture, stats

log = logging.getLogger(__name__)

INK, MUTED, FAINT = "#F7F7F5", "#B9B9B4", "#5A5A57"
YELLOW = "#FFD60A"
W = 600                     # layout width in 96-dpi pixels; scaled for the screen


def _num(v, suffix=""):
    return "–" if v is None else f"{v}{suffix}"


class StatsWindow:
    def __init__(self, root, recorder):
        self.root, self.recorder = root, recorder
        self.win = tk.Toplevel(root)
        self.win.title("Stats - Sloucher")
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
        self.draw()
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        self.win.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{max(0, (root.winfo_screenheight() - h) // 3)}")
        self.win.focus_force()
        self.refresh_job = self.win.after(60_000, self.refresh)

    def px(self, v):
        return int(round(v * self.k))

    def font(self, size, weight=""):
        return ("Segoe UI" + (f" {weight}" if weight else ""), size)

    @property
    def open(self):
        return self.win is not None

    def rows(self):
        return stats.load(paths.stats_dir(), self.recorder.pending() if self.recorder else ())

    def refresh(self):
        """Redraw from the files plus the minute in progress; also runs once a minute on its own."""
        if self.win is None:
            return
        self.win.after_cancel(self.refresh_job)
        self.draw()
        self.refresh_job = self.win.after(60_000, self.refresh)

    def lift(self):
        self.refresh()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        if self.win is not None:
            self.win.after_cancel(self.refresh_job)
            self.win.destroy()
            self.win = None

    def on_press(self, e):
        # Empty glass moves the window (there's no title bar); buttons handle their own clicks
        if not self.cv.find_withtag("current"):
            glass.drag(self.win)

    # -- drawing

    def text(self, x, y, s, size=11, colour=INK, weight="", anchor="nw"):
        return self.cv.create_text(self.px(x), self.px(y), text=s, font=self.font(size, weight), fill=colour,
                                   anchor=anchor)

    def tile(self, x, y, w, h, r, tint=None):
        img = liquid.piece(self.px(w), self.px(h), self.px(r), tint)
        return self.cv.create_image(self.px(x), self.px(y), image=img, anchor="nw")

    def button(self, x, y, label, command, tint=None, anchor="nw", h=40, size=11, pad=20):
        return liquid.Button(self.cv, self.px(x), self.px(y), label, command, tint=tint,
                             font=self.font(size, "Semibold"), pad=self.px(pad), h=self.px(h),
                             anchor=anchor)

    def draw(self):
        cv = self.cv
        cv.delete("all")
        rep = self.report = stats.report(self.rows())
        t = rep["today"]
        yellow = liquid.rgb(YELLOW)
        m = 28

        # Header: title, last update, Refresh, close
        self.text(m, 20, "Stats", 24, weight="Black")
        close = self.button(W - m, 24, "✕", self.close, anchor="ne", h=36, size=10)
        ref = self.button(W - m - close.w / self.k - 8, 24, "↻  Refresh", self.refresh, anchor="ne", h=36, size=10)
        self.text(ref.x / self.k - 12, 34, f"Updated {time.strftime('%H:%M')}", 9, MUTED, anchor="ne")

        # Today: six glass tiles in two rows
        y = 84
        self.text(m, y, "Today", 10, MUTED, "Semibold")
        y += 26
        walks = f"{t['walks_done']}/{int(t['walks_due'])}" if t["walks_due"] else str(t["walks_done"])
        cells = [(_num(t["upright_pct"], "%"), "upright"), (stats.hours_text(t["bad_min"]), "slouched"),
                 (str(int(t["alerts"])), "alerts"), (_num(t["avg_correct_s"], " s"), "to sit up"),
                 (str(int(t["self_corrected"])), "fixed yourself"), (walks, "walks")]
        gap, tw, th = 10, (W - 2 * m - 20) / 3, 74
        for i, (value, caption) in enumerate(cells):
            x = m + (i % 3) * (tw + gap)
            ty = y + (i // 3) * (th + gap)
            self.tile(x, ty, tw, th, 18)
            self.text(x + 16, ty + 12, value, 18, YELLOW if i == 0 else INK, "Semibold")
            self.text(x + 16, ty + 46, caption, 9, MUTED)
        y += 2 * th + gap + 14

        trend = []
        c = stats.change(t, rep["yesterday"])
        if c:
            trend.append(f"vs yesterday: {c}")
        trend.append(f"sitting {stats.hours_text(t['sitting_min'])}")
        self.text(m, y, "  ·  ".join(trend), 10, MUTED)
        y += 34

        # Last 7 days: a glass panel with glass bars
        w7 = rep["week"]
        head = "Last 7 days"
        if w7["upright_pct"] is not None:
            head += f": {w7['upright_pct']}% upright"
            c = stats.change(w7, rep["prev_week"])
            if c:
                head += f" ({c} vs the 7 days before)"
        self.text(m, y, head, 10, MUTED, "Semibold")
        y += 26
        ph = 196
        self.tile(m, y, W - 2 * m, ph, 24)
        self.chart(m, y, W - 2 * m, ph, rep["days"], yellow)
        y += ph + 14

        best, worst = rep["best_hour"], rep["worst_hour"]
        if best and worst:
            self.text(m, y, f"Best time of day {stats.hour_range(best[0])} ({best[1]['upright_pct']}%)  ·  "
                            f"hardest {stats.hour_range(worst[0])} ({worst[1]['upright_pct']}%)", 10, MUTED)
            y += 30

        # Actions: the main one tinted, the others clear glass
        b = self.button(m, y, "Copy for my AI coach", self.copy, tint=yellow, h=44)
        e = self.button(m + b.w / self.k + 10, y, "Export…", self.export, h=44)
        self.button(m + (b.w + e.w) / self.k + 20, y, "Open stats folder", self.folder, h=44)
        y += 60
        note = self.note_text or "Numbers only, kept on this laptop. Nothing is sent anywhere unless you paste or share it."
        self.note = cv.create_text(self.px(m), self.px(y), text=note, font=self.font(9), fill=MUTED, anchor="nw",
                                   width=self.px(W - 2 * m))
        cv.configure(height=self.px(y + 44))

    def chart(self, x0, y0, w, h, days, tint):
        """Upright % per day as glass bars; today labelled, the rest on hover."""
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
            if d == today:
                self.text(cx, bottom - bh - 18, f"{pct}%", 9, INK, "Semibold", anchor="n")
            info = (f"{d:%a %b %d}: {pct}% upright, {stats.hours_text(s['sitting_min'])} sitting, "
                    f"{int(s['alerts'])} alerts, {s['walks_done']} walks")
            cv.tag_bind(bar, "<Enter>", lambda e, t=info: cv.itemconfigure(tip, text=t))
            cv.tag_bind(bar, "<Leave>", lambda e: cv.itemconfigure(tip, text=""))

    # -- actions

    def say(self, text):
        self.note_text = text
        self.cv.itemconfigure(self.note, text=text, fill=INK)

    def copy(self):
        text = stats.coach_summary(self.report, drop_pct=round(100 * (1 - posture.DROP_TH)), alert_s=posture.ALERT_S)
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
