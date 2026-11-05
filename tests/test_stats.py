import datetime as dt
import os

from sloucher import stats


class Clock:
    """Wall clock for the rows: starts at a fixed local time, moved by the test."""
    def __init__(self, y=2026, m=11, d=5, h=10):
        self.t = dt.datetime(y, m, d, h).timestamp()

    def __call__(self):
        return self.t


def run(rec, clock, script, fps=2, start=0.0, alerting_for=()):
    """script: (seconds, present, state, alerting); advances both clocks together."""
    t = start
    for seconds, present, state, alerting in script:
        end = t + seconds
        while t < end:
            rec.frame(t, present, state, alerting)
            t += 1 / fps
            clock.t += 1 / fps
    return t


def test_minutes_and_upright_share(tmp_path):
    clock = Clock()
    rec = stats.Recorder(str(tmp_path), clock)
    run(rec, clock, [(90, True, "good", False), (30, True, "slouch", False)])
    rec.flush()
    rows = stats.load(str(tmp_path))
    assert [r["minute"] for r in rows] == ["2026-11-05 10:00", "2026-11-05 10:01"]
    t = stats.total(rows)
    assert round(t["sitting_s"]) == 120
    assert t["upright_pct"] == 75


def test_alert_corrected_and_self_corrected(tmp_path):
    clock = Clock()
    rec = stats.Recorder(str(tmp_path), clock)
    run(rec, clock, [
        (60, True, "good", False),
        (8, True, "slouch", False),      # fixed before any alert: self-corrected
        (20, True, "good", False),
        (30, True, "slouch", False),     # long slouch ...
        (6, True, "slouch", True),       # ... alert on for 6 s ...
        (10, True, "good", False),       # ... sat up: corrected after 6 s
        (3, True, "slouch", False),      # too short to count
        (5, True, "good", False),
    ])
    rec.flush()
    t = stats.total(stats.load(str(tmp_path)))
    assert t["alerts"] == 1 and t["corrected"] == 1
    assert t["avg_correct_s"] == 6
    assert t["self_corrected"] == 1


def test_leaving_isnt_correcting_and_gaps_dont_count(tmp_path):
    clock = Clock()
    rec = stats.Recorder(str(tmp_path), clock)
    t = run(rec, clock, [(40, True, "slouch", False), (5, True, "slouch", True), (20, False, "unknown", False)])
    rec.gap()                      # e.g. screen locked for 10 min
    clock.t += 600
    run(rec, clock, [(30, True, "good", False)], start=t + 600)
    rec.flush()
    s = stats.total(stats.load(str(tmp_path)))
    assert s["alerts"] == 1 and s["corrected"] == 0
    # 45 s + 30 s, less the first half-second of each stretch; the 20 s away and the 10 min locked aren't sitting
    assert round(s["sitting_s"]) == 74


def test_walks(tmp_path):
    clock = Clock()
    rec = stats.Recorder(str(tmp_path), clock)
    rec.walk_due(); rec.snoozed(); rec.walk_done("ticked", 3700)
    rec.walk_due(); rec.walk_done("locked", 3650)
    rec.walk_done("seen", 1200)
    rec.flush()
    t = stats.total(stats.load(str(tmp_path)))
    assert t["walks_due"] == 2 and t["walks_done"] == 3 and t["snoozes"] == 1
    assert t["longest_sit_s"] == 3700


def week_of_rows(folder):
    """Two weeks: the first 60% upright, the second 75%, slouching in the afternoon."""
    clock = Clock()
    rec = stats.Recorder(folder, clock)
    for day in range(1, 15):          # Oct 23 .. Nov 5
        for h in (10, 15):
            clock.t = (dt.datetime(2026, 10, 22, h) + dt.timedelta(days=day)).timestamp()
            good = 0.75 if day > 7 else 0.6
            if h == 15:
                good -= 0.2
            run(rec, clock, [(1200 * good, True, "good", False), (1200 * (1 - good), True, "slouch", False)])
            rec.flush()
            rec.gap()
    return stats.load(folder)


def test_report_trend_and_coach_summary(tmp_path):
    rows = week_of_rows(str(tmp_path))
    rep = stats.report(rows, today=dt.date(2026, 11, 5))
    assert rep["week"]["upright_pct"] == 65 and rep["prev_week"]["upright_pct"] == 50
    assert stats.change(rep["week"], rep["prev_week"]) == "+15 points"
    (bh, _), (wh, _) = rep["best_hour"], rep["worst_hour"]
    assert (bh, wh) == (10, 15)
    assert len(rep["days"]) == 7 and rep["days"][-1][0] == dt.date(2026, 11, 5)
    text = stats.coach_summary(rep)
    assert "Upright 65% of the time" in text and "+15 points" in text
    assert "Worst: 15:00-16:00" in text
    assert "what's one habit" in text


def test_coach_summary_with_no_data():
    rep = stats.report([], today=dt.date(2026, 11, 5))
    assert "No sitting time was recorded" in stats.coach_summary(rep)


def test_export(tmp_path):
    rows = week_of_rows(str(tmp_path / "stats"))
    csv_path, json_path = stats.export(rows, str(tmp_path / "out"), "0.2.0")
    assert os.path.exists(csv_path) and os.path.exists(json_path)
    with open(csv_path, encoding="utf-8") as f:
        assert f.readline().startswith("date,sitting_min,upright_pct")
        assert len(f.readlines()) == 14
