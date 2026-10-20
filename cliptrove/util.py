"""Small helpers shared by the rest of Cliptrove."""
import datetime as dt
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def norm(name):
    """A game name reduced to lowercase letters and digits, so "Counter-strike 2" matches "Counter-Strike 2"."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def clip_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def iso_time(ts):
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "")
    return " ".join(s.split()).strip(" .")[:100]


def path_key(path):
    """A path in a form that compares equal however it was typed (case and slashes on Windows)."""
    return os.path.normcase(os.path.abspath(path))


def is_inside(path, folder):
    try:
        return os.path.commonpath([path_key(path), path_key(folder)]) == path_key(folder)
    except ValueError:  # different drives
        return False


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj, indent=None):
    """Write the file in one go, so a crash never leaves half a file behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
    os.replace(tmp, path)


def retry_io(action, tries=12):
    """Windows won't replace a file while something has it open; the browser only holds it briefly."""
    for i in range(tries):
        try:
            return action()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.25)


def bundled_tools_dir():
    """Where the Windows app keeps the ffmpeg it comes with (next to Cliptrove.exe), or None when running from
    the source code."""
    return os.path.join(os.path.dirname(sys.executable), "ffmpeg") if getattr(sys, "frozen", False) else None


def find_tool(name):
    """ffmpeg / ffprobe: the copy that comes with the Windows app, else on the PATH, or where winget and the
    usual installers put them."""
    exe = name + (".exe" if sys.platform == "win32" else "")
    bundled = bundled_tools_dir()
    if bundled and os.path.isfile(os.path.join(bundled, exe)):
        return os.path.join(bundled, exe)
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    patterns = [
        os.path.join(local, "Microsoft", "WinGet", "Links", exe),
        os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", exe),
        os.path.join(local, "Microsoft", "WinGet", "Packages", "BtbN.FFmpeg*", "*", "bin", exe),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "ffmpeg", "bin", exe),
        os.path.join("C:\\", "ffmpeg", "bin", exe),
        os.path.join("/opt/homebrew/bin", exe),
        os.path.join("/usr/local/bin", exe),
    ]
    for pattern in patterns:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def run(args, timeout=600):
    return subprocess.run(args, capture_output=True, text=True, errors="replace",
                          creationflags=NO_WINDOW, timeout=timeout)


def open_folder(path, select=False):
    """Show a folder (or a file, selected in its folder) in Explorer / Finder / the file manager."""
    if sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{path}"' if select else f'explorer "{path}"')
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if select else ["open", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) if select else path])
