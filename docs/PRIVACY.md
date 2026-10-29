# Privacy

Sloucher watches you through your webcam all day, so it's built to tell no one. It's designed with Québec's Law 25
in mind: the most private settings by default, as little information as possible, and nothing that leaves your laptop.

- **Your video stays on your laptop.** Each camera frame goes to your laptop's NPU, becomes 17 body points, and is
  then discarded. Sloucher never saves an image or a video.
- **Nothing is sent anywhere.** No account, no cloud, no telemetry, no analytics. Sloucher makes no network
  connections; the only socket it opens is between its own two processes on your laptop (127.0.0.1).
- **Your calibration is three numbers**, saved in `%LOCALAPPDATA%\Sloucher\calibration.json`. Delete the file, or
  choose "remove my settings" when uninstalling, and they're gone.
- **You're in control.** Pause turns the camera and the NPU off until you resume. Quit stops everything.
- **Logs** in `%LOCALAPPDATA%\Sloucher\logs` record what the app did (started, NPU ready, calibrated), never images
  or keypoints.

Questions: https://sloucher.karthikeyanumesh.com/privacy/
