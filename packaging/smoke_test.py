"""Start a built Cliptrove.exe on a spare port with an empty data folder, and check that the site works.

    python packaging/smoke_test.py dist/Cliptrove/Cliptrove.exe
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 48711


def get(path, timeout=10):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return r.status, r.read()


def main(exe):
    data = tempfile.mkdtemp(prefix="cliptrove-smoke-")
    proc = subprocess.Popen([exe, "--background", "--port", str(PORT), "--data-dir", data])
    try:
        for _ in range(90):
            try:
                ping = json.loads(get("/api/ping", 2)[1])
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("Cliptrove didn't start")
        assert ping["app"] == "cliptrove", ping
        status, html = get("/", 60)
        page = html.decode("utf-8")
        assert status == 200 and "<title>Cliptrove</title>" in page and "__CLIPTROVE_DATA__" not in page, page[:300]
        for asset in ("/app.js", "/app.css", "/favicon.svg"):
            assert get(asset)[0] == 200, asset
        with open(os.path.join(data, "cliptrove.log"), encoding="utf-8") as f:
            log = f.read()
        assert "Cliptrove" in log, log
        internal = os.path.join(os.path.dirname(exe), "_internal")
        assert os.path.exists(os.path.join(internal, "_tkinter.pyd")), "the folder picker (tkinter) wasn't bundled"
        print("Smoke test passed:", ping)
    finally:
        proc.kill()


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
