import json
import os
import shutil
import tempfile
import unittest

from cliptrove import paths, settings


class FirstStart(unittest.TestCase):
    def setUp(self):
        self.old = paths.DATA
        self.dir = tempfile.mkdtemp()
        paths.configure(self.dir)

    def tearDown(self):
        paths.configure(self.old)
        shutil.rmtree(self.dir, ignore_errors=True)

    def write(self, cfg):
        with open(paths.SETTINGS, "w", encoding="utf-8") as f:
            json.dump(cfg, f)

    def test_no_settings_yet_means_setup(self):
        self.assertFalse(os.path.exists(paths.SETTINGS))
        self.assertFalse(settings.load()["setupDone"])

    def test_settings_from_before_setup_existed_count_as_done(self):
        self.write({"sources": {"gg": {"enabled": True}, "folders": []}})
        self.assertTrue(settings.load()["setupDone"])

    def test_setup_is_shown_once(self):
        cfg = settings.load()
        self.assertFalse(cfg["setupDone"])
        settings.save(dict(cfg, setupDone=True))  # finished or skipped
        self.assertTrue(settings.load()["setupDone"])

    def test_a_broken_settings_file_starts_over(self):
        with open(paths.SETTINGS, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertFalse(settings.load()["setupDone"])


if __name__ == "__main__":
    unittest.main()
