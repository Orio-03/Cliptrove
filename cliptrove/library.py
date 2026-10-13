"""Your clip library: the clips from every source in one list, plus what you add to them (nicknames, favorites,
trims, audio levels, games), the log of title changes, and the edited copies you've saved."""
import collections
import hashlib
import os
import re
import threading
import time

from . import analytics, covers, paths, settings
from .sources import folder, gg
from .sources.folder import UNSORTED
from .util import clip_id, iso_time, load_json, norm, now_iso, path_key, safe_name, save_json

INDEX_VERSION = 1
STEM = re.compile(r"(.+?__\d{4}-\d{2}-\d{2}__\d{2}-\d{2}-\d{2})")  # "Game__date__time" at the start of a GG clip's name
EDIT_EXTS = (".mp4", ".m4v", ".mov", ".webm")  # videos in "Edited Clips" the browser can play
PER_CLIP = ("nicknames", "mix", "favorites", "trims", "games")  # what you've added, by clip key


def load_state():
    state = {"started": None, "last_run": None, "changes": [], "snapshot": {}}
    state.update({k: {} for k in PER_CLIP})
    saved = load_json(paths.LIBRARY, {})
    if isinstance(saved, dict):
        state.update(saved)
    return state


# ---------- GG title tracking ----------

def find_changes(old, clips, now):
    """Compare the previous snapshot of GG's clips with GG's library now. Only clips you've titled count."""
    changes = []

    def entry(kind, key, clip, before, after):
        return {"when": now, "kind": kind, "key": key, "game": clip["game"], "recorded": clip["recorded"],
                "file": clip["file"], "before": before, "after": after}

    for key, clip in clips.items():
        prev = old.get(key)
        if prev is None:
            if gg.is_custom(clip["title"]):
                changes.append(entry("new", key, clip, None, clip["title"]))
            continue
        titled = gg.is_custom(prev["title"]) or gg.is_custom(clip["title"])
        if titled and prev["title"] != clip["title"]:
            changes.append(entry("title", key, clip, prev["title"], clip["title"]))
        if titled and os.path.normcase(prev["file"]) != os.path.normcase(clip["file"]):
            changes.append(entry("file", key, clip, os.path.basename(prev["file"]), os.path.basename(clip["file"])))
    for key, prev in old.items():
        if key not in clips and gg.is_custom(prev["title"]):
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


class Library:
    def __init__(self, media):
        self.media = media
        self.lock = threading.RLock()
        self.cfg = settings.load()
        self.state = load_state()
        idx = load_json(paths.INDEX, {})
        self.index = idx.get("files", {}) if isinstance(idx, dict) and idx.get("version") == INDEX_VERSION else {}
        self.clips, self.ids = {}, {}
        self.covers, self.own_covers, self.game_names = {}, {}, {}
        self.gg_info = {"installed": gg.installed(), "clips": 0, "folder": None, "error": None}
        self.gg_dir = None
        self.gg_stamp = None
        self.folder_counts = {}
        self.folder_sig = None
        self.version = 0  # goes up whenever clips are added, removed or get their details
        self.queue, self.queued = [], set()  # files waiting to be read with ffprobe
        self.scan_total = 0
        self.wake = threading.Event()
        self.edits, self.edit_prefix = {}, {}
        self.last_seen = 0.0
        self.forecast = (None, None)  # (what it was worked out from, result)

    # ----- reading the sources -----

    def gg_enabled(self):
        return self.cfg["sources"]["gg"]["enabled"] and gg.installed()

    def export_dir(self):
        """Where edited copies go: your choice in Settings, else "Edited Clips" in your first clips folder."""
        if self.cfg.get("exportDir"):
            return self.cfg["exportDir"]
        if self.gg_dir:
            return os.path.join(self.gg_dir, "Edited Clips")
        for f in self.cfg["sources"]["folders"]:
            if f["enabled"]:
                return os.path.join(f["path"], "Edited Clips")
        return os.path.join(settings.videos_dir(), "Cliptrove", "Edited Clips")

    def refresh(self, wait=0.0):
        """Re-read every source. Returns the GG title changes found. With `wait`, give newly found files up to
        that many seconds to be read, so a handful of new clips show up complete straight away."""
        with self.lock:
            clips = {}
            if self.gg_enabled():
                try:
                    found, self.gg_dir = gg.read()
                    self.gg_info.update(clips=len(found), folder=self.gg_dir, error=None)
                except Exception as e:  # keep what GG had last time (GG may be writing to its library)
                    found = {k: c for k, c in self.clips.items() if c["source"] == "gg"}
                    self.gg_info["error"] = str(e)
                self.gg_stamp = gg.stamp()
                clips.update(found)
            else:
                self.gg_dir = None
                self.gg_info.update(clips=0, error=None)
            self.gg_info["installed"] = gg.installed()
            self._scan_folders(clips)
            self._apply(clips)
            self.covers = covers.resolve(clips)
            self.own_covers = covers.custom_covers()
            changes = self._track_titles(clips)
            if set(clips) != set(self.clips):
                self.version += 1
            self.clips = clips
            self.ids = {clip_id(k): k for k in clips}
            self._save_index()
        if wait and 0 < len(self.queue) <= 40:
            end = time.time() + wait
            while self.queue and time.time() < end:
                time.sleep(0.1)
        return changes

    def _scan_folders(self, clips):
        taken = {path_key(c["file"]) for c in clips.values()}
        exclude = {path_key(self.export_dir())}
        by_time = {(e.get("size"), int(e.get("mtime") or 0)): pk for pk, e in self.index.items()}
        seen, counts, new = set(), {}, []
        for f in self.cfg["sources"]["folders"]:
            if not f["enabled"]:
                continue
            root, count = f["path"], 0
            if not os.path.isdir(root):
                counts[path_key(root)] = None
                continue
            for path, st in folder.walk(root, exclude):
                pk = path_key(path)
                if pk in taken or pk in seen:  # GG's own clips, or a folder inside another one
                    continue
                seen.add(pk)
                info = self._known(pk, path, st, by_time, new)
                c = folder.make_clip(path, st, root, f["recorder"], info)
                clips[c["key"]] = c
                count += 1
            counts[path_key(root)] = count
        self.folder_counts = counts
        # Forget files that are gone, unless their folder can't be reached right now (a drive that's unplugged)
        roots = [f["path"] for f in self.cfg["sources"]["folders"] if os.path.isdir(f["path"])]
        for pk in [pk for pk in self.index if pk not in seen]:
            path = self.index[pk].get("path", "")
            if any(pk.startswith(path_key(r)) for r in roots) and not os.path.exists(path):
                del self.index[pk]
        if new:
            new.sort(key=lambda x: -x[1])  # newest first
            for pk, _ in new:
                if pk not in self.queued:
                    self.queue.append(pk)
                    self.queued.add(pk)
            self.scan_total = len(self.queue)
            self.wake.set()

    def _known(self, pk, path, st, by_time, new):
        """What's already been read from this file, or None (it's then queued to be read)."""
        e = self.index.get(pk)
        size, mtime = st.st_size, int(st.st_mtime)
        if not e:
            # Renamed or moved? A file that's gone with the same size and time is the same clip.
            old = by_time.get((size, mtime))
            if old and old in self.index and not os.path.exists(self.index[old].get("path", "")):
                e = self.index.pop(old)
                e["path"] = path
                self.index[pk] = e
                self._move_state("f|" + old, "f|" + pk)
        if e and e.get("size") == size and int(e.get("mtime") or 0) == mtime:
            e["path"] = path
            if e.get("probed"):
                return e
        else:
            self.index[pk] = {"path": path, "size": size, "mtime": st.st_mtime, "probed": False}
        new.append((pk, st.st_mtime))
        return None

    def _move_state(self, old, new):
        for k in PER_CLIP:
            d = self.state.setdefault(k, {})
            if old in d:
                d[new] = d.pop(old)
        self._save_state()

    def _apply(self, clips):
        """Add what you've set for each clip, and give each game one spelling across sources."""
        games = self.state.setdefault("games", {})
        for key, c in clips.items():
            c["gameSet"] = bool(games.get(key))
            if c["gameSet"]:
                c["game"] = games[key]
        groups, from_gg = collections.defaultdict(collections.Counter), {}
        for c in clips.values():
            n = norm(c["game"])
            groups[n][c["game"]] += 1
            if c["source"] == "gg":
                from_gg.setdefault(n, c["game"])
        steam = covers.known_names()
        names = {}
        for n, variants in groups.items():
            names[n] = from_gg.get(n) or steam.get(n) or max(
                variants, key=lambda v: (variants[v], sum(ch.isupper() for ch in v)))
        self.game_names = names
        for c in clips.values():
            self._apply_one(c)

    def _apply_one(self, c):
        key = c["key"]
        c["game"] = self.game_names.get(norm(c["game"]), c["game"])
        c["fav"] = bool(self.state["favorites"].get(key))
        c["starred"] = bool(c.get("ggStar") or c["fav"])
        saved = self.state["trims"].get(key)
        trim, src = (saved, "saved") if saved else (c.get("baseTrim"), "gg" if c.get("baseTrim") else "")
        full = c["full"]
        if trim and trim[1] > trim[0]:
            end = min(float(trim[1]), full) if full else float(trim[1])
            c.update(start=float(trim[0]), end=end, trimmed=True, trimSrc=src)
        else:
            c.update(start=0.0, end=full, trimmed=False, trimSrc="")

    def _track_titles(self, clips):
        st = self.state
        now = now_iso()
        if not st["started"]:
            st["started"] = now
        st["last_run"] = now
        changes = []
        if self.gg_enabled() and not self.gg_info["error"]:
            ours = {k: c for k, c in clips.items() if c["source"] == "gg"}
            if st["snapshot"]:
                changes = find_changes(st["snapshot"], ours, now)
            st["changes"].extend(changes)
            st["snapshot"] = {k: {f: c[f] for f in ("title", "file", "game", "recorded")} for k, c in ours.items()}
        self._save_state()
        return changes

    def _save_state(self):
        save_json(paths.LIBRARY, self.state, indent=1)

    def _save_index(self):
        try:
            save_json(paths.INDEX, {"version": INDEX_VERSION, "files": self.index})
        except OSError:
            pass

    # ----- reading new files in the background -----

    def scan_status(self):
        return {"pending": len(self.queue), "total": self.scan_total}

    def work(self):
        """Background thread: read new files with ffprobe (newest first), then look for new clips now and then
        while the site is open."""
        while True:
            self.wake.wait(30)
            self.wake.clear()
            done = 0
            last_save = time.time()
            while True:
                with self.lock:
                    if not self.queue:
                        break
                    pk = self.queue.pop(0)
                    self.queued.discard(pk)
                    entry = self.index.get(pk)
                    path = entry and entry.get("path")
                if not path:
                    continue
                try:
                    info = self.media.probe(path)
                except OSError:
                    continue
                with self.lock:
                    entry = self.index.get(pk)
                    if entry is None:
                        continue
                    entry.update(info, probed=True)
                    c = self.clips.get("f|" + pk)
                    if c:  # fill in the clip in place
                        try:
                            st = os.stat(path)
                        except OSError:
                            continue
                        fresh = folder.make_clip(path, st, c["root"], self._recorder_of(c["root"]), entry)
                        fresh["gameSet"] = c.get("gameSet", False)
                        if fresh["gameSet"]:
                            fresh["game"] = c["game"]
                        self._apply_one(fresh)
                        self.clips[c["key"]] = fresh
                    done += 1
                    if time.time() - last_save > 2:
                        self._save_index()
                        self.version += 1
                        last_save = time.time()
            if done:
                with self.lock:
                    self._save_index()
                    self.version += 1
                    self.scan_total = 0
                self._make_thumbs()
            if time.time() - self.last_seen < 120:
                self._check_for_new()

    def _recorder_of(self, root):
        for f in self.cfg["sources"]["folders"]:
            if path_key(f["path"]) == path_key(root):
                return f["recorder"]
        return "auto"

    def _make_thumbs(self, limit=60):
        """Thumbnails for the newest clips from folders, so the first pages show up quickly."""
        with self.lock:
            recent = sorted((c for c in self.clips.values() if c["source"] == "folder"),
                            key=lambda c: c["recorded"], reverse=True)[:limit]
        for c in recent:
            if self.queue:
                return  # new files first
            try:
                self.media.thumbnail(clip_id(c["key"]), c["file"])
            except (LookupError, OSError, RuntimeError):
                pass

    def _check_for_new(self):
        """Re-read the library if GG or any clips folder has changed."""
        sig = []
        for f in self.cfg["sources"]["folders"]:
            if f["enabled"] and os.path.isdir(f["path"]):
                n = size = newest = 0
                for _, st in folder.walk(f["path"], {path_key(self.export_dir())}):
                    n, size, newest = n + 1, size + st.st_size, max(newest, st.st_mtime)
                sig.append((path_key(f["path"]), n, size, newest))
        sig = tuple(sig)
        changed = self.folder_sig is not None and sig != self.folder_sig
        self.folder_sig = sig
        if self.gg_enabled() and self.gg_stamp is not None and gg.stamp() != self.gg_stamp:
            changed = True
        if changed:
            try:
                for ch in self.refresh():
                    print("  " + describe(ch))
            except Exception as e:
                print("Couldn't re-read the library:", e)

    # ----- what you add to clips -----

    def clip(self, cid):
        with self.lock:
            key = self.ids.get(cid)
            if key is None:
                raise LookupError("That clip isn't in your library any more")
            return key, self.clips[key]

    def set_nickname(self, cid, nick):
        nick = " ".join(str(nick or "").split())[:120]
        with self.lock:
            key, c = self.clip(cid)
            nicks = self.state.setdefault("nicknames", {})
            before = nicks.get(key, "")
            change = None
            if nick != before:
                if nick:
                    nicks[key] = nick
                else:
                    nicks.pop(key, None)
                change = {"when": now_iso(), "kind": "nickname", "key": key, "game": c["game"],
                          "recorded": c["recorded"], "file": c["file"], "before": before or None, "after": nick or None}
                self.state["changes"].append(change)
                self._save_state()
            return {"nick": nick, "change": self.client_change(change) if change else None}

    def set_mix(self, cid, tracks):
        """Remember the Game/Chat/Mic levels you set for a clip (going back to the recorded levels forgets them)."""
        with self.lock:
            key, c = self.clip(cid)
            base = c["tracks"]
            levels = [{"vol": t["volume"], "muted": t["muted"]} for t in base]
            for t in tracks or []:
                i = int(t.get("stream", -1))
                if 0 <= i < len(levels):
                    levels[i] = {"vol": round(min(2.0, max(0.0, float(t.get("vol", 1.0)))), 3),
                                 "muted": bool(t.get("muted"))}
            mixes = self.state.setdefault("mix", {})
            if all(abs(l["vol"] - b["volume"]) < 0.005 and l["muted"] == b["muted"] for l, b in zip(levels, base)):
                mixes.pop(key, None)
            else:
                mixes[key] = levels
            self._save_state()
            return {"ok": True}

    def set_favorite(self, cid, on):
        with self.lock:
            key, c = self.clip(cid)
            favs = self.state.setdefault("favorites", {})
            if on:
                favs[key] = True
            else:
                favs.pop(key, None)
            self._apply_one(c)
            self._save_state()
            return {"starred": c["starred"], "fav": c["fav"], "ggStar": bool(c.get("ggStar"))}

    def set_trim(self, cid, start, end):
        """Keep a part of the clip as its trim (used by previews and the home page). The whole clip clears it."""
        with self.lock:
            key, c = self.clip(cid)
            trims = self.state.setdefault("trims", {})
            full = float(c["full"] or 0)
            if start is None or end is None:
                trims.pop(key, None)
            else:
                start, end = max(0.0, float(start)), float(end)
                if full:
                    end = min(end, full)
                if end - start < 0.2:
                    raise ValueError("Pick a start and end at least 0.2 seconds apart")
                whole = start < 0.05 and (not full or end > full - 0.05)
                base = c.get("baseTrim")
                same_as_gg = base and abs(base[0] - start) < 0.05 and abs(base[1] - end) < 0.05
                if (whole and not base) or same_as_gg:
                    trims.pop(key, None)
                else:
                    trims[key] = [round(start, 3), round(end, 3)]
            self._apply_one(c)
            self._save_state()
            return {k: c[k] for k in ("start", "end", "trimmed", "trimSrc")}

    def set_game(self, cid, game):
        """Put a clip from a folder under another game ("" goes back to the game worked out from its name)."""
        game = " ".join(str(game or "").split())[:80]
        with self.lock:
            key, c = self.clip(cid)
            if c["source"] != "folder":
                raise ValueError("Only clips from folders can be moved to another game")
            games = self.state.setdefault("games", {})
            if game:
                games[key] = self.game_names.get(norm(game), game)
                c["game"], c["gameSet"] = games[key], True
            else:
                games.pop(key, None)
                st = os.stat(c["file"])
                fresh = folder.make_clip(c["file"], st, c["root"], self._recorder_of(c["root"]),
                                         self.index.get(path_key(c["file"])))
                c["game"], c["gameSet"] = self.game_names.get(norm(fresh["game"]), fresh["game"]), False
            self.game_names.setdefault(norm(c["game"]), c["game"])
            self._save_state()
            return {"game": c["game"], "gameSet": c["gameSet"]}

    # ----- edited copies (everything in the "Edited Clips" folder) -----

    def _name_index(self):
        """Lookups from a file name (without extension) to the clip it belongs to."""
        by_stem, by_base = {}, {}
        for key, c in self.clips.items():
            base = os.path.splitext(os.path.basename(c["file"]))[0]
            by_base.setdefault(base.lower(), key)
            m = STEM.match(base)
            if m:
                by_stem.setdefault(m.group(1).lower(), key)
        return by_stem, by_base

    @staticmethod
    def made_from(base, lookups):
        """(clip key or None, the clip's part of the name or None, the rest) for a copy saved as
        "<clip's file name>__<name>"."""
        by_stem, by_base = lookups
        m = STEM.match(base)
        if m and m.group(1).lower() in by_stem:
            return by_stem[m.group(1).lower()], m.group(1), base[len(m.group(1)):].strip("_ ")
        parts = base.split("__")
        for i in range(len(parts) - 1, 0, -1):
            prefix = "__".join(parts[:i])
            key = by_base.get(prefix.lower())
            if key:
                return key, prefix, "__".join(parts[i:]).strip("_ ")
        if m:
            return None, m.group(1), base[len(m.group(1)):].strip("_ ")
        return None, None, base

    def list_edits(self, token):
        """Every video in "Edited Clips", with the clip it was made from (worked out from its name)."""
        out_dir = self.export_dir()
        try:
            names = os.listdir(out_dir)
        except OSError:
            names = []
        with self.lock:
            clips = self.clips
            lookups = self._name_index()
            nicks = self.state.get("nicknames", {})
        items, edits, prefixes = [], {}, {}
        for name in names:
            path = os.path.join(out_dir, name)
            if not name.lower().endswith(EDIT_EXTS) or not os.path.isfile(path):
                continue
            st = os.stat(path)
            eid = "x" + hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:11]  # "x": never clashes with clip ids
            edits[eid] = path
            info = self.media.probe(path)
            base = os.path.splitext(name)[0]
            src_key, prefix, label = self.made_from(re.sub(r" \(18MB\)$", "", base), lookups)
            prefixes[eid] = prefix
            src = clips.get(src_key) if src_key else None
            v = f"t={token}&v={int(st.st_mtime)}"
            n_audio = max(1, info["audio"])
            items.append({
                "id": eid, "edited": True, "src": "edit", "title": label.replace(" (18MB)", "") or base, "custom": True,
                "nick": "", "game": src["game"] if src else "Unknown game",
                "recorded": src["recorded"] if src else iso_time(st.st_mtime), "made": iso_time(st.st_mtime),
                "size": st.st_size, "full": info["duration"], "start": 0.0, "end": info["duration"], "trimmed": False,
                "trimSrc": "", "starred": False, "ggStar": False, "fav": False, "file": name, "prefix": prefix or "",
                "video": f"/media/{eid}?{v}", "thumb": f"/thumb/{eid}?{v}",
                "tracks": [{"name": "Mix" if n_audio == 1 else f"Track {i + 1}", "volume": 1.0, "muted": False,
                            "baseVolume": 1.0, "baseMuted": False} for i in range(n_audio)],
                "source": clip_id(src_key) if src_key else None,
                "sourceTitle": (nicks.get(src_key) or src["title"]) if src else "",
            })
        with self.lock:
            self.edits, self.edit_prefix = edits, prefixes
        return sorted(items, key=lambda e: e["made"], reverse=True)

    def edit_path(self, eid):
        with self.lock:
            path = self.edits.get(eid)
        if not path or not os.path.isfile(path):
            raise LookupError("That edited clip isn't there any more")
        return path

    def file_of(self, cid):
        return self.edit_path(cid) if cid.startswith("x") else self.clip(cid)[1]["file"]

    def export_plan(self, cid, name, small, overwrite):
        """(source file, name for the new file without extension, file it replaces or None)."""
        tag = " (18MB)" if small else ""
        if cid.startswith("x"):  # an edited clip: overwrite it, or save a new copy next to it
            src = self.edit_path(cid)
            base = re.sub(r" \(18MB\)$", "", os.path.splitext(os.path.basename(src))[0])
            if overwrite:
                return src, base + tag, src
            with self.lock:
                _, prefix, _ = self.made_from(base, self._name_index())
            if safe_name(name):
                return src, (f"{prefix}__{safe_name(name)}" if prefix else safe_name(name)) + tag, None
            return src, f"{base} (edit){tag}", None
        src = self.clip(cid)[1]["file"]
        base = os.path.splitext(os.path.basename(src))[0]
        m = STEM.match(base)
        return src, f"{m.group(1) if m else base}__{safe_name(name) or 'edit'}{tag}", None

    # ----- what the page gets -----

    def client_change(self, ch):
        key = ch.get("key")
        return {"when": ch.get("when"), "kind": ch.get("kind"), "game": ch.get("game"), "recorded": ch.get("recorded"),
                "file": os.path.basename(ch.get("file") or ""), "before": ch.get("before"), "after": ch.get("after"),
                "id": clip_id(key) if key in self.clips else None}

    def client_clips(self, token):
        nicks, mixes = self.state.get("nicknames", {}), self.state.get("mix", {})
        items = []
        for key, c in self.clips.items():
            cid = clip_id(key)
            # Track levels: the ones you saved for this clip, else the recorder's (kept for "Reset")
            tracks = [dict(t, baseVolume=t["volume"], baseMuted=t["muted"]) for t in c["tracks"]]
            for t, saved in zip(tracks, mixes.get(key) or []):
                t["volume"], t["muted"] = saved["vol"], saved["muted"]
            v = f"t={token}"
            if c["source"] == "gg":
                thumb = f"/thumb/{cid}?{v}" if c["thumb"] else ""
                label = "SteelSeries GG"
            else:
                v += f"&v={int(c['mtime'])}"
                thumb = f"/thumb/{cid}?{v}"
                label = folder.SHORT.get(c["recorder"]) or os.path.basename(c["root"].rstrip("\\/")) or c["root"]
            items.append({
                "id": cid, "src": c["source"], "srcLabel": label, "title": c["title"], "custom": c["custom"],
                "nick": nicks.get(key, ""), "game": c["game"], "gameSet": c.get("gameSet", False),
                "recorded": c["recorded"], "full": c["full"], "start": c["start"], "end": c["end"],
                "trimmed": c["trimmed"], "trimSrc": c["trimSrc"], "starred": c["starred"], "ggStar": bool(c.get("ggStar")),
                "fav": c["fav"], "file": os.path.basename(c["file"]), "folder": os.path.dirname(c["file"]),
                "video": f"/media/{cid}?{v}", "thumb": thumb, "tracks": tracks,
            })
        return items

    def client_games(self, token):
        games = []
        for g in sorted({c["game"] for c in self.clips.values()}, key=str.lower):
            own = self.own_covers.get(norm(g))
            cover = f"/cover/{clip_id(g)}?t={token}" if own else self.covers.get(norm(g), "")
            games.append({"name": g, "cover": cover})
        return games

    def cover_file(self, gid):
        with self.lock:
            for g in {c["game"] for c in self.clips.values()}:
                if clip_id(g) == gid:
                    return self.own_covers.get(norm(g))
        return None

    def client_data(self, token):
        with self.lock:
            return {
                "clips": self.client_clips(token),
                "games": self.client_games(token),
                "changes": [self.client_change(ch) for ch in self.state["changes"]],
                "started": self.state["started"],
                "lastRun": self.state["last_run"],
                "version": self.version,
                "sources": {"gg": self.gg_enabled(), "folders": sum(f["enabled"] for f in self.cfg["sources"]["folders"])},
                "exportDir": self.export_dir(),
            }

    # ----- analytics -----

    def predictions(self):
        """Which games you're likely to play in the next week (worked out again when your clips or the date change)."""
        with self.lock:
            clips = [{"game": c["game"], "recorded": c["recorded"]} for c in self.clips.values()]
        sig = (time.strftime("%Y-%m-%d"), hash(tuple(sorted((c["recorded"], c["game"]) for c in clips))))
        if self.forecast[0] == sig:
            return self.forecast[1]
        result = analytics.predict(clips)
        self.forecast = (sig, result)
        return result

    # ----- settings -----

    def settings_info(self):
        with self.lock:
            cfg = self.cfg
            folders = [dict(f, exists=os.path.isdir(f["path"]), clips=self.folder_counts.get(path_key(f["path"])))
                       for f in cfg["sources"]["folders"]]
            gg_info = dict(self.gg_info, enabled=cfg["sources"]["gg"]["enabled"])
            skip = [f["path"] for f in cfg["sources"]["folders"]] + ([self.gg_dir] if self.gg_dir else [])
            export = {"path": self.export_dir(), "custom": bool(cfg.get("exportDir"))}
            total = len(self.clips)
        return {"gg": gg_info, "folders": folders, "recorders": list(folder.RECORDERS.items()),
                "suggestions": settings.detect(skip), "exportDir": export, "total": total,
                "scan": self.scan_status()}

    def setup_info(self):
        """What the first-start setup needs: is GG here, and which recorders' folders are on this PC."""
        with self.lock:
            gg_info = {"installed": gg.installed(), "clips": self.gg_info.get("clips", 0), "folder": self.gg_dir}
        return {"gg": gg_info, "found": settings.detect(include_empty=True), "videosDir": settings.videos_dir()}

    def finish_setup(self, body):
        """Save what was picked in the first-start setup (or just remember it was skipped)."""
        with self.lock:
            cfg = dict(self.cfg, sources=dict(self.cfg["sources"]), setupDone=True)
            if not body.get("skip"):
                folders = settings.clean_folders(body.get("folders"))
                for f in folders:
                    if not os.path.isdir(f["path"]):
                        raise ValueError(f"Can't find the folder {f['path']}")
                cfg["sources"]["gg"] = {"enabled": bool(body.get("gg"))}
                cfg["sources"]["folders"] = folders
            cfg = settings.normalize(cfg)
            settings.save(cfg)
            self.cfg = cfg
            self.folder_sig = None
        if not body.get("skip"):
            self.refresh(wait=3)
        return {"total": len(self.clips), "scan": self.scan_status()}

    def update_settings(self, body):
        """Change where clips come from and where copies go; the library is re-read straight away."""
        with self.lock:
            cfg = dict(self.cfg, sources=dict(self.cfg["sources"]))
            if isinstance(body.get("gg"), dict) and "enabled" in body["gg"]:
                cfg["sources"]["gg"] = {"enabled": bool(body["gg"]["enabled"])}
            if "folders" in body:
                folders = settings.clean_folders(body.get("folders"))
                known = {path_key(f["path"]) for f in self.cfg["sources"]["folders"]}
                for f in folders:
                    if path_key(f["path"]) not in known and not os.path.isdir(f["path"]):
                        raise ValueError(f"Can't find the folder {f['path']}")
                cfg["sources"]["folders"] = folders
            if "exportDir" in body:
                cfg["exportDir"] = str(body.get("exportDir") or "")
            cfg["setupDone"] = True  # changing settings by hand counts as having set things up
            cfg = settings.normalize(cfg)
            settings.save(cfg)
            self.cfg = cfg
            self.folder_sig = None
        self.refresh(wait=3)
