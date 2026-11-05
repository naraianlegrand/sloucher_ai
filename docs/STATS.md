# Your posture stats

Sloucher keeps a few numbers about every minute you spend in the chair, so you can see how much you slouched, how
quickly you sat up again, and whether you're improving. Open them from the tray: **Stats** (or double-click the
icon). It refreshes itself every minute; **Refresh** updates it now.

They're counted from the posture calls the NPU already makes, twice a second. There's no extra model, and nothing
extra runs while the window is closed.

## What the window shows

- **Today:** upright %, time slouched, alerts, average time to sit up after an alert, slouches you fixed yourself
  before an alert came, and walks (done / reminded).
- **Last 7 days:** upright % per day, and the change against the 7 days before.
- **Best and hardest hour of the day:** your most and least upright hour over the last 7 days. Hours with less than
  10 minutes of data are left out.
- **Copy for my AI coach:** a short plain-English summary of the last 7 days, copied to the clipboard. Paste it into
  Gemini, ChatGPT, Claude or a coach app, and ask what to change.
- **Export…:** saves `sloucher-days-DATE.csv` (one row per day, opens in Excel) and `sloucher-stats-DATE.json` (days
  and hours of the day) to a folder you choose.

Why paste rather than a direct link to a health app? Google Health Connect is Android-only, and as far as we know the
AI coaches don't accept data from a Windows app. Pasting works with all of them today, and you see exactly what you
share.

## What counts

| Term | Meaning |
|---|---|
| In the chair | Someone's face and shoulders are in view (4 or more keypoints). Paused, locked and away time isn't counted. |
| Upright % | Good-posture time / (good + slouched + leaned-in time). Moments where your eyes or shoulders weren't visible are left out. |
| Slouched | Eye drop (eyes to shoulder line, / shoulder width) below 96% of your calibration. Looking down at a phone counts too. |
| Leaned in | Face ratio (eye to eye, / shoulder width) above 115% of your calibration: your face is closer to the screen than your shoulders. |
| Alert | The glow came on: bad posture for 80% of the last 30 s. |
| To sit up | Seconds from the alert to good posture. If you leave the chair instead, it doesn't count. |
| Fixed yourself | A slouch of at least 5 s that you fixed before the alert came. |
| Walk | Away from the chair for 30 s or more. **Seen:** the camera saw the empty chair. **Locked:** the screen was locked that long (Win+L). **Ticked:** you pressed "I walked". |
| Walks reminded | Times the hourly reminder came. Repeat nudges aren't counted again. |
| Longest sit | The longest time in the chair before a walk. |

## The files

`%LOCALAPPDATA%\Sloucher\stats\YYYY-MM.csv`, one row per minute in the chair, written when each minute ends (and on
Pause and Quit):

`minute, sitting_s, good_s, slouch_s, lean_s, alerts, corrected, corrected_s, self_corrected, walks_due, walks_seen,
walks_ticked, walks_locked, snoozes, longest_sit_s`

Numbers only: never images, video or keypoints. Delete the folder to start over; Sloucher makes a new one.
