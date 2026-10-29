"""Hourly walk reminder: the camera can't see you walk, but it sees the empty chair.

- Sitting time counts while you're in the chair. Gaps shorter than AWAY_GRACE
  (a missed detection, reaching for something) are ignored.
- After SIT_LIMIT of sitting: "time to walk for 30 s", repeated every NUDGE_EVERY
  while you stay.
- Leaving for BREAK_S or longer is a break: the sitting clock resets. That also
  works if you get up on your own before the reminder.
- Coming back early from a due break: "not done yet, N s left", and a sooner nudge.

Pure logic: feed it (time, present) once per frame. The clock is passed in, so
it can be tested without waiting an hour.
"""
SIT_LIMIT = 60 * 60     # s of sitting before the walk reminder
BREAK_S = 30            # s away that count as a break
AWAY_GRACE = 5          # s of no person before you count as away
NUDGE_EVERY = 5 * 60    # s between repeat reminders while the walk is due
RETRY_NUDGE = 60        # s until the next nudge after coming back too early


class BreakCoach:
    def __init__(self, sit_limit=SIT_LIMIT, break_s=BREAK_S, away_grace=AWAY_GRACE,
                 nudge_every=NUDGE_EVERY, retry_nudge=RETRY_NUDGE):
        self.sit_limit, self.break_s, self.away_grace = sit_limit, break_s, away_grace
        self.nudge_every, self.retry_nudge = nudge_every, retry_nudge
        self.sit_start = None       # when the current sitting stretch began
        self.last_seen = None       # last time a person was in the frame
        self.due = False            # walk reminder active
        self.next_nudge = None

    def sitting(self, now):
        """Seconds of the current sitting stretch (0 when nobody has sat down yet)."""
        return 0.0 if self.sit_start is None else now - self.sit_start

    def away(self, now):
        return self.last_seen is not None and now - self.last_seen >= self.away_grace

    def update(self, now, present):
        """-> None or an event: ("walk_due",), ("walk_nudge",), ("not_done", seconds_left), ("break_done",)."""
        if not present:
            return None
        event = None
        gap = 0.0 if self.last_seen is None else now - self.last_seen
        self.last_seen = now
        if self.sit_start is None or gap >= self.break_s:
            # First sit-down, or back from a full break
            if self.due:
                event = ("break_done",)
            self.sit_start, self.due, self.next_nudge = now, False, None
            return event
        if gap >= self.away_grace and self.due:
            self.next_nudge = now + self.retry_nudge
            return ("not_done", round(self.break_s - gap))
        if not self.due and self.sitting(now) >= self.sit_limit:
            self.due, self.next_nudge = True, now + self.nudge_every
            return ("walk_due",)
        if self.due and now >= self.next_nudge:
            self.next_nudge = now + self.nudge_every
            return ("walk_nudge",)
        return None
