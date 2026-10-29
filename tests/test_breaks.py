from sloucher.breaks import BreakCoach


def simulate(script, coach=None, fps=2):
    """Run (seconds, present) steps at `fps`; return [(time, event)]."""
    c = coach or BreakCoach()
    events, t = [], 0.0
    for seconds, present in script:
        end = t + seconds
        while t < end:
            e = c.update(t, present)
            if e:
                events.append((round(t), e))
            t += 1 / fps
    return events


def test_simulated_hour():
    events = simulate([
        (30 * 60, True),          # 30 min sitting
        (3, False),               # a 3 s detection drop: ignored
        (29 * 60 + 57, True),     # ... to 60 min: walk_due
        (4 * 60, True),           # 4 more min seated: no nudge yet
        (2 * 60, True),           # 5 min after due: walk_nudge
        (12, False),              # leave for 12 s
        (70, True),               # back too early: not_done (18 s left); retry nudge after 60 s
        (45, False),              # a proper 45 s walk
        (10, True),               # back: break_done, clock reset
        (20 * 60, True),          # 20 min sitting
        (40, False),              # a walk on my own before the reminder
        (59 * 60, True),          # 59 min: no reminder, because my own walk reset the clock
    ])
    assert [e[1][0] for e in events] == ["walk_due", "walk_nudge", "not_done", "walk_nudge", "break_done"]
    assert events[0][0] == 3600             # the 3 s drop didn't pause the clock
    assert events[2][1] == ("not_done", 18)


def test_short_timings_for_trying_it_out():
    events = simulate([(61, True), (12, False), (5, True)], BreakCoach(sit_limit=60, break_s=10))
    assert [e[1][0] for e in events] == ["walk_due", "break_done"]
