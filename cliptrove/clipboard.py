"""Copy files to the Windows clipboard the way Explorer's Copy does, so Ctrl+V in Discord (or a folder) pastes
the saved clip itself."""
import ctypes
import struct
import sys
import time

CF_HDROP = 15
GMEM_MOVEABLE = 0x0002
DROPEFFECT_COPY = 1


def supported():
    return sys.platform == "win32"


def dropfiles(paths):
    """The clipboard's file-list format (DROPFILES, then the paths as wide strings, ending with an empty one)."""
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # offset of the list, drop point x/y, non-client area, wide
    return header + "".join(p + "\0" for p in paths).encode("utf-16-le") + "\0".encode("utf-16-le")


def _api():
    from ctypes import wintypes
    user32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes, user32.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes, user32.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    user32.GetClipboardData.argtypes, user32.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
    user32.RegisterClipboardFormatW.argtypes, user32.RegisterClipboardFormatW.restype = [wintypes.LPCWSTR], wintypes.UINT
    kernel32.GlobalAlloc.argtypes, kernel32.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes, kernel32.GlobalLock.restype = [wintypes.HGLOBAL], ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes, kernel32.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
    kernel32.GlobalFree.argtypes, kernel32.GlobalFree.restype = [wintypes.HGLOBAL], wintypes.HGLOBAL
    kernel32.GlobalSize.argtypes, kernel32.GlobalSize.restype = [wintypes.HGLOBAL], ctypes.c_size_t
    return user32, kernel32


def _open(user32):
    for _ in range(20):  # another program may be holding the clipboard for a moment
        if user32.OpenClipboard(None):
            return
        time.sleep(0.05)
    raise RuntimeError("The clipboard is busy. Try again in a moment.")


def _put(user32, kernel32, fmt, data):
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    if not handle:
        raise MemoryError("Couldn't copy to the clipboard")
    ptr = kernel32.GlobalLock(handle)
    ctypes.memmove(ptr, data, len(data))
    kernel32.GlobalUnlock(handle)
    if not user32.SetClipboardData(fmt, handle):  # on success the clipboard owns the memory
        kernel32.GlobalFree(handle)
        raise RuntimeError("Couldn't copy to the clipboard")


def copy_files(paths):
    if not supported():
        raise ValueError("Copying files to the clipboard works on Windows only")
    user32, kernel32 = _api()
    _open(user32)
    try:
        user32.EmptyClipboard()
        _put(user32, kernel32, CF_HDROP, dropfiles(paths))
        effect = user32.RegisterClipboardFormatW("Preferred DropEffect")  # paste as a copy, not a move
        if effect:
            _put(user32, kernel32, effect, struct.pack("<I", DROPEFFECT_COPY))
    finally:
        user32.CloseClipboard()


def copied_files():
    """The files on the clipboard (used by the tests)."""
    user32, kernel32 = _api()
    _open(user32)
    try:
        handle = user32.GetClipboardData(CF_HDROP)
        if not handle:
            return []
        ptr = kernel32.GlobalLock(handle)
        try:
            raw = ctypes.string_at(ptr, kernel32.GlobalSize(handle))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()
    offset, wide = struct.unpack_from("<I", raw)[0], struct.unpack_from("<I", raw, 16)[0]
    text = raw[offset:].decode("utf-16-le" if wide else "mbcs", errors="replace")
    return [p for p in text.split("\0\0")[0].split("\0") if p]
