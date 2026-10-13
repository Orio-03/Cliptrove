"""Cover art for each game, from Steam, cached in covers.json.

Only game names and Steam app IDs are sent to Steam. Games Steam doesn't have (and games while you're offline)
get a tile made from one of their clips instead. To use your own picture for a game, put an image named after
the game (e.g. "VALORANT.jpg") in the covers folder in ClipShelf's data folder.
"""
import json
import os
import time
import urllib.parse
import urllib.request

from . import __version__, paths
from .util import load_json, norm, save_json

STEAM_ASSETS = "https://shared.cloudflare.steamstatic.com/store_item_assets/"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
NO_ART = {"desktop", "unsorted", "unknowngame"}

# Games GG knows from other stores that are also on Steam, which is where cover art comes from.
STEAM_IDS = {norm(k): v for k, v in {
    "Rocket League": 252950, "Among Us": 945360, "Overcooked! 2": 728880, "Destiny 2": 1085660,
    "Tom Clancy's The Division 2": 2221490, "Marvel's Spider-Man Remastered": 1817070,
    "ARC Raiders - Server Slam": 1808500,
}.items()}


def fetch_json(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": f"ClipShelf/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def known_names():
    """{norm(game): Steam's spelling of the name} for games found on Steam by name."""
    return load_json(paths.COVER_CACHE, {}).get("names", {})


def resolve(clips):
    """{norm(game): cover art URL} from Steam, cached. Steam is only asked about games it hasn't been asked
    about yet (and not again for 6 hours if it couldn't be reached)."""
    cache = load_json(paths.COVER_CACHE, {})
    apps, search, names = cache.setdefault("apps", {}), cache.setdefault("search", {}), cache.setdefault("names", {})
    games = {}
    for c in clips.values():
        games.setdefault(norm(c["game"]), c["game"])
    ids = {}
    for c in clips.values():
        uid = c.get("uid") or ""
        if uid.startswith("1_") and uid[2:].isdigit():  # GG: "1_<id>" is a Steam game
            ids[norm(c["game"])] = int(uid[2:])
    for n in set(games) - set(ids):
        if n in STEAM_IDS:
            ids[n] = STEAM_IDS[n]
        elif search.get(n):
            ids[n] = search[n]
    now = time.time()
    unsearched = [g for n, g in games.items() if n not in ids and n not in search and n not in NO_ART and n]
    stale = {str(a) for a in ids.values() if now - apps.get(str(a), {}).get("at", 0) > 30 * 86400}
    if (unsearched or stale) and now - cache.get("failed", 0) > 6 * 3600:
        try:
            for g in unsearched[:20]:
                found = fetch_json("https://store.steampowered.com/api/storesearch/?l=english&cc=US&term="
                                   + urllib.parse.quote(g))
                match = next((it for it in found.get("items", []) if norm(it.get("name", "")) == norm(g)), None)
                search[norm(g)] = match["id"] if match else None
                if match:
                    ids[norm(g)] = match["id"]
                    names[norm(g)] = match.get("name") or g
                    stale.add(str(match["id"]))
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
            save_json(paths.COVER_CACHE, cache)
        except OSError:
            pass
    return {n: apps.get(str(a), {}).get("url", "") for n, a in ids.items()}


def custom_covers():
    """{norm(game): path} for the pictures in the covers folder."""
    out = {}
    try:
        names = os.listdir(paths.COVERS_DIR)
    except OSError:
        return out
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext.lower() in IMAGE_EXTS:
            out.setdefault(norm(stem), os.path.join(paths.COVERS_DIR, name))
    return out
