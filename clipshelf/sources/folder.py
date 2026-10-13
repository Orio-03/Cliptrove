"""Any folder of videos as a clip source: NVIDIA, AMD, Xbox Game Bar, OBS, Medal, or clips you keep yourself.

The game and date come from each file's name and folder (see names.py). Length and audio tracks are read with
ffprobe once per file and remembered in index.json, so only new or changed files are read again.
"""
import datetime as dt
import os

from ..names import game_from_folders, parse_name
from ..util import iso_time, path_key

VIDEO_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".flv", ".ts"}
# Recorders' working folders, which hold half-made recordings and pictures rather than clips
SKIP_DIRS = {"replay_cache", "thumb_cache", "temp", "tmp", "thumbnails", "editor", "edited clips",
             "$recycle.bin", "system volume information"}
MAX_DEPTH = 4
MIN_SIZE = 64 * 1024
UNSORTED = "Unsorted"

RECORDERS = {  # what can be picked for a folder in Settings
    "auto": "Detect automatically",
    "nvidia": "NVIDIA (ShadowPlay / NVIDIA App)",
    "amd": "AMD (Radeon ReLive / Adrenalin)",
    "xbox": "Xbox Game Bar",
    "obs": "OBS Studio",
    "medal": "Medal",
    "gg": "SteelSeries GG files",
    "other": "Other",
}
SHORT = {"nvidia": "NVIDIA", "amd": "AMD ReLive", "xbox": "Xbox Game Bar", "obs": "OBS", "medal": "Medal",
         "gg": "SteelSeries GG"}

# Audio stream names that only say "this is audio"
GENERIC_TRACK_NAMES = {"", "soundhandler", "sound media handler", "core media audio", "audiohandler", "audio",
                       "stereo", "mono", "surround", "gpac isomedia audio handler", "isomedia file produced by google",
                       "applehandler", "sound"}


def walk(root, exclude=()):
    """(path, stat) for every video under root, skipping recorders' working folders and the excluded ones."""
    stack = [(root, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            name = e.name
            try:
                if e.is_dir(follow_symlinks=False):
                    if (depth < MAX_DEPTH and not name.startswith((".", "$")) and name.lower() not in SKIP_DIRS
                            and path_key(e.path) not in exclude):
                        stack.append((e.path, depth + 1))
                elif os.path.splitext(name)[1].lower() in VIDEO_EXTS and not name.startswith(("~", ".")):
                    st = e.stat()
                    if st.st_size >= MIN_SIZE:
                        yield e.path, st
            except OSError:
                continue


def count_videos(root, cap=2000):
    n = 0
    for _ in walk(root):
        n += 1
        if n >= cap:
            break
    return n


def started(st):
    """When a file was first written: its creation time if that's earlier than its last change."""
    times = [st.st_mtime, getattr(st, "st_birthtime", None)]
    if os.name == "nt":
        times.append(st.st_ctime)  # creation time on Windows
    return min(t for t in times if t)


def track_names(info, recorder):
    n = info.get("audio", 1) if info else 1
    titles = (info or {}).get("titles") or []
    names = []
    for i in range(n):
        t = (titles[i] if i < len(titles) else "") or ""
        if t.strip().lower() not in GENERIC_TRACK_NAMES:
            names.append(t.strip()[:40])
        elif recorder == "gg" and n <= 3:
            names.append(["Game", "Chat", "Mic"][i])
        elif recorder in ("nvidia", "amd") and n == 2:
            names.append(["Game", "Mic"][i])
        elif n == 1:
            names.append("Audio")
        else:
            names.append(f"Track {i + 1}")
    return names


def default_title(when, recorder, stem):
    kind = "Replay" if recorder in ("nvidia", "amd") and ("dvr" in stem.lower() or "replay" in stem.lower()) else "Clip"
    return f"{kind} from {when:%b} {when.day}, {when.year}"


def make_clip(path, st, root, recorder, info):
    """A clip from a folder, in the same shape as every other source's clips."""
    stem = os.path.splitext(os.path.basename(path))[0]
    p = parse_name(stem, near=st.st_mtime)
    if recorder in ("auto", "other", "", None):
        recorder = p.recorder or ""
    when = p.when or dt.datetime.fromtimestamp(started(st))
    recorded = when.astimezone().isoformat(timespec="seconds") if p.when else iso_time(started(st))
    full = float((info or {}).get("duration") or 0.0)
    pk = path_key(path)
    return {
        "key": "f|" + pk,
        "source": "folder",
        "recorder": recorder,
        "root": root,
        "title": p.title or default_title(when, recorder, stem),
        "custom": bool(p.title),
        "file": path,
        "game": p.game or game_from_folders(path, root) or UNSORTED,
        "uid": "",
        "recorded": recorded,
        "full": full,
        "baseTrim": None,
        "ggStar": False,
        "thumb": None,
        "tracks": [{"name": n, "volume": 1.0, "muted": False} for n in track_names(info, recorder)],
        "size": st.st_size,
        "mtime": st.st_mtime,
        "probed": bool(info and info.get("probed")),
    }
