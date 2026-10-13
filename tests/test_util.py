"""Small helpers, cover art (offline), the move from the old data folder, and Start with Windows."""
import os
import sys
import unittest
from unittest import mock

import support  # noqa: F401  (keeps the test run in temporary folders)
from support import TempDir
from cliptrove import autostart, covers, paths, util


class Helpers(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(util.norm("Counter-Strike 2"), util.norm("counter strike 2"))
        self.assertEqual(util.norm(None), "")

    def test_safe_name(self):
        self.assertEqual(util.safe_name('  a<b>c:"d/e\\f|g?h*  '), "abcdefgh")
        self.assertEqual(util.safe_name("name..."), "name")
        self.assertEqual(len(util.safe_name("x" * 500)), 100)
        self.assertEqual(util.safe_name(None), "")

    def test_is_inside(self):
        with TempDir() as t:
            self.assertTrue(util.is_inside(t.sub("a", "b"), t.path))
            self.assertFalse(util.is_inside(t.path, t.sub("a")))
        if os.name == "nt":
            self.assertFalse(util.is_inside("D:\\x", "C:\\"))  # different drives

    def test_load_json_survives_missing_and_broken_files(self):
        with TempDir() as t:
            self.assertEqual(util.load_json(t.sub("missing.json"), {"d": 1}), {"d": 1})
            with open(t.sub("bad.json"), "w") as f:
                f.write("{nope")
            self.assertEqual(util.load_json(t.sub("bad.json"), []), [])

    def test_save_json_writes_the_whole_file(self):
        with TempDir() as t:
            util.save_json(t.sub("deep", "x.json"), {"a": [1, 2]}, indent=1)
            self.assertEqual(util.load_json(t.sub("deep", "x.json"), None), {"a": [1, 2]})
            self.assertEqual(os.listdir(t.sub("deep")), ["x.json"])  # no leftover temporary file

    def test_retry_io(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("in use")
            return "ok"
        with mock.patch("time.sleep"):
            self.assertEqual(util.retry_io(flaky), "ok")
            with self.assertRaises(PermissionError):
                util.retry_io(lambda: (_ for _ in ()).throw(PermissionError("always")), tries=3)

    def test_iso_time(self):
        self.assertRegex(util.iso_time(1_760_000_000), r"^2025-10-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")


class CoverArt(unittest.TestCase):
    def test_offline_falls_back_and_waits_before_trying_again(self):
        calls = []

        def offline(url, timeout=6):
            calls.append(url)
            raise OSError("offline")
        with TempDir(), mock.patch.object(covers, "fetch_json", offline):
            clips = {"a": {"game": "Some Game", "uid": ""}, "b": {"game": "Desktop", "uid": ""}}
            self.assertEqual(covers.resolve(clips), {})
            self.assertEqual(len(calls), 1)  # Desktop isn't looked up
            covers.resolve(clips)
            self.assertEqual(len(calls), 1)  # not again for a while
            self.assertIn("failed", util.load_json(paths.COVER_CACHE, {}))

    def test_found_on_steam(self):
        def steam(url, timeout=6):
            if "storesearch" in url:
                return {"items": [{"id": 42, "name": "Some Game"}]}
            return {"response": {"store_items": [{"appid": 42, "assets": {
                "asset_url_format": "steam/apps/42/${FILENAME}", "library_capsule": "cap.jpg"}}]}}
        with TempDir(), mock.patch.object(covers, "fetch_json", steam):
            found = covers.resolve({"a": {"game": "some game", "uid": ""}})
            self.assertEqual(found, {"somegame": covers.STEAM_ASSETS + "steam/apps/42/cap.jpg"})
            self.assertEqual(covers.known_names(), {"somegame": "Some Game"})

    def test_your_own_covers(self):
        with TempDir():
            os.makedirs(paths.COVERS_DIR)
            for name in ("VALORANT.jpg", "notes.txt"):
                open(os.path.join(paths.COVERS_DIR, name), "w").close()
            self.assertEqual(list(covers.custom_covers()), ["valorant"])


class OldDataFolder(unittest.TestCase):
    def test_data_from_the_old_name_moves_over_once(self):
        with TempDir() as t, mock.patch.dict(os.environ, {"CLIPTROVE_DATA": ""}):
            paths.configure(t.sub("Cliptrove"))
            os.makedirs(t.sub("ClipShelf"))
            open(t.sub("ClipShelf", "library.json"), "w").close()
            self.assertEqual(paths.adopt_legacy(), t.sub("ClipShelf"))
            self.assertTrue(os.path.exists(t.sub("Cliptrove", "library.json")))
            self.assertIsNone(paths.adopt_legacy())  # nothing left to move

    def test_nothing_moves_when_a_data_folder_is_chosen(self):
        with TempDir() as t, mock.patch.dict(os.environ, {"CLIPTROVE_DATA": t.sub("custom")}):
            paths.configure(t.sub("Cliptrove"))
            os.makedirs(t.sub("ClipShelf"))
            self.assertIsNone(paths.adopt_legacy())


class StartWithWindows(unittest.TestCase):
    def test_the_app_starts_itself_when_it_is_an_exe(self):
        with mock.patch.object(autostart, "FROZEN", True), mock.patch.object(sys, "executable", "C:\\Apps\\Cliptrove.exe"):
            self.assertEqual(autostart.launcher(), ("C:\\Apps\\Cliptrove.exe", "--background"))

    @unittest.skipUnless(sys.platform == "win32", "Windows only")
    def test_shortcut_made_and_removed_and_old_one_replaced(self):
        with TempDir() as t:
            link, old = t.sub("Cliptrove.lnk"), t.sub("ClipShelf.lnk")
            open(old, "w").close()
            with mock.patch.multiple(autostart, STARTUP=t.path, LINK=link, LEGACY_LINKS=[old]):
                autostart.enable()
                self.assertTrue(autostart.enabled())
                self.assertFalse(os.path.exists(old))
                autostart.disable()
                self.assertFalse(autostart.enabled())

    @unittest.skipIf(sys.platform == "win32", "not on Windows")
    def test_not_offered_elsewhere(self):
        self.assertFalse(autostart.supported())
        with self.assertRaises(RuntimeError):
            autostart.enable()


if __name__ == "__main__":
    unittest.main()
