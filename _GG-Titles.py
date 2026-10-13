"""
GG Clips: browse, play and lightly edit your SteelSeries GG clips, and keep track of the titles you give them.

Double-click "_Update GG Titles.bat" (or run:  python "_GG-Titles.py"). Each run:
  1. reads GG's clip library (from a temporary copy, so GG's own files are never touched),
  2. compares every clip's title and file with the previous run and logs changes in _GG-Titles-history.json,
  3. rewrites _GG-Titles.html, a read-only copy of the page you can open any time, and
  4. starts the player on this PC only (http://127.0.0.1) and opens it in your browser. It stops by itself
     a few minutes after you close the browser tab, or straight away if you close its window.

The home page plays your 5 newest clips and lists your games with their cover art. Cover art comes from
Steam (only Steam app IDs and game names are sent) and is cached; to use your own picture for a game, put an
image named exactly like the game (e.g. "VALORANT.jpg") in the "covers" folder next to this script.

In the player you can give clips nicknames (stored in _GG-Titles-history.json; your files and GG aren't changed),
set the Game/Chat/Mic volumes, trim, and save an edited copy to "Edited Clips" inside your clips folder.
Chat/Mic audio and saving copies need ffmpeg.

Options:
  --report-only   update the history and _GG-Titles.html without starting the player
  --no-open       start the player without opening the browser
  --background    run the player quietly and keep it running (used by the shortcut in Windows' Startup
                  folder, which runs this with pyw.exe so there's no window); the site is then always at
                  http://127.0.0.1:48650 and _GG-Titles.html switches to it
"""
import datetime as dt
import glob
import hashlib
import json
import os
import re
import secrets
import select
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GG_DB = r"C:\ProgramData\SteelSeries\GG\apps\moments\db\database.db"
HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "_GG-Titles.html")
HISTORY = os.path.join(HERE, "_GG-Titles-history.json")
COVERS_DIR = os.path.join(HERE, "covers")  # your own cover images, named after the game
CACHE_ROOT = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "GG-Clips")
CACHE_DIR = os.path.join(CACHE_ROOT, "audio")
COVER_CACHE = os.path.join(CACHE_ROOT, "covers.json")
LOG = os.path.join(CACHE_ROOT, "player.log")  # used when the player runs in the background (no window)
STEAM_ASSETS = "https://shared.cloudflare.steamstatic.com/store_item_assets/"
PORT = 48650
IDLE_EXIT = 300  # seconds without the browser tab checking in before the player stops
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Titles GG makes up on its own. Anything else is a title you typed.
DEFAULT_TITLE = re.compile(
    r"(?:(?:Moments|Moments Desktop|Trimmed) clip from|Montage created) [A-Z][a-z]{2} \d{1,2}, \d{4}"
    r"|Auto-clip: .*"
)

# GG's internal names for a few games, and what to show instead.
DISPLAY_NAMES = {"moments.desktopModeGameName": "Desktop", "Bungie.Destiny2PCbasegame": "Destiny 2"}


def norm(name):
    return re.sub(r"[^a-z0-9]+", "", name.lower())


# Games GG knows from other stores that are also on Steam, which is where cover art comes from.
STEAM_IDS = {norm(k): v for k, v in {
    "Rocket League": 252950, "Among Us": 945360, "Overcooked! 2": 728880, "Destiny 2": 1085660,
    "Tom Clancy's The Division 2": 2221490, "Marvel's Spider-Man Remastered": 1817070,
    "ARC Raiders - Server Slam": 1808500,
}.items()}

# Video encoders for precise cuts, fastest first. The first one that works on this PC is used.
ENCODERS = [
    ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "18", "-qp_p", "20", "-pix_fmt", "nv12"],
    ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"],
    ["-c:v", "h264_qsv", "-global_quality", "20", "-pix_fmt", "nv12"],
    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"],
]


SHARE_LIMIT = 18_000_000  # bytes: "Compressed" copies stay under 18 MB so they're easy to share
STEM = re.compile(r"(.+?__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2})")  # "Game__date__time" at the start of a clip's name
EDIT_EXTS = (".mp4", ".m4v", ".mov", ".webm")  # videos in "Edited Clips" the browser can play


def iso_time(ts):
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def share_settings(seconds):
    """Video bitrate (kb/s) and picture height that fit a copy of this length under SHARE_LIMIT."""
    total = SHARE_LIMIT * 0.9 * 8 / 1000 / max(seconds, 1)  # 10% headroom for the container and the encoder
    kbps = max(250, int(total - 128))  # minus the audio
    for need, height in ((9000, 1440), (4500, 1080), (1900, 720), (1100, 540)):
        if kbps >= need:
            return kbps, height
    return kbps, 480


def is_custom(title):
    return bool(title) and not DEFAULT_TITLE.fullmatch(title)


def clip_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def export_dir_for(capture_dir):
    return os.path.join(capture_dir, "Edited Clips")


def safe_name(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s or "")
    return " ".join(s.split()).strip(" .")[:100]


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def parse_tracks(raw):
    try:
        tracks = [{"name": t.get("name") or f"Track {i + 1}", "volume": float(t.get("volume", 1.0)),
                   "muted": bool(t.get("muted"))} for i, t in enumerate(json.loads(raw or "[]"))]
    except (ValueError, TypeError, AttributeError):
        tracks = []
    return tracks or [{"name": "Game", "volume": 1.0, "muted": False}]


def read_library():
    """Return ({clip key: clip info}, GG's clips folder)."""
    if not os.path.exists(GG_DB):
        sys.exit(f"Can't find SteelSeries GG's clip library at {GG_DB}")
    # GG keeps the database open, so read a copy. Recent edits sit in the -wal file,
    # which SQLite folds in when it opens the copy.
    tmp = tempfile.mkdtemp(prefix="gg-titles-")
    try:
        for suffix in ("", "-wal"):
            if os.path.exists(GG_DB + suffix):
                shutil.copyfile(GG_DB + suffix, os.path.join(tmp, "database.db" + suffix))
        con = sqlite3.connect(os.path.join(tmp, "database.db"))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """select name, path, last_game_name, library_game_unique_id, recording_timestamp,
                      last_user_edit_timestamp, clip_start_point, clip_end_point, full_length,
                      is_manually_trimmed, thumbnail_path, tags, audio_tracks_props
               from moments_clips where is_deleted = 0"""
        ).fetchall()
        setting = con.execute("select value from moments_settings where key = 'captureDir'").fetchone()
        con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    clips = {}
    for r in rows:
        try:
            starred = any(t.get("type") == 2 for t in json.loads(r["tags"] or "[]"))
        except ValueError:
            starred = False
        full = r["full_length"] or 0.0
        trimmed = bool(r["is_manually_trimmed"]) and r["clip_end_point"] > r["clip_start_point"]
        game = r["last_game_name"] or "Unknown game"
        # Recording time and game are stored inside the video file itself, so together
        # they still identify a clip after it's moved or renamed.
        key = f"{r['recording_timestamp']}|{r['library_game_unique_id']}"
        clips[key] = {
            "title": r["name"].strip(),
            "file": r["path"],
            "game": DISPLAY_NAMES.get(game, game),
            "uid": r["library_game_unique_id"] or "",
            "recorded": r["recording_timestamp"],
            "edited": r["last_user_edit_timestamp"],
            "full": full,
            "start": r["clip_start_point"] if trimmed else 0.0,
            "end": r["clip_end_point"] if trimmed else full,
            "trimmed": trimmed,
            "starred": starred,
            "thumb": r["thumbnail_path"],
            "tracks": parse_tracks(r["audio_tracks_props"]),
        }
    if setting and setting[0]:
        capture_dir = setting[0]
    elif clips:
        capture_dir = os.path.dirname(next(iter(clips.values()))["file"])
    else:
        capture_dir = HERE
    return clips, capture_dir


# ---------- cover art ----------

def fetch_json(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "GG-Clips"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def resolve_covers(clips):
    """{game: cover art URL} from Steam, cached. Steam is only asked about games it hasn't been asked about
    yet (and not again for 6 hours if it couldn't be reached); games without art get a tile made from a clip."""
    cache = load_json(COVER_CACHE, {})
    apps, search = cache.setdefault("apps", {}), cache.setdefault("search", {})
    games = {c["game"] for c in clips.values()}
    ids = {}
    for c in clips.values():
        if c["uid"].startswith("1_") and c["uid"][2:].isdigit():  # "1_<id>" is a Steam game
            ids[c["game"]] = int(c["uid"][2:])
    for g in games - set(ids):
        if norm(g) in STEAM_IDS:
            ids[g] = STEAM_IDS[norm(g)]
        elif search.get(norm(g)):
            ids[g] = search[norm(g)]
    now = time.time()
    unsearched = [g for g in games if g not in ids and norm(g) not in search and g != "Desktop"]
    stale = {str(a) for a in ids.values() if now - apps.get(str(a), {}).get("at", 0) > 30 * 86400}
    if (unsearched or stale) and now - cache.get("failed", 0) > 6 * 3600:
        try:
            for g in unsearched[:20]:
                found = fetch_json("https://store.steampowered.com/api/storesearch/?l=english&cc=US&term="
                                   + urllib.parse.quote(g))
                match = next((it["id"] for it in found.get("items", []) if norm(it.get("name", "")) == norm(g)), None)
                search[norm(g)] = match
                if match:
                    ids[g] = match
                    stale.add(str(match))
            stale = sorted(stale)
            for i in range(0, len(stale), 50):
                query = {"ids": [{"appid": int(a)} for a in stale[i:i + 50]],
                         "context": {"language": "english", "country_code": "US", "steam_realm": 1},
                         "data_request": {"include_assets": True}}
                got = fetch_json("https://api.steampowered.com/IStoreBrowseService/GetItems/v1?input_json="
                                 + urllib.parse.quote(json.dumps(query)))
                for item in got.get("response", {}).get("store_items", []):
                    assets = item.get("assets") or {}
                    fmt, cap = assets.get("asset_url_format"), assets.get("library_capsule")
                    url = STEAM_ASSETS + fmt.replace("${FILENAME}", cap) if fmt and cap else ""
                    apps[str(item.get("appid"))] = {"url": url, "at": now}
        except Exception:  # offline or Steam unreachable: fall back to clip art and try again later
            cache["failed"] = now
        try:
            os.makedirs(CACHE_ROOT, exist_ok=True)
            with open(COVER_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache, f)
        except OSError:
            pass
    return {g: apps.get(str(a), {}).get("url", "") for g, a in ids.items()}


def custom_cover(game):
    base = os.path.join(COVERS_DIR, safe_name(game))
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if os.path.isfile(base + ext):
            return base + ext
    return None


# ---------- history ----------

def load_history():
    hist = {"started": None, "last_run": None, "changes": [], "snapshot": {}, "nicknames": {}, "mix": {}}
    hist.update(load_json(HISTORY, {}))
    return hist


def save_history(hist):
    tmp = HISTORY + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)
    os.replace(tmp, HISTORY)


def find_changes(old, clips, now):
    """Compare the previous run's snapshot with the library now. Only clips you've titled count."""
    changes = []

    def entry(kind, key, clip, before, after):
        return {"when": now, "kind": kind, "key": key, "game": clip["game"], "recorded": clip["recorded"],
                "file": clip["file"], "before": before, "after": after}

    for key, clip in clips.items():
        prev = old.get(key)
        if prev is None:
            if is_custom(clip["title"]):
                changes.append(entry("new", key, clip, None, clip["title"]))
            continue
        titled = is_custom(prev["title"]) or is_custom(clip["title"])
        if titled and prev["title"] != clip["title"]:
            changes.append(entry("title", key, clip, prev["title"], clip["title"]))
        if titled and os.path.normcase(prev["file"]) != os.path.normcase(clip["file"]):
            changes.append(entry("file", key, clip, os.path.basename(prev["file"]), os.path.basename(clip["file"])))
    for key, prev in old.items():
        if key not in clips and is_custom(prev["title"]):
            changes.append(entry("removed", key, prev, prev["title"], None))
    return changes


def describe(ch):
    if ch["kind"] == "title":
        return f'{ch["game"]}: "{ch["before"]}" -> "{ch["after"]}"'
    if ch["kind"] == "file":
        return f'{ch["game"]}: file {ch["before"]} -> {ch["after"]}'
    if ch["kind"] == "new":
        return f'{ch["game"]}: new titled clip "{ch["after"]}"'
    return f'{ch["game"]}: removed from GG "{ch["before"]}"'


def sync(hist):
    """Read GG's library, log what changed since last time, and rewrite the saved page."""
    clips, capture_dir = read_library()
    covers = resolve_covers(clips)
    now = now_iso()
    changes = find_changes(hist["snapshot"], clips, now) if hist["snapshot"] else []
    if not hist["started"]:
        hist["started"] = now
    hist["last_run"] = now
    hist["changes"].extend(changes)
    hist["snapshot"] = {k: {f: c[f] for f in ("title", "file", "game", "recorded")} for k, c in clips.items()}
    save_history(hist)
    write_report(clips, hist, covers)
    return clips, capture_dir, covers, changes


# ---------- the page ----------

def href(path):
    """Link from the saved page to a file: relative when on the same drive, otherwise file:///."""
    try:
        return urllib.parse.quote(os.path.relpath(path, HERE).replace("\\", "/"))
    except ValueError:  # different drive
        return "file:///" + urllib.parse.quote(path.replace("\\", "/"), safe="/:")


def client_change(ch, clips):
    key = ch.get("key")
    return {"when": ch.get("when"), "kind": ch.get("kind"), "game": ch.get("game"), "recorded": ch.get("recorded"),
            "file": os.path.basename(ch.get("file") or ""), "before": ch.get("before"), "after": ch.get("after"),
            "id": clip_id(key) if key in clips else None}


def client_data(clips, hist, covers, server=None):
    nicks, mixes = hist.get("nicknames", {}), hist.get("mix", {})
    token = server.token if server else ""
    items = []
    for key, c in clips.items():
        cid = clip_id(key)
        # Game/Chat/Mic levels: the ones you saved for this clip, else GG's (kept for "Reset to GG levels")
        tracks = [dict(t, ggVolume=t["volume"], ggMuted=t["muted"]) for t in c["tracks"]]
        for t, saved in zip(tracks, mixes.get(key) or []):
            t["volume"], t["muted"] = saved["vol"], saved["muted"]
        if server:
            video = f"/media/{cid}?t={token}"
            thumb = f"/thumb/{cid}?t={token}" if c["thumb"] else ""
        else:
            video = href(c["file"])
            thumb = href(c["thumb"]) if c["thumb"] and os.path.exists(c["thumb"]) else ""
        items.append({"id": cid, "title": c["title"], "custom": is_custom(c["title"]), "nick": nicks.get(key, ""),
                      "game": c["game"], "recorded": c["recorded"], "full": c["full"], "start": c["start"],
                      "end": c["end"], "trimmed": c["trimmed"], "starred": c["starred"],
                      "file": os.path.basename(c["file"]), "video": video, "thumb": thumb, "tracks": tracks})
    games = []
    for g in sorted({c["game"] for c in clips.values()}):
        own = custom_cover(g)
        if own:
            cover = f"/cover/{clip_id(g)}?t={token}" if server else href(own)
        else:
            cover = covers.get(g, "")
        games.append({"name": g, "cover": cover})
    meta = {"mode": "server" if server else "static", "token": token, "session": server.session if server else "",
            "port": PORT, "ffmpeg": bool(server and server.ffmpeg),
            "started": hist["started"], "lastRun": hist["last_run"]}
    return {"meta": meta, "clips": items, "games": games, "edits": server.list_edits() if server else [],
            "changes": [client_change(ch, clips) for ch in hist["changes"]]}


def build_page(data):
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    blob = blob.replace("</", "<\\/").replace("<!--", "<\\u0021--")
    return PAGE.replace("__GG_DATA__", blob)


def write_report(clips, hist, covers):
    tmp = REPORT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(build_page(client_data(clips, hist, covers)))
    os.replace(tmp, REPORT)


# ---------- the player (a small web server on this PC only) ----------

def find_tool(name):
    found = shutil.which(name)
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA", "")
    for pattern in (os.path.join(local, "Microsoft", "WinGet", "Links", name + ".exe"),
                    os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", name + ".exe")):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def client_gone(sock):
    """True when the browser has hung up, e.g. you stopped hovering a clip before its audio was ready."""
    try:
        ready, _, _ = select.select([sock], [], [], 0)
        return bool(ready) and sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


class ClipServer:
    def __init__(self, hist, clips, capture_dir, covers):
        self.hist = hist
        self.lock = threading.RLock()
        self.extract_lock = threading.Lock()  # one extraction at a time: the hard drive is the bottleneck
        self.token = secrets.token_urlsafe(18)
        self.session = secrets.token_hex(4)  # lets a page left open from an earlier run notice the restart
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        self.encoder = None
        self.jobs = {}
        self.probes = {}
        self.prefetching = set()
        self.edits = {}  # id -> path of each video in "Edited Clips"
        self.fprobes = {}
        self.thumb_lock = threading.Lock()
        self.last_seen = time.time()
        self.page_loaded = False
        self.set_library(clips, capture_dir, covers)

    def set_library(self, clips, capture_dir, covers):
        with self.lock:
            self.clips = clips
            self.covers = covers
            self.export_dir = export_dir_for(capture_dir)
            self.ids = {clip_id(k): k for k in clips}

    def refresh(self):
        with self.lock:
            clips, capture_dir, covers, changes = sync(self.hist)
            self.set_library(clips, capture_dir, covers)
            for ch in changes:
                print("  " + describe(ch))

    def page(self):
        with self.lock:
            return build_page(client_data(self.clips, self.hist, self.covers, self))

    def clip(self, cid):
        with self.lock:
            key = self.ids.get(cid)
            if key is None:
                raise LookupError("That clip isn't in GG's library any more")
            return key, self.clips[key]

    def cover_file(self, gid):
        with self.lock:
            games = {c["game"] for c in self.clips.values()}
        for g in games:
            if clip_id(g) == gid:
                return custom_cover(g)
        return None

    def run(self, args, timeout=600):
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              creationflags=NO_WINDOW, timeout=timeout)

    def audio_count(self, path):
        """How many audio tracks (Game, Chat, Mic...) the file really has."""
        st = os.stat(path)
        ck = (path, st.st_mtime, st.st_size)
        if ck not in self.probes:
            if self.ffprobe:
                out = self.run([self.ffprobe, "-v", "error", "-select_streams", "a",
                                "-show_entries", "stream=index", "-of", "csv=p=0", path], timeout=60)
                self.probes[ck] = len([l for l in out.stdout.splitlines() if l.strip()]) or 1
            else:
                self.probes[ck] = 1
        return self.probes[ck]

    def audio_track(self, cid, n, wanted=None):
        """Path to audio track n (1 = Chat, 2 = Mic...) pulled out of the clip. Track 0 plays from the video."""
        _, c = self.clip(cid)
        if not self.ffmpeg:
            raise LookupError("ffmpeg isn't installed")
        src = c["file"]
        st = os.stat(src)
        stem = os.path.join(CACHE_DIR, f"{cid}-{int(st.st_mtime)}-{st.st_size}")
        want = f"{stem}-{n}.m4a"
        if not os.path.exists(want):
            with self.extract_lock:
                if not os.path.exists(want):
                    if wanted and not wanted():
                        raise LookupError("No longer needed")
                    count = self.audio_count(src)
                    if not 1 <= n < count:
                        raise LookupError("This clip has no such audio track")
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    args, outs = [self.ffmpeg, "-v", "error", "-y", "-i", src], []
                    for i in range(1, count):  # one pass over the file for all tracks
                        outs.append((f"{stem}-{i}.part", f"{stem}-{i}.m4a"))
                        args += ["-map", f"0:a:{i}", "-c", "copy", "-f", "mp4", outs[-1][0]]
                    r = self.run(args)
                    if r.returncode:
                        raise RuntimeError((r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
                    for part, final in outs:
                        os.replace(part, final)
        try:
            os.utime(want)  # keep recently used tracks in the cache
        except OSError:
            pass
        return want

    def prefetch(self, cid):
        """Get a clip's Chat/Mic ready in the background (used for the next clip on the home page)."""
        with self.lock:
            if cid in self.prefetching or not self.ffmpeg:
                return
            self.prefetching.add(cid)

        def work():
            try:
                self.audio_track(cid, 1)
            except Exception:  # nothing to prepare, or the clip is gone
                pass
            finally:
                self.prefetching.discard(cid)

        threading.Thread(target=work, daemon=True).start()

    def set_nickname(self, cid, nick):
        nick = " ".join(str(nick or "").split())[:120]
        with self.lock:
            key, c = self.clip(cid)
            nicks = self.hist.setdefault("nicknames", {})
            before = nicks.get(key, "")
            change = None
            if nick != before:
                if nick:
                    nicks[key] = nick
                else:
                    nicks.pop(key, None)
                change = {"when": now_iso(), "kind": "nickname", "key": key, "game": c["game"],
                          "recorded": c["recorded"], "file": c["file"], "before": before or None, "after": nick or None}
                self.hist["changes"].append(change)
                save_history(self.hist)
                write_report(self.clips, self.hist, self.covers)
            return {"nick": nick, "change": client_change(change, self.clips) if change else None}

    def set_mix(self, cid, tracks):
        """Remember the Game/Chat/Mic levels you set for a clip (going back to GG's levels forgets them)."""
        with self.lock:
            key, c = self.clip(cid)
            gg = c["tracks"]
            levels = [{"vol": t["volume"], "muted": t["muted"]} for t in gg]
            for t in tracks or []:
                i = int(t.get("stream", -1))
                if 0 <= i < len(levels):
                    levels[i] = {"vol": round(min(2.0, max(0.0, float(t.get("vol", 1.0)))), 3), "muted": bool(t.get("muted"))}
            mixes = self.hist.setdefault("mix", {})
            if all(abs(l["vol"] - g["volume"]) < 0.005 and l["muted"] == g["muted"] for l, g in zip(levels, gg)):
                mixes.pop(key, None)
            else:
                mixes[key] = levels
            save_history(self.hist)
            return {"ok": True}

    def video_encoder(self):
        if self.encoder is None:
            self.encoder = ENCODERS[-1]
            for enc in ENCODERS[:-1]:
                test = [self.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.2",
                        *enc, "-f", "null", "-"]
                if self.run(test, timeout=60).returncode == 0:
                    self.encoder = enc
                    break
        return self.encoder

    def rate_encoder(self, kbps):
        """The same encoder, set to a fixed bitrate so a compressed copy lands on a predictable size."""
        name = self.video_encoder()[1]
        rate = ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k"]
        if name == "h264_amf":
            return ["-c:v", name, "-quality", "quality", "-rc", "cbr", *rate, "-pix_fmt", "nv12"]
        if name == "h264_nvenc":
            return ["-c:v", name, "-preset", "p5", "-rc", "cbr", *rate, "-pix_fmt", "yuv420p"]
        if name == "h264_qsv":
            return ["-c:v", name, *rate, "-pix_fmt", "nv12"]
        return ["-c:v", "libx264", "-preset", "medium", *rate, "-pix_fmt", "yuv420p"]

    # ----- edited clips (everything in the "Edited Clips" folder) -----

    def probe_file(self, path, st):
        ck = (path, st.st_mtime, st.st_size)
        if ck not in self.fprobes:
            info = {"duration": 0.0, "audio": 1}
            if self.ffprobe:
                out = self.run([self.ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                "-of", "json", path], timeout=60)
                try:
                    j = json.loads(out.stdout or "{}")
                    info["duration"] = float(j.get("format", {}).get("duration") or 0)
                    info["audio"] = sum(1 for s in j.get("streams", []) if s.get("codec_type") == "audio")
                except ValueError:
                    pass
            self.fprobes[ck] = info
        return self.fprobes[ck]

    def list_edits(self):
        """Every video in "Edited Clips", with the clip it was made from (worked out from its name)."""
        try:
            names = os.listdir(self.export_dir)
        except OSError:
            names = []
        with self.lock:
            clips = self.clips
        by_stem = {}
        for key, c in clips.items():
            m = STEM.match(os.path.splitext(os.path.basename(c["file"]))[0])
            if m:
                by_stem.setdefault(m.group(1), key)
        nicks = self.hist.get("nicknames", {})
        items, edits = [], {}
        for name in names:
            path = os.path.join(self.export_dir, name)
            if not name.lower().endswith(EDIT_EXTS) or not os.path.isfile(path):
                continue
            st = os.stat(path)
            eid = "x" + hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:11]  # "x": never clashes with clip ids
            edits[eid] = path
            info = self.probe_file(path, st)
            base = os.path.splitext(name)[0]
            m = STEM.match(base)
            src_key = by_stem.get(m.group(1)) if m else None
            src = clips.get(src_key) if src_key else None
            label = (base[len(m.group(1)):].strip("_ ") if m else base).replace(" (18MB)", "")  # size shows as a tag
            v = f"t={self.token}&v={int(st.st_mtime)}"
            n_audio = max(1, info["audio"])
            items.append({
                "id": eid, "edited": True, "title": label or base, "custom": True, "nick": "",
                "game": src["game"] if src else "Unknown game", "recorded": src["recorded"] if src else iso_time(st.st_mtime),
                "made": iso_time(st.st_mtime), "size": st.st_size, "full": info["duration"], "start": 0.0,
                "end": info["duration"], "trimmed": False, "starred": False, "file": name,
                "video": f"/media/{eid}?{v}", "thumb": f"/thumb/{eid}?{v}",
                "tracks": [{"name": "Mix" if n_audio == 1 else f"Track {i + 1}", "volume": 1.0, "muted": False,
                            "ggVolume": 1.0, "ggMuted": False} for i in range(n_audio)],
                "source": clip_id(src_key) if src_key else None,
                "sourceTitle": (nicks.get(src_key) or src["title"]) if src else "",
            })
        with self.lock:
            self.edits = edits
        return sorted(items, key=lambda e: e["made"], reverse=True)

    def edit_path(self, eid):
        with self.lock:
            path = self.edits.get(eid)
        if not path or not os.path.isfile(path):
            raise LookupError("That edited clip isn't there any more")
        return path

    def media_path(self, cid):
        return self.edit_path(cid) if cid.startswith("x") else self.clip(cid)[1]["file"]

    def edit_thumb(self, eid):
        """A thumbnail for an edited clip, made once and cached."""
        path = self.edit_path(eid)
        st = os.stat(path)
        out = os.path.join(CACHE_ROOT, "thumbs", f"{eid}-{int(st.st_mtime)}-{st.st_size}.jpg")
        if not os.path.exists(out) and self.ffmpeg:
            with self.thumb_lock:
                if not os.path.exists(out):
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    at = min(2.0, self.probe_file(path, st)["duration"] * 0.3)
                    tmp = out + ".tmp.jpg"
                    r = self.run([self.ffmpeg, "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", path, "-frames:v", "1",
                                  "-vf", "scale=640:-2", "-q:v", "4", tmp], timeout=60)
                    if r.returncode == 0:
                        os.replace(tmp, out)
        if not os.path.exists(out):
            raise LookupError("No thumbnail")
        return out

    def start_export(self, cid, start, end, volumes, precise, loud, name, small=False, overwrite=False):
        if not self.ffmpeg:
            raise RuntimeError("Saving edited copies needs ffmpeg")
        replace = None  # the edited clip a save overwrites
        tag = " (18MB)" if small else ""
        if cid.startswith("x"):  # an edited clip: overwrite it, or save a new copy next to it
            src = self.edit_path(cid)
            base = re.sub(r" \(18MB\)$", "", os.path.splitext(os.path.basename(src))[0])
            m = STEM.match(base)
            if overwrite:
                stem, replace = base + tag, src
            elif safe_name(name):
                stem = (f"{m.group(1)}__{safe_name(name)}" if m else safe_name(name)) + tag
            else:
                stem = f"{base} (edit){tag}"
        else:
            src = self.clip(cid)[1]["file"]
            base = os.path.splitext(os.path.basename(src))[0]
            m = STEM.match(base)
            stem = f"{m.group(1) if m else base}__{safe_name(name) or 'edit'}{tag}"
        start, end = float(start), float(end)
        if not (0 <= start < end) or end - start < 0.2:
            raise ValueError("Pick a start and end at least 0.2 seconds apart")
        count = self.audio_count(src)
        vols = [min(4.0, max(0.0, float(v))) for v in list(volumes)[:count]]
        vols += [1.0] * (count - len(vols))
        with self.lock:
            os.makedirs(self.export_dir, exist_ok=True)
            n = 1
            while True:  # never clobber another file: add (2), (3)... and reserve the name with a .part file
                out = os.path.join(self.export_dir, stem + (f" ({n})" if n > 1 else "") + ".mp4")
                same = replace and os.path.normcase(out) == os.path.normcase(replace)
                if (same or not os.path.exists(out)) and not os.path.exists(out + ".part"):
                    open(out + ".part", "wb").close()
                    break
                n += 1
            jid = secrets.token_hex(4)
            self.jobs[jid] = {"state": "running", "progress": 0.0, "file": os.path.basename(out), "error": "",
                              "overwrote": bool(replace)}
        threading.Thread(target=self._export, args=(jid, src, out, start, end, vols, bool(precise), bool(loud),
                                                    bool(small), replace)).start()
        return jid

    def _export(self, jid, src, out, start, end, vols, precise, loud, small, replace=None):
        job, part = self.jobs[jid], out + ".part"
        try:
            length = end - start
            kbps, height = share_settings(length) if small else (0, 0)
            for attempt in range(3):
                args = [self.ffmpeg, "-hide_banner", "-v", "error", "-y",
                        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src]
                # Mix every audio track into one, each at the volume picked in the player
                chains = [f"[0:a:{i}]volume={v:.3f}[a{i}]" for i, v in enumerate(vols)]
                if len(vols) > 1:
                    chains.append("".join(f"[a{i}]" for i in range(len(vols)))
                                  + f"amix=inputs={len(vols)}:normalize=0:duration=longest[aout]")
                    mixed = "[aout]"
                else:
                    mixed = "[a0]"
                if loud:  # bring the whole mix to normal online-video loudness
                    chains.append(f"{mixed}loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aloud]")
                    mixed = "[aloud]"
                video = "0:v:0"
                if small:  # smaller picture for longer clips, so the size limit doesn't make it blocky
                    chains.append(f"[0:v:0]scale=-2:'min(ih,{height})'" + (",fps=30" if kbps < 2500 else "") + "[v]")
                    video = "[v]"
                args += ["-filter_complex", ";".join(chains), "-map", video, "-map", mixed,
                         "-c:a", "aac", "-b:a", "128k" if small else "192k"]
                if small:
                    args += self.rate_encoder(kbps)
                elif precise:
                    args += self.video_encoder()
                else:
                    args += ["-c:v", "copy"]
                args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", "-f", "mp4", part]
                job.update(progress=0.0, retry=attempt)
                self._run_ffmpeg(args, job, length)
                if not small or os.path.getsize(part) <= SHARE_LIMIT:
                    break
                kbps = max(150, int(kbps * SHARE_LIMIT / os.path.getsize(part) * 0.9))  # came out too big: go a bit lower
            else:
                raise RuntimeError("Couldn't get this clip under 18 MB. Try trimming it shorter.")
            retry_io(lambda: os.replace(part, out))  # the browser may be reading the old file for a moment
            if replace and os.path.normcase(replace) != os.path.normcase(out):
                retry_io(lambda: os.remove(replace))  # overwritten under a new name (its quality changed)
            job.update(state="done", progress=1.0, size=os.path.getsize(out))
        except Exception as e:  # report any failure to the page
            job.update(state="error", error=str(e))
            try:
                os.remove(part)
            except OSError:
                pass

    def _run_ffmpeg(self, args, job, length):
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             errors="replace", creationflags=NO_WINDOW)
        err = []
        reader = threading.Thread(target=lambda: err.append(p.stderr.read()))
        reader.start()
        for line in p.stdout:
            m = re.match(r"out_time_(?:us|ms)=(\d+)", line)
            if m:
                job["progress"] = min(0.99, int(m.group(1)) / 1e6 / length)
        p.wait()
        reader.join()
        if p.returncode:
            lines = "".join(err).strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"ffmpeg stopped with code {p.returncode}")

    def reveal(self, cid=None, file=None, folder=False):
        if folder:
            os.makedirs(self.export_dir, exist_ok=True)
            subprocess.Popen(f'explorer "{self.export_dir}"')
            return
        if cid:
            path = self.media_path(cid)
        else:
            path = os.path.join(self.export_dir, os.path.basename(file or ""))
        if not os.path.isfile(path):
            raise LookupError("File not found")
        subprocess.Popen(f'explorer /select,"{path}"')


def retry_io(action, tries=12):
    """Windows won't replace a file while something has it open; the browser only holds it briefly."""
    for i in range(tries):
        try:
            return action()
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.25)


def make_handler(app, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def allowed(self, need_token):
            app.last_seen = time.time()
            if self.headers.get("Host") not in hosts:
                self.fail(403, "Not allowed")
                return False
            if need_token:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if (self.headers.get("X-Token") or query.get("t", [""])[0]) != app.token:
                    self.fail(403, "Not allowed")
                    return False
            return True

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                if not self.allowed(False):
                    return
                app.page_loaded = True
                try:
                    app.refresh()
                except Exception as e:  # keep serving the last good copy
                    print("Couldn't re-read GG's library:", e)
                return self.send_bytes(app.page().encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/ping":
                if self.allowed(False):
                    self.send_json({"app": "gg-clips", "session": app.session})
                return
            if not self.allowed(True):
                return
            parts = path.strip("/").split("/")
            try:
                if parts[0] == "media" and len(parts) == 2:
                    return self.send_file(app.media_path(parts[1]), "video/mp4")
                if parts[0] == "thumb" and len(parts) == 2:
                    if parts[1].startswith("x"):
                        return self.send_file(app.edit_thumb(parts[1]), "image/jpeg", cache=True)
                    return self.send_file(app.clip(parts[1])[1]["thumb"], "image/jpeg", cache=True)
                if parts[:2] == ["api", "edited"]:
                    return self.send_json({"items": app.list_edits()})
                if parts[0] == "cover" and len(parts) == 2:
                    path = app.cover_file(parts[1])
                    ctype = {".png": "image/png", ".webp": "image/webp"}.get(os.path.splitext(path or "")[1].lower(), "image/jpeg")
                    return self.send_file(path, ctype)
                if parts[0] == "audio" and len(parts) == 3:
                    track = app.audio_track(parts[1], int(parts[2]), wanted=lambda: not client_gone(self.connection))
                    return self.send_file(track, "audio/mp4")
                if parts[:2] == ["api", "job"] and len(parts) == 3:
                    return self.send_json(app.jobs.get(parts[2]) or {"state": "error", "error": "Unknown job"})
                self.fail(404, "Not found")
            except (LookupError, ValueError, OSError) as e:
                self.fail(404, str(e))
            except Exception as e:
                self.fail(500, str(e))

        def do_POST(self):
            # Always read the whole request first, even one that gets refused, or its leftover bytes
            # would be taken for the start of the browser's next request on this connection.
            try:
                size = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                size = -1
            if not 0 <= size <= 65536:
                self.close_connection = True
                return self.fail(413, "Too large")
            raw = self.rfile.read(size) if size else b""
            if not self.allowed(True):
                return
            path = urllib.parse.urlsplit(self.path).path
            try:
                body = json.loads(raw or b"{}")
                if path == "/api/nickname":
                    return self.send_json(app.set_nickname(body.get("id"), body.get("nickname", "")))
                if path == "/api/export":
                    job = app.start_export(body.get("id"), body.get("start"), body.get("end"),
                                           body.get("volumes") or [], body.get("precise"), body.get("loud"),
                                           str(body.get("name", "")), body.get("quality") == "small",
                                           bool(body.get("overwrite")))
                    return self.send_json({"job": job})
                if path == "/api/mix":
                    return self.send_json(app.set_mix(body.get("id"), body.get("tracks")))
                if path == "/api/prefetch":
                    app.prefetch(body.get("id"))
                    return self.send_json({"ok": True})
                if path == "/api/reveal":
                    app.reveal(body.get("id"), body.get("file"), bool(body.get("folder")))
                    return self.send_json({"ok": True})
                self.fail(404, "Not found")
            except (LookupError, ValueError, TypeError) as e:
                self.fail(400, str(e))
            except Exception as e:
                self.fail(500, str(e))

        def send_bytes(self, data, ctype, status=200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, obj, status=200):
            self.send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status)

        def fail(self, status, message):
            self.send_json({"error": message}, status)

        def send_file(self, path, ctype, cache=False):
            if not path or not os.path.isfile(path):
                return self.fail(404, "File not found")
            size = os.path.getsize(path)
            start, end, status = 0, size - 1, 200
            m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, start + (16 << 20) - 1)  # short answers; the browser asks for the rest
                status = 206
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "private, max-age=86400" if cache else "no-store")
            self.end_headers()
            # Re-open the file for every chunk so it's never held open while waiting on the browser;
            # GG needs to be able to replace a clip file whenever you edit it there.
            pos = start
            try:
                while pos <= end:
                    with open(path, "rb") as f:
                        f.seek(pos)
                        chunk = f.read(min(1 << 20, end - pos + 1))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    pos += len(chunk)
            except OSError:  # the browser cancelled (normal when you seek)
                self.close_connection = True

    return Handler


def clean_cache():
    if not os.path.isdir(CACHE_DIR):
        return
    cutoff = time.time() - 14 * 86400
    for name in os.listdir(CACHE_DIR):
        path = os.path.join(CACHE_DIR, name)
        try:
            if name.endswith(".part") or os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            pass


def watchdog(app, httpd):
    while True:
        time.sleep(10)
        busy = any(j["state"] == "running" for j in app.jobs.values())
        idle = time.time() - app.last_seen
        if not busy and ((app.page_loaded and idle > IDLE_EXIT) or (not app.page_loaded and idle > 600)):
            print("The player tab was closed, so the player has stopped.")
            httpd.shutdown()
            return


def player_running():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/ping", timeout=1) as r:
            return json.load(r).get("app") == "gg-clips"
    except Exception:
        return False


def serve(hist, clips, capture_dir, covers, background):
    app = ClipServer(hist, clips, capture_dir, covers)
    httpd = None
    for port in (PORT, 0):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), BaseHTTPRequestHandler)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit("Couldn't start the player.")
    httpd.daemon_threads = True
    httpd.RequestHandlerClass = make_handler(app, httpd.server_port)
    url = f"http://127.0.0.1:{httpd.server_port}/"
    clean_cache()
    print(f"\nPlayer: {url}")
    if not app.ffmpeg:
        print("ffmpeg wasn't found, so Chat/Mic audio and saving edited copies are off.")
    if not background:  # the background player keeps running; a window-run one stops when its tab is closed
        print("Keep this window open while you use it. It closes by itself a few minutes after you close the tab.")
        threading.Thread(target=watchdog, args=(app, httpd), daemon=True).start()
        if "--no-open" not in sys.argv:
            threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main():
    background = "--background" in sys.argv
    if sys.stdout is None:  # started without a window (pyw.exe): keep a small log instead
        os.makedirs(CACHE_ROOT, exist_ok=True)
        try:
            if os.path.getsize(LOG) > 1 << 20:
                os.remove(LOG)
        except OSError:
            pass
        sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
        print(f"--- {now_iso()}")
    sys.stdout.reconfigure(errors="replace")
    os.makedirs(COVERS_DIR, exist_ok=True)
    if "--report-only" not in sys.argv and player_running():
        # It re-reads GG's library itself whenever the page is opened, so just show it.
        print("The player is already running" + ("." if background else ", opening it."))
        if not background and "--no-open" not in sys.argv:
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    hist = load_history()
    clips, capture_dir, covers, changes = sync(hist)
    titled = sum(is_custom(c["title"]) for c in clips.values())
    print(f"{titled} clips with your own GG titles, out of {len(clips)}.")
    print(f"{len(changes)} change(s) since the last run" + (":" if changes else "."))
    for ch in changes:
        print("  " + describe(ch))
    print(f"Saved page: {REPORT}")
    if "--report-only" not in sys.argv:
        serve(hist, clips, capture_dir, covers, background)


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GG Clips</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Chakra+Petch:wght@500;600;700&display=swap">
<script>try{document.documentElement.dataset.theme=localStorage.getItem('ggclips.theme')||'dark'}catch(e){document.documentElement.dataset.theme='dark'}</script>
<style>
:root{--bg:#050505;--glow:rgba(7,242,204,.07);--glow2:rgba(255,255,255,.035);--panel:#111111;--panel-2:#171717;--panel-3:#222222;--line:#262626;--line-2:#383838;--text:#ffffff;--muted:#a6a6a6;--faint:#6f6f6f;--accent:#07f2cc;--accent-hi:#45f6da;--accent-soft:rgba(7,242,204,.14);--accent-text:#07f2cc;--on-accent:#00140f;--nick:#ff6a1a;--star:#ffcc33;--ok:#35d08f;--bad:#ff5d6e;--shadow:0 18px 40px rgba(0,0,0,.5);--r:14px;color-scheme:dark}
:root[data-theme=light]{--bg:#f3f3f3;--glow:rgba(7,242,204,.10);--glow2:rgba(0,0,0,.02);--panel:#ffffff;--panel-2:#f7f7f7;--panel-3:#ebebeb;--line:#e2e2e2;--line-2:#cfcfcf;--text:#0a0a0a;--muted:#5a5a5a;--faint:#8c8c8c;--accent:#07f2cc;--accent-hi:#45f6da;--accent-soft:rgba(7,242,204,.18);--accent-text:#00826c;--star:#d99a00;--shadow:0 18px 40px rgba(0,0,0,.12);color-scheme:light}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0}
body{min-height:100vh;overflow-x:hidden;background:radial-gradient(900px 420px at 8% -10%,var(--glow),transparent 65%),radial-gradient(800px 420px at 100% -5%,var(--glow2),transparent 60%),var(--bg);background-attachment:fixed;color:var(--text);font:14px/1.45 "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif;-webkit-font-smoothing:antialiased}
body.noscroll{overflow:hidden}
a{color:inherit}
button,input,select{font:inherit;color:inherit}
button{cursor:pointer}
button:disabled{cursor:not-allowed;opacity:.4}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.ic{width:18px;height:18px;flex:none;display:block}
.dim{color:var(--faint)}
.mono{font-family:"Cascadia Mono",Consolas,monospace;font-size:12px}
.spacer{flex:1}

.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;padding:12px 24px;background:color-mix(in srgb,var(--bg) 80%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.brand{display:flex;align-items:center;gap:10px;font-weight:700;font-size:17px;white-space:nowrap;text-decoration:none}
.logo{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:linear-gradient(135deg,var(--accent),#04a98e);color:var(--on-accent);box-shadow:0 6px 18px rgba(7,242,204,.25)}
.logo .ic{width:14px;height:14px}
.search{flex:1;max-width:520px;position:relative;display:block}
.search .ic{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--faint);width:16px;height:16px}
.search input{width:100%;padding:9px 12px 9px 36px;border-radius:10px;border:1px solid var(--line);background:var(--panel);outline:none;transition:border-color .15s,box-shadow .15s}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.tabs,.seg{display:flex;gap:3px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:3px}
.tabs a,.seg button{border:0;background:none;padding:6px 12px;border-radius:7px;color:var(--muted);font-weight:600;display:flex;align-items:center;gap:6px;white-space:nowrap;text-decoration:none}
.tabs a:hover,.seg button:hover{color:var(--text)}
.tabs a.on{background:var(--panel-3);color:var(--text)}
.seg button.on{background:var(--accent);color:var(--on-accent)}
.seg .ic{width:14px;height:14px}
.pill{display:inline-block;min-width:18px;padding:0 6px;border-radius:9px;background:var(--accent-soft);color:var(--accent-text);font-size:11px;font-weight:700;text-align:center}
.pill:empty{display:none}
.icon-btn{width:36px;height:36px;border-radius:10px;border:1px solid var(--line);background:var(--panel);display:grid;place-items:center;color:var(--muted);transition:color .15s,border-color .15s;flex:none}
.icon-btn:hover{color:var(--text);border-color:var(--line-2)}
.icon-btn.sm{width:30px;height:30px;border-radius:8px}
.icon-btn.sm .ic{width:15px;height:15px}
.banner{margin:14px 24px 0;padding:10px 14px;border-radius:10px;background:var(--accent-soft);border:1px solid color-mix(in srgb,var(--accent) 35%,transparent);font-size:13px}
.page{max-width:1720px;margin:0 auto;padding:22px 24px 56px}
.sechead{display:flex;align-items:center;gap:12px;margin:0 0 16px}
.sechead h2{margin:0;font-size:20px}
.count{color:var(--muted);font-size:13px}
.select{padding:7px 32px 7px 12px;border-radius:10px;border:1px solid var(--line);background:var(--panel) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23a6a6a6' stroke-width='2.5' stroke-linecap='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right 10px center;appearance:none;-webkit-appearance:none;outline:none;cursor:pointer}
.select:focus{border-color:var(--accent)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:8px 12px;border-radius:9px;border:1px solid var(--line-2);background:var(--panel-2);font-weight:600;text-decoration:none;transition:border-color .12s,background .12s}
.btn:hover:not(:disabled){border-color:var(--muted)}
.btn.sm{padding:5px 10px;font-size:12.5px}
.btn.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn.primary:hover:not(:disabled){background:var(--accent-hi);border-color:var(--accent-hi)}
.btn.wide{width:100%}
.btn .ic{width:16px;height:16px}
.tag{display:inline-flex;align-items:center;gap:4px;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;background:var(--panel-3);color:var(--muted);white-space:nowrap}
.tag.star{color:var(--star)}
.tag.nick{background:var(--nick);color:#fff;letter-spacing:.03em;text-transform:uppercase;font-size:10px}
.tags{display:flex;gap:5px;flex-wrap:wrap}
.gicon{width:26px;height:26px;border-radius:7px;flex:none;display:grid;place-items:center;font-size:10px;font-weight:800;letter-spacing:.02em;color:var(--text);background:var(--panel-3);box-shadow:inset 0 0 0 1px var(--line-2)}

/* home: highlighted clips */
.hero{position:relative;height:var(--hh,380px);margin:0 0 52px}
.hitem{position:absolute;left:50%;top:0;width:var(--vw);height:var(--hh);margin-left:calc(var(--vw) / -2);border-radius:14px;overflow:hidden;background:#05070a;cursor:pointer;transition:transform .55s cubic-bezier(.2,.8,.2,1),filter .55s,opacity .45s,border-radius .3s;will-change:transform;box-shadow:0 22px 50px rgba(0,0,0,.5)}
.hitem img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.hitem.side{filter:brightness(.4) saturate(.8)}
.hitem.side:hover{filter:brightness(.62) saturate(.95)}
.hitem.center{border-radius:14px 0 0 14px}
.hitem.instant{transition:none}
.hitem video{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .45s}
.hitem video.on{opacity:1}
.hprog{position:absolute;left:0;bottom:0;height:3px;width:0;background:var(--accent);z-index:2}
.hinfo{position:absolute;top:0;left:50%;width:var(--iw);height:var(--hh);z-index:7;background:var(--panel);border:1px solid var(--line);border-left:0;border-radius:0 14px 14px 0;padding:20px;display:flex;flex-direction:column;gap:9px;box-shadow:0 22px 50px rgba(0,0,0,.35);transition:transform .55s cubic-bezier(.2,.8,.2,1);overflow:hidden}
.hlabel{align-self:flex-start;display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:var(--on-accent);background:var(--accent);padding:3px 8px;border-radius:6px}
.hlabel .ic{width:11px;height:11px}
.hgame{display:flex;align-items:center;gap:10px;font-weight:700;text-decoration:none}
.hgame:hover{color:var(--accent-text)}
.hgame img{width:30px;height:40px;border-radius:5px;object-fit:cover;flex:none}
.hinfo>*{flex-shrink:0}
.htitle{font-size:20px;font-weight:700;line-height:1.25;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.htitle.auto{color:var(--muted);font-weight:600}
.hmeta{color:var(--muted);font-size:13px}
.hbtns{margin-top:auto;display:flex;gap:8px;flex-wrap:wrap}
.harrow{position:absolute;top:calc(var(--hh) / 2 - 20px);width:40px;height:40px;border-radius:50%;border:1px solid var(--line-2);background:color-mix(in srgb,var(--panel) 85%,transparent);backdrop-filter:blur(6px);display:grid;place-items:center;color:var(--text);z-index:9}
.harrow:hover{border-color:var(--accent)}
.harrow.l{left:0}.harrow.r{right:0}
.hdots{position:absolute;left:50%;bottom:-28px;transform:translateX(-50%);display:flex;gap:6px}
.hdots button{width:8px;height:8px;border-radius:4px;border:0;background:var(--line-2);padding:0;transition:width .3s,background .3s}
.hdots button.on{width:24px;background:var(--accent)}
.hvol{position:absolute;left:50%;top:calc(var(--hh) - 46px);z-index:8;transition:transform .55s cubic-bezier(.2,.8,.2,1)}
.hero:not(.ready) *{transition:none!important}
.hero.compact .hinfo{left:0;top:var(--hh);width:100%;height:auto;transform:none!important;border-left:1px solid var(--line);border-radius:0 0 14px 14px}
.hero.compact .hitem.center{border-radius:14px 14px 0 0}
.hero.compact .harrow{top:calc(var(--hh) / 2 - 20px)}

/* home: games */
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(158px,1fr));gap:24px 16px}
.tile{display:block;text-decoration:none;outline:none;min-width:0}
.cover{position:relative;aspect-ratio:3/4;border-radius:10px;overflow:hidden;background:var(--panel-3);transition:transform .18s,box-shadow .18s}
.tile:hover>.cover,.tile:focus-visible>.cover{transform:translate(5px,-5px);box-shadow:-5px 5px 0 var(--accent)}
.mosaic .cover{border-radius:0;height:100%}
.cover img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.cover>img{z-index:1}
.gen{position:absolute;inset:0;z-index:0;background:linear-gradient(160deg,#2c2c2c,#0b0b0b);border-top:3px solid var(--accent)}
.gen img{opacity:.55}
.gen::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.85),rgba(0,0,0,.05) 65%)}
.gen span{position:absolute;left:10px;right:10px;bottom:10px;z-index:1;font-weight:800;font-size:18px;line-height:1.1;color:#fff;text-transform:uppercase;overflow-wrap:anywhere;text-shadow:0 2px 8px rgba(0,0,0,.6)}
.mosaic{position:absolute;inset:0;display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:2px;background:var(--panel)}
.mosaic>div{position:relative;overflow:hidden}
.mosaic>div .gen span{font-size:11px;left:6px;bottom:6px}
.all-label{position:absolute;inset:auto 0 0 0;padding:28px 10px 10px;background:linear-gradient(to top,rgba(0,0,0,.9),transparent);color:#fff;font-weight:800;font-size:18px;text-transform:uppercase;z-index:2}
.tname{margin-top:9px;font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tmeta{font-size:13px;color:var(--muted);margin-bottom:6px}
.foot{margin-top:28px;color:var(--faint);font-size:12.5px}

/* game page */
.back{display:inline-flex;align-items:center;gap:4px;color:var(--muted);text-decoration:none;font-weight:600;font-size:13px;margin-bottom:12px}
.back:hover{color:var(--text)}
.back .ic{width:16px;height:16px}
.ghead{display:flex;align-items:flex-end;gap:18px;margin:0 0 22px}
.ghead .cover{width:92px;flex:none;border-radius:8px}
.ghead h1{margin:0 0 6px;font-size:30px;line-height:1.15}
.gstats{color:var(--muted);font-size:13px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;cursor:pointer;transition:transform .16s,border-color .16s,box-shadow .16s;outline:none}
.card:hover,.card:focus-visible{transform:translateY(-3px);border-color:color-mix(in srgb,var(--accent) 70%,transparent);box-shadow:var(--shadow)}
.thumb{aspect-ratio:16/9;background:var(--panel-3);position:relative;overflow:hidden}
.thumb>img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .35s}
.card:hover .thumb>img{transform:scale(1.05)}
.thumb::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.55),transparent 50%);pointer-events:none;z-index:1}
.thumb video.pv{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;transition:opacity .3s}
.thumb video.pv.on{opacity:1}
.play-ic{position:absolute;inset:0;margin:auto;width:50px;height:50px;border-radius:50%;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);display:grid;place-items:center;color:#fff;opacity:0;transform:scale(.9);transition:.16s;z-index:2}
.card:hover .play-ic{opacity:1;transform:none}
.card.previewing .play-ic,.card.previewing .badge.len{opacity:0}
.badge{position:absolute;z-index:2;display:flex;align-items:center;gap:4px;background:rgba(0,0,0,.72);color:#fff;font-size:12px;font-weight:600;padding:2px 7px;border-radius:6px;font-variant-numeric:tabular-nums;transition:opacity .2s}
.badge .ic{width:13px;height:13px}
.badge.len{right:8px;bottom:8px}
.badge.star{left:8px;top:8px;color:var(--star);padding:3px 5px}
.badge.cut{right:8px;top:8px;padding:3px 5px}
.pbar{position:absolute;left:0;bottom:0;height:3px;width:0;background:var(--accent);z-index:3}
.card .vctl{position:absolute;left:8px;bottom:8px;z-index:3}
.info{padding:10px 12px 12px}
.ginfo{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);min-width:0}
.ginfo>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ginfo .tag{margin-left:auto}
.gdot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--accent)}
.ctitle{font-weight:600;font-size:15px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ctitle.auto{color:var(--muted);font-weight:500}
.csub{font-size:12px;color:var(--faint);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.empty{color:var(--muted);background:var(--panel);border:1px dashed var(--line-2);border-radius:var(--r);padding:20px;text-align:center;margin:0}
#sentinel{height:1px}

/* volume control (home page and hover previews) */
.vctl{display:flex;align-items:center;gap:6px;padding:3px 10px 3px 3px;border-radius:999px;background:rgba(0,0,0,.72);backdrop-filter:blur(6px);color:#fff;cursor:default}
.vctl button{width:28px;height:28px;border:0;border-radius:50%;background:none;color:#fff;display:grid;place-items:center;padding:0}
.vctl button:hover{background:rgba(255,255,255,.12)}
.vctl button .ic{width:16px;height:16px}
.vctl input{width:76px;margin:0;accent-color:#07f2cc;cursor:pointer}
.vctl .vval{font-size:11px;font-weight:600;min-width:30px;font-variant-numeric:tabular-nums}

/* change log */
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:var(--r);background:var(--panel)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 14px;border-bottom:1px solid var(--line);vertical-align:middle;font-size:13px}
th{color:var(--faint);font-weight:700;font-size:11px;letter-spacing:.07em;text-transform:uppercase;background:var(--panel-2)}
tr:last-child td{border-bottom:0}
td.when{white-space:nowrap;color:var(--muted)}
.kind{display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700;background:var(--panel-3);color:var(--muted);white-space:nowrap}
.kind.title{background:var(--accent-soft);color:var(--accent-text)}
.kind.nickname{background:color-mix(in srgb,var(--nick) 16%,transparent);color:var(--nick)}
.kind.new{background:color-mix(in srgb,var(--ok) 15%,transparent);color:var(--ok)}
.kind.removed{background:color-mix(in srgb,var(--bad) 15%,transparent);color:var(--bad)}
.old{color:var(--faint);text-decoration:line-through}
.arrow{color:var(--faint);margin:0 5px}
.link-btn{border:0;background:none;padding:0;color:var(--accent-text);font-weight:600;cursor:pointer;text-align:left}
.link-btn:hover{text-decoration:underline}
.clipcell{display:flex;gap:10px;align-items:center;min-width:0}
.clipcell .gicon{width:24px;height:24px;font-size:9px;border-radius:6px}

/* player */
.player{position:fixed;inset:0;z-index:50;display:grid;place-items:center;padding:24px}
.player-bg{position:absolute;inset:0;background:rgba(0,0,0,.82);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px)}
.shell{position:relative;width:min(1600px,100%);height:min(940px,100%);display:grid;grid-template-columns:minmax(0,1fr) 360px;background:var(--panel);border:1px solid var(--line);border-radius:18px;overflow:hidden;box-shadow:0 30px 90px rgba(0,0,0,.6);animation:pop .18s ease-out;outline:none}
@keyframes pop{from{opacity:0;transform:scale(.98)}}
.pmain{display:flex;flex-direction:column;min-width:0;min-height:0;background:#000}
.stage{flex:1;min-height:0;position:relative;display:grid;place-items:center;background:#000;cursor:pointer}
.stage video{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;display:block}
.bigplay{position:relative;width:76px;height:76px;border-radius:50%;background:rgba(0,0,0,.55);backdrop-filter:blur(6px);display:grid;place-items:center;color:#fff;opacity:0;transform:scale(.9);transition:opacity .2s,transform .2s;pointer-events:none}
.bigplay .ic{width:30px;height:30px}
.stage.paused .bigplay{opacity:1;transform:none}
.stage-msg{position:absolute;left:50%;bottom:18px;transform:translateX(-50%);background:rgba(0,0,0,.85);color:#fff;padding:7px 12px;border-radius:8px;font-size:13px;text-align:center}
.controls{padding:6px 16px 12px;background:#0a0a0a;color:#fff}
.tl{position:relative;height:34px;cursor:pointer;touch-action:none;user-select:none;-webkit-user-select:none}
.tl-rail{position:absolute;left:0;right:0;top:14px;height:6px;border-radius:3px;background:#2b2b2b}
.tl-played{position:absolute;left:0;top:14px;height:6px;border-radius:3px;background:rgba(255,255,255,.32)}
.tl-sel{position:absolute;top:10px;height:14px;border-radius:4px;background:rgba(7,242,204,.2);border:2px solid #07f2cc}
.tl-h{position:absolute;top:6px;width:12px;height:22px;margin-left:-6px;border-radius:4px;background:#07f2cc;cursor:ew-resize;box-shadow:0 2px 6px rgba(0,0,0,.5);z-index:2}
.tl-h::after{content:"";position:absolute;left:4px;right:4px;top:6px;bottom:6px;border-left:1.5px solid rgba(0,20,15,.6);border-right:1.5px solid rgba(0,20,15,.6)}
.tl-head{position:absolute;top:4px;width:3px;height:26px;margin-left:-1.5px;border-radius:2px;background:#fff;box-shadow:0 0 0 1px rgba(0,0,0,.5);pointer-events:none;z-index:3}
.tl-tip{position:absolute;bottom:34px;transform:translateX(-50%);background:#222;color:#fff;font-size:11px;padding:2px 7px;border-radius:5px;pointer-events:none;opacity:0;transition:opacity .1s;white-space:nowrap;font-variant-numeric:tabular-nums}
.tl:hover .tl-tip{opacity:1}
.crow{display:flex;align-items:center;gap:4px}
.cbtn{width:36px;height:36px;border:0;border-radius:9px;background:none;color:#d9d9d9;display:grid;place-items:center;transition:background .12s,color .12s;flex:none}
.cbtn:hover:not(:disabled){background:#1f1f1f;color:#fff}
.cbtn.on{color:#07f2cc;background:rgba(7,242,204,.12)}
.cbtn.main{width:44px;height:44px;border-radius:50%;background:#07f2cc;color:#00140f;margin:0 4px}
.cbtn.main:hover{background:#45f6da}
.cbtn.main .ic{width:20px;height:20px}
.ctime{margin-left:10px;font-variant-numeric:tabular-nums;font-size:13px;white-space:nowrap}
.ctime .dim{color:#8c8c8c}
.cspeed{background:#161616;border:1px solid #2b2b2b;color:#d9d9d9;border-radius:8px;padding:5px 8px;margin:0 4px;cursor:pointer;color-scheme:dark;outline:none}
.pmain:fullscreen{background:#000}
.pside{display:flex;flex-direction:column;min-height:0;min-width:0;border-left:1px solid var(--line);background:var(--panel)}
.phead{display:flex;align-items:center;gap:10px;padding:14px 16px;border-bottom:1px solid var(--line)}
.phead .gicon{width:34px;height:34px;border-radius:9px;font-size:12px}
.phead-txt{flex:1;min-width:0}
.pgame{font-weight:700;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pdate{font-size:12px;color:var(--muted)}
.pbody{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:22px;scrollbar-width:thin}
.sec h3{display:flex;align-items:center;gap:8px;margin:0 0 10px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.sec h3 .hint{margin-left:auto;text-transform:none;letter-spacing:0;font-weight:500;color:var(--muted);font-size:12px}
.trow{display:flex;align-items:flex-start;gap:8px}
.ptitle{margin:0;font-size:19px;line-height:1.3;flex:1;overflow-wrap:anywhere}
.ptitle.auto{color:var(--muted);font-weight:500}
.pmeta{margin-top:6px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;gap:5px;align-items:flex-start}
.pmeta b{color:var(--text);font-weight:600}
.pfile{display:flex;align-items:center;gap:8px;margin-top:10px;padding:8px 10px;border-radius:9px;background:var(--panel-2);border:1px solid var(--line);min-width:0}
.pfile .mono{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}
.rename{display:flex;flex-direction:column;gap:8px}
.input{width:100%;padding:8px 10px;border-radius:9px;border:1px solid var(--line-2);background:var(--panel-2);outline:none}
.input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.row{display:flex;gap:8px;flex-wrap:wrap}
.track{display:grid;grid-template-columns:30px minmax(0,1fr) 44px;align-items:center;gap:10px;padding:8px 10px;border-radius:10px;background:var(--panel-2);border:1px solid var(--line)}
.track+.track{margin-top:6px}
.track.off{opacity:.5}
.tname{font-size:13px;font-weight:600;display:flex;gap:6px;align-items:baseline}
.tname .dim{font-weight:400;font-size:12px}
.track input[type=range]{width:100%;margin:4px 0 0;accent-color:var(--accent)}
.val{font-size:12px;color:var(--muted);text-align:right;font-variant-numeric:tabular-nums}
.mute-btn{width:30px;height:30px;border-radius:8px;border:1px solid var(--line-2);background:var(--panel);display:grid;place-items:center;color:var(--muted)}
.mute-btn .ic{width:15px;height:15px}
.mute-btn.on{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 45%,transparent)}
.trim{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.tbox{padding:8px 10px;border-radius:10px;background:var(--panel-2);border:1px solid var(--line);display:flex;flex-direction:column;gap:2px}
.tbox span{font-size:11px;color:var(--faint);text-transform:uppercase;letter-spacing:.06em;font-weight:700}
.tbox b{font-size:17px;font-variant-numeric:tabular-nums}
.tbox .btn{margin-top:6px}
.tsel{margin:10px 0;font-size:13px;color:var(--muted)}
.tsel b{color:var(--text);font-variant-numeric:tabular-nums}
.field{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted);font-weight:600}
.exfile{margin:6px 0 10px;font-size:12px;color:var(--faint);overflow-wrap:anywhere}
.check{display:flex;align-items:center;gap:8px;margin:0 0 12px;font-size:13px;cursor:pointer}
.check input{accent-color:var(--accent);width:16px;height:16px;margin:0}
.exprog{margin-top:10px;display:flex;flex-direction:column;gap:6px;font-size:12.5px;color:var(--muted)}
.exprog.err{color:var(--bad)}
.exprog .ic{display:inline-block;vertical-align:-3px;width:15px;height:15px;color:var(--ok)}
.bar{height:6px;border-radius:3px;background:var(--panel-3);overflow:hidden}
.bar i{display:block;height:100%;width:0;background:var(--accent);transition:width .3s}
.note{margin:0;font-size:13px;color:var(--muted);background:var(--panel-2);border:1px dashed var(--line-2);border-radius:10px;padding:10px 12px}
.keys summary{cursor:pointer;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--faint)}
.keys dl{display:grid;grid-template-columns:auto 1fr;gap:7px 12px;margin:10px 0 0;font-size:12.5px}
.keys dt{white-space:nowrap}
.keys dd{margin:0;color:var(--muted)}
kbd{font-family:inherit;font-size:11px;padding:1px 6px;border-radius:5px;border:1px solid var(--line-2);border-bottom-width:2px;background:var(--panel-2)}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:80;background:var(--panel-3);color:var(--text);border:1px solid var(--line-2);padding:9px 14px;border-radius:10px;box-shadow:var(--shadow);font-size:13px;font-weight:600}
.toast.err{border-color:var(--bad);color:var(--bad)}

/* ---------- motion & polish ---------- */
html{scrollbar-gutter:stable}
:root{--ease-out:cubic-bezier(.2,.8,.2,1);--ease-in:cubic-bezier(.4,0,1,1);--ease-spring:cubic-bezier(.34,1.4,.64,1);--font-display:"Chakra Petch","Segoe UI Variable Display","Segoe UI",system-ui,sans-serif}
.brand,.sechead h2,.ghead h1,.htitle,.ptitle,.tname,.all-label,.gen span{font-family:var(--font-display)}
.sechead h2,.ghead h1{letter-spacing:.01em}
.ghead h1{font-size:34px}
.top{transition:background .25s var(--ease-out),box-shadow .25s var(--ease-out)}
.top.scrolled{background:color-mix(in srgb,var(--bg) 93%,transparent);box-shadow:0 10px 30px rgba(0,0,0,.35)}

/* sliding highlight under the active tab / filter */
.tabs,.seg{position:relative}
.tabs a,.seg button{position:relative;z-index:1;transition:color .2s var(--ease-out),transform .15s var(--ease-out)}
.seg-ind{position:absolute;top:3px;left:0;height:calc(100% - 6px);border-radius:7px;background:var(--accent);pointer-events:none;transition:transform .34s var(--ease-spring),width .34s var(--ease-spring),opacity .2s}
.tabs .seg-ind{background:var(--panel-3)}
.seg.has-ind button.on,.tabs.has-ind a.on{background:none}

/* press feedback */
.btn,.icon-btn,.cbtn,.harrow,.mute-btn{transition:transform .15s var(--ease-out),background .15s var(--ease-out),border-color .15s var(--ease-out),color .15s var(--ease-out)}
.btn:active:not(:disabled),.icon-btn:active,.cbtn:active:not(:disabled),.seg button:active,.tabs a:active,.harrow:active,.mute-btn:active:not(:disabled),.hdots button:active{transform:scale(.95)}
.card{transition:transform .22s var(--ease-out),border-color .22s var(--ease-out),box-shadow .22s var(--ease-out)}
.card:active{transform:translateY(-1px) scale(.985)}
.cover{transition:transform .26s var(--ease-spring),box-shadow .26s var(--ease-out)}
.tile:active>.cover{transform:translate(5px,-5px) scale(.97)}
.tile .tname{transition:color .2s var(--ease-out)}
.tile:hover .tname{color:var(--accent-text)}

/* images fade in once loaded; clip thumbnails shimmer while the drive catches up */
@keyframes shimmer{to{background-position:-200% 0}}
.thumb::before{content:"";position:absolute;inset:0;background:linear-gradient(100deg,transparent 30%,rgba(255,255,255,.06) 50%,transparent 70%) 0 0/200% 100%;animation:shimmer 1.3s linear infinite}
.thumb.ready::before{display:none}
.thumb>img,.cover>img,.hitem>img{opacity:0;transition:opacity .45s var(--ease-out),transform .35s}
.thumb>img.in,.cover>img.in,.hitem>img.in{opacity:1}
.gen>img{opacity:0;transition:opacity .45s var(--ease-out)}
.gen>img.in{opacity:.55}

/* tiles and clips rise in, one after another */
@keyframes rise{from{opacity:0;transform:translateY(14px) scale(.985)}}
.rise{animation:rise .4s var(--ease-out) backwards;animation-delay:var(--d,0ms)}
@keyframes view-in{from{opacity:0;transform:translateY(10px)}}
.view-in{animation:view-in .3s var(--ease-out)}

/* home: soft glow from the clip that's playing, progress on the active dot, info that eases in */
.hero-amb{position:absolute;left:-6%;right:-6%;top:-70px;bottom:-80px;pointer-events:none;z-index:0}
.hero-amb i{position:absolute;inset:0;background:center/cover no-repeat;filter:blur(80px) saturate(1.5);opacity:0;transition:opacity .9s var(--ease-out)}
.hero-amb i.on{opacity:.3}
:root[data-theme=light] .hero-amb i.on{opacity:.22}
.hdots button{position:relative;overflow:hidden}
.hdots button.on{width:32px;background:var(--line-2)}
.hdots button.on::after{content:"";position:absolute;inset:0;background:var(--accent);transform:scaleX(var(--p,0));transform-origin:left;transition:transform .3s linear}
@keyframes swap-in{from{opacity:0;transform:translateY(8px)}}
.hinfo.swap>*{animation:swap-in .38s var(--ease-out) backwards}
.hinfo.swap>:nth-child(2){animation-delay:.03s}.hinfo.swap>:nth-child(3){animation-delay:.06s}.hinfo.swap>:nth-child(4){animation-delay:.09s}.hinfo.swap>:nth-child(n+5){animation-delay:.12s}
.harrow{opacity:.75}
.hero:hover .harrow{opacity:1}

/* game page: blurred art behind the header */
#gameView{position:relative;isolation:isolate}
.gbanner{position:absolute;left:-24px;right:-24px;top:-22px;height:320px;z-index:-1;overflow:hidden;pointer-events:none;-webkit-mask-image:linear-gradient(#000 35%,transparent);mask-image:linear-gradient(#000 35%,transparent)}
.gbanner i{position:absolute;inset:-60px;background:center/cover no-repeat;filter:blur(50px) saturate(1.3);opacity:.32;transition:opacity .6s var(--ease-out)}
.ghead .cover{box-shadow:0 14px 34px rgba(0,0,0,.45)}

/* player: opens from the clip you clicked, closes back into it */
@keyframes pop{from{opacity:0;transform:translateY(10px) scale(.96)}}
@keyframes pop-out{to{opacity:0;transform:translateY(6px) scale(.97)}}
@keyframes fade-in{from{opacity:0}}
@keyframes fade-out{to{opacity:0}}
.shell{animation:pop .3s var(--ease-out)}
.player-bg{animation:fade-in .25s var(--ease-out)}
.player.morph .shell{animation:none}
.player.closing .shell{animation:pop-out .16s var(--ease-in) forwards}
.player.closing .player-bg{animation:fade-out .16s var(--ease-in) forwards}
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{position:absolute;width:46px;height:46px;border-radius:50%;border:3px solid rgba(255,255,255,.14);border-top-color:#07f2cc;animation:spin .8s linear infinite;opacity:0;transition:opacity .2s;pointer-events:none}
.stage.loading .spinner{opacity:1;transition-delay:.3s}
.stage.loading .bigplay{opacity:0}
@keyframes toast-in{from{opacity:0;transform:translate(-50%,12px)}}
.toast{animation:toast-in .28s var(--ease-out)}

/* page transitions (browsers with view transitions: Chrome, Edge, Firefox) */
::view-transition-group(*){animation-duration:.34s;animation-timing-function:var(--ease-out)}
::view-transition-old(root),::view-transition-new(root){animation-duration:.22s}
@keyframes vt-out-left{to{opacity:0;transform:translateX(-28px)}}
@keyframes vt-out-right{to{opacity:0;transform:translateX(28px)}}
@keyframes vt-in-right{from{opacity:0;transform:translateX(40px)}}
@keyframes vt-in-left{from{opacity:0;transform:translateX(-40px)}}
html[data-vt=forward]::view-transition-old(root){animation:.18s var(--ease-in) both vt-out-left}
html[data-vt=forward]::view-transition-new(root){animation:.34s var(--ease-out) both vt-in-right}
html[data-vt=back]::view-transition-old(root){animation:.18s var(--ease-in) both vt-out-right}
html[data-vt=back]::view-transition-new(root){animation:.34s var(--ease-out) both vt-in-left}
html[data-vt=forward] .top,html[data-vt=back] .top,html[data-vt=fade] .top{view-transition-name:topbar}
::view-transition-group(topbar){animation:none}
html[data-vt=open]::view-transition-group(clip-media){animation-duration:.38s}
html[data-vt=close]::view-transition-group(*){animation-duration:.26s}
html[data-vt=close]::view-transition-old(root),html[data-vt=close]::view-transition-new(root){animation-duration:.18s}
html[data-vt=next]::view-transition-group(clip-media),html[data-vt=prev]::view-transition-group(clip-media){animation:none}
html[data-vt=next]::view-transition-old(clip-media){animation:.18s var(--ease-in) both vt-out-left}
html[data-vt=next]::view-transition-new(clip-media){animation:.3s var(--ease-out) both vt-in-right}
html[data-vt=prev]::view-transition-old(clip-media){animation:.18s var(--ease-in) both vt-out-right}
html[data-vt=prev]::view-transition-new(clip-media){animation:.3s var(--ease-out) both vt-in-left}

/* save copy: quality choice, result actions */
.exq{display:flex;margin:0 0 6px}
.exq button{flex:1;justify-content:center}
.exnote{margin:0 0 12px;font-size:12px;color:var(--faint)}
#exActions:empty{display:none}
.check.over{padding:9px 10px;border-radius:10px;background:var(--accent-soft);border:1px solid color-mix(in srgb,var(--accent) 30%,transparent)}
.input:disabled{opacity:.6;cursor:not-allowed}
.pfile .btn{flex:none}
.sec h3 #mixReset{margin-left:8px;letter-spacing:0;text-transform:none}

@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.01ms!important;animation-iteration-count:1!important;animation-delay:0s!important;transition-duration:.01ms!important;transition-delay:0s!important}
}

@media (max-width:900px){
  .page{padding:16px 16px 40px}
  .top{flex-wrap:wrap;padding:10px 16px}
  .search{order:5;flex-basis:100%;max-width:none}
  .tiles{grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:18px 12px}
  .player{padding:0}
  .shell{grid-template-columns:1fr;grid-template-rows:auto minmax(0,1fr);height:100%;border-radius:0}
  .stage{aspect-ratio:16/9;flex:none}
  .pside{border-left:0;border-top:1px solid var(--line)}
  .ctime{margin-left:4px}
  #bBack,#bFwd{display:none}
}
</style>
</head>
<body>
<header class="top">
  <a class="brand" href="#/"><span class="logo" data-ic="play"></span><span>GG Clips</span></a>
  <label class="search"><span data-ic="search"></span><input id="q" type="search" placeholder="Search titles, nicknames, games, files, dates   ( / )" autocomplete="off" spellcheck="false"></label>
  <nav class="tabs" id="tabs"><a href="#/" data-tab="home">Home</a><a href="#/edited" data-tab="edited">Edited <span class="pill" id="edPill"></span></a><a href="#/log" data-tab="log">Change log <span class="pill" id="logCount"></span></a></nav>
  <div class="spacer"></div>
  <button class="icon-btn" id="bRefresh" data-ic="refresh" title="Re-read GG's library" hidden></button>
  <button class="icon-btn" id="bTheme" title="Light / dark theme"></button>
</header>
<div class="banner" id="banner" hidden></div>
<main class="page">
  <section id="homeView">
    <div class="hero" id="hero"></div>
    <div class="sechead">
      <h2>Browse games</h2><span class="count" id="catCount"></span>
      <div class="spacer"></div>
      <select class="select" id="catSort" aria-label="Sort games">
        <option value="recent">Recently played</option>
        <option value="clips">Most clips</option>
        <option value="name">A–Z</option>
      </select>
    </div>
    <div class="tiles" id="tiles"></div>
    <p class="foot">To use your own cover for a game, put a picture named exactly like the game (for example <span class="mono">VALORANT.jpg</span>) in the <span class="mono">covers</span> folder next to this page.</p>
  </section>
  <section id="gameView" hidden>
    <div class="gbanner" aria-hidden="true"><i id="gbannerArt"></i></div>
    <a class="back" href="#/" data-ic="chevl">Home</a>
    <div class="ghead" id="ghead"></div>
    <div class="toolbar">
      <div class="seg" id="filters">
        <button data-f="all">All</button>
        <button data-f="titled">Titled &amp; nicknamed</button>
        <button data-f="starred" data-ic="star">Starred</button>
      </div>
      <span class="count" id="count"></span>
      <div class="spacer"></div>
      <select class="select" id="sort" aria-label="Sort clips">
        <option value="new">Newest first</option>
        <option value="old">Oldest first</option>
        <option value="long">Longest first</option>
        <option value="short">Shortest first</option>
        <option value="title">Title A–Z</option>
        <option value="game">Game A–Z</option>
      </select>
    </div>
    <div class="grid" id="grid"></div>
    <div id="sentinel"></div>
    <p class="empty" id="noResults" hidden>No clips match these filters.</p>
  </section>
  <section id="editedView" hidden>
    <div class="sechead">
      <h2>Edited clips</h2><span class="count" id="edCount"></span>
      <div class="spacer"></div>
      <button class="btn sm" id="edFolder" type="button" data-ic="folder">Open folder</button>
      <select class="select" id="edSort" aria-label="Sort edited clips">
        <option value="new">Newest first</option>
        <option value="old">Oldest first</option>
        <option value="big">Largest first</option>
        <option value="name">Name A–Z</option>
      </select>
    </div>
    <div class="grid" id="edGrid"></div>
    <p class="empty" id="edEmpty" hidden></p>
  </section>
  <section id="logView" hidden><div class="sechead"><h2>Change log</h2></div><div id="logBody"></div></section>
</main>

<div class="player" id="player" hidden>
  <div class="player-bg" data-close></div>
  <div class="shell" id="shell" role="dialog" aria-modal="true" aria-label="Clip player" tabindex="-1">
    <div class="pmain" id="pmain">
      <div class="stage paused" id="stage">
        <video id="vid" playsinline preload="auto"></video>
        <div class="bigplay" data-ic="play"></div>
        <div class="spinner" aria-hidden="true"></div>
        <div class="stage-msg" id="stageMsg" hidden></div>
      </div>
      <div class="controls">
        <div class="tl" id="tl">
          <div class="tl-rail"></div>
          <div class="tl-sel" id="tlSel"></div>
          <div class="tl-played" id="tlPlayed"></div>
          <div class="tl-h" id="hIn" title="Start: drag, or press I"></div>
          <div class="tl-h" id="hOut" title="End: drag, or press O"></div>
          <div class="tl-head" id="tlHead"></div>
          <div class="tl-tip" id="tlTip">0:00</div>
        </div>
        <div class="crow">
          <button class="cbtn" id="bPrev" data-ic="prev" title="Previous clip (P)"></button>
          <button class="cbtn" id="bBack" data-ic="back" title="Back 5 seconds (←)"></button>
          <button class="cbtn main" id="bPlay" title="Play / pause (Space)"></button>
          <button class="cbtn" id="bFwd" data-ic="fwd" title="Forward 5 seconds (→)"></button>
          <button class="cbtn" id="bNext" data-ic="next" title="Next clip (N)"></button>
          <div class="ctime"><span id="tCur">0:00</span> <span class="dim">/ <span id="tDur">0:00</span></span></div>
          <div class="spacer"></div>
          <button class="cbtn" id="bLoop" data-ic="loop" title="Loop the selection"></button>
          <select class="cspeed" id="speed" title="Playback speed">
            <option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="0.75">0.75×</option>
            <option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option>
          </select>
          <button class="cbtn" id="bMute" title="Mute everything (M)"></button>
          <button class="cbtn" id="bFull" data-ic="full" title="Full screen (F)"></button>
        </div>
      </div>
    </div>
    <aside class="pside">
      <div class="phead">
        <span class="gicon" id="pIcon"></span>
        <div class="phead-txt"><div class="pgame" id="pGame"></div><div class="pdate" id="pDate"></div></div>
        <button class="icon-btn sm" data-close data-ic="close" title="Close (Esc)"></button>
      </div>
      <div class="pbody">
        <section class="sec">
          <div class="trow" id="titleView">
            <h2 class="ptitle" id="pTitle"></h2>
            <button class="icon-btn sm" id="bRename" data-ic="edit" title="Give this clip a nickname (R)"></button>
          </div>
          <form class="rename" id="renameForm" hidden>
            <input class="input" id="renameInput" maxlength="120" autocomplete="off">
            <div class="row"><button class="btn primary sm" type="submit">Save nickname</button><button class="btn sm" type="button" id="renameCancel">Cancel</button></div>
          </form>
          <div class="pmeta" id="pMeta"></div>
          <div class="pfile"><span class="mono" id="pFile"></span><button class="btn sm" id="bReveal" type="button" data-ic="folder">Show in folder</button></div>
        </section>
        <section class="sec">
          <h3>Audio <span class="hint" id="mixHint"></span><button class="btn sm" id="mixReset" type="button" hidden>Reset to GG levels</button></h3>
          <div id="mixer"></div>
        </section>
        <section class="sec">
          <h3>Trim</h3>
          <div class="trim">
            <div class="tbox"><span>Start</span><b id="tIn">0:00.0</b><button class="btn sm" id="setIn">Set here (I)</button></div>
            <div class="tbox"><span>End</span><b id="tOut">0:00.0</b><button class="btn sm" id="setOut">Set here (O)</button></div>
          </div>
          <div class="tsel">Selection length <b id="tSel">0:00.0</b></div>
          <div class="row"><button class="btn sm" id="trimFull">Whole clip</button><button class="btn sm" id="trimGG">GG's trim</button></div>
        </section>
        <section class="sec">
          <h3 id="exTitle">Save edited copy</h3>
          <div id="exportBody">
            <label class="check over" id="exOverRow"><input type="checkbox" id="exOverwrite" checked> Overwrite this edited clip <span class="dim">(untick to save a new copy instead)</span></label>
            <label class="field">Name<input class="input" id="exName" maxlength="100" placeholder="edit" autocomplete="off"></label>
            <div class="exfile" id="exFile"></div>
            <div class="seg exq" id="exQuality" role="group" aria-label="Quality">
              <button type="button" data-q="original">Original quality</button>
              <button type="button" data-q="small">Compressed · 18 MB</button>
            </div>
            <p class="exnote" id="exQNote"></p>
            <label class="check" id="exPreciseRow"><input type="checkbox" id="exPrecise"> Exact cut <span class="dim">(re-encodes the video, a bit slower)</span></label>
            <label class="check"><input type="checkbox" id="exLoud"> Even out loudness <span class="dim">(normal YouTube level)</span></label>
            <button class="btn primary wide" id="exGo" data-ic="save">Save copy</button>
            <div class="exprog" id="exProg" hidden><div class="bar"><i id="exBar"></i></div><span id="exText"></span><div class="row" id="exActions"></div></div>
          </div>
          <p class="note" id="exportNote" hidden></p>
        </section>
        <details class="sec keys">
          <summary>Keyboard shortcuts</summary>
          <dl>
            <dt><kbd>Space</kbd> <kbd>K</kbd></dt><dd>Play / pause</dd>
            <dt><kbd>←</kbd> <kbd>→</kbd></dt><dd>Back / forward 5 s (with Shift: 1 s)</dd>
            <dt><kbd>J</kbd> <kbd>L</kbd></dt><dd>Back / forward 10 s</dd>
            <dt><kbd>,</kbd> <kbd>.</kbd></dt><dd>One frame back / forward</dd>
            <dt><kbd>I</kbd> <kbd>O</kbd></dt><dd>Set start / end of the selection</dd>
            <dt><kbd>Home</kbd> <kbd>End</kbd></dt><dd>Jump to start / end of the selection</dd>
            <dt><kbd>P</kbd> <kbd>N</kbd></dt><dd>Previous / next clip</dd>
            <dt><kbd>R</kbd></dt><dd>Nickname</dd>
            <dt><kbd>M</kbd> <kbd>F</kbd></dt><dd>Mute / full screen</dd>
            <dt><kbd>Esc</kbd></dt><dd>Close the player</dd>
          </dl>
        </details>
      </div>
    </aside>
  </div>
</div>
<div class="toast" id="toast" hidden></div>
<script id="data" type="application/json">__GG_DATA__</script>
<script>
(() => {
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const META = D.meta, SERVER = META.mode === 'server', TOKEN = META.token || '';
const AUDIO = SERVER && META.ffmpeg;  // Chat/Mic can be played (they're pulled out of the clip by the player)
const $ = id => document.getElementById(id);

const P = {
  play: '<path d="M7 4.6v14.8a.6.6 0 0 0 .9.5l11.6-7.4a.6.6 0 0 0 0-1L7.9 4.1a.6.6 0 0 0-.9.5z" fill="currentColor" stroke="none"/>',
  pause: '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/>',
  prev: '<path d="M18 5.5v13L8.5 12z" fill="currentColor" stroke="none"/><path d="M6 5.5v13"/>',
  next: '<path d="M6 5.5v13l9.5-6.5z" fill="currentColor" stroke="none"/><path d="M18 5.5v13"/>',
  chevl: '<path d="m15 5-7 7 7 7"/>',
  chevr: '<path d="m9 5 7 7-7 7"/>',
  back: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1"/><path d="M3.5 4v4.5H8"/><text x="12.5" y="15.5" font-size="7.5" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none">5</text>',
  fwd: '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/><path d="M20.5 4v4.5H16"/><text x="11.5" y="15.5" font-size="7.5" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none">5</text>',
  vol: '<path d="M11 5 6 9H3v6h3l5 4z" fill="currentColor"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/>',
  mute: '<path d="M11 5 6 9H3v6h3l5 4z" fill="currentColor"/><path d="m22 9-6 6M16 9l6 6"/>',
  full: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  loop: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14"/><path d="m7 22-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  star: '<path d="m12 3.5 2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z" fill="currentColor"/>',
  scissors: '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  save: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7"/>',
  pad: '<path d="M6.5 8h11a4.5 4.5 0 0 1 4.3 5.8l-.6 2a2.8 2.8 0 0 1-4.6 1.2L14.4 15H9.6L7.4 17a2.8 2.8 0 0 1-4.6-1.2l-.6-2A4.5 4.5 0 0 1 6.5 8z"/><path d="M7.5 10.5v3M6 12h3"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
  folder: '<path d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2h8.5A1.5 1.5 0 0 1 21 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z"/>',
};
const ic = n => `<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ''}</svg>`;
document.querySelectorAll('[data-ic]').forEach(el => el.insertAdjacentHTML('afterbegin', ic(el.dataset.ic)));

const esc = s => String(s ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
const pad = n => String(n).padStart(2, '0');
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function fmtDate(iso) {
  const d = new Date(iso);
  if (!iso || isNaN(d)) return '—';
  return `${d.getDate()} ${MON[d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fmtAgo(ts) {
  const s = (Date.now() - ts) / 1000;
  if (s < 3600) return 'just now';
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  if (d < 31) return d === 1 ? 'yesterday' : `${d} days ago`;
  if (d < 365) return `${Math.floor(d / 30.4)} mo ago`;
  return `${Math.floor(d / 365)} yr ago`;
}
function fmtLen(s) {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`;
}
function fmtExact(s) {
  const t = Math.round(Math.max(0, s || 0) * 10), m = Math.floor(t / 600), r = t - m * 600;
  return `${m}:${pad(Math.floor(r / 10))}.${r % 10}`;
}
function hue(s) { let h = 0; for (const ch of String(s)) h = (h * 31 + ch.codePointAt(0)) >>> 0; return h % 360; }
function initials(g) {
  const w = String(g).replace(/[™®©]/g, '').split(/[\s\-_:.]+/).filter(Boolean);
  if (!w.length) return '?';
  return (w.length > 1 ? w[0][0] + w[1][0] : w[0].slice(0, 2)).toUpperCase();
}
const store = {
  get(k, d) { try { const v = localStorage.getItem('ggclips.' + k); return v === null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('ggclips.' + k, v); } catch (e) {} },
};
let toastTimer;
function toast(msg, err) {
  const t = $('toast');
  t.textContent = msg; t.className = 'toast' + (err ? ' err' : ''); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
}
async function post(path, body) {
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Token': TOKEN}, body: JSON.stringify(body)});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
async function getJSON(path) {
  const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + encodeURIComponent(TOKEN));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}
const trackUrl = (c, n) => `/audio/${c.id}/${n}?t=${encodeURIComponent(TOKEN)}`;
const level = t => (t && !t.muted ? (t.volume ?? 1) : 0);  // a track's volume in your GG mix

// ---------- motion helpers ----------
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
const canAnimate = () => !reduceMotion.matches && !!document.startViewTransition && !document.hidden;
let vtSeq = 0;
// Run a page change as a smooth transition (kind picks the animation); falls back to an instant change.
function vt(kind, update) {
  if (!canAnimate()) { update(); return Promise.resolve(); }
  const seq = ++vtSeq;
  document.documentElement.dataset.vt = kind;
  const t = document.startViewTransition(update);
  t.ready.catch(() => {});  // a transition interrupted by the next click is fine; the page still updates
  return t.finished.catch(() => {}).finally(() => { if (seq === vtSeq) delete document.documentElement.dataset.vt; });
}
window.ggImg = img => { img.classList.add('in'); const t = img.closest('.thumb'); if (t) t.classList.add('ready'); };
window.ggImgFail = img => { const t = img.closest('.thumb'); if (t) t.classList.add('ready'); img.remove(); };
// The highlight that slides under the active tab / filter
function placeInd(box) {
  if (!box || !box.offsetParent) return;
  let ind = box.querySelector(':scope > .seg-ind');
  const fresh = !ind;
  if (fresh) { ind = document.createElement('span'); ind.className = 'seg-ind'; box.prepend(ind); box.classList.add('has-ind'); }
  const on = box.querySelector('.on');
  if (fresh) ind.style.transition = 'none';
  ind.style.opacity = on ? '1' : '0';
  if (on) { ind.style.width = on.offsetWidth + 'px'; ind.style.transform = `translateX(${on.offsetLeft}px)`; }
  if (fresh) requestAnimationFrame(() => { ind.style.transition = ''; });
}
function replay(el, cls) { el.classList.remove(cls); void el.offsetWidth; el.classList.add(cls); }

// ---------- data ----------
const clips = D.clips, byId = new Map();
const shownTitle = c => c.nick || c.title;
function indexClip(c) { c.search = [c.nick, c.title, c.game, c.file, fmtDate(c.recorded)].join(' ').toLowerCase(); }
for (const c of clips) {
  c.ts = Date.parse(c.recorded) || 0;
  c.len = c.trimmed ? c.end - c.start : c.full;
  indexClip(c);
  byId.set(c.id, c);
}
const COVER = new Map(D.games.map(g => [g.name, g.cover]));
const GAMES = new Set(clips.map(c => c.game));
const filterPref = store.get('filter', 'all');
const state = {view: 'home', game: '', filter: filterPref === 'nick' ? 'titled' : filterPref, sort: store.get('sort', 'new'), catSort: store.get('catSort', 'recent'), q: []};

// Clips that have Chat/Mic: keep them playing in step with the video they belong to.
function syncTracks(video, els, force) {
  const t = video.currentTime, running = !video.paused && !video.seeking && video.readyState >= 3;
  for (const el of els) {
    if (el.readyState < 1) continue;
    if (el.playbackRate !== video.playbackRate) el.playbackRate = video.playbackRate;
    const inside = t < (el.duration || Infinity) - 0.05;
    if (inside && (force || Math.abs(el.currentTime - t) > 0.12)) el.currentTime = t;
    if (running && inside) { if (el.paused) el.play().catch(() => {}); }
    else if (!el.paused) el.pause();
  }
}
// Chat/Mic for the home page and hover previews (plain audio elements; volumes up to 100%)
function attachTracks(video, c) {
  if (!AUDIO || c.tracks.length < 2) return null;
  const els = c.tracks.slice(1).map((t, k) => { const a = new Audio(); a.preload = 'auto'; a.lvl = level(t); a.src = trackUrl(c, k + 1); return a; });
  const sync = force => syncTracks(video, els, force);
  const evs = {seeked: () => sync(true), play: () => sync(true), playing: () => sync(true), pause: () => sync(false), waiting: () => sync(false), seeking: () => sync(false), ratechange: () => sync(false)};
  for (const k in evs) video.addEventListener(k, evs[k]);
  els.forEach(a => a.addEventListener('canplay', () => { applyPreviewVolumes(); sync(true); }, {once: true}));
  const timer = setInterval(() => sync(false), 250);
  return {els, destroy() {
    clearInterval(timer);
    for (const k in evs) video.removeEventListener(k, evs[k]);
    els.forEach(a => { a.pause(); a.removeAttribute('src'); a.load(); });
  }};
}

// ---------- preview volume (home page + hover previews), default 20% ----------
const pvol = {vol: clamp(+store.get('pvol', '0.2') || 0, 0, 1), muted: store.get('pmuted', '0') === '1'};
function setPreviewVolume(video, tracks, c) {
  const blocked = video.dataset.blocked === '1';
  video.volume = clamp(pvol.vol * level(c.tracks[0]), 0, 1);
  video.muted = pvol.muted || blocked;
  if (tracks) for (const a of tracks.els) { a.volume = clamp(pvol.vol * a.lvl, 0, 1); a.muted = video.muted; }
}
function applyPreviewVolumes() {
  if (hero.cur) {
    if (!hero.video.muted && !hero.audio && !hero.video.paused) hero.audio = attachTracks(hero.video, hero.cur);
    setPreviewVolume(hero.video, hero.audio, hero.cur);
  }
  if (pv) setPreviewVolume(pv.v, pv.audio, pv.c);
  document.querySelectorAll('.vctl').forEach(updateVolCtl);
}
function playWithSound(video) {
  video.play().catch(err => {
    if (err && err.name === 'NotAllowedError' && !video.muted) {
      // The browser only allows sound after you've clicked something on the page
      video.dataset.blocked = '1';
      video.muted = true;
      video.play().catch(() => {});
      document.querySelectorAll('.vctl').forEach(updateVolCtl);
    }
  });
}
function volCtl() {
  const el = document.createElement('div');
  el.className = 'vctl';
  el.title = 'Preview volume';
  el.innerHTML = '<button type="button" aria-label="Mute or unmute"></button><input type="range" min="0" max="100" step="1" aria-label="Preview volume"><span class="vval"></span>';
  const unblock = () => document.querySelectorAll('video[data-blocked="1"]').forEach(v => { v.dataset.blocked = ''; });
  el.querySelector('button').onclick = () => {
    const blocked = document.querySelector('video[data-blocked="1"]');
    unblock();
    pvol.muted = blocked ? false : !pvol.muted;
    if (!pvol.muted && pvol.vol === 0) pvol.vol = 0.2;
    store.set('pmuted', pvol.muted ? '1' : '0'); store.set('pvol', String(pvol.vol));
    applyPreviewVolumes();
  };
  el.querySelector('input').oninput = e => {
    unblock();
    pvol.vol = +e.target.value / 100;
    pvol.muted = pvol.vol === 0;
    store.set('pvol', String(pvol.vol)); store.set('pmuted', pvol.muted ? '1' : '0');
    applyPreviewVolumes();
  };
  ['click', 'pointerdown', 'mousedown', 'keydown'].forEach(ev => el.addEventListener(ev, e => e.stopPropagation()));
  updateVolCtl(el);
  return el;
}
function updateVolCtl(el) {
  const silent = pvol.muted || pvol.vol === 0 || !!document.querySelector('video[data-blocked="1"]');
  el.querySelector('button').innerHTML = ic(silent ? 'mute' : 'vol');
  el.querySelector('input').value = Math.round(pvol.vol * 100);
  el.querySelector('.vval').textContent = silent ? 'Muted' : Math.round(pvol.vol * 100) + '%';
}

// ---------- header and navigation ----------
const root = document.documentElement, banner = $('banner');
function setThemeIcon() { $('bTheme').innerHTML = ic(root.dataset.theme === 'dark' ? 'sun' : 'moon'); }
$('bTheme').onclick = () => { root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark'; store.set('theme', root.dataset.theme); setThemeIcon(); };
if (!SERVER) {
  // The saved copy can't play Chat/Mic or save anything, so switch to the full player when it's running.
  const player = `http://127.0.0.1:${META.port || 48650}/`;
  banner.textContent = 'Looking for the full player…';
  banner.hidden = false;
  fetch(player + 'api/ping', {mode: 'no-cors', cache: 'no-store'})
    .then(() => { banner.textContent = 'Opening the full player…'; location.replace(player + location.hash); })
    .catch(() => {
      banner.innerHTML = 'This is the saved copy of the page, so Chat &amp; Mic, nicknames and saving copies are off. '
        + `The full player starts with Windows at <a href="${player}">${player}</a>; `
        + 'if that link doesn’t open, double-click <b>_Update GG Titles.bat</b> to start it.';
    });
} else {
  if (!META.ffmpeg) { banner.textContent = 'ffmpeg wasn’t found, so Chat/Mic audio and saving edited copies are turned off.'; banner.hidden = false; }
  $('bRefresh').hidden = false;
  $('bRefresh').onclick = () => location.reload();
  let misses = 0;
  setInterval(async () => {
    try {
      const r = await getJSON('/api/ping');
      misses = 0;
      if (r.session !== META.session && !cur) location.reload();  // the player was restarted
    } catch (e) { if (++misses === 2) { banner.textContent = 'The player has stopped. Double-click _Update GG Titles.bat to start it again.'; banner.hidden = false; } }
  }, 20000);
}
function parseHash() {
  const h = decodeURIComponent(location.hash.replace(/^#\/?/, ''));
  if (h === 'all') return {view: 'game', game: ''};
  if (h.startsWith('game/') && GAMES.has(h.slice(5))) return {view: 'game', game: h.slice(5)};
  if (h === 'log') return {view: 'log', game: ''};
  if (h === 'edited') return {view: 'edited', game: ''};
  return {view: 'home', game: ''};
}
const DEPTH = {home: 0, log: 0, edited: 0, game: 1};
const scrollMemo = new Map();
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';  // the page restores scroll itself, after the transition starts
let curHash = null;
const tileCover = game => $('tiles').querySelector(`a.tile[href="#/game/${encodeURIComponent(game)}"] > .cover`);
function applyRoute(to) {
  state.view = to.view; state.game = to.game;
  const views = {home: $('homeView'), game: $('gameView'), edited: $('editedView'), log: $('logView')};
  for (const [v, el] of Object.entries(views)) el.hidden = v !== state.view;
  const tab = state.view === 'game' ? 'home' : state.view;
  $('tabs').querySelectorAll('a').forEach(a => a.classList.toggle('on', a.dataset.tab === tab));
  stopPreview();
  render();
  heroSync();
  placeInd($('tabs'));
  placeInd($('filters'));
  if (!document.startViewTransition && !reduceMotion.matches) replay(views[state.view], 'view-in');
}
function restoreScroll(y) {
  if (y > 0 && state.view === 'game') {
    while (document.documentElement.scrollHeight < y + innerHeight && shown < list.length) more();
  }
  window.scrollTo({top: y, behavior: 'instant'});
}
// Going into a game slides forward and its cover grows into the page's cover; going back reverses it.
function route(first) {
  const to = parseHash(), from = {view: state.view, game: state.game};
  const hash = location.hash || '#/';
  if (curHash !== null) scrollMemo.set(curHash, scrollY);
  curHash = hash;
  if (first === true) { applyRoute(to); return; }
  const dir = DEPTH[to.view] > DEPTH[from.view] ? 'forward' : DEPTH[to.view] < DEPTH[from.view] ? 'back' : 'fade';
  const y = dir === 'forward' ? 0 : scrollMemo.get(hash) || 0;
  let source = null, target = null;
  if (canAnimate()) {
    source = dir === 'forward' && to.game ? tileCover(to.game) : dir === 'back' && from.game ? $('ghead').querySelector('.cover') : null;
    if (source && inView(source)) source.style.viewTransitionName = 'game-cover'; else source = null;
  }
  vt(dir, () => {
    if (source) source.style.viewTransitionName = '';
    applyRoute(to);
    restoreScroll(y);
    if (source) {
      target = dir === 'forward' ? $('ghead').querySelector('.cover') : tileCover(from.game);
      if (target && inView(target)) target.style.viewTransitionName = 'game-cover'; else target = null;
    }
  }).then(() => { if (target) target.style.viewTransitionName = ''; });
}
window.addEventListener('hashchange', route);
let scrollRaf = 0;
window.addEventListener('scroll', () => {
  if (scrollRaf) return;
  scrollRaf = requestAnimationFrame(() => { scrollRaf = 0; document.querySelector('.top').classList.toggle('scrolled', scrollY > 4); });
}, {passive: true});
window.addEventListener('resize', () => { placeInd($('tabs')); placeInd($('filters')); });
if (document.fonts) document.fonts.ready.then(() => { placeInd($('tabs')); placeInd($('filters')); });
function render() {
  if (state.view === 'home') renderHome();
  else if (state.view === 'game') renderGame();
  else if (state.view === 'edited') renderEdited();
  else renderLog();
}
let qTimer;
$('q').addEventListener('input', () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => {
    state.q = $('q').value.toLowerCase().split(/\s+/).filter(Boolean);
    if (state.q.length && state.view === 'home') location.hash = '#/all';
    else render();
  }, 150);
});

// ---------- home: highlighted clips (your 5 newest, playing one after another) ----------
const hero = {clips: [...clips].sort((a, b) => b.ts - a.ts).slice(0, 5), i: 0, items: [], offs: [], video: null, prog: null, audio: null, cur: null, s: 0, e: 0};
function buildHero() {
  const el = $('hero');
  if (!hero.clips.length) { el.hidden = true; return; }
  el.innerHTML = '<div class="hero-amb" aria-hidden="true"><i></i><i></i></div>'
    + hero.clips.map((c, i) => `<div class="hitem" data-i="${i}">${c.thumb ? `<img src="${esc(c.thumb)}" alt="" onload="ggImg(this)">` : ''}</div>`).join('')
    + '<div class="hinfo" id="hinfo"></div><div class="hvol" id="hvol"></div>'
    + `<button class="harrow l" data-d="-1" title="Previous">${ic('chevl')}</button><button class="harrow r" data-d="1" title="Next">${ic('chevr')}</button>`
    + `<div class="hdots">${hero.clips.map((c, i) => `<button data-i="${i}" title="${esc(shownTitle(c))}"></button>`).join('')}</div>`;
  hero.items = [...el.querySelectorAll('.hitem')];
  $('hvol').appendChild(volCtl());
  const v = hero.video = document.createElement('video');
  v.playsInline = true; v.preload = 'auto';
  hero.prog = document.createElement('div'); hero.prog.className = 'hprog';
  v.addEventListener('playing', () => { v.classList.add('on'); applyPreviewVolumes(); });
  v.addEventListener('timeupdate', () => {
    const c = hero.cur; if (!c) return;
    const p = clamp((v.currentTime - hero.s) / Math.max(0.1, hero.e - hero.s), 0, 1);
    hero.prog.style.width = p * 100 + '%';
    const dot = $('hero').querySelector('.hdots button.on');
    if (dot) dot.style.setProperty('--p', p);
    if (v.currentTime >= hero.e - 0.08) heroShow(hero.i + 1);
  });
  v.addEventListener('ended', () => heroShow(hero.i + 1));
  v.addEventListener('error', () => { const c = hero.cur; if (c && v.getAttribute('src')) setTimeout(() => { if (hero.cur === c) heroShow(hero.i + 1); }, 1500); });
  el.addEventListener('click', e => {
    const item = e.target.closest('.hitem'), arrow = e.target.closest('.harrow'), dot = e.target.closest('.hdots button'), watch = e.target.closest('[data-watch]');
    if (arrow) heroShow(hero.i + +arrow.dataset.d);
    else if (dot) heroShow(+dot.dataset.i);
    else if (watch || (item && +item.dataset.i === hero.i)) openClip(hero.clips[hero.i].id, hero.clips, hero.items[hero.i]);
    else if (item) heroShow(+item.dataset.i);
  });
  heroShow(0);
}
function layoutHero() {
  const el = $('hero'), W = el.clientWidth;
  if (!W || !hero.items.length) return;
  const compact = W < 860;
  const iw = compact ? 0 : Math.round(clamp(W * 0.2, 260, 340));
  const vw = compact ? W : Math.round(clamp(W * 0.48, 420, 820)), hh = Math.round(vw * 9 / 16);
  el.classList.toggle('compact', compact);
  el.style.setProperty('--vw', vw + 'px'); el.style.setProperty('--hh', hh + 'px'); el.style.setProperty('--iw', iw + 'px');
  el.style.height = (compact ? hh + $('hinfo').offsetHeight : hh) + 'px';
  const n = hero.items.length, cx = -iw / 2, CW = (vw + iw) / 2;
  hero.items.forEach((it, i) => {
    let o = ((i - hero.i) % n + n) % n;
    if (o > n / 2) o -= n;
    let x = cx, s = 1, z = 5, show = true;
    if (o !== 0) {
      const sg = Math.sign(o), s1 = 0.8, s2 = 0.64;
      const out1 = sg * CW + sg * 0.28 * vw * s1;
      if (Math.abs(o) === 1) { s = s1; x = out1 - sg * vw * s1 / 2; z = 4; }
      else { s = s2; x = out1 + sg * 0.2 * vw * s2 - sg * vw * s2 / 2; z = 3; }
      show = !compact && Math.abs(o) <= 2;
    }
    const prev = hero.offs[i];
    it.classList.toggle('instant', prev !== undefined && Math.abs(prev - o) > 2);  // wrapping round: jump instead of flying across
    it.style.transform = `translateX(${x}px) scale(${s})`;
    it.style.zIndex = z;
    it.style.opacity = show ? 1 : 0;
    it.style.pointerEvents = show ? '' : 'none';
    it.classList.toggle('center', o === 0);
    it.classList.toggle('side', o !== 0);
    hero.offs[i] = o;
  });
  $('hinfo').style.transform = compact ? '' : `translateX(${cx + vw / 2}px)`;
  $('hvol').style.transform = `translateX(${cx - vw / 2 + 12}px)`;
  if (!el.classList.contains('ready')) requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add('ready')));
}
function heroShow(i) {
  const n = hero.clips.length;
  if (!n) return;
  hero.i = ((i % n) + n) % n;
  const c = hero.clips[hero.i], v = hero.video;
  $('hero').querySelectorAll('.hdots button').forEach((b, k) => { b.classList.toggle('on', k === hero.i); b.style.setProperty('--p', 0); });
  // Soft glow behind the carousel, cross-fading to the new clip
  const amb = $('hero').querySelectorAll('.hero-amb i');
  hero.amb = hero.amb ? 0 : 1;
  if (c.thumb) amb[hero.amb].style.backgroundImage = `url("${c.thumb}")`;
  amb[hero.amb].classList.toggle('on', !!c.thumb);
  amb[1 - hero.amb].classList.remove('on');
  const cover = COVER.get(c.game);
  $('hinfo').innerHTML = `<span class="hlabel">${ic('play')} Recent clip</span>`
    + `<a class="hgame" href="#/game/${encodeURIComponent(c.game)}">${cover ? `<img src="${esc(cover)}" alt="" onerror="this.remove()">` : `<span class="gicon" style="--h:${hue(c.game)}">${esc(initials(c.game))}</span>`}<span>${esc(c.game)}</span></a>`
    + `<div class="htitle${!c.custom && !c.nick ? ' auto' : ''}">${esc(shownTitle(c))}</div>`
    + (c.nick ? `<div class="hmeta">GG title: ${esc(c.title)}</div>` : '')
    + `<div class="hmeta">${fmtDate(c.recorded)} · ${fmtLen(c.len)}</div>`
    + `<div class="tags">${c.nick ? '<span class="tag nick">Nickname</span>' : ''}${c.starred ? `<span class="tag star">${ic('star')} Starred</span>` : ''}${c.trimmed ? '<span class="tag">Trimmed in GG</span>' : ''}</div>`
    + `<div class="hbtns"><button class="btn primary" data-watch>${ic('play')} Watch</button><a class="btn" href="#/game/${encodeURIComponent(c.game)}">More ${esc(c.game)}</a></div>`;
  replay($('hinfo'), 'swap');
  layoutHero();
  if (hero.audio) { hero.audio.destroy(); hero.audio = null; }
  v.pause();
  v.classList.remove('on');
  hero.items[hero.i].append(v, hero.prog);
  hero.prog.style.width = '0';
  hero.cur = c; hero.s = c.trimmed ? c.start : 0; hero.e = c.trimmed ? c.end : c.full;
  v.addEventListener('loadedmetadata', () => {
    if (hero.cur !== c) return;
    hero.e = Math.min(hero.e || v.duration, v.duration);
    v.currentTime = hero.s;
    heroSync();
  }, {once: true});
  v.src = c.video;
  setPreviewVolume(v, null, c);
  const nextClip = hero.clips[(hero.i + 1) % n];
  if (AUDIO && nextClip !== c) post('/api/prefetch', {id: nextClip.id}).catch(() => {});
}
function heroSync() {
  const v = hero.video;
  if (!v || !hero.cur) return;
  const active = state.view === 'home' && !cur && !document.hidden;
  if (active && v.readyState >= 1) {
    if (v.paused) { setPreviewVolume(v, hero.audio, hero.cur); playWithSound(v); }
  } else if (!active && !v.paused) v.pause();
}
document.addEventListener('visibilitychange', heroSync);
let resizeRaf = 0;
window.addEventListener('resize', () => { cancelAnimationFrame(resizeRaf); resizeRaf = requestAnimationFrame(layoutHero); });

// ---------- home: games ----------
function gameStats() {
  const m = new Map();
  for (const c of clips) {
    let s = m.get(c.game);
    if (!s) m.set(c.game, s = {name: c.game, count: 0, titled: 0, starred: 0, last: 0, thumb: ''});
    s.count++;
    if (c.custom || c.nick) s.titled++;
    if (c.starred) s.starred++;
    if (c.ts >= s.last) { s.last = c.ts; if (c.thumb) s.thumb = c.thumb; }
  }
  return [...m.values()];
}
// Cover art, or (offline / no art) a tile made from the game's newest clip
function coverHTML(s, extraClass = '') {
  const url = COVER.get(s.name);
  const gen = `<div class="gen" style="--h:${hue(s.name)}"${url ? ` data-thumb="${esc(s.thumb)}"` : ''}>${!url && s.thumb ? `<img loading="lazy" src="${esc(s.thumb)}" alt="" onload="ggImg(this)">` : ''}<span>${esc(s.name)}</span></div>`;
  return `<div class="cover ${extraClass}">${gen}${url ? `<img loading="lazy" src="${esc(url)}" alt="" onload="ggImg(this)" onerror="ggCoverFailed(this)">` : ''}</div>`;
}
window.ggCoverFailed = img => {
  const gen = img.parentNode.querySelector('.gen');
  if (gen && gen.dataset.thumb) gen.insertAdjacentHTML('afterbegin', `<img loading="lazy" src="${esc(gen.dataset.thumb)}" alt="" onload="ggImg(this)">`);
  img.remove();
};
const CAT_SORTS = {recent: (a, b) => b.last - a.last, clips: (a, b) => b.count - a.count, name: (a, b) => a.name.localeCompare(b.name)};
function renderHome() {
  const stats = gameStats().sort(CAT_SORTS[state.catSort] || CAT_SORTS.recent);
  const total = stats.reduce((n, s) => n + s.count, 0), titled = stats.reduce((n, s) => n + s.titled, 0), starred = stats.reduce((n, s) => n + s.starred, 0);
  const four = [...stats].sort((a, b) => (COVER.get(b.name) ? 1 : 0) - (COVER.get(a.name) ? 1 : 0) || b.last - a.last).slice(0, 4);
  const tags = s => `<div class="tags">${s.titled ? `<span class="tag">${s.titled} titled</span>` : ''}${s.starred ? `<span class="tag star">${ic('star')} ${s.starred}</span>` : ''}</div>`;
  const rise = i => `class="tile rise" style="--d:${Math.min(i, 16) * 28}ms"`;
  $('tiles').innerHTML = `<a ${rise(0)} href="#/all"><div class="cover"><div class="mosaic">${four.map(s => `<div>${coverHTML(s)}</div>`).join('')}</div><div class="all-label">All games</div></div>`
    + `<div class="tname">All games</div><div class="tmeta">${total.toLocaleString()} clips</div>${tags({titled, starred})}</a>`
    + stats.map((s, i) => `<a ${rise(i + 1)} href="#/game/${encodeURIComponent(s.name)}" title="${esc(s.name)}">${coverHTML(s)}<div class="tname">${esc(s.name)}</div>`
      + `<div class="tmeta">${s.count.toLocaleString()} ${s.count === 1 ? 'clip' : 'clips'} · ${fmtAgo(s.last)}</div>${tags(s)}</a>`).join('');
  $('catCount').textContent = `${stats.length} games`;
}
$('catSort').value = CAT_SORTS[state.catSort] ? state.catSort : 'recent';
$('catSort').onchange = () => { state.catSort = $('catSort').value; store.set('catSort', state.catSort); renderHome(); };

// ---------- a game's clips (or all clips) ----------
const grid = $('grid');
function matches(c) {
  if (state.filter === 'titled' && !(c.custom || c.nick)) return false;
  if (state.filter === 'starred' && !c.starred) return false;
  if (state.game && c.game !== state.game) return false;
  return state.q.every(t => c.search.includes(t));
}
const SORTS = {
  new: (a, b) => b.ts - a.ts,
  old: (a, b) => a.ts - b.ts,
  long: (a, b) => b.len - a.len || b.ts - a.ts,
  short: (a, b) => a.len - b.len || b.ts - a.ts,
  title: (a, b) => shownTitle(a).localeCompare(shownTitle(b)) || b.ts - a.ts,
  game: (a, b) => a.game.localeCompare(b.game) || b.ts - a.ts,
};
let list = [], shown = 0;
const PAGE = 48;
function renderGame() {
  const name = state.game, own = clips.filter(c => !name || c.game === name);
  const s = gameStats().find(x => x.name === name) || {name: 'All games', thumb: (own[0] || {}).thumb || ''};
  const titled = own.filter(c => c.custom || c.nick).length, starred = own.filter(c => c.starred).length;
  const last = own.reduce((m, c) => Math.max(m, c.ts), 0);
  $('ghead').innerHTML = (name ? coverHTML(s) : '')
    + `<div><h1>${esc(name || 'All games')}</h1><div class="gstats"><span>${own.length.toLocaleString()} clips</span>`
    + (titled ? `<span class="tag">${titled} titled</span>` : '') + (starred ? `<span class="tag star">${ic('star')} ${starred}</span>` : '')
    + (last ? `<span>· last played ${fmtAgo(last)}</span>` : '') + '</div></div>';
  // Blurred art behind the header: the game's cover, or the newest clip
  const newest = own.reduce((a, c) => (!a || c.ts > a.ts ? c : a), null);
  const art = (name && COVER.get(name)) || (newest && newest.thumb) || '';
  $('gbannerArt').style.backgroundImage = art ? `url("${art}")` : 'none';
  renderClips();
}
function renderClips() {
  stopPreview();
  list = clips.filter(matches).sort(SORTS[state.sort] || SORTS.new);
  grid.textContent = '';
  shown = 0;
  more();
  $('count').textContent = `${list.length.toLocaleString()} ${list.length === 1 ? 'clip' : 'clips'}`;
  $('noResults').hidden = list.length > 0;
}
function more() {
  if (state.view !== 'game' || shown >= list.length) return;
  const frag = document.createDocumentFragment();
  list.slice(shown, shown + PAGE).forEach((c, i) => frag.appendChild(cardEl(c, i)));
  grid.appendChild(frag);
  shown = Math.min(list.length, shown + PAGE);
  requestAnimationFrame(() => { if ($('sentinel').getBoundingClientRect().top < innerHeight + 900) more(); });
}
new IntersectionObserver(es => { if (es[0].isIntersecting) more(); }, {rootMargin: '900px'}).observe($('sentinel'));
function cardEl(c, i) {
  const el = document.createElement('article');
  el.className = 'card'; el.dataset.id = c.id; el.tabIndex = 0;
  if (i !== undefined) { el.classList.add('rise'); el.style.setProperty('--d', Math.min(i, 12) * 30 + 'ms'); }
  const auto = !c.custom && !c.nick;
  el.innerHTML = `<div class="thumb${c.thumb ? '' : ' ready'}">${c.thumb ? `<img loading="lazy" decoding="async" src="${esc(c.thumb)}" alt="" onload="ggImg(this)" onerror="ggImgFail(this)">` : ''}`
    + `<span class="play-ic">${ic('play')}</span>`
    + (c.starred ? `<span class="badge star" title="Starred in GG">${ic('star')}</span>` : '')
    + (c.trimmed ? `<span class="badge cut" title="Trimmed in GG">${ic('scissors')}</span>` : '')
    + `<span class="badge len">${fmtLen(c.len)}</span></div>`
    + `<div class="info"><div class="ginfo"><i class="gdot" style="--h:${hue(c.game)}"></i><span>${esc(c.game)}</span>`
    + (c.nick ? '<span class="tag nick" title="You gave this clip a nickname">Nickname</span>' : c.edited && /\(18MB\)/.test(c.file) ? '<span class="tag">18 MB</span>' : '') + '</div>'
    + `<div class="ctitle${auto ? ' auto' : ''}" title="${esc(shownTitle(c))}">${esc(shownTitle(c))}</div>`
    + `<div class="csub">${c.edited ? `${fmtSize(c.size)} · saved ${fmtDate(c.made)}` : `${c.nick ? `GG: ${esc(c.title)} · ` : ''}${fmtDate(c.recorded)}`}</div></div>`;
  el.addEventListener('mouseenter', () => hoverStart(el));
  el.addEventListener('mouseleave', () => hoverEnd(el));
  return el;
}
grid.addEventListener('click', e => { const card = e.target.closest('.card'); if (card) openClip(card.dataset.id, list, card.querySelector('.thumb')); });
grid.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || cur) return;
  const card = e.target.closest('.card');
  if (card) { e.preventDefault(); openClip(card.dataset.id, list, card.querySelector('.thumb')); }
});
function refreshCard(c) { const old = grid.querySelector(`.card[data-id="${c.id}"]`); if (old) old.replaceWith(cardEl(c)); }
function syncFilterButtons() { $('filters').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.f === state.filter)); placeInd($('filters')); }
$('filters').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  state.filter = b.dataset.f; store.set('filter', state.filter);
  syncFilterButtons(); renderClips();
};
$('sort').onchange = () => { state.sort = $('sort').value; store.set('sort', state.sort); renderClips(); };

// Hover a clip to preview it (with sound at the preview volume)
const canHover = matchMedia('(hover: hover)').matches;
let pv = null, pvTimer = 0;
function hoverStart(card) {
  if (!canHover || cur) return;
  clearTimeout(pvTimer);
  pvTimer = setTimeout(() => startPreview(card), 450);
}
function hoverEnd(card) {
  clearTimeout(pvTimer);
  if (pv && pv.card === card) stopPreview();
}
function startPreview(card) {
  stopPreview();
  const c = byId.get(card.dataset.id);
  if (!c || !card.isConnected) return;
  const thumb = card.querySelector('.thumb');
  const v = document.createElement('video');
  v.className = 'pv'; v.playsInline = true; v.preload = 'auto';
  const bar = document.createElement('div'); bar.className = 'pbar';
  const ctl = volCtl();
  const s = c.trimmed ? c.start : 0, e = c.trimmed ? c.end : c.full;
  thumb.append(v, bar, ctl);
  card.classList.add('previewing');
  pv = {card, c, v, bar, ctl, audio: null, audioTimer: 0};
  v.addEventListener('loadedmetadata', () => { v.currentTime = s; setPreviewVolume(v, null, c); playWithSound(v); }, {once: true});
  v.addEventListener('playing', () => v.classList.add('on'));
  v.addEventListener('timeupdate', () => {
    if (v.currentTime >= Math.min(e, v.duration || e) - 0.08) v.currentTime = s;
    bar.style.width = clamp((v.currentTime - s) / Math.max(0.1, e - s), 0, 1) * 100 + '%';
  });
  v.src = c.video;
  // Only fetch Chat/Mic once you've stayed on the clip for a moment
  pv.audioTimer = setTimeout(() => { if (pv && pv.c === c) { pv.audio = attachTracks(v, c); setPreviewVolume(v, pv.audio, c); } }, 700);
}
function stopPreview() {
  clearTimeout(pvTimer);
  if (!pv) return;
  const p = pv; pv = null;
  clearTimeout(p.audioTimer);
  if (p.audio) p.audio.destroy();
  p.v.pause(); p.v.removeAttribute('src'); p.v.load();
  p.v.remove(); p.bar.remove(); p.ctl.remove();
  p.card.classList.remove('previewing');
}

// ---------- edited clips (everything in "Edited Clips") ----------
let edits = [], edList = [], edSort = store.get('edSort', 'new');
const ED_SORTS = {new: (a, b) => b.ts - a.ts, old: (a, b) => a.ts - b.ts, big: (a, b) => b.size - a.size, name: (a, b) => a.title.localeCompare(b.title)};
function setEdits(items) {
  for (const e of edits) byId.delete(e.id);
  edits = items || [];
  for (const e of edits) {
    e.ts = Date.parse(e.made) || 0;
    e.len = e.full;
    e.search = [e.title, e.game, e.file, e.sourceTitle].join(' ').toLowerCase();
    byId.set(e.id, e);
  }
  $('edPill').textContent = edits.length || '';
}
async function refreshEdited() {
  if (!SERVER) return;
  try { setEdits((await getJSON('/api/edited')).items); } catch (e) { return; }
  if (state.view === 'edited') renderEdited();
}
function renderEdited() {
  stopPreview();
  edList = edits.filter(e => state.q.every(t => e.search.includes(t))).sort(ED_SORTS[edSort] || ED_SORTS.new);
  const g = $('edGrid');
  g.textContent = '';
  const frag = document.createDocumentFragment();
  edList.forEach((e, i) => frag.appendChild(cardEl(e, i)));
  g.appendChild(frag);
  $('edCount').textContent = edits.length ? `${edList.length} of ${edits.length}` : '';
  $('edEmpty').hidden = edList.length > 0;
  $('edEmpty').textContent = !SERVER ? 'Edited clips show up here in the full player.'
    : edits.length ? 'No edited clips match your search.' : 'No edited clips yet. Open a clip, trim it and press Save copy.';
  $('edFolder').hidden = !SERVER;
}
$('edGrid').addEventListener('click', e => { const card = e.target.closest('.card'); if (card) openClip(card.dataset.id, edList, card.querySelector('.thumb')); });
$('edGrid').addEventListener('keydown', e => {
  if (e.key !== 'Enter' || cur) return;
  const card = e.target.closest('.card');
  if (card) { e.preventDefault(); openClip(card.dataset.id, edList, card.querySelector('.thumb')); }
});
$('edSort').value = ED_SORTS[edSort] ? edSort : 'new';
$('edSort').onchange = () => { edSort = $('edSort').value; store.set('edSort', edSort); renderEdited(); };
$('edFolder').onclick = () => post('/api/reveal', {folder: true}).catch(err => toast(err.message, true));
setEdits(D.edits);

// ---------- change log ----------
const KIND = {title: 'GG title', file: 'File renamed', new: 'New titled clip', removed: 'Removed from GG', nickname: 'Nickname'};
function changeText(ch) {
  const old = v => v ? `<span class="old">${esc(v)}</span>` : '<span class="dim">none</span>';
  const after = v => v ? `<b>${esc(v)}</b>` : '<span class="dim">removed</span>';
  if (ch.kind === 'title' || ch.kind === 'nickname') return `${old(ch.before)}<span class="arrow">→</span>${after(ch.after)}`;
  if (ch.kind === 'file') return `${old(ch.before)}<span class="arrow">→</span><span class="mono">${esc(ch.after)}</span>`;
  if (ch.kind === 'new') return `<b>${esc(ch.after)}</b>`;
  return old(ch.before);
}
function renderLog() {
  $('logCount').textContent = D.changes.length || '';
  if (state.view !== 'log') return;
  const body = $('logBody');
  if (!D.changes.length) {
    body.innerHTML = `<p class="empty">Tracking since ${fmtDate(META.started)}. When you change a clip’s title in GG, a clip file is renamed, or you give a clip a nickname here, it shows up in this list.</p>`;
    return;
  }
  const rows = D.changes
    .map(ch => ({ch, s: [ch.game, ch.before, ch.after, ch.file, KIND[ch.kind]].join(' ').toLowerCase()}))
    .filter(r => state.q.every(t => r.s.includes(t)))
    .reverse();
  if (!rows.length) { body.innerHTML = '<p class="empty">No changes match your search.</p>'; return; }
  body.innerHTML = `<div class="tablewrap"><table><thead><tr><th>When</th><th>What</th><th>Clip</th><th>Change</th></tr></thead><tbody>`
    + rows.map(({ch}) => `<tr><td class="when">${fmtDate(ch.when)}</td><td><span class="kind ${esc(ch.kind)}">${esc(KIND[ch.kind] || ch.kind)}</span></td>`
      + `<td><div class="clipcell"><span class="gicon" style="--h:${hue(ch.game || '')}">${esc(initials(ch.game || '?'))}</span><div>${esc(ch.game)}<br>`
      + (ch.id && byId.has(ch.id) ? `<button class="link-btn mono" data-open="${ch.id}">${esc(ch.file)}</button>` : `<span class="mono dim">${esc(ch.file)}</span>`)
      + `</div></div></td><td>${changeText(ch)}</td></tr>`).join('')
    + `</tbody></table></div>`;
}
$('logBody').addEventListener('click', e => { const b = e.target.closest('[data-open]'); if (b) openClip(b.dataset.open, [byId.get(b.dataset.open)], null); });

// ---------- player ----------
const vid = $('vid'), stage = $('stage'), tl = $('tl');
const E = {};
['tlSel', 'tlPlayed', 'hIn', 'hOut', 'tlHead', 'tlTip', 'tCur', 'tDur', 'tIn', 'tOut', 'tSel'].forEach(id => { E[id] = $(id); });
const MIN_SEL = 0.2;
let cur = null, navList = [], opener = null, sel = {a: 0, b: 0}, loop = false, lastT = 0, raf = 0, drag = null, masterMuted = false;
let mix = [], actx = null, master = null, vidGain = null, extras = [], syncTimer = 0, exJob = null, exNameTouched = false;
const dur = () => (isFinite(vid.duration) && vid.duration > 0 ? vid.duration : (cur && cur.full) || 1);

function openPlayer(id, from) {
  const c = byId.get(id);
  if (!c) return;
  stopPreview();
  if (cur) teardown(); else opener = document.activeElement;
  cur = c;
  if (from) navList = from;
  heroSync();
  $('player').hidden = false;
  document.body.classList.add('noscroll');
  fillInfo();
  sel = c.trimmed && c.end > c.start ? {a: c.start, b: c.end} : {a: 0, b: c.full || 0};
  lastT = sel.a;
  mix = buildMix(c);
  renderMixer();
  $('stageMsg').hidden = true;
  stage.classList.add('paused');
  vid.poster = c.thumb || '';
  vid.src = c.video;
  vid.addEventListener('loadedmetadata', () => {
    if (cur !== c) return;
    const d = dur();
    if (!(sel.b > 0) || sel.b > d) sel.b = d;
    if (sel.b - sel.a < MIN_SEL) sel = {a: 0, b: d};
    vid.playbackRate = +$('speed').value;
    seek(sel.a);
    drawTL();
    vid.play().catch(() => {});
  }, {once: true});
  setupAudio(c);
  exNameTouched = false;
  $('exName').value = c.nick || (c.custom ? c.title : '');
  $('exOverwrite').checked = true;  // edits to an edited clip overwrite it unless you untick this
  if (!exJob) $('exProg').hidden = true;
  $('exGo').disabled = !!exJob;
  updateExport();
  updateNav();
  drawTL();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(tick);
  $('shell').focus({preventScroll: true});
}
function fillInfo() {
  const c = cur;
  $('pIcon').style.setProperty('--h', hue(c.game));
  $('pIcon').textContent = initials(c.game);
  $('pGame').textContent = c.game;
  $('pDate').textContent = 'Recorded ' + fmtDate(c.recorded);
  $('pTitle').textContent = shownTitle(c);
  $('pTitle').className = 'ptitle' + (!c.custom && !c.nick ? ' auto' : '');
  const lines = [];
  if (c.edited) {
    const src = c.source && byId.get(c.source);
    lines.push('<span class="tag">Edited copy</span>', `<span>Length <b>${fmtLen(c.full)}</b> · ${fmtSize(c.size)} · saved ${fmtDate(c.made)}</span>`);
    if (src) lines.push(`<button class="btn sm" type="button" data-open-src="${src.id}">${ic('play')} Made from: ${esc(shownTitle(src))}</button>`);
  } else {
    if (c.nick) lines.push(`<span class="tag nick">Nickname</span>`, `<span>GG title: <b>${esc(c.title)}</b></span>`);
    lines.push(`<span>Length <b>${fmtLen(c.full)}</b>` + (c.trimmed ? ` · trimmed in GG to <b>${fmtLen(c.len)}</b>` : '') + (c.starred ? ' · <span style="color:var(--star)">★ starred</span>' : '') + '</span>');
  }
  $('pMeta').innerHTML = lines.join('');
  $('pFile').textContent = c.file;
  $('pFile').title = c.file;
  $('bReveal').hidden = !SERVER;
  $('bRename').hidden = !SERVER || !!c.edited;  // an edited clip's name is its file name
  $('trimGG').disabled = !c.trimmed;
  endRename();
}
function teardown() {
  vid.pause();
  for (const x of extras) {
    x.el.pause(); x.el.removeAttribute('src'); x.el.load();
    try { x.node.disconnect(); x.gain.disconnect(); } catch (e) {}
  }
  extras = [];
  clearInterval(syncTimer); syncTimer = 0;
  vid.removeAttribute('src'); vid.load();
}
function closePlayer() {
  if (!cur) return;
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  teardown();
  cur = null;
  cancelAnimationFrame(raf);
  $('player').hidden = true;
  document.body.classList.remove('noscroll');
  if (opener && opener.focus) opener.focus({preventScroll: true});
  heroSync();
}
// Opening grows the clip's thumbnail into the player; closing shrinks it back into its card.
let flyBack = null, closing = false;
function openClip(id, from, sourceEl) {
  flyBack = sourceEl || null;
  if (cur || !sourceEl || !canAnimate()) { openPlayer(id, from); return; }
  sourceEl.style.viewTransitionName = 'clip-media';
  $('player').classList.add('morph');
  vt('open', () => {
    sourceEl.style.viewTransitionName = '';
    openPlayer(id, from);
    stage.style.viewTransitionName = 'clip-media';
  }).then(() => { stage.style.viewTransitionName = ''; $('player').classList.remove('morph'); });
}
function inView(el) { const r = el.getBoundingClientRect(); return r.bottom > 0 && r.top < innerHeight && r.width > 0; }
function closeClip() {
  if (!cur || closing) return;
  let target = flyBack;
  const card = target && target.closest('.card');
  if (card && card.dataset.id !== cur.id) target = card.closest('.grid').querySelector(`.card[data-id="${cur.id}"] .thumb`);  // moved on with Prev/Next
  if (target && (!target.isConnected || !inView(target))) target = null;
  if (canAnimate()) {
    stage.style.viewTransitionName = 'clip-media';
    vt('close', () => {
      stage.style.viewTransitionName = '';
      closePlayer();
      if (target) target.style.viewTransitionName = 'clip-media';
    }).then(() => { if (target) target.style.viewTransitionName = ''; });
  } else if (!reduceMotion.matches) {
    closing = true;
    $('player').classList.add('closing');
    setTimeout(() => { closing = false; $('player').classList.remove('closing'); closePlayer(); }, 160);
  } else closePlayer();
}
document.querySelectorAll('[data-close]').forEach(el => { el.onclick = closeClip; });

// Audio mixer. The video element plays the first track (Game); the other tracks (Chat, Mic) are pulled out
// of the clip by the player and played alongside it in sync, each with its own volume (up to 200%).
// Every clip lists Game, Chat and Mic; a track GG didn't record for that clip is shown as such.
const STD = ['game', 'chat', 'mic'];
function buildMix(c) {
  const rows = c.tracks.map((t, i) => ({name: t.name, vol: Math.round(clamp((t.volume ?? 1) * 100, 0, SERVER ? 200 : 100)), muted: !!t.muted, stream: i, state: i === 0 ? 'ok' : AUDIO ? 'wait' : 'off'}));
  if (c.edited) return rows;  // saved copies have Game/Chat/Mic already mixed into one track
  for (const name of ['Chat', 'Mic']) {
    if (!rows.some(r => r.name.toLowerCase() === name.toLowerCase())) rows.push({name, vol: 100, muted: false, stream: -1, state: 'missing'});
  }
  const rank = r => { const k = STD.indexOf(r.name.toLowerCase()); return k < 0 ? 9 : k; };
  return rows.sort((a, b) => rank(a) - rank(b) || a.stream - b.stream);
}
function ensureGraph() {
  if (!SERVER) return false;
  if (!actx) {
    try {
      actx = new AudioContext();
      master = actx.createGain(); master.connect(actx.destination);
      vidGain = actx.createGain(); vidGain.connect(master);
      actx.createMediaElementSource(vid).connect(vidGain);
    } catch (e) { actx = null; return false; }
  }
  if (actx.state === 'suspended') actx.resume().catch(() => {});
  return true;
}
function setupAudio(c) {
  const graph = ensureGraph();
  updateMixHint();
  applyGains();
  if (!graph || !AUDIO) return;
  for (const row of mix) {
    if (row.stream < 1) continue;
    const el = new Audio();
    el.preload = 'auto';
    const node = actx.createMediaElementSource(el), gain = actx.createGain();
    node.connect(gain).connect(master);
    extras.push({el, node, gain, stream: row.stream});
    el.addEventListener('canplay', () => { if (cur !== c) return; row.state = 'ok'; updateTrack(row); applyGains(); syncTracks(vid, extras.map(x => x.el), true); }, {once: true});
    el.addEventListener('error', () => { if (cur !== c) return; row.state = 'error'; updateTrack(row); }, {once: true});
    el.src = trackUrl(c, row.stream);
  }
  applyGains();
  syncTimer = setInterval(() => syncTracks(vid, extras.map(x => x.el), false), 250);
}
['seeked', 'play', 'playing'].forEach(ev => vid.addEventListener(ev, () => syncTracks(vid, extras.map(x => x.el), true)));
['pause', 'waiting', 'seeking', 'ratechange'].forEach(ev => vid.addEventListener(ev, () => syncTracks(vid, extras.map(x => x.el), false)));
const gainOf = m => (m && !m.muted && m.stream >= 0 ? m.vol / 100 : 0);
const rowFor = stream => mix.find(r => r.stream === stream);
function applyGains() {
  if (actx) {
    vidGain.gain.value = gainOf(rowFor(0));
    for (const x of extras) x.gain.gain.value = gainOf(rowFor(x.stream));
    master.gain.value = masterMuted ? 0 : 1;
  } else {
    vid.volume = Math.min(1, gainOf(rowFor(0)));
    vid.muted = masterMuted;
  }
  $('bMute').innerHTML = ic(masterMuted ? 'mute' : 'vol');
  $('bMute').classList.toggle('on', masterMuted);
}
const TICON = {game: 'pad', chat: 'chat', mic: 'mic'};
const NOTE = {wait: 'loading…', missing: 'not recorded in this clip', error: 'couldn’t load', off: ''};
function trackHTML(m, i) {
  const off = m.state === 'missing' || m.state === 'off' || m.state === 'error';
  const note = m.state === 'off' ? (!SERVER ? 'needs the full player' : 'needs ffmpeg') : NOTE[m.state] || '';
  return `<div class="track${off ? ' off' : ''}" data-i="${i}">`
    + `<button class="mute-btn${m.muted && !off ? ' on' : ''}" data-act="mute" title="${m.muted ? 'Unmute' : 'Mute'} ${esc(m.name)}"${off ? ' disabled' : ''}>${ic(m.muted && !off ? 'mute' : TICON[m.name.toLowerCase()] || 'vol')}</button>`
    + `<div><div class="tname">${esc(m.name)}${note ? `<span class="dim">${note}</span>` : ''}</div>`
    + `<input type="range" min="0" max="${SERVER ? 200 : 100}" step="1" value="${off ? 0 : m.vol}" aria-label="${esc(m.name)} volume"${off ? ' disabled' : ''}></div>`
    + `<span class="val">${off ? '—' : m.vol + '%'}</span></div>`;
}
function renderMixer() { $('mixer').innerHTML = mix.map(trackHTML).join(''); }
function updateTrack(row) {
  const i = mix.indexOf(row), el = $('mixer').querySelector(`[data-i="${i}"]`);
  if (!el) return;
  if (row.state === 'ok' && el.contains(document.activeElement)) { el.classList.remove('off'); const n = el.querySelector('.tname .dim'); if (n) n.remove(); return; }
  el.outerHTML = trackHTML(row, i);
}
$('mixer').addEventListener('input', e => {
  if (e.target.type !== 'range') return;
  const el = e.target.closest('.track'), m = mix[+el.dataset.i];
  m.vol = +e.target.value;
  el.querySelector('.val').textContent = m.vol + '%';
  applyGains();
  rememberMix(m);
});
$('mixer').addEventListener('click', e => {
  const b = e.target.closest('[data-act="mute"]'); if (!b) return;
  const m = mix[+b.closest('.track').dataset.i];
  m.muted = !m.muted;
  updateTrack(m); applyGains();
  rememberMix(m);
});
// Levels are remembered per clip (like GG does), and also used by hover previews and the home page.
let mixTimer = 0;
const isCustomMix = c => c.tracks.some(t => Math.abs(t.volume - (t.ggVolume ?? t.volume)) > 0.005 || t.muted !== (t.ggMuted ?? t.muted));
function updateMixHint() {
  const custom = SERVER && cur && !cur.edited && isCustomMix(cur);
  $('mixHint').textContent = cur && cur.edited ? 'Game, Chat & Mic are mixed in this copy'
    : !SERVER ? 'Chat & Mic need the full player' : !META.ffmpeg ? 'Chat & Mic need ffmpeg'
    : custom ? 'your levels for this clip' : 'GG’s levels';
  $('mixReset').hidden = !custom;
}
function rememberMix(m) {
  if (!cur || m.stream < 0 || cur.edited) return;
  const c = cur, t = c.tracks[m.stream];
  if (!t) return;
  t.volume = m.vol / 100;
  t.muted = m.muted;
  updateMixHint();
  if (!SERVER) return;
  clearTimeout(mixTimer);
  mixTimer = setTimeout(() => {
    post('/api/mix', {id: c.id, tracks: c.tracks.map((x, i) => ({stream: i, vol: x.volume, muted: x.muted}))})
      .catch(err => toast('Couldn’t save the audio levels: ' + err.message, true));
  }, 500);
}
$('mixReset').onclick = () => {
  if (!cur) return;
  for (const t of cur.tracks) { t.volume = t.ggVolume ?? t.volume; t.muted = t.ggMuted ?? t.muted; }
  for (const m of mix) {
    const t = cur.tracks[m.stream];
    if (t) { m.vol = Math.round(clamp(t.volume * 100, 0, SERVER ? 200 : 100)); m.muted = t.muted; }
  }
  renderMixer(); applyGains();
  const first = mix.find(m => m.stream >= 0);
  if (first) rememberMix(first);  // saves the whole clip's levels, which are now GG's again
  toast('Back to GG’s levels');
};

// Timeline and playback
const pct = t => clamp(t / dur(), 0, 1) * 100 + '%';
function drawTL() {
  if (!cur) return;
  const t = vid.currentTime;
  E.tlSel.style.left = pct(sel.a);
  E.tlSel.style.width = clamp((sel.b - sel.a) / dur(), 0, 1) * 100 + '%';
  E.hIn.style.left = pct(sel.a);
  E.hOut.style.left = pct(sel.b);
  E.tlHead.style.left = pct(t);
  E.tlPlayed.style.width = pct(t);
  E.tCur.textContent = fmtLen(t);
  E.tDur.textContent = fmtLen(dur());
  E.tIn.textContent = fmtExact(sel.a);
  E.tOut.textContent = fmtExact(sel.b);
  E.tSel.textContent = fmtExact(sel.b - sel.a);
}
function seek(t) { t = clamp(t, 0, dur()); vid.currentTime = t; lastT = t; }
function tick() {
  if (!cur) return;
  const t = vid.currentTime;
  if (!vid.paused && !drag && lastT < sel.b - 0.01 && t >= sel.b) {
    if (loop) seek(sel.a); else { vid.pause(); seek(sel.b); }
  } else lastT = t;
  drawTL();
  raf = requestAnimationFrame(tick);
}
function togglePlay() {
  if (!cur) return;
  if (vid.paused) {
    if (vid.currentTime >= sel.b - 0.05) seek(sel.a);
    ensureGraph();
    vid.play().catch(() => {});
  } else vid.pause();
}
function toggleMute() { masterMuted = !masterMuted; applyGains(); }
function toggleFull() { if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); else $('pmain').requestFullscreen().catch(() => {}); }
function setIn() { const t = vid.currentTime; if (t > sel.b - MIN_SEL) sel.b = dur(); sel.a = clamp(t, 0, sel.b - MIN_SEL); drawTL(); }
function setOut() { const t = vid.currentTime; if (t < sel.a + MIN_SEL) sel.a = 0; sel.b = clamp(t, sel.a + MIN_SEL, dur()); drawTL(); }
vid.addEventListener('play', () => { stage.classList.remove('paused'); $('bPlay').innerHTML = ic('pause'); });
vid.addEventListener('pause', () => { stage.classList.add('paused'); $('bPlay').innerHTML = ic('play'); });
vid.addEventListener('ended', () => { if (loop && cur) { seek(sel.a); vid.play().catch(() => {}); } });
// Spinner while the video loads (only shows if that takes more than a moment)
['loadstart', 'waiting', 'seeking'].forEach(ev => vid.addEventListener(ev, () => { if (vid.getAttribute('src')) stage.classList.add('loading'); }));
['playing', 'canplay', 'seeked', 'pause', 'error', 'emptied'].forEach(ev => vid.addEventListener(ev, () => stage.classList.remove('loading')));
vid.addEventListener('error', () => {
  if (!cur || !vid.getAttribute('src')) return;
  $('stageMsg').textContent = 'This clip can’t be played. The file may have been moved or deleted.';
  $('stageMsg').hidden = false;
});
$('bPlay').innerHTML = ic('play');
$('bPlay').onclick = togglePlay;
stage.onclick = togglePlay;
stage.ondblclick = toggleFull;
$('bBack').onclick = () => seek(vid.currentTime - 5);
$('bFwd').onclick = () => seek(vid.currentTime + 5);
$('bLoop').onclick = () => { loop = !loop; $('bLoop').classList.toggle('on', loop); };
$('speed').onchange = () => { vid.playbackRate = +$('speed').value; };
$('bMute').onclick = toggleMute;
$('bFull').onclick = toggleFull;
$('setIn').onclick = setIn;
$('setOut').onclick = setOut;
$('trimFull').onclick = () => { sel = {a: 0, b: dur()}; drawTL(); };
$('trimGG').onclick = () => { if (cur && cur.trimmed) { sel = {a: cur.start, b: Math.min(cur.end, dur())}; seek(sel.a); drawTL(); } };

const xToTime = x => { const r = tl.getBoundingClientRect(); return clamp((x - r.left) / r.width, 0, 1) * dur(); };
function dragMove(e) {
  const t = xToTime(e.clientX);
  if (drag === 'seek') seek(t);
  else if (drag === 'a') { sel.a = clamp(t, 0, sel.b - MIN_SEL); seek(sel.a); }
  else { sel.b = clamp(t, sel.a + MIN_SEL, dur()); seek(sel.b); }
  drawTL();
}
tl.addEventListener('pointerdown', e => {
  if (!cur || e.button !== 0) return;
  e.preventDefault();
  tl.setPointerCapture(e.pointerId);
  drag = e.target === E.hIn ? 'a' : e.target === E.hOut ? 'b' : 'seek';
  if (drag !== 'seek') vid.pause();
  dragMove(e);
});
tl.addEventListener('pointermove', e => {
  const r = tl.getBoundingClientRect();
  E.tlTip.style.left = clamp(e.clientX - r.left, 20, r.width - 20) + 'px';
  E.tlTip.textContent = fmtExact(xToTime(e.clientX));
  if (drag) dragMove(e);
});
const endDrag = () => { drag = null; };
tl.addEventListener('pointerup', endDrag);
tl.addEventListener('pointercancel', endDrag);

function neighbor(d) { const i = navList.indexOf(cur); return i < 0 ? null : navList[i + d] || null; }
function updateNav() { $('bPrev').disabled = !neighbor(-1); $('bNext').disabled = !neighbor(1); }
function step(d) {
  const n = neighbor(d);
  if (!n) return;
  if (!canAnimate()) { openPlayer(n.id); return; }
  stage.style.viewTransitionName = 'clip-media';
  vt(d > 0 ? 'next' : 'prev', () => openPlayer(n.id)).then(() => { stage.style.viewTransitionName = ''; });
}
$('bPrev').onclick = () => step(-1);
$('bNext').onclick = () => step(1);

// Nickname
function startRename() {
  if (!SERVER || !cur) return;
  $('titleView').hidden = true;
  $('renameForm').hidden = false;
  const inp = $('renameInput');
  inp.value = cur.nick || '';
  inp.placeholder = cur.custom ? cur.title : 'Give this clip a nickname';
  inp.focus(); inp.select();
}
function endRename() { $('titleView').hidden = false; $('renameForm').hidden = true; }
$('bRename').onclick = startRename;
$('renameCancel').onclick = endRename;
$('renameForm').onsubmit = async e => {
  e.preventDefault();
  const c = cur;
  try {
    const r = await post('/api/nickname', {id: c.id, nickname: $('renameInput').value});
    c.nick = r.nick || '';
    indexClip(c);
    if (r.change) { D.changes.push(r.change); renderLog(); }
    toast(c.nick ? 'Nickname saved' : 'Nickname removed');
    refreshCard(c);
    if (cur === c) {
      fillInfo();
      if (!exNameTouched) { $('exName').value = c.nick || (c.custom ? c.title : ''); updateExport(); }
      $('shell').focus({preventScroll: true});
    }
  } catch (err) { toast(err.message, true); }
};

// Save edited copy
function stemOf(f) { const b = f.replace(/\.[^.]+$/, ''); const m = /^(.+?__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2})/.exec(b); return m ? m[1] : b; }
function safeName(s) { return s.replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().replace(/^[ .]+|[ .]+$/g, '').slice(0, 100); }
function updateExport() {
  $('exportBody').hidden = !AUDIO;
  $('exportNote').hidden = AUDIO;
  $('exportNote').textContent = !SERVER
    ? 'Saving edited copies needs the full player. It starts with Windows; to start it now, double-click “_Update GG Titles.bat”.'
    : 'Saving edited copies needs ffmpeg, which wasn’t found on this PC.';
  const small = exQuality === 'small', ed = !!(cur && cur.edited), over = ed && $('exOverwrite').checked;
  $('exOverRow').hidden = !ed;
  $('exTitle').textContent = ed ? 'Save changes' : 'Save edited copy';
  $('exGo').innerHTML = ic('save') + (over ? ' Save changes' : ' Save copy');
  $('exName').disabled = over;  // overwriting keeps the clip's name
  if (AUDIO && cur) {
    const tag = small ? ' (18MB)' : '';
    if (over) {
      const target = cur.file.replace(/\.[^.]+$/, '').replace(/ \(18MB\)$/, '') + tag + '.mp4';
      $('exFile').textContent = target === cur.file ? `Overwrites Edited Clips\\${cur.file}` : `Replaces ${cur.file} with ${target}`;
    } else {
      const name = safeName($('exName').value), base = cur.file.replace(/\.[^.]+$/, '').replace(/ \(18MB\)$/, '');
      const stem = !ed ? `${stemOf(cur.file)}__${name || 'edit'}` : name ? (stemOf(base) !== base ? `${stemOf(base)}__${name}` : name) : `${base} (edit)`;
      $('exFile').textContent = `Saves to Edited Clips\\${stem}${tag}.mp4`;
    }
  }
  $('exQuality').querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.q === exQuality));
  $('exQNote').textContent = small
    ? 'Re-encoded to stay under 18 MB, so it’s easy to send (Discord and similar). Longer clips get a smaller picture.'
    : 'Same quality as the original recording.';
  $('exPreciseRow').hidden = small;  // compressed copies are always cut exactly
  placeInd($('exQuality'));
}
let exQuality = store.get('exq', 'original') === 'small' ? 'small' : 'original';
$('exQuality').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  exQuality = b.dataset.q; store.set('exq', exQuality);
  updateExport();
};
$('exName').addEventListener('input', () => { exNameTouched = true; updateExport(); });
$('exOverwrite').addEventListener('change', updateExport);
const fmtSize = bytes => (bytes / 1048576).toFixed(1) + ' MB';
function setProg(p, html, err, actions = '') {
  $('exProg').hidden = false;
  $('exProg').classList.toggle('err', !!err);
  $('exBar').style.width = Math.round(p * 100) + '%';
  $('exText').innerHTML = html;
  $('exActions').innerHTML = actions;
}
$('exGo').onclick = async () => {
  if (!cur || exJob) return;
  $('exGo').disabled = true;
  setProg(0, 'Starting…');
  try {
    const r = await post('/api/export', {
      id: cur.id, start: sel.a, end: sel.b, precise: $('exPrecise').checked, loud: $('exLoud').checked, name: $('exName').value,
      quality: exQuality, volumes: cur.tracks.map((t, i) => gainOf(rowFor(i))),
      overwrite: !!(cur.edited && $('exOverwrite').checked),
    });
    exJob = r.job;
    pollJob(r.job);
  } catch (err) { setProg(0, esc(err.message), true); $('exGo').disabled = false; }
};
async function pollJob(job) {
  let misses = 0;
  for (;;) {
    await new Promise(r => setTimeout(r, 600));
    let j;
    try { j = await getJSON(`/api/job/${job}`); misses = 0; }
    catch (e) { if (++misses < 20) continue; j = {state: 'error', error: 'Lost contact with the player'}; }
    if (j.state === 'running') {
      setProg(j.progress || 0, `Saving… ${Math.round((j.progress || 0) * 100)}%` + (j.retry ? ' · making it a little smaller' : ''));
      continue;
    }
    exJob = null;
    $('exGo').disabled = false;
    if (j.state === 'done') {
      const done = () => setProg(1, `${ic('check')} ${j.overwrote ? 'Overwrote' : 'Saved'} <b>${esc(j.file)}</b>${j.size ? ` · ${fmtSize(j.size)}` : ''}`, false,
        `<button class="btn sm" type="button" data-reveal="${esc(j.file)}">${ic('folder')} Show in folder</button>`);
      done();
      toast(j.overwrote ? 'Changes saved' : 'Edited copy saved');
      const wasEdited = cur && cur.edited;
      await refreshEdited();
      if (j.overwrote && wasEdited && cur && cur.edited) {  // show the new version straight away
        const fresh = edits.find(e => e.file === j.file);
        if (fresh) { openPlayer(fresh.id, state.view === 'edited' ? edList : edits); done(); }
      }
    } else setProg(0, esc(j.error || 'Saving failed'), true);
    return;
  }
}
document.addEventListener('click', async e => {
  const src = e.target.closest('[data-open-src]');
  if (src) { const c = byId.get(src.dataset.openSrc); if (c) openPlayer(c.id, [c]); return; }
  const b = e.target.closest('[data-reveal]'); if (!b) return;
  try { await post('/api/reveal', {file: b.dataset.reveal}); } catch (err) { toast(err.message, true); }
});
$('bReveal').onclick = async () => { try { await post('/api/reveal', {id: cur.id}); } catch (err) { toast(err.message, true); } };

// Keyboard
document.addEventListener('keydown', e => {
  const tag = e.target.tagName, type = e.target.type;
  const typing = tag === 'TEXTAREA' || (tag === 'INPUT' && type !== 'range' && type !== 'checkbox');
  if (!cur) {
    if (e.key === '/' && !typing) { e.preventDefault(); $('q').focus(); }
    return;
  }
  if (typing) {
    if (e.key === 'Escape') { e.preventDefault(); if (!$('renameForm').hidden) endRename(); $('shell').focus({preventScroll: true}); }
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if ((type === 'range' || tag === 'SELECT') && e.key.startsWith('Arrow')) return;
  if (tag === 'BUTTON' && (e.key === ' ' || e.key === 'Enter')) return;
  const actions = {
    ' ': togglePlay, k: togglePlay,
    arrowleft: () => seek(vid.currentTime - (e.shiftKey ? 1 : 5)),
    arrowright: () => seek(vid.currentTime + (e.shiftKey ? 1 : 5)),
    j: () => seek(vid.currentTime - 10), l: () => seek(vid.currentTime + 10),
    ',': () => { vid.pause(); seek(vid.currentTime - 1 / 30); },
    '.': () => { vid.pause(); seek(vid.currentTime + 1 / 30); },
    i: setIn, o: setOut, home: () => seek(sel.a), end: () => seek(sel.b),
    f: toggleFull, m: toggleMute, r: startRename,
    n: () => step(1), pagedown: () => step(1), p: () => step(-1), pageup: () => step(-1),
    escape: () => { if (!document.fullscreenElement) closeClip(); },
  };
  const act = actions[e.key.toLowerCase()];
  if (act) { e.preventDefault(); act(); }
});

// ---------- start ----------
$('sort').value = SORTS[state.sort] ? state.sort : 'new';
syncFilterButtons();
setThemeIcon();
renderLog();
buildHero();
route(true);
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
