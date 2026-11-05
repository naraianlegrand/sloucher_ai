"""The Stats window: today, the last 7 days, the trend, and a summary for an AI coach.

Created when opened and destroyed when closed, so it costs nothing the rest of the time.
Windows 11 Mica glass behind it (glass.py); it redraws every minute, or on Refresh.
"""
import datetime as dt
import logging
import time
import os
import subprocess
import tkinter as tk
from tkinter import filedialog

from . import __version__, glass, paths, posture, stats

log = logging.getLogger(__name__)

BG, PANEL, INK, MUTED, FAINT = glass.GLASS, glass.TILE, "#F7F7F5", "#B4B4B0", "#4A4A48"
YELLOW = "#FFD60A"


def _num(v, suffix=""):
    return "–" if v is None else f"{v}{suffix}"


class StatsWindow:
    def __init__(self, root, recorder):
        self.root, self.recorder = root, recorder
        self.win = tk.Toplevel(root)
        self.win.title("Stats - Sloucher")
        self.win.configure(bg=BG, padx=28, pady=24)
        self.win.resizable(False, False)
        try:
            self.win.iconbitmap(paths.asset("icon.ico"))
        except tk.TclError:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.body = None
        self.updated = None
        self.glassy = glass.apply(self.win, "mica")
        self.accent = glass.tint(YELLOW) if self.glassy else YELLOW
        self.draw()
        self.win.update_idletasks()
        w, h = self.win.winfo_width(), self.win.winfo_height()
        self.win.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{max(0, (root.winfo_screenheight() - h) // 3)}")
        self.win.focus_force()
        self.refresh_job = self.win.after(60_000, self.refresh)

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
        self.draw()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    def close(self):
        if self.win is not None:
            self.win.after_cancel(self.refresh_job)
            self.win.destroy()
            self.win = None

    # -- layout

    def label(self, parent, text, size=11, colour=INK, weight="", **kw):
        font = ("Segoe UI" + (f" {weight}" if weight else ""), size)
        return tk.Label(parent, text=text, font=font, fg=colour, bg=parent["bg"], **kw)

    def draw(self):
        if self.body is not None:
            self.body.destroy()
        self.body = b = tk.Frame(self.win, bg=BG)
        b.pack(fill="both")
        rep = self.report = stats.report(self.rows())
        t = rep["today"]

        head = tk.Frame(b, bg=BG)
        head.pack(fill="x")
        self.label(head, "Stats", 22, weight="Black").pack(side="left")
        tk.Button(head, text="\u21bb  Refresh", font=("Segoe UI", 10), bg=PANEL, fg=INK, relief="flat",
                  activebackground="#3A3A38", activeforeground=INK, padx=12, pady=3, cursor="hand2",
                  command=self.refresh).pack(side="right", pady=(6, 0))
        self.label(head, f"Updated {time.strftime('%H:%M')}", 9, MUTED).pack(side="right", padx=10, pady=(6, 0))
        self.label(b, "Today", 10, MUTED, "Semibold").pack(anchor="w", pady=(14, 4))

        tiles = tk.Frame(b, bg=BG)
        tiles.pack(anchor="w", fill="x")
        walks = f"{t['walks_done']}/{int(t['walks_due'])}" if t["walks_due"] else str(t["walks_done"])
        for i, (value, caption) in enumerate([
            (_num(t["upright_pct"], "%"), "upright"),
            (stats.hours_text(t["bad_min"]), "slouched"),
            (str(int(t["alerts"])), "alerts"),
            (_num(t["avg_correct_s"], " s"), "to sit up"),
            (str(int(t["self_corrected"])), "fixed yourself"),
            (walks, "walks"),
        ]):
            cell = tk.Frame(tiles, bg=PANEL, padx=12, pady=8)
            cell.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0), sticky="nsew")
            self.label(cell, value, 16, self.accent if i == 0 else INK, "Semibold").pack(anchor="w")
            self.label(cell, caption, 9, MUTED).pack(anchor="w")

        trend = []
        c = stats.change(t, rep["yesterday"])
        if c:
            trend.append(f"vs yesterday: {c}")
        trend.append(f"sitting {stats.hours_text(t['sitting_min'])}")
        self.label(b, "  ·  ".join(trend), 10, MUTED).pack(anchor="w", pady=(8, 0))

        w = rep["week"]
        head = "Last 7 days"
        if w["upright_pct"] is not None:
            head += f": {w['upright_pct']}% upright"
            c = stats.change(w, rep["prev_week"])
            if c:
                head += f" ({c} vs the 7 days before)"
        self.label(b, head, 10, MUTED, "Semibold").pack(anchor="w", pady=(18, 4))
        self.chart(b, rep["days"])

        best, worst = rep["best_hour"], rep["worst_hour"]
        if best and worst:
            self.label(b, f"Best time of day {stats.hour_range(best[0])} ({best[1]['upright_pct']}%)  ·  "
                          f"hardest {stats.hour_range(worst[0])} ({worst[1]['upright_pct']}%)", 10, MUTED
                       ).pack(anchor="w", pady=(6, 0))

        row = tk.Frame(b, bg=BG)
        row.pack(anchor="w", pady=(20, 0))
        tk.Button(row, text="Copy for my AI coach", font=("Segoe UI Semibold", 11), bg=self.accent, fg="#000000",
                  relief="flat", activebackground="#FFE45C", padx=16, pady=6, cursor="hand2",
                  command=self.copy).pack(side="left")
        for text, cmd in (("Export…", self.export), ("Open stats folder", self.folder)):
            tk.Button(row, text=text, font=("Segoe UI", 11), bg=BG, fg=MUTED, relief="flat",
                      activebackground=PANEL, activeforeground=INK, padx=12, pady=6, cursor="hand2",
                      command=cmd).pack(side="left", padx=(8, 0))
        self.note = self.label(b, "Numbers only, kept on this laptop. Nothing is sent anywhere unless you paste "
                                  "or share it.", 9, MUTED, wraplength=520, justify="left")
        self.note.pack(anchor="w", pady=(12, 0))

    def chart(self, parent, days):
        """Upright % per day: one bar each, today labelled, the rest on hover."""
        W, H, top, bottom = 520, 150, 20, 26
        cv = tk.Canvas(parent, width=W, height=H, bg=BG, highlightthickness=0)
        cv.pack(anchor="w")
        slot = W / len(days)
        bw = min(36, slot * 0.5)
        base = H - bottom
        cv.create_line(0, base, W, base, fill=FAINT)
        tip = cv.create_text(W, 0, text="", fill=MUTED, font=("Segoe UI", 9), anchor="ne")
        today = dt.date.today()
        for i, (d, s) in enumerate(days):
            cx = slot * i + slot / 2
            cv.create_text(cx, base + 13, text="Today" if d == today else f"{d:%a}",
                           fill=INK if d == today else MUTED, font=("Segoe UI", 9))
            pct = s["upright_pct"] if s else None
            if pct is None:
                cv.create_line(cx - bw / 4, base - 2, cx + bw / 4, base - 2, fill=FAINT, width=2)
                continue
            y = base - (base - top) * pct / 100
            bar = cv.create_rectangle(cx - bw / 2, y, cx + bw / 2, base, fill=self.accent, outline="")
            info = f"{d:%a %b %d}: {pct}% upright, {stats.hours_text(s['sitting_min'])} sitting, " \
                   f"{int(s['alerts'])} alerts, {s['walks_done']} walks"
            if d == today:
                cv.create_text(cx, y - 9, text=f"{pct}%", fill=INK, font=("Segoe UI Semibold", 9))
            for item in (bar,):
                cv.tag_bind(item, "<Enter>", lambda e, t=info: cv.itemconfigure(tip, text=t))
                cv.tag_bind(item, "<Leave>", lambda e: cv.itemconfigure(tip, text=""))

    # -- actions

    def say(self, text):
        self.note.configure(text=text, fg=INK)

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
