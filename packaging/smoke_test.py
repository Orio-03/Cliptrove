"""Start a built Cliptrove.exe on a spare port and check that it works, including the ffmpeg it comes with:
it reads a test clip made with that ffmpeg, draws its waveforms, saves a still, and saves a portrait copy.

    python packaging/smoke_test.py dist/Cliptrove/Cliptrove.exe
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 48711


def call(path, body=None, token="", timeout=60):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "X-Token": token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def page_data():
    html = call("/", timeout=60)[1].decode("utf-8")
    return html, json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1))


def run(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"{args[0]} failed: {r.stderr.strip()[-500:]}")
    return r.stdout


def main(exe):
    app_dir = os.path.dirname(exe)
    ffmpeg, ffprobe = (os.path.join(app_dir, "ffmpeg", n) for n in ("ffmpeg.exe", "ffprobe.exe"))
    for tool in (ffmpeg, ffprobe):
        assert os.path.isfile(tool), f"{tool} wasn't bundled"
    print(run(ffmpeg, "-hide_banner", "-version").splitlines()[0])
    encoders = [line.split()[1] for line in run(ffmpeg, "-hide_banner", "-encoders").splitlines()
                if " h264" in line or "openh264" in line]
    print("H.264 encoders in the bundled ffmpeg:", ", ".join(encoders))
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cliptrove.media import FILTERS
    have = {line.split()[1] for line in run(ffmpeg, "-hide_banner", "-filters").splitlines()[1:] if len(line.split()) > 2}
    missing = [f for f in FILTERS if f not in have]
    assert not missing, f"the bundled ffmpeg lacks filters Cliptrove uses: {missing}"
    for lic in ("FFmpeg-LICENSE.txt", "FFmpeg-SOURCE.txt", "GPL-3.0.txt"):
        assert os.path.isfile(os.path.join(app_dir, "licenses", lic)), f"{lic} is missing"

    # A short clip with Game and Mic tracks, made with the bundled ffmpeg (OpenH264 is in every LGPL build)
    work = tempfile.mkdtemp(prefix="cliptrove-smoke-")
    data, clips, edits = (os.path.join(work, n) for n in ("data", "clips", "edits"))
    os.makedirs(os.path.join(clips, "Game"))
    os.makedirs(data)
    clip = os.path.join(clips, "Game", "Game 2026.01.02 - 20.00.00.01.DVR.mp4")
    run(ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4",
        "-f", "lavfi", "-i", "sine=f=330:d=4", "-f", "lavfi", "-i", "sine=f=660:d=4",
        "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libopenh264", "-b:v", "2M", "-pix_fmt", "yuv420p",
        "-c:a", "aac", clip)
    with open(os.path.join(data, "settings.json"), "w", encoding="utf-8") as f:
        json.dump({"sources": {"gg": {"enabled": False}, "folders": [{"path": clips, "recorder": "auto"}]},
                   "exportDir": edits, "setupDone": True}, f)

    proc = subprocess.Popen([exe, "--background", "--port", str(PORT), "--data-dir", data])
    try:
        for _ in range(90):
            try:
                ping = json.loads(call("/api/ping", timeout=2)[1])
                break
            except OSError:
                time.sleep(1)
        else:
            raise SystemExit("Cliptrove didn't start")
        assert ping["app"] == "cliptrove", ping
        html, d = page_data()
        assert "<title>Cliptrove</title>" in html and "__CLIPTROVE_DATA__" not in html, html[:300]
        for asset in ("/app.js", "/app.css", "/favicon.svg"):
            assert call(asset)[0] == 200, asset
        token = d["meta"]["token"]
        assert d["meta"]["ffmpeg"], "Cliptrove didn't find ffmpeg"
        settings = json.loads(call("/api/settings", token=token)[1])
        assert os.path.normcase(settings["ffmpeg"]) == os.path.normcase(ffmpeg), settings["ffmpeg"]
        internal = os.path.join(app_dir, "_internal")
        assert os.path.exists(os.path.join(internal, "_tkinter.pyd")), "the folder picker (tkinter) wasn't bundled"

        for _ in range(60):  # the clip is read in the background
            clip_info = next(iter(page_data()[1]["clips"]), None)
            if clip_info and clip_info["full"]:
                break
            time.sleep(1)
        else:
            raise SystemExit("The test clip wasn't read")
        cid = clip_info["id"]
        assert len(clip_info["tracks"]) == 2, clip_info["tracks"]
        assert call(f"/thumb/{cid}?t={token}")[0] == 200
        waves = json.loads(call(f"/api/waves/{cid}", token=token)[1])
        assert len(waves["tracks"]) == 2 and max(waves["tracks"][0]) > 150, "waveforms look wrong"
        still = json.loads(call("/api/still", {"id": cid, "at": 1.5}, token=token)[1])
        assert os.path.getsize(os.path.join(edits, still["file"])) > 1000, still
        job = json.loads(call("/api/export", {"id": cid, "start": 0.5, "end": 3.5, "volumes": [1, 0.5], "name": "smoke",
                                              "shape": "portrait", "fit": "blur", "fade": True}, token=token)[1])["job"]
        for _ in range(240):
            state = json.loads(call(f"/api/job/{job}", token=token)[1])
            if state["state"] != "running":
                break
            time.sleep(0.5)
        assert state["state"] == "done", state
        out = os.path.join(edits, state["file"])
        dims = run(ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height",
                   "-of", "csv=p=0", out).strip()
        assert dims == "h264,1080,1920", dims
        with open(os.path.join(data, "cliptrove.log"), encoding="utf-8") as f:
            log = f.read()
        assert "Cliptrove" in log, log
        print("Smoke test passed:", ping, "| portrait copy:", dims, "| still:", still["file"])
    finally:
        proc.kill()


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
