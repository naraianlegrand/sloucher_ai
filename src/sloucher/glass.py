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
