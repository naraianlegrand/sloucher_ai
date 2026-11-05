"""Posture stats: how much you slouched, how fast you corrected, and whether you're improving.

Recording: counters updated from the posture calls the NPU already makes; no extra model.
One CSV row per minute in the chair, appended to %LOCALAPPDATA%\\Sloucher\\stats\\YYYY-MM.csv.
Numbers only: never images or keypoints. Field meanings: docs/STATS.md.

Reading: day and hour totals, the last 7 days vs the 7 before, a summary to paste into an
AI health coach, and CSV / JSON export. Pure Python, so it's tested without a camera or NPU.
"""
import csv
import datetime as dt
import glob
import json
import os
import time

FIELDS = ["minute", "sitting_s", "good_s", "slouch_s", "lean_s", "alerts", "corrected", "corrected_s",
          "self_corrected", "walks_due", "walks_seen", "walks_ticked", "walks_locked", "snoozes", "longest_sit_s"]
COUNTS = FIELDS[1:]
SELF_FIX_S = 5          # a bad stretch this long, fixed before the alert, counts as "fixed it yourself"
MAX_DT = 2.0            # longest gap between two frames that still counts as time in the chair
BAD = ("slouch", "lean-in")


def _minute(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


class Recorder:
    """Feed it every frame and every walk event; it writes a row when each minute ends.

    `clock` is wall-clock time (time.time) for the row's minute; `now` passed in is the app's
    monotonic time for durations. Tests pass both.
    """

    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = folder, clock
        self.row, self.key = None, None
        self.last_t = None
        self.bad_since = None       # start of the current bad stretch
        self.alerted = False        # that stretch reached an alert
        self.alert_at = None        # when the current alert started

    # -- recording

    def _bucket(self):
        key = _minute(self.clock())
        if key != self.key:
            self.flush()
            self.key, self.row = key, dict.fromkeys(COUNTS, 0)
        return self.row

    def frame(self, now, present, state, alerting):
        """One posture call: present = someone in the chair, alerting = the glow is on."""
        row = self._bucket()
        gap = 0.0 if self.last_t is None else now - self.last_t
        self.last_t = now
        if not present:
            self.bad_since, self.alerted = None, False
            self.alert_at = None            # leaving isn't "correcting"
            return
        if 0 < gap <= MAX_DT:
            row["sitting_s"] += gap
            if state == "good":
                row["good_s"] += gap
            elif state == "slouch":
                row["slouch_s"] += gap
            elif state == "lean-in":
                row["lean_s"] += gap
        if alerting and self.alert_at is None:
            row["alerts"] += 1
            self.alert_at, self.alerted = now, True
        elif not alerting and self.alert_at is not None:
            row["corrected"] += 1
            row["corrected_s"] += now - self.alert_at
            self.alert_at = None
        if state in BAD:
            if self.bad_since is None:
                self.bad_since, self.alerted = now, alerting
        elif state == "good" and self.bad_since is not None:
            if not self.alerted and now - self.bad_since >= SELF_FIX_S:
                row["self_corrected"] += 1
            self.bad_since, self.alerted = None, False

    def gap(self):
        """Paused, locked or asleep: the next frame doesn't continue the current stretch."""
        self.last_t, self.bad_since, self.alerted, self.alert_at = None, None, False, None

    def walk_due(self):
        self._bucket()["walks_due"] += 1

    def snoozed(self):
        self._bucket()["snoozes"] += 1

    def walk_done(self, how, sat_s):
        """how: "seen" (the camera saw the empty chair), "ticked" (I walked) or "locked" (screen locked)."""
        row = self._bucket()
        row[f"walks_{how}"] += 1
        row["longest_sit_s"] = max(row["longest_sit_s"], sat_s)

    def flush(self):
        """Append the current minute's row (if anything happened) to this month's file."""
        row, key = self.row, self.key
        self.row, self.key = None, None
        if not row or not any(row.values()):
            return
        os.makedirs(self.folder, exist_ok=True)
        path = os.path.join(self.folder, key[:7] + ".csv")
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(FIELDS)
            w.writerow([key] + [round(row[k], 1) if isinstance(row[k], float) else row[k] for k in COUNTS])

    def pending(self):
        """The unwritten current minute, so the stats window can include it."""
        return [dict(self.row, minute=self.key)] if self.row else []


# ---------------------------------------------------------------- reading

def load(folder, extra=()):
    """All rows, oldest first, as dicts with numbers. Broken lines are skipped."""
    rows = []
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    try:
                        rows.append({"minute": r["minute"], **{k: float(r.get(k) or 0) for k in COUNTS}})
                    except (KeyError, ValueError):
                        continue
        except OSError:
            continue
    rows.extend(extra)
    return rows


def _empty():
    return dict.fromkeys(COUNTS, 0.0)


def _add(total, row):
    for k in COUNTS:
        if k == "longest_sit_s":
            total[k] = max(total[k], row[k])
        else:
            total[k] += row[k]


def finish(t):
    """Derived numbers for a total: upright %, median-ish correction time, walks done."""
    tracked = t["good_s"] + t["slouch_s"] + t["lean_s"]
    t["upright_pct"] = round(100 * t["good_s"] / tracked) if tracked >= 60 else None
    t["bad_min"] = round((t["slouch_s"] + t["lean_s"]) / 60)
    t["sitting_min"] = round(t["sitting_s"] / 60)
    t["avg_correct_s"] = round(t["corrected_s"] / t["corrected"]) if t["corrected"] else None
    t["walks_done"] = int(t["walks_seen"] + t["walks_ticked"] + t["walks_locked"])
    return t


def by_day(rows):
    days = {}
    for r in rows:
        _add(days.setdefault(r["minute"][:10], _empty()), r)
    return {d: finish(t) for d, t in days.items()}


def by_hour(rows):
    """Hour of the day (0..23) -> total over all the given rows."""
    hours = {}
    for r in rows:
        _add(hours.setdefault(int(r["minute"][11:13]), _empty()), r)
    return {h: finish(t) for h, t in sorted(hours.items())}


def span(rows, first, last):
    """Rows from date `first` to `last` (inclusive, dt.date)."""
    a, b = first.isoformat(), last.isoformat()
    return [r for r in rows if a <= r["minute"][:10] <= b]


def total(rows):
    t = _empty()
    for r in rows:
        _add(t, r)
    return finish(t)


def best_worst_hours(rows, min_minutes=10):
    hours = [(h, t) for h, t in by_hour(rows).items()
             if t["upright_pct"] is not None and t["good_s"] + t["slouch_s"] + t["lean_s"] >= 60 * min_minutes]
    if len(hours) < 2:
        return None, None
    hours.sort(key=lambda ht: ht[1]["upright_pct"])
    return hours[-1], hours[0]


def report(rows, today=None):
    """Everything the stats window and the coach summary show."""
    today = today or dt.date.today()
    week = span(rows, today - dt.timedelta(days=6), today)
    prev = span(rows, today - dt.timedelta(days=13), today - dt.timedelta(days=7))
    days = by_day(week)
    best, worst = best_worst_hours(week)
    return {
        "today": total(span(rows, today, today)),
        "yesterday": total(span(rows, today - dt.timedelta(days=1), today - dt.timedelta(days=1))),
        "week": total(week),
        "prev_week": total(prev),
        "days": [(today - dt.timedelta(days=6 - i), days.get((today - dt.timedelta(days=6 - i)).isoformat()))
                 for i in range(7)],
        "best_hour": best,
        "worst_hour": worst,
        "first": today - dt.timedelta(days=6),
        "last": today,
    }


def change(now, before):
    """'+6 points' / '-3 points' / None, for upright %."""
    a, b = now["upright_pct"], before["upright_pct"]
    if a is None or b is None:
        return None
    d = a - b
    return "no change" if d == 0 else f"{d:+d} points"


def hours_text(minutes):
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def hour_range(h):
    return f"{h:02d}:00-{(h + 1) % 24:02d}:00"


def coach_summary(rep, drop_pct=4, alert_s=30):
    """Plain English, ready to paste into an AI health coach (Gemini, ChatGPT, Claude...)."""
    w, p, t = rep["week"], rep["prev_week"], rep["today"]
    used = [d for d, s in rep["days"] if s and s["sitting_s"] >= 60]
    first, last = rep["first"], rep["last"]
    lines = [
        f"My posture at my desk, measured by Sloucher (a posture app that runs a pose model on my laptop's NPU "
        f"and compares me with my own calibrated upright posture), for the last 7 days "
        f"({first:%b %d} to {last:%b %d, %Y}):",
        "",
    ]
    if not used:
        lines.append("- No sitting time was recorded in these 7 days.")
    else:
        lines.append(f"- Sat at my desk for {hours_text(w['sitting_min'])} in total, on {len(used)} of 7 days "
                     f"(about {hours_text(w['sitting_min'] / len(used))} a day).")
        if w["upright_pct"] is not None:
            line = f"- Upright {w['upright_pct']}% of the time"
            c = change(w, p)
            if c:
                line += f" (the 7 days before: {p['upright_pct']}%, {c})"
            if t["upright_pct"] is not None:
                line += f". Today: {t['upright_pct']}%"
            lines.append(line + ".")
        lines.append(f"- Slouched or leaned in toward the screen for {hours_text(w['bad_min'])}.")
        if rep["best_hour"] and rep["worst_hour"]:
            (bh, b), (wh, wo) = rep["best_hour"], rep["worst_hour"]
            lines.append(f"- Best time of day: {hour_range(bh)} ({b['upright_pct']}% upright). "
                         f"Worst: {hour_range(wh)} ({wo['upright_pct']}% upright).")
        alert = f"- Got {int(w['alerts'])} slouch alerts (after slouching for most of {alert_s} s)"
        if w["avg_correct_s"] is not None:
            alert += f"; I sat up again after {w['avg_correct_s']} s on average"
        lines.append(alert + f". I also fixed {int(w['self_corrected'])} slouches myself before an alert came.")
        if w["walks_due"] or w["walks_done"]:
            lines.append(f"- Hourly walk reminders: {int(w['walks_due'])}. Walks of 30 s or more: {w['walks_done']} "
                         f"({int(w['walks_seen'] + w['walks_locked'])} seen by the app, "
                         f"{int(w['walks_ticked'])} I confirmed myself). Snoozed {int(w['snoozes'])} times.")
        if w["longest_sit_s"]:
            lines.append(f"- Longest stretch sitting without a break: {hours_text(w['longest_sit_s'] / 60)}.")
        lines += ["", "Per day (upright %, sitting time, alerts, walks):"]
        for d, s in rep["days"]:
            if s and s["sitting_s"] >= 60:
                pct = f"{s['upright_pct']}%" if s["upright_pct"] is not None else "n/a"
                lines.append(f"- {d:%a %b %d}: {pct}, {hours_text(s['sitting_min'])}, "
                             f"{int(s['alerts'])} alerts, {s['walks_done']} walks")
    lines += [
        "",
        f"How it's measured: \"slouched\" means my eyes dropped toward my shoulders by more than {drop_pct}% "
        f"compared with my upright calibration (it also catches looking down). \"Leaned in\" means my face came "
        f"noticeably closer to the screen than my shoulders. Only the webcam's view from the front is used.",
        "",
        "Based on this, what's one habit I should change this week, and how will I know it's working?",
    ]
    return "\n".join(lines)


def export(rows, folder, version=""):
    """Write sloucher-days.csv and sloucher-stats.json into `folder`; returns the two paths."""
    days, hours = by_day(rows), by_hour(rows)
    os.makedirs(folder, exist_ok=True)
    stamp = dt.date.today().isoformat()
    csv_path = os.path.join(folder, f"sloucher-days-{stamp}.csv")
    json_path = os.path.join(folder, f"sloucher-stats-{stamp}.json")
    cols = ["date", "sitting_min", "upright_pct", "bad_min", "alerts", "avg_correct_s", "self_corrected",
            "walks_due", "walks_done", "walks_seen", "walks_ticked", "walks_locked", "snoozes", "longest_sit_min"]

    def day_row(d, t):
        return {"date": d, "sitting_min": t["sitting_min"], "upright_pct": t["upright_pct"], "bad_min": t["bad_min"],
                "alerts": int(t["alerts"]), "avg_correct_s": t["avg_correct_s"],
                "self_corrected": int(t["self_corrected"]), "walks_due": int(t["walks_due"]),
                "walks_done": t["walks_done"], "walks_seen": int(t["walks_seen"]),
                "walks_ticked": int(t["walks_ticked"]), "walks_locked": int(t["walks_locked"]),
                "snoozes": int(t["snoozes"]), "longest_sit_min": round(t["longest_sit_s"] / 60)}

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for d in sorted(days):
            w.writerow(day_row(d, days[d]))
    doc = {
        "source": "Sloucher posture app" + (f" {version}" if version else ""),
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "about": "Posture at a desk from a front webcam, compared with the user's own upright calibration. "
                 "Field meanings: https://github.com/naraianlegrand/sloucher_ai/blob/main/docs/STATS.md",
        "days": [day_row(d, days[d]) for d in sorted(days)],
        "hours_of_day": [{"hour": h, "upright_pct": t["upright_pct"], "sitting_min": t["sitting_min"],
                          "bad_min": t["bad_min"], "alerts": int(t["alerts"])} for h, t in hours.items()],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)
    return csv_path, json_path
