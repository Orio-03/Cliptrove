"""The local server: who may use it, how it answers bad requests, the first-start setup, and the library behind it.
These tests use stand-in clip files, so they don't need ffmpeg."""
import json
import os
import time
import unittest
import urllib.error
import urllib.request

import support
from support import Running, fake_clip, folder_settings


def clip_library(tmp):
    """Two games in folders, plus a clip with no game in its name."""
    clips = tmp.sub("clips")
    fake_clip(os.path.join(clips, "Neon Drift", "Neon Drift 2026.01.02 - 20.00.00.01.DVR.mp4"))
    fake_clip(os.path.join(clips, "Neon Drift", "Neon Drift 2026.01.03 - 21.30.00.02.DVR.mp4"))
    fake_clip(os.path.join(clips, "Orbit Arena", "Orbit Arena 2026.02.10 - 19.00.00.01.DVR.mp4"))
    fake_clip(os.path.join(clips, "2026-03-01 10-00-00.mkv"))
    return folder_settings(clips)


class Shared(unittest.TestCase):
    """One running Cliptrove for the whole class."""

    @classmethod
    def setUpClass(cls):
        cls.cs = Running(clip_library)
        cls.data = cls.cs.page()
        cls.clips = {c["file"]: c for c in cls.data["clips"]}

    @classmethod
    def tearDownClass(cls):
        cls.cs.close()

    def clip(self, start):
        return next(c for name, c in self.clips.items() if name.startswith(start))


class Security(Shared):
    def test_the_page_opens_without_the_token(self):
        status, html = self.cs.get("/", token=False)
        self.assertEqual(status, 200)
        self.assertIn(b"<title>Cliptrove</title>", html)
        self.assertNotIn(b"__CLIPTROVE_DATA__", html)

    def test_the_api_needs_the_token(self):
        for path in ("/api/settings", "/api/edited", "/api/analytics", "/api/setup"):
            status, body = self.cs.get_json(path, token=False)
            self.assertEqual(status, 403, path)
            self.assertIn("error", body)

    def test_a_wrong_token_is_refused(self):
        status, _ = self.cs.post("/api/nickname", {"id": "x", "nickname": "y"}, token=False, headers={"X-Token": "nope"})
        self.assertEqual(status, 403)

    def test_the_token_works_in_the_address_too(self):
        status, _ = self.cs.get(f"/api/edited?t={self.cs.app.token}", token=False)
        self.assertEqual(status, 200)

    def test_other_websites_are_refused(self):
        # A request addressed to another host name is what a DNS-rebinding attack looks like
        for path in ("/", "/api/ping", "/app.js"):
            status, _ = self.cs.get(path, token=False, host="evil.example")
            self.assertEqual(status, 403, path)

    def test_static_files(self):
        for path, ctype in (("/app.js", b"javascript"), ("/app.css", b"css"), ("/favicon.svg", b"svg")):
            req = urllib.request.Request(self.cs.base + path)
            with urllib.request.urlopen(req, timeout=30) as r:
                self.assertEqual(r.status, 200)
                self.assertIn(ctype, r.headers["Content-Type"].encode())

    def test_ping(self):
        status, body = self.cs.get_json("/api/ping", token=False)
        self.assertEqual((status, body["app"]), (200, "cliptrove"))


class BadRequests(Shared):
    def test_unknown_addresses(self):
        self.assertEqual(self.cs.get("/nope")[0], 404)
        self.assertEqual(self.cs.post("/api/nope")[0], 404)

    def test_unknown_clips(self):
        for path in ("/media/000000000000", "/thumb/000000000000", "/audio/000000000000/1", "/media/xdeadbeef000"):
            status, body = self.cs.get_json(path)
            self.assertEqual(status, 404, path)
            self.assertIn("error", body)
        status, body = self.cs.post_json("/api/nickname", {"id": "000000000000", "nickname": "x"})
        self.assertEqual(status, 400)
        self.assertIn("isn't in your library", body["error"])

    def test_broken_json(self):
        status, _ = self.cs.post("/api/nickname", raw=b"{not json")
        self.assertEqual(status, 400)

    def test_requests_that_are_too_big(self):
        status, _ = self.cs.post("/api/nickname", raw=b"x" * 70_000)
        self.assertEqual(status, 413)

    def test_a_folder_that_doesnt_exist(self):
        status, body = self.cs.post_json("/api/settings", {"folders": [{"path": self.cs.tmp.sub("missing")}]})
        self.assertEqual(status, 400)
        self.assertIn("Can't find the folder", body["error"])

    def test_a_trim_that_is_too_short(self):
        status, body = self.cs.post_json("/api/trim", {"id": self.clip("Neon Drift 2026.01.02")["id"], "start": 1, "end": 1.1})
        self.assertEqual(status, 400)
        self.assertIn("0.2 seconds", body["error"])

    def test_saving_a_backwards_selection(self):
        status, body = self.cs.post_json("/api/export", {"id": self.clip("Orbit")["id"], "start": 2, "end": 1})
        self.assertEqual(status, 400)
        self.assertIn("error", body)

    def test_showing_a_file_that_isnt_there(self):
        status, body = self.cs.post_json("/api/reveal", {"file": "not-here.mp4"})
        self.assertEqual(status, 400)
        self.assertIn("File not found", body["error"])

    def test_opening_an_unknown_place(self):
        status, _ = self.cs.post_json("/api/open", {"what": "nope"})
        self.assertEqual(status, 400)

    def test_an_unknown_job(self):
        status, body = self.cs.get_json("/api/job/nope")
        self.assertEqual((status, body["state"]), (200, "error"))

    def test_a_clip_that_isnt_a_real_video(self):
        # The stand-in clips are random bytes: asking for their picture is a clean "not found", not a crash
        status, _ = self.cs.get(f"/thumb/{self.clip('Neon Drift 2026.01.03')['id']}")
        self.assertEqual(status, 404)


class Library(Shared):
    def test_games_come_from_names_and_folders(self):
        games = {c["game"] for c in self.data["clips"]}
        self.assertEqual(games, {"Neon Drift", "Orbit Arena", "Unsorted"})
        self.assertEqual(self.clip("Neon Drift 2026.01.02")["recorded"][:16], "2026-01-02T20:00")

    def test_nickname_set_and_cleared(self):
        cid = self.clip("Orbit")["id"]
        status, body = self.cs.post_json("/api/nickname", {"id": cid, "nickname": "  big   play  "})
        self.assertEqual((status, body["nick"]), (200, "big play"))
        self.assertEqual(body["change"]["kind"], "nickname")
        status, body = self.cs.post_json("/api/nickname", {"id": cid, "nickname": ""})
        self.assertEqual(body["nick"], "")

    def test_star(self):
        cid = self.clip("Neon Drift 2026.01.02")["id"]
        self.assertTrue(self.cs.post_json("/api/favorite", {"id": cid, "on": True})[1]["starred"])
        self.assertFalse(self.cs.post_json("/api/favorite", {"id": cid, "on": False})[1]["starred"])

    def test_moving_a_clip_to_a_game_and_back(self):
        cid = self.clip("2026-03-01")["id"]
        status, body = self.cs.post_json("/api/game", {"id": cid, "game": "orbit arena"})
        self.assertEqual((status, body["game"], body["gameSet"]), (200, "Orbit Arena", True))  # matches the known spelling
        status, body = self.cs.post_json("/api/game", {"id": cid, "game": ""})
        self.assertEqual((body["game"], body["gameSet"]), ("Unsorted", False))

    def test_audio_levels_for_tracks_a_clip_doesnt_have_are_ignored(self):
        cid = self.clip("Neon Drift 2026.01.03")["id"]
        tracks = len(self.cs.app.library.clip(cid)[1]["tracks"])
        status, _ = self.cs.post_json("/api/mix", {"id": cid, "tracks": [{"stream": tracks + 5, "vol": 0.5}]})
        self.assertEqual(status, 200)
        self.assertNotIn(self.cs.app.library.ids[cid], self.cs.app.library.state["mix"])

    def test_saved_trim_and_clearing_it(self):
        cid = self.clip("Orbit")["id"]
        status, body = self.cs.post_json("/api/trim", {"id": cid, "start": 0.5, "end": 3})
        self.assertEqual((status, body["trimmed"], body["trimSrc"]), (200, True, "saved"))
        self.assertFalse(self.cs.post_json("/api/trim", {"id": cid, "clear": True})[1]["trimmed"])

    def test_settings_and_analytics_answer(self):
        status, info = self.cs.get_json("/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(info["total"], 4)
        self.assertEqual(info["folders"][0]["clips"], 4)
        status, pred = self.cs.get_json("/api/analytics")
        self.assertEqual(status, 200)
        self.assertFalse(pred["enough"])  # four clips isn't enough history


class Changes(unittest.TestCase):
    """Things that change the files on disk get their own Cliptrove."""

    def setUp(self):
        self.cs = Running(clip_library)

    def tearDown(self):
        self.cs.close()

    def test_a_renamed_clip_keeps_its_nickname(self):
        clips = {c["file"]: c for c in self.cs.page()["clips"]}
        old = next(n for n in clips if n.startswith("Orbit"))
        self.cs.post_json("/api/nickname", {"id": clips[old]["id"], "nickname": "keep me"})
        folder = self.cs.tmp.sub("clips", "Orbit Arena")
        os.replace(os.path.join(folder, old), os.path.join(folder, "Orbit Arena 2026.02.10 - 19.00.00.09.DVR.mp4"))
        self.assertEqual(self.cs.post_json("/api/rescan")[0], 200)
        after = {c["file"]: c for c in self.cs.page()["clips"]}
        self.assertEqual(after["Orbit Arena 2026.02.10 - 19.00.00.09.DVR.mp4"]["nick"], "keep me")

    def test_new_clips_are_picked_up(self):
        before = len(self.cs.page()["clips"])
        fake_clip(self.cs.tmp.sub("clips", "Orbit Arena", "Orbit Arena 2026.02.11 - 19.00.00.01.DVR.mp4"))
        status, body = self.cs.post_json("/api/rescan")
        self.assertEqual((status, body["total"]), (200, before + 1))

    def test_quit(self):
        self.assertEqual(self.cs.post_json("/api/quit")[0], 200)
        for _ in range(40):
            try:
                urllib.request.urlopen(self.cs.base + "/api/ping", timeout=1)
            except (urllib.error.URLError, ConnectionError, OSError):
                return
            time.sleep(0.1)
        self.fail("Cliptrove kept running after Quit")


class BrokenFiles(unittest.TestCase):
    def test_damaged_data_files_dont_stop_it(self):
        def damaged(tmp):
            cfg = clip_library(tmp)
            os.makedirs(support.paths.DATA, exist_ok=True)
            for name in ("library.json", "index.json", "covers.json"):
                with open(os.path.join(support.paths.DATA, name), "w", encoding="utf-8") as f:
                    f.write("{this is not json")
            return cfg
        cs = Running(damaged)
        try:
            self.assertEqual(len(cs.page()["clips"]), 4)
            self.assertEqual(cs.app.library.state["nicknames"], {})
        finally:
            cs.close()

    def test_a_folder_that_went_away(self):
        cs = Running(lambda tmp: folder_settings(tmp.sub("unplugged drive")))
        try:
            self.assertEqual(cs.page()["clips"], [])
            status, info = cs.get_json("/api/settings")
            self.assertEqual(status, 200)
            self.assertFalse(info["folders"][0]["exists"])
        finally:
            cs.close()


class FirstStartSetup(unittest.TestCase):
    def test_setup_shows_until_finished(self):
        cs = Running()  # no settings yet
        try:
            self.assertTrue(cs.page()["meta"]["firstRun"])
            status, info = cs.get_json("/api/setup")
            self.assertEqual(status, 200)
            self.assertTrue({"gg", "found", "ffmpeg", "autostart", "videosDir"} <= set(info))
            # A wrong folder is refused, and setup is still needed
            status, body = cs.post_json("/api/setup", {"gg": False, "folders": [{"path": cs.tmp.sub("nope")}]})
            self.assertEqual(status, 400)
            self.assertTrue(cs.page()["meta"]["firstRun"])
            # A real one finishes it
            clips = clip_library(cs.tmp)["sources"]["folders"][0]["path"]
            status, body = cs.post_json("/api/setup", {"gg": False, "folders": [{"path": clips, "recorder": "nvidia"}]})
            self.assertEqual((status, body["total"]), (200, 4))
            self.assertFalse(cs.page()["meta"]["firstRun"])
            with open(support.paths.SETTINGS, encoding="utf-8") as f:
                saved = json.load(f)
            self.assertTrue(saved["setupDone"])
            self.assertEqual(saved["sources"]["folders"][0]["recorder"], "nvidia")
        finally:
            cs.close()

    def test_skipping_setup(self):
        cs = Running()
        try:
            self.assertEqual(cs.post_json("/api/setup", {"skip": True})[0], 200)
            self.assertFalse(cs.page()["meta"]["firstRun"])
        finally:
            cs.close()

    def test_existing_settings_skip_setup(self):
        cs = Running({"sources": {"gg": {"enabled": False}, "folders": []}})  # saved by an earlier version
        try:
            self.assertFalse(cs.page()["meta"]["firstRun"])
        finally:
            cs.close()


if __name__ == "__main__":
    unittest.main()
