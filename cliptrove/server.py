"""The site: a small web server on this PC only (127.0.0.1), with the page, your clips and the actions behind it.

Requests must come from the page itself: every call carries a random token that only the page knows, and the
Host header must be this PC, so other websites open in your browser can't use it.
"""
import json
import os
import re
import secrets
import select
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import APP_NAME, __version__, autostart, paths
from .library import Library, describe
from .media import Media
from .util import open_folder

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
STATIC = {"/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
IDLE_EXIT = 300  # seconds without the browser tab checking in before a window-run Cliptrove stops
PING_NAME = "cliptrove"


def client_gone(sock):
    """True when the browser has hung up, e.g. you stopped hovering a clip before its audio was ready."""
    try:
        ready, _, _ = select.select([sock], [], [], 0)
        return bool(ready) and sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


class App:
    def __init__(self, port):
        self.port = port
        self.token = secrets.token_urlsafe(18)
        self.session = secrets.token_hex(4)  # lets a page left open from an earlier run notice the restart
        self.media = Media()
        self.library = Library(self.media)
        self.last_seen = time.time()
        self.page_loaded = False
        self.dialog_lock = threading.Lock()
        self.httpd = None
        self.background = False

    def seen(self):
        self.last_seen = self.library.last_seen = time.time()

    def start(self):
        for ch in self.library.refresh():
            print("  " + describe(ch))
        threading.Thread(target=self.library.work, daemon=True).start()

    def page(self):
        try:
            for ch in self.library.refresh(wait=3):
                print("  " + describe(ch))
        except Exception as e:  # keep serving the last good copy
            print("Couldn't re-read the library:", e)
        data = self.library.client_data(self.token)
        data["edits"] = self.library.list_edits(self.token)
        data["meta"] = {
            "token": self.token, "session": self.session, "port": self.port, "ffmpeg": bool(self.media.ffmpeg),
            "app": APP_NAME, "appVersion": __version__, "version": data.pop("version"),
            "scan": self.library.scan_status(), "started": data.pop("started"), "lastRun": data.pop("lastRun"),
            "sources": data.pop("sources"), "exportDir": data.pop("exportDir"),
            "firstRun": not self.library.cfg.get("setupDone", True),
        }
        blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        blob = blob.replace("</", "<\\/").replace("<!--", "<\\u0021--")
        with open(os.path.join(WEB, "index.html"), encoding="utf-8") as f:
            html = f.read()
        return html.replace("__CLIPTROVE_DATA__", blob).replace("__V__", self.session)

    def ping(self):
        return {"app": PING_NAME, "session": self.session, "version": self.library.version,
                "scan": self.library.scan_status()}

    def media_file(self, cid):
        return self.media.playable(cid, self.library.file_of(cid))

    def thumb_file(self, cid):
        if cid.startswith("x"):
            path = self.library.edit_path(cid)
            return self.media.thumbnail(cid, path, at=min(2.0, self.media.probe(path)["duration"] * 0.3))
        _, c = self.library.clip(cid)
        if c["source"] == "gg":
            return c["thumb"]
        return self.media.thumbnail(cid, c["file"])

    def audio_file(self, cid, n, wanted):
        return self.media.audio_track(cid, self.library.file_of(cid), n, wanted)

    def prefetch(self, cid):
        try:
            self.media.prefetch(cid, self.library.file_of(cid))
        except LookupError:
            pass

    def start_export(self, body):
        cid = str(body.get("id") or "")
        small = body.get("quality") == "small"
        src, stem, replace = self.library.export_plan(cid, str(body.get("name", "")), small, bool(body.get("overwrite")))
        return self.media.start_export(src, self.library.export_dir(), stem, replace, body.get("start"), body.get("end"),
                                       body.get("volumes") or [], body.get("precise"), body.get("loud"), small)

    def reveal(self, cid=None, file=None, folder=False):
        out_dir = self.library.export_dir()
        if folder:
            os.makedirs(out_dir, exist_ok=True)
            return open_folder(out_dir)
        path = self.library.file_of(cid) if cid else os.path.join(out_dir, os.path.basename(file or ""))
        if not os.path.isfile(path):
            raise LookupError("File not found")
        open_folder(path, select=True)

    def open_place(self, what):
        places = {"data": paths.DATA, "covers": paths.COVERS_DIR, "export": self.library.export_dir()}
        if what not in places:
            raise ValueError("Unknown folder")
        os.makedirs(places[what], exist_ok=True)
        open_folder(places[what])

    def settings_info(self):
        info = self.library.settings_info()
        info.update(autostart={"supported": autostart.supported(), "enabled": autostart.enabled()},
                    dataDir=paths.DATA, coversDir=paths.COVERS_DIR, ffmpeg=self.media.ffmpeg, appVersion=__version__,
                    port=self.port, background=self.background)
        return info

    def quit(self):
        """Stop Cliptrove (after answering the page)."""
        print("Quit from the page.")
        threading.Timer(0.3, self.httpd.shutdown).start()

    def setup_info(self):
        info = self.library.setup_info()
        info.update(ffmpeg=bool(self.media.ffmpeg), autostart={"supported": autostart.supported(),
                                                               "enabled": autostart.enabled()}, port=self.port)
        return info

    def finish_setup(self, body):
        result = self.library.finish_setup(body)
        if body.get("autostart") and autostart.supported() and not autostart.enabled():
            try:
                autostart.enable()
            except RuntimeError as e:
                result["autostartError"] = str(e)
        return result

    def set_autostart(self, on):
        if on:
            autostart.enable()
        else:
            autostart.disable()
        return {"enabled": autostart.enabled()}

    def pick_folder(self, initial=""):
        """Show the system's folder picker on this PC and return the folder chosen (None if cancelled)."""
        if not self.dialog_lock.acquire(blocking=False):
            raise ValueError("A folder picker is already open")
        result = {}

        def ask():  # Tk must run on the thread that made it
            try:
                import tkinter
                from tkinter import filedialog
                root = tkinter.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                root.update()
                result["path"] = filedialog.askdirectory(parent=root, title="Choose a folder with clips",
                                                         initialdir=initial if os.path.isdir(initial or "") else None,
                                                         mustexist=True)
                root.destroy()
            except Exception as e:
                result["error"] = str(e)

        try:
            t = threading.Thread(target=ask, daemon=True)
            t.start()
            t.join()
        finally:
            self.dialog_lock.release()
        if "error" in result:
            raise RuntimeError("Couldn't open the folder picker. Paste the folder's path instead.")
        return {"path": os.path.normpath(result["path"]) if result.get("path") else None}


def make_handler(app):
    hosts = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def allowed(self, need_token):
            app.seen()
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
                return self.send_bytes(app.page().encode("utf-8"), "text/html; charset=utf-8")
            if path in STATIC:
                if not self.allowed(False):
                    return
                name, ctype = STATIC[path]
                return self.send_file(os.path.join(WEB, name), ctype)
            if path == "/api/ping":
                if self.allowed(False):
                    self.send_json(app.ping())
                return
            if not self.allowed(True):
                return
            parts = path.strip("/").split("/")
            try:
                if parts[0] == "media" and len(parts) == 2:
                    return self.send_file(app.media_file(parts[1]), "video/mp4")
                if parts[0] == "thumb" and len(parts) == 2:
                    return self.send_file(app.thumb_file(parts[1]), "image/jpeg", cache=True)
                if parts[0] == "cover" and len(parts) == 2:
                    found = app.library.cover_file(parts[1])
                    ext = os.path.splitext(found or "")[1].lower()
                    return self.send_file(found, {".png": "image/png", ".webp": "image/webp"}.get(ext, "image/jpeg"))
                if parts[0] == "audio" and len(parts) == 3:
                    track = app.audio_file(parts[1], int(parts[2]), wanted=lambda: not client_gone(self.connection))
                    return self.send_file(track, "audio/mp4")
                if parts[:2] == ["api", "edited"]:
                    return self.send_json({"items": app.library.list_edits(app.token)})
                if parts[:2] == ["api", "job"] and len(parts) == 3:
                    return self.send_json(app.media.jobs.get(parts[2]) or {"state": "error", "error": "Unknown job"})
                if parts[:2] == ["api", "settings"]:
                    return self.send_json(app.settings_info())
                if parts[:2] == ["api", "setup"]:
                    return self.send_json(app.setup_info())
                if parts[:2] == ["api", "analytics"]:
                    return self.send_json(app.library.predictions())
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
            lib = app.library
            try:
                body = json.loads(raw or b"{}")
                cid = body.get("id")
                if path == "/api/nickname":
                    return self.send_json(lib.set_nickname(cid, body.get("nickname", "")))
                if path == "/api/mix":
                    return self.send_json(lib.set_mix(cid, body.get("tracks")))
                if path == "/api/favorite":
                    return self.send_json(lib.set_favorite(cid, bool(body.get("on"))))
                if path == "/api/trim":
                    clear = bool(body.get("clear"))
                    return self.send_json(lib.set_trim(cid, None if clear else body.get("start"),
                                                       None if clear else body.get("end")))
                if path == "/api/game":
                    return self.send_json(lib.set_game(cid, body.get("game", "")))
                if path == "/api/export":
                    return self.send_json({"job": app.start_export(body)})
                if path == "/api/prefetch":
                    app.prefetch(cid)
                    return self.send_json({"ok": True})
                if path == "/api/reveal":
                    app.reveal(cid, body.get("file"), bool(body.get("folder")))
                    return self.send_json({"ok": True})
                if path == "/api/open":
                    app.open_place(body.get("what"))
                    return self.send_json({"ok": True})
                if path == "/api/settings":
                    lib.update_settings(body)
                    return self.send_json(app.settings_info())
                if path == "/api/setup":
                    return self.send_json(app.finish_setup(body))
                if path == "/api/autostart":
                    return self.send_json(app.set_autostart(bool(body.get("enabled"))))
                if path == "/api/pick-folder":
                    return self.send_json(app.pick_folder(str(body.get("initial") or "")))
                if path == "/api/quit":
                    app.quit()
                    return self.send_json({"ok": True})
                if path == "/api/rescan":
                    lib.folder_sig = None
                    lib.refresh(wait=3)
                    return self.send_json({"ok": True, "version": lib.version, "total": len(lib.clips)})
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
            self.send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
                            status)

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
            # recorders need to be able to replace a clip file whenever you edit it there.
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


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError)):
            return  # the browser hung up mid-request (normal when skipping through a video)
        super().handle_error(request, client_address)


def watchdog(app, httpd):
    while True:
        time.sleep(10)
        idle = time.time() - app.last_seen
        if not app.media.busy() and ((app.page_loaded and idle > IDLE_EXIT) or (not app.page_loaded and idle > 600)):
            print("The tab was closed, so Cliptrove has stopped.")
            httpd.shutdown()
            return


def running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1) as r:
            return json.load(r).get("app") == PING_NAME
    except Exception:
        return False


def serve(port, background=False, open_browser=True):
    httpd = None
    for p in (port, 0):
        try:
            httpd = Server(("127.0.0.1", p), BaseHTTPRequestHandler)
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit("Couldn't start Cliptrove.")
    app = App(httpd.server_port)
    app.httpd = httpd
    app.background = background
    httpd.RequestHandlerClass = make_handler(app)
    app.start()
    app.media.clean_cache()
    lib = app.library
    print(f"{len(lib.clips)} clips" + (f", {lib.gg_info['clips']} from SteelSeries GG" if lib.gg_enabled() else "")
          + (f", {len(lib.queue)} new files being read" if lib.queue else "") + ".")
    url = f"http://127.0.0.1:{httpd.server_port}/"
    print(f"{APP_NAME}: {url}")
    if not app.media.ffmpeg:
        print("ffmpeg wasn't found, so Chat/Mic audio, thumbnails for folder clips and saving edited copies are off.")
    if not background:  # the background copy keeps running; a window-run one stops when its tab is closed
        print("Keep this window open while you use it. It closes by itself a few minutes after you close the tab.")
        threading.Thread(target=watchdog, args=(app, httpd), daemon=True).start()
        if open_browser:
            import webbrowser
            threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
