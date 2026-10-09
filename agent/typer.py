"""Vepisování kódu do aktivního okna přes Win32 SendInput (jako USB čtečka)."""
import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_NUMPAD0 = 0x60
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)


def _key(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)
    return inp


def _press(down: INPUT, up: INPUT):
    arr = (INPUT * 2)(down, up)
    if user32.SendInput(2, arr, ctypes.sizeof(INPUT)) != 2:
        raise OSError(f"SendInput selhal (chyba {ctypes.get_last_error()})")


def _press_vk(vk):
    scan = user32.MapVirtualKeyW(vk, 0)
    _press(_key(vk, scan), _key(vk, scan, KEYEVENTF_KEYUP))


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalFree.argtypes = (wintypes.HGLOBAL,)
user32.OpenClipboard.argtypes = (wintypes.HWND,)
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE


def copy_to_clipboard(text: str) -> bool:
    """Vloží text do schránky Windows (pro ruční Ctrl+V)."""
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    for _ in range(50):  # schránku může mít chvíli otevřenou jiný program (až ~1 s)
        if user32.OpenClipboard(None):
            break
        time.sleep(0.02)
    else:
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False
        ctypes.memmove(kernel32.GlobalLock(handle), data, size)
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        return True  # od teď paměť patří schránce
    finally:
        user32.CloseClipboard()


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def type_code(code: str, mode="unicode", suffix="none", delay_ms=8, clipboard=True) -> str:
    """Vepíše kód do okna s fokusem a vrátí titulek toho okna."""
    if clipboard:
        copy_to_clipboard(code)
    if mode == "off":
        return foreground_title()
    delay = max(delay_ms, 0) / 1000
    for ch in code:
        if mode == "numpad" and ch.isdigit():
            _press_vk(VK_NUMPAD0 + int(ch))
        else:
            _press(_key(scan=ord(ch), flags=KEYEVENTF_UNICODE),
                   _key(scan=ord(ch), flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        time.sleep(delay)
    if suffix == "enter":
        _press_vk(VK_RETURN)
    elif suffix == "tab":
        _press_vk(VK_TAB)
    return foreground_title()
