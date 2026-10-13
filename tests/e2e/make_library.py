"""Makes a small clip library for the browser test: three made-up games, a few months of clips, named the way NVIDIA
names them. Needs ffmpeg.

    python tests/e2e/make_library.py <folder>
"""
import datetime as dt
import os
import shutil
import subprocess
import sys

GAMES = {"Neon Drift": 6, "Orbit Arena": 5, "Pixel Rally": 3}


def main(root):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg isn't installed")
    first = dt.datetime.now().replace(microsecond=0) - dt.timedelta(days=80)
    n = 0
    for g, (game, count) in enumerate(GAMES.items()):
        folder = os.path.join(root, game)
        os.makedirs(folder, exist_ok=True)
        for i in range(count):
            when = first + dt.timedelta(days=i * 9 + g * 3, hours=g)
            name = f"{game} {when:%Y.%m.%d - %H.%M.%S}.{i + 1:02d}.DVR.mp4"
            subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=24:d=3",
                            "-f", "lavfi", "-i", "sine=f=220:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3",
                            "-map", "0:v", "-map", "1:a", "-map", "2:a", "-c:v", "libx264", "-preset", "ultrafast",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", os.path.join(folder, name)], check=True)
            n += 1
    print(f"{n} clips in {root}")


if __name__ == "__main__":
    main(sys.argv[1])
