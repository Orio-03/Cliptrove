"""Starting Cliptrove in the background when you sign in to Windows, so the site is always there.

This is a shortcut in your Startup folder that runs Cliptrove.exe --background (or, when running from the source
code, Cliptrove.pyw --background with pythonw), so there's no window.
"""
import os
import shutil
import subprocess
import sys

from .util import NO_WINDOW

FROZEN = getattr(sys, "frozen", False)  # running as Cliptrove.exe
HERE = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STARTUP = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
LINK = os.path.join(STARTUP, "Cliptrove.lnk")
LEGACY_LINKS = [os.path.join(STARTUP, "ClipShelf.lnk")]  # left by earlier versions


def supported():
    return sys.platform == "win32" and os.path.isdir(STARTUP)


def enabled():
    return supported() and os.path.exists(LINK)


def launcher():
    """(program, arguments) that start Cliptrove without a window."""
    if FROZEN:
        return sys.executable, "--background"
    script = os.path.join(HERE, "Cliptrove.pyw")
    exe = sys.executable or ""
    if os.path.basename(exe).lower() == "python.exe":
        exe = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.basename(exe).lower() == "pythonw.exe" and os.path.exists(exe):
        return exe, f'"{script}" --background'
    pyw = shutil.which("pyw")
    if pyw:
        return pyw, f'-3 "{script}" --background'
    raise RuntimeError("Couldn't find pythonw.exe to start Cliptrove with")


def enable():
    if not supported():
        raise RuntimeError("Starting with Windows only works on Windows")
    exe, args = launcher()
    env = dict(os.environ, CS_LINK=LINK, CS_TARGET=exe, CS_ARGS=args, CS_DIR=HERE)
    script = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CS_LINK); "
              "$s.TargetPath = $env:CS_TARGET; $s.Arguments = $env:CS_ARGS; $s.WorkingDirectory = $env:CS_DIR; "
              "$s.Description = 'Cliptrove: your clip library, in the background'; $s.WindowStyle = 7; $s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                       capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=60)
    if r.returncode or not os.path.exists(LINK):
        raise RuntimeError((r.stderr.strip().splitlines() or ["Couldn't create the startup shortcut"])[-1])
    remove_legacy()


def remove_legacy():
    """Shortcuts left by earlier versions would start an old copy as well."""
    for old in LEGACY_LINKS:
        try:
            os.remove(old)
        except OSError:
            pass


def disable():
    if os.path.exists(LINK):
        os.remove(LINK)
