"""Build the Windows app: dist/Cliptrove/Cliptrove.exe, zipped as dist/Cliptrove-<version>-windows.zip.
It comes with ffmpeg (the build pinned in packaging/ffmpeg.json), so editing works straight away.

Needs PyInstaller:  python -m pip install -r packaging/requirements-build.txt
GitHub builds this for every release (see .github/workflows/release.yml), so you only need it to test a build.
"""
import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from cliptrove import __version__  # noqa: E402

with open(os.path.join(HERE, "ffmpeg.json"), encoding="utf-8") as _f:
    FFMPEG = json.load(_f)
CACHE = os.path.join(HERE, ".cache")

QUICK_START = """Cliptrove {version}
==================

1. Double-click Cliptrove.exe. Your browser opens at http://127.0.0.1:48650
   (Windows may say it "protected your PC" the first time: click "More info", then "Run anyway").
2. Click the gear (Settings) and add the folders your recorder saves clips to.
3. Optional: turn on "Start with Windows" in Settings.

ffmpeg (for thumbnails, Chat/Mic audio, waveforms and saving edited copies) is included,
in the "ffmpeg" folder. Its license and where to get its source code are in "licenses".

Keep all the files in this folder together. Full guide: https://github.com/Orio-03/Cliptrove
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_ffmpeg():
    """The pinned ffmpeg zip, downloaded once into packaging/.cache and checked against its checksum."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, os.path.basename(FFMPEG["url"]))
    if os.path.exists(path) and sha256(path) == FFMPEG["sha256"]:
        return path
    print("Downloading", FFMPEG["url"])
    part = path + ".part"
    urllib.request.urlretrieve(FFMPEG["url"], part)
    if sha256(part) != FFMPEG["sha256"]:
        os.remove(part)
        raise SystemExit("The ffmpeg download doesn't match the checksum in packaging/ffmpeg.json")
    os.replace(part, path)
    return path


def bundle_ffmpeg(app):
    """ffmpeg.exe, ffprobe.exe and their libraries into app/ffmpeg (not ffplay: Cliptrove doesn't use it),
    with ffmpeg's license and where its source code is."""
    dest = os.path.join(app, "ffmpeg")
    os.makedirs(dest, exist_ok=True)
    os.makedirs(os.path.join(app, "licenses"), exist_ok=True)
    with zipfile.ZipFile(fetch_ffmpeg()) as z:
        for name in z.namelist():
            base = os.path.basename(name)  # (only plain file names: nothing can land outside dest)
            if "/bin/" in name and base.lower().endswith((".exe", ".dll")) and base.lower() != "ffplay.exe":
                target = os.path.join(dest, base)
            elif base == "LICENSE.txt":
                target = os.path.join(app, "licenses", "FFmpeg-LICENSE.txt")
            else:
                continue
            with z.open(name) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        if not os.path.exists(os.path.join(dest, exe)):
            raise SystemExit(f"{exe} wasn't in the ffmpeg zip")
    # The LGPL version 3 builds on the GPL version 3, so a copy of that goes with it
    shutil.copy2(os.path.join(HERE, "licenses", "GPL-3.0.txt"), os.path.join(app, "licenses", "GPL-3.0.txt"))
    with open(os.path.join(app, "licenses", "FFmpeg-SOURCE.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(f"The ffmpeg folder holds FFmpeg {FFMPEG['version']} (https://ffmpeg.org), built by BtbN's FFmpeg-Builds\n"
                f"under the GNU Lesser General Public License (LGPL), version 3 or later: see FFmpeg-LICENSE.txt\n"
                f"(and GPL-3.0.txt, which it builds on).\n\n"
                f"The build: {FFMPEG['url']}\nIts source code: {FFMPEG['source']}\n"
                f"How it was built: {FFMPEG['build_scripts']}\n\n"
                f"Cliptrove runs ffmpeg.exe and ffprobe.exe as separate programs. You can replace the files in the\n"
                f"ffmpeg folder with another build of FFmpeg.\n")


def main():
    dist, build = os.path.join(ROOT, "dist"), os.path.join(ROOT, "build")
    shutil.rmtree(dist, ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "Cliptrove",
        "--icon", os.path.join(ROOT, "assets", "cliptrove.ico"),
        "--add-data", os.path.join(ROOT, "cliptrove", "web") + os.pathsep + "cliptrove/web",
        "--distpath", dist, "--workpath", build, "--specpath", build,
        os.path.join(ROOT, "Cliptrove.pyw"),
    ], check=True)

    app = os.path.join(dist, "Cliptrove")
    bundle_ffmpeg(app)
    for name in ("LICENSE.md", "THIRD-PARTY-NOTICES.md", "PRIVACY.md"):
        shutil.copy2(os.path.join(ROOT, name), app)
    # Python and Tcl/Tk (the folder picker) are bundled, under their own licenses
    os.makedirs(os.path.join(app, "licenses"), exist_ok=True)
    found = [(os.path.join(sys.base_prefix, "LICENSE.txt"), "Python-LICENSE.txt")]
    found += [(p, "Tcl-Tk-license.terms") for p in glob.glob(os.path.join(sys.base_prefix, "tcl", "tk*", "license.terms"))[:1]]
    for src, name in found:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(app, "licenses", name))
    with open(os.path.join(app, "Read me.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(QUICK_START.format(version=__version__))

    out = os.path.join(dist, f"Cliptrove-{__version__}-windows.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for folder, _, files in os.walk(app):
            for name in files:
                path = os.path.join(folder, name)
                z.write(path, os.path.join("Cliptrove", os.path.relpath(path, app)))
    print(f"Built {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
