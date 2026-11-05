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
    assert [e[1][0] for e in events] == ["walk_due", "walk_nudge", "not_done", "walk_nudge", "break_done",
                                         "break_taken"]
    assert events[0][0] == 3600             # the 3 s drop didn't pause the clock
    assert events[2][1] == ("not_done", 18)
    assert round(events[4][1][1]) == 3600 + 6 * 60 + 12 + 70     # sat that long before the 45 s walk
    assert round(events[5][1][1]) == 10 + 20 * 60                 # the walk on my own, after 20 min 10 s


def test_short_timings_for_trying_it_out():
    events = simulate([(61, True), (12, False), (5, True)], BreakCoach(sit_limit=60, break_s=10))
    assert [e[1][0] for e in events] == ["walk_due", "break_done"]


def test_i_walked_resets_the_clock():
    c = BreakCoach(sit_limit=60, break_s=30)
    events = simulate([(61, True)], c)
    assert events[-1][1] == ("walk_due",) and c.due
    c.walked(61)
    assert not c.due and c.sitting(61) == 0
    assert simulate([(1, True)], c) == []          # no "break_done" on the next frame either


def test_snooze_puts_the_nudge_off():
    c = BreakCoach(sit_limit=60, break_s=30, nudge_every=300)
    simulate([(61, True)], c)
    c.snooze(61, 600)
    assert c.next_nudge == 661 and c.due


def test_resume_keeps_the_sitting_clock():
    # Sit 10 min, pause for 2 min (no frames), resume: still 12 min of sitting, no break counted
    c = BreakCoach()
    t = 0.0
    while t < 600:
        c.update(t, True)
        t += 0.5
    # The NPU warms up for ~40 s after Resume, so the first frame comes at 760 s
    c.resume()
    assert c.update(760, True) is None
    assert c.sitting(760) == 760


def test_a_real_break_after_resume_still_counts():
    c = BreakCoach()
    for i in range(1200):
        c.update(i * 0.5, True)
    c.resume()
    c.update(700, False)                # first frame after Resume: chair empty
    assert c.update(740, True)[0] == "break_taken"
