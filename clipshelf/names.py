"""Working out a clip's game and recording time from its file name.

Each recorder names its files its own way:

  SteelSeries GG   Counter-Strike-2__2024-06-16__23-06-36.mp4 (renamed: ...__23-06-36__My title.mp4)
  NVIDIA           Counter-strike 2 2024.06.16 - 23.06.36.02.DVR.mp4, in a folder per game
  AMD              WARDOGS_replay_2026.09.12-17.41.mp4, in a folder per game; desktop: 2026.09.10-10.05.mp4
  Xbox Game Bar    Halo Infinite 2026-01-31 18-04-12.mp4, or in the PC's own date format:
                   Halo Infinite 1_31_2026 6_04_12 PM.mp4, Halo Infinite 26_01_31 18_04_12.mp4
  OBS              2024-06-16 23-06-36.mkv, Replay 2024-06-16 23-06-36.mkv

Anything else falls back to the first date found in the name. The game, when the name doesn't have one,
comes from the folder the clip is in (see game_from_folders).
"""
import datetime as dt
import os
import re
from collections import namedtuple

Parsed = namedtuple("Parsed", "game when title recorder")

# Words that name a kind of recording or a recorder's folder, not a game
GENERIC = {
    "replay", "replays", "instant replay", "instantreplay", "clip", "clips", "recording", "recordings", "record",
    "capture", "captures", "video", "videos", "highlight", "highlights", "dvr", "screen recording", "untitled",
    "vid", "img", "movie", "output", "obs", "medal", "nvidia", "radeon relive", "relive", "shadowplay",
    "moments", "steelseries moments", "exported clips", "edited clips", "temp", "new folder",
}

_TIME = r"(?P<h>\d{2})-(?P<mi>\d{2})-(?P<s>\d{2})"
PATTERNS = [
    ("gg", re.compile(r"^(?P<game>.+?)__(?P<Y>\d{4})-(?P<M>\d{2})-(?P<D>\d{2})__" + _TIME + r"(?:__(?P<title>.+))?$")),
    ("nvidia", re.compile(r"^(?P<game>.*?) ?(?P<Y>\d{4})\.(?P<M>\d{2})\.(?P<D>\d{2}) - (?P<h>\d{2})\.(?P<mi>\d{2})\."
                          r"(?P<s>\d{2})(?:\.\d+)?(?:\.DVR)?$", re.I)),
    ("amd", re.compile(r"^(?:(?P<game>.+?)_(?:replay_|record_|recording_)?)?(?P<Y>\d{4})\.(?P<M>\d{2})\.(?P<D>\d{2})"
                       r"-(?P<h>\d{2})\.(?P<mi>\d{2})(?:\.(?P<s>\d{2}))?(?:_\d+)?$", re.I)),
    ("obs", re.compile(r"^(?:(?P<game>.*?)[ _-]+)?(?P<Y>\d{4})-(?P<M>\d{2})-(?P<D>\d{2})[ _]" + _TIME
                       + r"(?:[ _-]+(?P<title>.*))?$")),
    ("xbox", re.compile(r"^(?P<game>.+?) (?P<a>\d{1,4})_(?P<b>\d{1,2})_(?P<c>\d{1,4}) (?P<h>\d{1,2})_(?P<mi>\d{2})_"
                        r"(?P<s>\d{2})(?: ?(?P<ampm>[AP]M))?$", re.I)),
]
# Fallbacks: a date (and maybe a time) anywhere in the name
SEPARATED = re.compile(r"(?<!\d)(?P<Y>(?:19|20)\d{2})(?P<sep>[-._])(?P<M>\d{1,2})(?P=sep)(?P<D>\d{1,2})(?!\d)"
                       r"(?:(?:[ _T]+|__| - |-)(?P<h>\d{1,2})[-._:](?P<mi>\d{2})(?:[-._:](?P<s>\d{2}))?(?!\d))?")
COMPACT = re.compile(r"(?<!\d)(?P<Y>(?:19|20)\d{2})(?P<M>[01]\d)(?P<D>[0-3]\d)"
                     r"(?:[_T-]?(?P<h>[0-2]\d)(?P<mi>[0-5]\d)(?P<s>[0-5]\d)?)?(?!\d)")


def make_time(y, mo, d, h=0, mi=0, s=0):
    try:
        when = dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
    except (TypeError, ValueError):
        return None
    return when if 1990 <= when.year <= 2100 else None


def clean_game(name, dashes_are_spaces=False):
    """The game part of a file name, tidied up; None if there isn't really one."""
    s = (name or "").strip(" _-.·")
    if " " not in s:
        if dashes_are_spaces:
            s = s.replace("-", " ")  # GG writes "Counter-Strike 2" as "Counter-Strike-2"
        s = s.replace("_", " ")
    s = re.sub(r"[ _-]+(?:instant[ _-]?replay|replay|record(?:ing)?|clip|dvr)$", "", s, flags=re.I)
    s = " ".join(s.split()).strip(" _-.")
    if not s or s.lower() in GENERIC or s.isdigit():
        return None
    if s.lower() in ("desktopcapture", "desktop capture"):
        return "Desktop"  # GG's label for clips of the desktop
    return s


def _xbox_time(m, near):
    """Game Bar writes the date the way the PC is set up to show it, so try each order and keep the one
    closest to when the file was saved."""
    a, b, c = m.group("a"), m.group("b"), m.group("c")
    if len(a) == 4:
        orders = [(a, b, c)]  # year month day
    elif len(c) == 4:
        orders = [(c, a, b), (c, b, a)]  # month day year, day month year
    else:
        orders = [("20" + a, b, c), ("20" + c, b, a), ("20" + c, a, b)]
    h = int(m.group("h"))
    ampm = (m.group("ampm") or "").upper()
    if ampm:
        h = h % 12 + (12 if ampm == "PM" else 0)
    options = [t for t in (make_time(y, mo, d, h, m.group("mi"), m.group("s")) for y, mo, d in orders) if t]
    if not options:
        return None
    if near is None:
        return options[0]
    saved = dt.datetime.fromtimestamp(near)
    # A recording is saved after it starts, so dates after the file's own time are unlikely
    return min(options, key=lambda t: (t > saved + dt.timedelta(days=1), abs((saved - t).total_seconds())))


def parse_name(stem, near=None):
    """Parsed(game, when, title, recorder) for a file name without its extension. Any part can be None/"".
    near is the file's own time (a timestamp), used where the name's date could be read more than one way."""
    for recorder, rx in PATTERNS:
        m = rx.match(stem)
        if not m:
            continue
        if recorder == "xbox":
            when = _xbox_time(m, near)
        else:
            when = make_time(m.group("Y"), m.group("M"), m.group("D"), m.group("h"), m.group("mi"), m.group("s"))
        if not when:
            continue
        title = (m.groupdict().get("title") or "").strip(" _-")
        game = clean_game(m.group("game"), recorder == "gg")
        if recorder == "obs":
            if title.isdigit():
                title = ""  # a counter OBS added, not a title
            if game:
                recorder = "xbox"  # OBS doesn't put the game in the name; Game Bar does, in this same format
        return Parsed(game, when, title, recorder)
    for rx in (SEPARATED, COMPACT):
        m = rx.search(stem)
        if m:
            when = make_time(m.group("Y"), m.group("M"), m.group("D"), m.group("h"), m.group("mi"), m.group("s"))
            if when:
                return Parsed(clean_game(stem[:m.start()]), when, "", "")
    # No date at all: a name someone typed, like "ace on mirage", is the clip's title
    title = " ".join(stem.replace("_", " ").split()) if re.search(r"[^\W\d_]{2}", stem) else ""
    return Parsed(None, None, title, "")


def game_from_folders(path, root):
    """The nearest folder between the clip and the source folder that's named after a game, e.g.
    Videos/Radeon ReLive/WARDOGS/clip.mp4 -> WARDOGS. Folders like "Clips" or "Radeon ReLive" are skipped."""
    rel = os.path.relpath(os.path.dirname(path), root)
    if rel in (".", "") or rel.startswith(".."):
        return None
    for part in reversed(rel.replace("\\", "/").split("/")):
        game = clean_game(part)
        if game:
            return game
    return None
