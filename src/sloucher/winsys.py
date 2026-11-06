"""Windows plumbing: is the screen locked, start with Windows, one copy at a time."""
import ctypes
import os
import sys

from . import APP_NAME, paths

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class _WtsInfoLevel1(ctypes.Structure):
    _fields_ = [("SessionId", ctypes.c_ulong), ("SessionState", ctypes.c_int), ("SessionFlags", ctypes.c_long),
                ("WinStationName", ctypes.c_wchar * 33), ("UserName", ctypes.c_wchar * 21),
                ("DomainName", ctypes.c_wchar * 18), ("LogonTime", ctypes.c_longlong),
                ("ConnectTime", ctypes.c_longlong), ("DisconnectTime", ctypes.c_longlong),
                ("LastInputTime", ctypes.c_longlong), ("CurrentTime", ctypes.c_longlong),
                ("Counters", ctypes.c_ulong * 6)]


class _WtsInfoEx(ctypes.Structure):
    _fields_ = [("Level", ctypes.c_ulong), ("Data", _WtsInfoLevel1)]


def screen_locked():
    """True while this Windows session is locked (Win+L), also once the display has turned off.

    Asks the session itself (WTSSessionInfoEx). Checking the input desktop instead only works while
    the lock screen is showing: once the screen goes black it reads "unlocked" again (seen in testing).
    """
    wts = ctypes.windll.wtsapi32
    buf, size = ctypes.c_void_p(), ctypes.c_ulong()
    if not wts.WTSQuerySessionInformationW(None, ctypes.c_ulong(0xFFFFFFFF), 25, ctypes.byref(buf), ctypes.byref(size)):
        return False                    # can't tell: assume unlocked, the camera still decides
    try:
        info = ctypes.cast(buf, ctypes.POINTER(_WtsInfoEx)).contents
        return info.Level == 1 and info.Data.SessionFlags == 0          # WTS_SESSIONSTATE_LOCK
    finally:
        wts.WTSFreeMemory(buf)


def autostart_command():
    if paths.frozen():
        return f'"{sys.executable}"'
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pythonw if os.path.exists(pythonw) else sys.executable}" -m sloucher'


def autostart_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def already_running():
    """One Sloucher at a time: two would fight over the camera and the NPU."""
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\Sloucher.App")
    return ctypes.windll.kernel32.GetLastError() == 183        # ERROR_ALREADY_EXISTS
