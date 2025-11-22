import ctypes
from ctypes import wintypes
import subprocess
import time
import os
import sys
import winreg

TARGET_W, TARGET_H = 1440, 1080
STEAM_APPID = "252490"

def _hide_console():
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
            ctypes.windll.kernel32.FreeConsole()
    except Exception:
        pass
_hide_console()

ENUM_CURRENT_SETTINGS = -1
CDS_FULLSCREEN = 0x00000004

DM_PELSWIDTH        = 0x00080000
DM_PELSHEIGHT       = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
DM_BITSPERPEL       = 0x00040000

DISP_CHANGE_SUCCESSFUL = 0

DISPLAY_DEVICE_ACTIVE = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004

SW_RESTORE = 9

class DEVMODE(ctypes.Structure):
    _fields_ = [
        ('dmDeviceName',   wintypes.WCHAR * 32),
        ('dmSpecVersion',  wintypes.WORD),
        ('dmDriverVersion',wintypes.WORD),
        ('dmSize',         wintypes.WORD),
        ('dmDriverExtra',  wintypes.WORD),
        ('dmFields',       wintypes.DWORD),
        ('dmOrientation',  wintypes.SHORT),
        ('dmPaperSize',    wintypes.SHORT),
        ('dmPaperLength',  wintypes.SHORT),
        ('dmPaperWidth',   wintypes.SHORT),
        ('dmScale',        wintypes.SHORT),
        ('dmCopies',       wintypes.SHORT),
        ('dmDefaultSource',wintypes.SHORT),
        ('dmPrintQuality', wintypes.SHORT),
        ('dmColor',        wintypes.SHORT),
        ('dmDuplex',       wintypes.SHORT),
        ('dmYResolution',  wintypes.SHORT),
        ('dmTTOption',     wintypes.SHORT),
        ('dmCollate',      wintypes.SHORT),
        ('dmFormName',     wintypes.WCHAR * 32),
        ('dmLogPixels',    wintypes.WORD),
        ('dmBitsPerPel',   wintypes.DWORD),
        ('dmPelsWidth',    wintypes.DWORD),
        ('dmPelsHeight',   wintypes.DWORD),
        ('dmDisplayFlags', wintypes.DWORD),
        ('dmDisplayFrequency', wintypes.DWORD),
        ('dmICMMethod',    wintypes.DWORD),
        ('dmICMIntent',    wintypes.DWORD),
        ('dmMediaType',    wintypes.DWORD),
        ('dmDitherType',   wintypes.DWORD),
        ('dmReserved1',    wintypes.DWORD),
        ('dmReserved2',    wintypes.DWORD),
        ('dmPanningWidth', wintypes.DWORD),
        ('dmPanningHeight',wintypes.DWORD),
    ]

class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]

user32 = ctypes.WinDLL("user32", use_last_error=True)

EnumDisplayDevicesW = user32.EnumDisplayDevicesW
EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DISPLAY_DEVICE), wintypes.DWORD]
EnumDisplayDevicesW.restype = wintypes.BOOL

EnumDisplaySettingsW = user32.EnumDisplaySettingsW
EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODE)]
EnumDisplaySettingsW.restype = wintypes.BOOL

ChangeDisplaySettingsExW = user32.ChangeDisplaySettingsExW
ChangeDisplaySettingsExW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(DEVMODE),
                                     wintypes.HWND, wintypes.DWORD, wintypes.LPVOID]
ChangeDisplaySettingsExW.restype = wintypes.LONG

EnumWindows = user32.EnumWindows
EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
EnumWindows.restype = wintypes.BOOL

GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
GetWindowThreadProcessId.restype = wintypes.DWORD

IsWindowVisible = user32.IsWindowVisible
IsWindowVisible.argtypes = [wintypes.HWND]
IsWindowVisible.restype = wintypes.BOOL

GetForegroundWindow = user32.GetForegroundWindow
GetForegroundWindow.restype = wintypes.HWND

IsIconic = user32.IsIconic
IsIconic.argtypes = [wintypes.HWND]
IsIconic.restype = wintypes.BOOL

GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW

ShowWindow = user32.ShowWindow

def get_primary_display_name():
    i = 0
    dd = DISPLAY_DEVICE()
    dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
    while EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
        if dd.StateFlags & DISPLAY_DEVICE_ACTIVE and dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE:
            return dd.DeviceName
        i += 1
        dd = DISPLAY_DEVICE()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICE)
    return None

def get_current_mode(dev_name):
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    if not EnumDisplaySettingsW(dev_name, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
        raise OSError("EnumDisplaySettingsW failed")
    return dm

def enumerate_modes(dev_name):
    modes = []
    i = 0
    while True:
        dm = DEVMODE()
        dm.dmSize = ctypes.sizeof(DEVMODE)
        if not EnumDisplaySettingsW(dev_name, i, ctypes.byref(dm)):
            break
        modes.append((dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency, dm.dmBitsPerPel))
        i += 1
    return modes

def pick_target_mode(dev_name):
    modes = enumerate_modes(dev_name)
    cands = [m for m in modes if m[0] == TARGET_W and m[1] == TARGET_H]
    if not cands:
        return None
    cands.sort(key=lambda m: (m[2], m[3]), reverse=True)
    return cands[0]

def _apply_mode(dev_name, w, h, hz=None, bpp=None):
    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT
    dm.dmPelsWidth = w
    dm.dmPelsHeight = h
    if hz:
        dm.dmFields |= DM_DISPLAYFREQUENCY
        dm.dmDisplayFrequency = hz
    if bpp:
        dm.dmFields |= DM_BITSPERPEL
        dm.dmBitsPerPel = bpp
    return ChangeDisplaySettingsExW(dev_name, ctypes.byref(dm), None, CDS_FULLSCREEN, None) == DISP_CHANGE_SUCCESSFUL

def ensure_mode(dev_name, w, h, hz=None, bpp=None):
    cur = get_current_mode(dev_name)
    if cur.dmPelsWidth == w and cur.dmPelsHeight == h and (not hz or cur.dmDisplayFrequency == hz):
        return True
    return _apply_mode(dev_name, w, h, hz, bpp)

def restore_mode(dev_name, original_dm):
    return ChangeDisplaySettingsExW(dev_name, ctypes.byref(original_dm), None, CDS_FULLSCREEN, None) == DISP_CHANGE_SUCCESSFUL

CREATE_NO_WINDOW = 0x08000000

def find_steam_exe():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            for v in ("SteamExe", "SteamPath"):
                try:
                    p, _ = winreg.QueryValueEx(k, v)
                    if v == "SteamPath":
                        p = os.path.join(p, "steam.exe")
                    if os.path.isfile(p):
                        return p
                except FileNotFoundError:
                    pass
    except FileNotFoundError:
        pass
    for p in (r"C:\Program Files (x86)\Steam\steam.exe", r"C:\Program Files\Steam\steam.exe"):
        if os.path.isfile(p):
            return p
    raise FileNotFoundError

def tasklist_pids(image_name):
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
        ).stdout.strip().splitlines()
        pids = []
        for line in out:
            if not line.strip():
                continue
            parts = [s.strip().strip('"') for s in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == image_name.lower():
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
        return pids
    except Exception:
        return []

def enum_windows_for_pid(pid):
    result = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, lparam):
        pid_out = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if pid_out.value == pid and IsWindowVisible(hwnd):
            result.append(hwnd)
        return True
    EnumWindows(cb, 0)
    return result

def find_rust_main_hwnd():
    pids = tasklist_pids("RustClient.exe")
    for pid in pids:
        wins = enum_windows_for_pid(pid)
        if wins:
            return wins[0]
    return None

def is_process_running(image):
    return len(tasklist_pids(image)) > 0

def wait_for_rust_window(timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_process_running("RustClient.exe"):
            hwnd = find_rust_main_hwnd()
            if hwnd:
                if IsIconic(hwnd):
                    ShowWindow(hwnd, SW_RESTORE)
                return hwnd
        time.sleep(1.5)
    return None

def set_unity_rust_screen(width, height, fullscreen=True):
    key_path = r"Software\Facepunch Studios LTD\Rust"
    try:
        hkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE)
    except FileNotFoundError:
        return
    try:
        i = 0
        while True:
            name, _, _ = winreg.EnumValue(hkey, i)
            low = name.lower()
            if low.startswith("screenmanager resolution width"):
                winreg.SetValueEx(hkey, name, 0, winreg.REG_DWORD, int(width))
            elif low.startswith("screenmanager resolution height"):
                winreg.SetValueEx(hkey, name, 0, winreg.REG_DWORD, int(height))
            elif low.startswith("screenmanager fullscreen mode"):
                winreg.SetValueEx(hkey, name, 0, winreg.REG_DWORD, 1 if fullscreen else 0)
            i += 1
    except OSError:
        pass
    finally:
        winreg.CloseKey(hkey)

def main():
    if os.name != "nt":
        return

    dev_name = get_primary_display_name()
    if not dev_name:
        return

    original = get_current_mode(dev_name)
    native_w, native_h, native_hz = original.dmPelsWidth, original.dmPelsHeight, original.dmDisplayFrequency

    target = pick_target_mode(dev_name)
    if not target:
        return
    _, _, best_hz, best_bpp = target

    set_unity_rust_screen(TARGET_W, TARGET_H, fullscreen=True)

    try:
        steam = find_steam_exe()
    except FileNotFoundError:
        return

    launch = [
        steam, "-applaunch", STEAM_APPID,
        "-adapter", "0",
        "-screen-width", str(TARGET_W),
        "-screen-height", str(TARGET_H),
        "-screen-fullscreen", "1",
        "-window-mode", "exclusive",
    ]
    try:
        subprocess.Popen(launch, creationflags=CREATE_NO_WINDOW)
    except Exception:
        return

    hwnd = wait_for_rust_window()
    if not hwnd:
        return

    applied_target = False

    try:
        while is_process_running("RustClient.exe"):
            fg = GetForegroundWindow()
            rust_in_front = (fg == hwnd) and not IsIconic(hwnd)

            if rust_in_front:
                ensure_mode(dev_name, TARGET_W, TARGET_H, best_hz, best_bpp)
                applied_target = True
            else:
                if applied_target:
                    restore_mode(dev_name, original)
                    applied_target = False

            time.sleep(0.3)

    finally:
        cur = get_current_mode(dev_name)
        if (cur.dmPelsWidth != native_w) or (cur.dmPelsHeight != native_h) or (cur.dmDisplayFrequency != native_hz):
            restore_mode(dev_name, original)

if __name__ == "__main__":
    main()
    os._exit(0)
