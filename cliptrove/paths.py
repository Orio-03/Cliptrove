"""Where Cliptrove keeps its settings, what you add to your clips, and its caches.

Everything lives in one data folder (on Windows %LOCALAPPDATA%\\Cliptrove). Set CLIPTROVE_DATA or pass
--data-dir to use another one. Your clip files themselves are never moved or changed.
"""
import os
import sys

LEGACY_NAMES = ("ClipShelf",)  # what the app (and its data folder) used to be called


def default_data_dir():
    env = os.environ.get("CLIPTROVE_DATA")
    if env:
        return os.path.abspath(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "Cliptrove")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Cliptrove")
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "cliptrove")


def adopt_legacy():
    """Earlier versions kept their data under an older name: move it to the current folder (once)."""
    if os.environ.get("CLIPTROVE_DATA") or os.path.exists(DATA):
        return None
    for name in LEGACY_NAMES:
        old = os.path.join(os.path.dirname(DATA), name)
        if os.path.isdir(old):
            try:
                os.replace(old, DATA)
                return old
            except OSError:
                return None
    return None


def configure(data_dir=None):
    global DATA, SETTINGS, LIBRARY, INDEX, COVER_CACHE, COVERS_DIR, CACHE, THUMBS, AUDIO, VIDEO, LOG
    DATA = os.path.abspath(data_dir) if data_dir else default_data_dir()
    SETTINGS = os.path.join(DATA, "settings.json")
    LIBRARY = os.path.join(DATA, "library.json")  # nicknames, favorites, trims, audio levels, games, change log
    INDEX = os.path.join(DATA, "index.json")  # what's been read from the clips in your folders (length, tracks)
    COVER_CACHE = os.path.join(DATA, "covers.json")
    COVERS_DIR = os.path.join(DATA, "covers")  # your own cover pictures, named after the game
    CACHE = os.path.join(DATA, "cache")
    THUMBS = os.path.join(CACHE, "thumbs")
    AUDIO = os.path.join(CACHE, "audio")  # Chat/Mic tracks pulled out of clips
    VIDEO = os.path.join(CACHE, "video")  # .mkv and similar clips repackaged as .mp4 so the browser can play them
    LOG = os.path.join(DATA, "cliptrove.log")  # used when Cliptrove runs in the background (no window)


configure()
