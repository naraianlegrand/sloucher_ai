"""The Windows 11 frame for the Stats window and the walk card: dark, rounded, no title bar.

Without the title bar there's no accent-coloured strip (it follows the Windows accent colour,
red on some laptops); the window draws its own close button and is dragged by its background.
The glass itself is drawn by liquid.py. On Windows 10 the corner and colour settings are simply
ignored.
"""
import ctypes
import logging

log = logging.getLogger(__name__)

BG = "#000000"
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_COLOR_NONE = 0xFFFFFFFE


def _set(hwnd, attribute, value):
    v = ctypes.c_uint(value & 0xFFFFFFFF)
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v)) == 0


def hwnd_of(win):
    win.update_idletasks()
    return ctypes.windll.user32.GetParent(win.winfo_id())


def frame(win, titlebar=True):
    """Dark mode, rounded corners, no accent-coloured border; titlebar=False removes the title bar
    (the window keeps its taskbar button)."""
    try:
        hwnd = hwnd_of(win)
        _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
        _set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, 2)               # round
        _set(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
        if not titlebar:
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, -16)                # GWL_STYLE
            user32.SetWindowLongW(hwnd, -16, style & ~0x00C00000)    # no WS_CAPTION
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)        # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
    except (AttributeError, OSError):
        log.debug("window frame settings not available", exc_info=True)


def drag(win):
    """Start moving the window, as if its title bar had been grabbed (call from a mouse press)."""
    hwnd = hwnd_of(win)
    ctypes.windll.user32.ReleaseCapture()
    ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, 2, 0)          # WM_NCLBUTTONDOWN, HTCAPTION


# ---------------------------------------------------------------- the website's headline font

DISPLAY = "Big Shoulders Display ExtraBold"     # weight 800, as on sloucher.karthikeyanumesh.com
_display_ok = None


def load_fonts():
    """Big Shoulders Display (SIL Open Font License, assets/BigShouldersDisplay-OFL.txt), for this
    app only: loaded privately, so nothing is installed on the laptop. Call before the first window."""
    from . import paths
    try:
        ctypes.windll.gdi32.AddFontResourceExW(paths.asset("BigShouldersDisplay.ttf"), 0x10, 0)   # FR_PRIVATE
    except (AttributeError, OSError):
        log.debug("headline font not loaded", exc_info=True)


def display(size):
    """The headline font at `size` points, or Segoe UI Black (a bit smaller) if it didn't load."""
    global _display_ok
    if _display_ok is None:
        import tkinter.font
        _display_ok = DISPLAY in tkinter.font.families()
    return (DISPLAY, size) if _display_ok else ("Segoe UI Black", round(size * 0.78))


def baseline_y(font, y_px):
    """Canvas y (pixels) for a south-anchored text so its baseline lands on y_px: the headline font
    has a lot of room above its capitals, so it's placed by its baseline rather than its box."""
    import tkinter.font
    return y_px + tkinter.font.Font(font=font).metrics("descent")
