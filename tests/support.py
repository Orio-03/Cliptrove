"""Shared test helpers: a throwaway data folder, fake or real clip files, and a running Cliptrove.

Importing this module makes the whole test run safe on a real PC:
- every test uses temporary folders, never your real Cliptrove data;
- nothing goes online (cover art lookups fail as if offline).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

from cliptrove import covers, paths
from cliptrove.util import NO_WINDOW, find_tool

# The default data folder for the whole test run is a temporary one
SESSION_DATA = tempfile.mkdtemp(prefix="cliptrove-tests-")
paths.configure(SESSION_DATA)


def _offline(url, timeout=6):
    raise OSError("tests don't go online")


covers.fetch_json = _offline

FFMPEG, FFPROBE = find_tool("ffmpeg"), find_tool("ffprobe")
needs_ffmpeg = unittest.skipUnless(FFMPEG and FFPROBE, "needs ffmpeg and ffprobe")


class TempDir:
    """A temporary folder (removed afterwards), and a data folder inside it that Cliptrove uses meanwhile."""

    def __enter__(self):
        self.path = tempfile.mkdtemp(prefix="cliptrove-test-")
        self.old = paths.DATA
        paths.configure(os.path.join(self.path, "data"))
        return self

    def __exit__(self, *exc):
        paths.configure(self.old)
        shutil.rmtree(self.path, ignore_errors=True)

    def sub(self, *parts):
        return os.path.join(self.path, *parts)


def fake_clip(path, size=70_000):
    """A file the folder scanner takes for a clip (a video's name, and big enough), but that isn't a real video."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(size))
    return path


def real_clip(path, seconds=2.0, extra_tracks=1, audio_codec="aac", peak=None):
    """A tiny real video (with 1 + extra_tracks audio tracks) made with ffmpeg. With `peak`, every track plays the
    same tone at that level (1.0 is the most a file can hold), so mixing them adds up."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    args = [FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x180:r=24:d={seconds}"]
    maps = ["-map", "0:v"]
    for i in range(1 + extra_tracks):
        tone = f"aevalsrc={peak}*sin(2*PI*440*t):s=48000:d={seconds}" if peak else f"sine=f={220 + 110 * i}:d={seconds}"
        args += ["-f", "lavfi", "-i", tone]
        maps += ["-map", f"{i + 1}:a"]
    args += maps + ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", audio_codec, path]
    subprocess.run(args, check=True, capture_output=True, creationflags=NO_WINDOW)
    return path


def write_settings(cfg):
    os.makedirs(paths.DATA, exist_ok=True)
    with open(paths.SETTINGS, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def folder_settings(*folders, gg=False, **extra):
    """Settings with SteelSeries GG off (so the tests never read a real GG library) and these clip folders."""
    cfg = {"sources": {"gg": {"enabled": gg}, "folders": [{"path": f, "recorder": "auto"} for f in folders]},
           "setupDone": True}
    cfg.update(extra)
    return cfg


class Running:
    """Cliptrove running on a free port, in its own temporary data folder."""

    def __init__(self, settings=None):
        self.tmp = TempDir().__enter__()
        if settings is not None:
            write_settings(settings(self.tmp) if callable(settings) else settings)
        from cliptrove.server import App, Server, make_handler
        self.httpd = Server(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.app = App(self.httpd.server_port)
        self.app.httpd = self.httpd
        self.httpd.RequestHandlerClass = make_handler(self.app)
        self.app.start()
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def close(self):
        self.app.library.stop()
        self.app.worker.join(timeout=10)
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.__exit__(None, None, None)

    def request(self, method, path, body=None, token=True, host=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Token"] = self.app.token
        if host:
            h["Host"] = host
        h.update(headers or {})
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read()

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def get_json(self, path, **kw):
        status, data = self.get(path, **kw)
        return status, json.loads(data or b"{}")

    def post_json(self, path, body=None, **kw):
        status, data = self.post(path, body, **kw)
        return status, json.loads(data or b"{}")

    def page(self):
        """The data the page starts with."""
        status, html = self.get("/", token=False)
        assert status == 200, status
        blob = re.search(rb'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1)
        return json.loads(blob)
