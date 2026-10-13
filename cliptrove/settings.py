"""Your settings: where your clips are and where edited copies go (settings.json in the data folder).

{
  "sources": {"gg": {"enabled": true},
              "folders": [{"path": "C:\\\\Users\\\\you\\\\Videos\\\\Radeon ReLive", "recorder": "amd", "enabled": true}]},
  "exportDir": "",   (empty: "Edited Clips" inside your first clips folder)
  "port": 48650,
  "setupDone": true  (false until the first-start setup is finished or skipped)
}
"""
import configparser
import copy
import glob
import os
import sys

from . import paths
from .sources.folder import RECORDERS, count_videos
from .util import load_json, path_key, save_json

DEFAULT_PORT = 48650
DEFAULTS = {"version": 1, "sources": {"gg": {"enabled": True}, "folders": []}, "exportDir": "", "port": DEFAULT_PORT,
            "setupDone": True}


def clean_folders(folders):
    out, seen = [], set()
    for f in folders or []:
        if isinstance(f, str):
            f = {"path": f}
        if not isinstance(f, dict) or not str(f.get("path") or "").strip():
            continue
        path = os.path.normpath(os.path.expandvars(os.path.expanduser(str(f["path"]).strip().strip('"'))))
        if path_key(path) in seen:
            continue
        seen.add(path_key(path))
        rec = f.get("recorder") if f.get("recorder") in RECORDERS else "auto"
        out.append({"path": path, "recorder": rec, "enabled": f.get("enabled", True) is not False})
    return out


def normalize(cfg):
    out = copy.deepcopy(DEFAULTS)
    src = cfg.get("sources") if isinstance(cfg.get("sources"), dict) else {}
    gg = src.get("gg") if isinstance(src.get("gg"), dict) else {}
    out["sources"]["gg"]["enabled"] = gg.get("enabled", True) is not False
    out["sources"]["folders"] = clean_folders(src.get("folders"))
    out["exportDir"] = os.path.normpath(cfg["exportDir"].strip()) if str(cfg.get("exportDir") or "").strip() else ""
    port = cfg.get("port")
    out["port"] = port if isinstance(port, int) and 1024 <= port <= 65535 else DEFAULT_PORT
    out["setupDone"] = cfg.get("setupDone", True) is not False  # settings saved before setup existed count as done
    return out


def load():
    saved = load_json(paths.SETTINGS, None)
    if not isinstance(saved, dict):
        return normalize({"setupDone": False})  # the first start: show the setup
    return normalize(saved)


def save(cfg):
    save_json(paths.SETTINGS, normalize(cfg), indent=2)


# ---------- finding recorders' folders on this PC ----------

def _reg(path, value):
    """A value from the current user's registry, or None."""
    if sys.platform != "win32":
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            data, kind = winreg.QueryValueEx(k, value)
    except OSError:
        return None
    if isinstance(data, bytes):  # NVIDIA stores its folder as UTF-16 bytes
        data = data.decode("utf-16-le", errors="ignore")
    data = str(data).split("\x00")[0].strip()
    return os.path.expandvars(data) if data else None


def videos_dir():
    found = _reg(r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders", "My Video")
    return found if found and os.path.isdir(found) else os.path.join(os.path.expanduser("~"), "Videos")


def obs_folders():
    """Where OBS Studio saves recordings, for each of its profiles (the active profile first)."""
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("APPDATA", ""), "obs-studio")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/obs-studio")
    else:
        base = os.path.expanduser("~/.config/obs-studio")

    def ini(path):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(path, encoding="utf-8-sig")
        except (configparser.Error, OSError, UnicodeDecodeError):
            pass
        return cp

    active = ini(os.path.join(base, "global.ini")).get("Basic", "ProfileDir", fallback="")
    profiles = sorted(glob.glob(os.path.join(base, "basic", "profiles", "*", "basic.ini")),
                      key=lambda p: os.path.basename(os.path.dirname(p)) != active)
    out = []
    for p in profiles:
        cp = ini(p)
        if cp.get("Output", "Mode", fallback="Simple").lower() == "advanced":
            key = "FFFilePath" if cp.get("AdvOut", "RecType", fallback="Standard") == "FFmpeg" else "RecFilePath"
            folder = cp.get("AdvOut", key, fallback="")
        else:
            folder = cp.get("SimpleOutput", "FilePath", fallback="")
        if folder:
            out.append(os.path.normpath(folder))
    return out


def detect(skip=(), include_empty=False):
    """Recorders' clip folders found on this PC that have videos in them (or, with include_empty, that exist),
    and aren't in `skip` yet."""
    vids = videos_dir()
    candidates = [
        ("amd", _reg(r"Software\AMD\DVR", "CaptureFileOutput")),
        ("amd", os.path.join(vids, "Radeon ReLive")),
        ("nvidia", _reg(r"Software\NVIDIA Corporation\Global\ShadowPlay\NVSPCAPS", "DefaultPathW")),
        ("nvidia", os.path.join(vids, "NVIDIA")),
        ("xbox", os.path.join(vids, "Captures")),
        ("medal", os.path.join(vids, "Medal")),
    ] + [("obs", p) for p in obs_folders()]
    seen, out = {path_key(p) for p in skip}, []
    for rec, path in candidates:
        if not path or not os.path.isdir(path) or path_key(path) in seen:
            continue
        seen.add(path_key(path))
        n = count_videos(path, cap=500)
        if n or include_empty:
            out.append({"path": os.path.normpath(path), "recorder": rec, "label": RECORDERS[rec], "videos": n})
    return out
