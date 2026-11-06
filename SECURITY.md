# Security

Sloucher watches your webcam all day, so security and privacy matter here more than in most apps.

## What Sloucher does and doesn't do
- Camera frames go to your laptop's NPU, become 17 body points, and are discarded. No image or video is ever saved.
- No network connections, no account, no telemetry. The only socket is between Sloucher's own two processes on
  `127.0.0.1`.
- Stored on your laptop: settings, three calibration numbers, posture stats (numbers per minute) and logs, in
  `%LOCALAPPDATA%\Sloucher`. See [docs/PRIVACY.md](docs/PRIVACY.md).

## Reporting a vulnerability
Please **don't open a public issue** for a security problem. Use
[**Report a vulnerability**](https://github.com/naraianlegrand/sloucher_ai/security/advisories/new) (GitHub's private
reporting) instead. Include the version (tray → hover, or `sloucher --version`), what you found, and how to reproduce it.

You'll get a reply within a week. Fixes ship as a patch release, with credit to the reporter unless you'd rather stay
anonymous.

## Supported versions
The latest release gets security fixes.
