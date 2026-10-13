"""The README, the docs and the website: every link and picture inside the repo points at something real, and every
version has release notes."""
import os
import re
import subprocess
import sys
import unittest

import support  # noqa: F401
from cliptrove import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = ["README.md", "PRIVACY.md", "SECURITY.md", "CONTRIBUTING.md", "THIRD-PARTY-NOTICES.md", "CHANGELOG.md",
        "docs/HOW-IT-WORKS.md"]
LINK = re.compile(r"\]\(([^)\s]+)\)|(?:src|href)=\"([^\"]+)\"")


def local_targets(text):
    for m in LINK.finditer(text):
        target = m.group(1) or m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", target):
            continue
        yield target.split("#")[0]


class Links(unittest.TestCase):
    def test_docs_point_at_files_that_exist(self):
        for doc in DOCS:
            with open(os.path.join(ROOT, doc), encoding="utf-8") as f:
                text = f.read()
            base = os.path.dirname(os.path.join(ROOT, doc))
            for target in local_targets(text):
                with self.subTest(doc=doc, target=target):
                    self.assertTrue(os.path.exists(os.path.join(base, target)), f"{doc} links to missing {target}")

    def test_website_files_exist(self):
        # The website is put together from site/, docs/images/ and assets/ (see .github/workflows/pages.yml)
        with open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8") as f:
            text = f.read()
        where = {"images/": os.path.join(ROOT, "docs", "images")}
        for target in local_targets(text):
            with self.subTest(target=target):
                if target.startswith("images/"):
                    path = os.path.join(where["images/"], target[len("images/"):])
                elif os.path.exists(os.path.join(ROOT, "site", target)):
                    path = os.path.join(ROOT, "site", target)
                else:
                    path = os.path.join(ROOT, "assets", target)
                self.assertTrue(os.path.exists(path), f"the website uses missing {target}")


class Release(unittest.TestCase):
    def test_this_version_has_release_notes(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "packaging", "release_notes.py"), f"v{__version__}"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.strip())

    def test_license_names_its_owner(self):
        with open(os.path.join(ROOT, "LICENSE.md"), encoding="utf-8") as f:
            self.assertTrue(f.readline().startswith("Required Notice: Copyright"))


if __name__ == "__main__":
    unittest.main()
