"""Build the Windows app: dist/Cliptrove/Cliptrove.exe, zipped as dist/Cliptrove-<version>-windows.zip.

Needs PyInstaller:  python -m pip install -r packaging/requirements-build.txt
GitHub builds this for every release (see .github/workflows/release.yml), so you only need it to test a build.
"""
import glob
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from cliptrove import __version__  # noqa: E402

QUICK_START = """Cliptrove {version}
==================

1. Double-click Cliptrove.exe. Your browser opens at http://127.0.0.1:48650
   (Windows may say it "protected your PC" the first time: click "More info", then "Run anyway").
2. Click the gear (Settings) and add the folders your recorder saves clips to.
3. Optional: turn on "Start with Windows" in Settings.

Thumbnails, extra audio tracks and saving edited copies need ffmpeg:
open PowerShell and run   winget install Gyan.FFmpeg   then restart Cliptrove.

Keep all the files in this folder together. Full guide: https://github.com/Orio-03/Cliptrove
"""


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
