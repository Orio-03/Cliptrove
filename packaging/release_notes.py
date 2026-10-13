"""Print the CHANGELOG.md section for a version (e.g. v0.3.0), used as the GitHub release notes."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(tag):
    version = tag.lstrip("v")
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")
    print(m.group(1).strip())
    print("\n---\n\n**Download** `Cliptrove-" + version + "-windows.zip` below, unzip it and run `Cliptrove.exe`. "
          "[Setup guide](https://github.com/Th30utcast/Cliptrove#get-started)")


if __name__ == "__main__":
    main(sys.argv[1])
