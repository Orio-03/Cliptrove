"""SteelSeries GG (Moments) as a clip source.

GG keeps its clip library in a SQLite database. Its format isn't documented, so this reads only the columns it
needs, from a temporary copy (GG keeps the file open). A GG update could change them; if that happens, GG clips
stop showing up here but nothing else is affected.
"""
import json
import os
import re
import shutil
import sqlite3
import tempfile

DB = os.path.join(os.environ.get("PROGRAMDATA") or r"C:\ProgramData",
                  "SteelSeries", "GG", "apps", "moments", "db", "database.db")

# Titles GG makes up on its own. Anything else is a title you typed.
DEFAULT_TITLE = re.compile(
    r"(?:(?:Moments|Moments Desktop|Trimmed) clip from|Montage created) [A-Z][a-z]{2} \d{1,2}, \d{4}"
    r"|Auto-clip: .*"
)

# GG's internal names for a few games, and what to show instead.
DISPLAY_NAMES = {"moments.desktopModeGameName": "Desktop", "Bungie.Destiny2PCbasegame": "Destiny 2"}


def installed():
    return os.path.exists(DB)


def stamp():
    """Changes whenever GG writes to its library (used to notice new clips)."""
    out = []
    for suffix in ("", "-wal"):
        try:
            st = os.stat(DB + suffix)
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def is_custom(title):
    return bool(title) and not DEFAULT_TITLE.fullmatch(title)


def parse_tracks(raw):
    try:
        tracks = [{"name": t.get("name") or f"Track {i + 1}", "volume": float(t.get("volume", 1.0)),
                   "muted": bool(t.get("muted"))} for i, t in enumerate(json.loads(raw or "[]"))]
    except (ValueError, TypeError, AttributeError):
        tracks = []
    return tracks or [{"name": "Game", "volume": 1.0, "muted": False}]


def read():
    """({clip key: clip}, GG's clips folder). Raises OSError or sqlite3.Error if the library can't be read."""
    # Recent edits sit in the -wal file, which SQLite folds in when it opens the copy.
    tmp = tempfile.mkdtemp(prefix="clipshelf-gg-")
    try:
        for suffix in ("", "-wal"):
            if os.path.exists(DB + suffix):
                shutil.copyfile(DB + suffix, os.path.join(tmp, "database.db" + suffix))
        con = sqlite3.connect(os.path.join(tmp, "database.db"))
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                """select name, path, last_game_name, library_game_unique_id, recording_timestamp,
                          clip_start_point, clip_end_point, full_length, is_manually_trimmed,
                          thumbnail_path, tags, audio_tracks_props
                   from moments_clips where is_deleted = 0"""
            ).fetchall()
            setting = con.execute("select value from moments_settings where key = 'captureDir'").fetchone()
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    clips = {}
    for r in rows:
        try:
            starred = any(t.get("type") == 2 for t in json.loads(r["tags"] or "[]"))
        except (ValueError, AttributeError):
            starred = False
        full = r["full_length"] or 0.0
        trimmed = bool(r["is_manually_trimmed"]) and r["clip_end_point"] > r["clip_start_point"]
        game = r["last_game_name"] or "Unknown game"
        title = (r["name"] or "").strip()
        # Recording time and game are stored inside the video file itself, so together
        # they still identify a clip after it's moved or renamed.
        key = f"{r['recording_timestamp']}|{r['library_game_unique_id']}"
        clips[key] = {
            "key": key,
            "source": "gg",
            "recorder": "gg",
            "title": title,
            "custom": is_custom(title),
            "file": r["path"],
            "game": DISPLAY_NAMES.get(game, game),
            "uid": r["library_game_unique_id"] or "",
            "recorded": r["recording_timestamp"],
            "full": full,
            "baseTrim": [r["clip_start_point"], r["clip_end_point"]] if trimmed else None,
            "ggStar": starred,
            "thumb": r["thumbnail_path"],
            "tracks": parse_tracks(r["audio_tracks_props"]),
        }
    if setting and setting[0]:
        folder = setting[0]
    elif clips:
        folder = os.path.dirname(next(iter(clips.values()))["file"])
    else:
        folder = None
    return clips, folder
