"""Reading SteelSeries GG's library, from a made-up GG database (never the real one)."""
import json
import os
import sqlite3
import unittest
from unittest import mock

import support
from support import Running, TempDir
from cliptrove.sources import gg

SCHEMA = """
create table moments_clips (name text, path text, last_game_name text, library_game_unique_id text,
    recording_timestamp text, last_user_edit_timestamp text, clip_start_point real, clip_end_point real,
    full_length real, is_manually_trimmed int, thumbnail_path text, tags text, audio_tracks_props text, is_deleted int);
create table moments_settings (key text, value text);
"""
TRACKS = json.dumps([{"name": "Game", "volume": 1.5}, {"name": "Chat", "volume": 0.2}, {"name": "Mic", "muted": True}])


def make_db(path, rows, capture="D:\\Clips"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.executemany("insert into moments_clips values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.execute("insert into moments_settings values ('captureDir', ?)", (capture,))
    con.commit()
    con.close()


ROWS = [
    # name, path, game, uid, recorded, edited, start, end, full, trimmed, thumb, tags, tracks, deleted
    ("Ace on Mirage", "D:\\Clips\\CS2__2026-01-02__20-00-00.mp4", "Counter-Strike 2", "1_730", "2026-01-02T20:00:00+01:00",
     None, 2.0, 8.0, 30.0, 1, "D:\\thumb1.jpg", json.dumps([{"type": 2}]), TRACKS, 0),
    ("Moments clip from Jan 03, 2026", "D:\\Clips\\Desk__2026-01-03__10-00-00.mp4", "moments.desktopModeGameName", "",
     "2026-01-03T10:00:00+01:00", None, 0, 0, 12.0, 0, None, "not json", "not json either", 0),
    ("Deleted one", "D:\\Clips\\gone.mp4", "Gone", "1_1", "2026-01-04T10:00:00+01:00", None, 0, 0, 5, 0, None, "[]", "[]", 1),
]


class Read(unittest.TestCase):
    def setUp(self):
        self.tmp = TempDir().__enter__()
        self.db = self.tmp.sub("gg", "database.db")
        make_db(self.db, ROWS)
        self.patch = mock.patch.object(gg, "DB", self.db)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.__exit__(None, None, None)

    def test_clips_titles_stars_trims_and_levels(self):
        clips, folder = gg.read()
        self.assertEqual(folder, "D:\\Clips")
        self.assertEqual(len(clips), 2)  # the deleted one is left out
        by_title = {c["title"]: c for c in clips.values()}
        ace = by_title["Ace on Mirage"]
        self.assertTrue(ace["custom"])
        self.assertTrue(ace["ggStar"])
        self.assertEqual(ace["baseTrim"], [2.0, 8.0])
        self.assertEqual([t["name"] for t in ace["tracks"]], ["Game", "Chat", "Mic"])
        self.assertEqual(ace["tracks"][0]["volume"], 1.5)
        self.assertTrue(ace["tracks"][2]["muted"])

    def test_gg_made_up_titles_desktop_and_broken_fields(self):
        clips, _ = gg.read()
        desk = next(c for c in clips.values() if c["game"] == "Desktop")  # GG's internal name is translated
        self.assertFalse(desk["custom"])
        self.assertFalse(desk["ggStar"])  # unreadable tags: not starred
        self.assertEqual(desk["tracks"], [{"name": "Game", "volume": 1.0, "muted": False}])  # unreadable levels
        self.assertIsNone(desk["baseTrim"])

    def test_stamp_changes_when_gg_writes(self):
        before = gg.stamp()
        con = sqlite3.connect(self.db)
        con.execute("insert into moments_settings values ('x', 'y')")
        con.commit()
        con.close()
        os.utime(self.db, (1e9, 1e9))
        self.assertNotEqual(before, gg.stamp())

    def test_if_gg_changes_its_format_reading_fails_cleanly(self):
        con = sqlite3.connect(self.db)
        con.execute("alter table moments_clips rename to something_else")
        con.commit()
        con.close()
        with self.assertRaises(sqlite3.Error):
            gg.read()

    def test_not_installed(self):
        with mock.patch.object(gg, "DB", self.tmp.sub("nowhere", "database.db")):
            self.assertFalse(gg.installed())


class TitlesWeMadeUp(unittest.TestCase):
    def test_which_titles_count_as_yours(self):
        for title in ("Moments clip from Jan 3, 2026", "Trimmed clip from Oct 12, 2026",
                      "Montage created Feb 1, 2025", "Auto-clip: Kill", ""):
            self.assertFalse(gg.is_custom(title), title)
        for title in ("Ace on Mirage", "Moments clip from my birthday"):
            self.assertTrue(gg.is_custom(title), title)


class LibraryWithGG(unittest.TestCase):
    def test_a_gg_hiccup_keeps_the_clips_already_shown(self):
        tmp_db = os.path.join(support.SESSION_DATA, "gg-hiccup", "database.db")
        if os.path.exists(tmp_db):
            os.remove(tmp_db)
        make_db(tmp_db, ROWS)
        with mock.patch.object(gg, "DB", tmp_db):
            cs = Running({"sources": {"gg": {"enabled": True}, "folders": []}, "setupDone": True})
            try:
                self.assertEqual(len(cs.page()["clips"]), 2)
                con = sqlite3.connect(tmp_db)
                con.execute("drop table moments_clips")
                con.commit()
                con.close()
                self.assertEqual(len(cs.page()["clips"]), 2)  # still there
                info = cs.get_json("/api/settings")[1]
                self.assertTrue(info["gg"]["error"])
                # A GG title change is logged, and only for clips you titled
                self.assertEqual(cs.page()["changes"], [])
            finally:
                cs.close()


if __name__ == "__main__":
    unittest.main()
