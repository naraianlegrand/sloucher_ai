"""Windows 11 glass behind a Tk window: Mica for the Stats window, Acrylic for the walk card.

Windows draws the blur itself (DWM), so it costs the app nothing. The window's pure-black pixels
become see-through to the backdrop, so pages built on GLASS (#000000) show it; other colours are
drawn on top, a little lighter. On older Windows nothing changes and the black stays black.
"""
import ctypes
import logging

log = logging.getLogger(__name__)

GLASS = "#000000"           # background that shows the backdrop
TILE = "#262626"            # frosted panel on top of it
BACKDROPS = {"mica": 2, "acrylic": 3}

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int), ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


def _set(hwnd, attribute, value):
    v = ctypes.c_int(value)
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v)) == 0


def apply(win, backdrop="mica"):
    """Dark title bar, rounded corners and the backdrop. -> True if the glass is on."""
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        _set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 1)
        _set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, 2)               # round
        if not _set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, BACKDROPS[backdrop]):
            return False                                            # before Windows 11 22H2: keep it solid
        m = _Margins(-1, -1, -1, -1)
        return ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m)) == 0
    except (AttributeError, OSError):
        log.debug("no glass", exc_info=True)
        return False


def tint(colour, backdrop=0x22):
    """The colour to draw so it looks like `colour` on glass: Windows adds the backdrop's own colour
    (about #222222 for dark Mica, #505050 for Acrylic) to what we draw, so take that off first."""
    r, g, b = (max(0, int(colour[i:i + 2], 16) - backdrop) for i in (1, 3, 5))
    return f"#{r:02X}{g:02X}{b:02X}"
