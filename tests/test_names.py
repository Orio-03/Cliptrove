"""Run with:  python -m unittest discover tests"""
import datetime as dt
import os
import unittest

from cliptrove.names import game_from_folders, parse_name


def at(*parts):
    return dt.datetime(*parts)


def stamp(*parts):
    return dt.datetime(*parts).timestamp()


class ParseName(unittest.TestCase):
    def check(self, stem, game, when, recorder, title="", near=None):
        p = parse_name(stem, near)
        self.assertEqual((p.game, p.when, p.recorder, p.title), (game, when, recorder, title), stem)

    def test_steelseries_gg(self):
        self.check("Counter-Strike-2__2024-06-16__23-06-36", "Counter Strike 2", at(2024, 6, 16, 23, 6, 36), "gg")
        self.check("Apex-Legends__2025-02-22__18-40-10__clutch 1v3", "Apex Legends", at(2025, 2, 22, 18, 40, 10), "gg",
                   "clutch 1v3")
        self.check("DESKTOPCAPTURE__2025-01-02__03-04-05", "Desktop", at(2025, 1, 2, 3, 4, 5), "gg")

    def test_nvidia(self):
        self.check("Counter-strike 2 2024.06.16 - 23.06.36.02.DVR", "Counter-strike 2", at(2024, 6, 16, 23, 6, 36),
                   "nvidia")
        self.check("Desktop 2023.01.05 - 09.15.00.12", "Desktop", at(2023, 1, 5, 9, 15), "nvidia")

    def test_amd(self):  # real names from an AMD Adrenalin install
        self.check("WARDOGS_replay_2026.09.12-17.41", "WARDOGS", at(2026, 9, 12, 17, 41), "amd")
        self.check("2026.09.10-10.05", None, at(2026, 9, 10, 10, 5), "amd")
        self.check("Rainbow Six Siege_2025.03.01-20.00.15", "Rainbow Six Siege", at(2025, 3, 1, 20, 0, 15), "amd")

    def test_obs(self):
        self.check("2024-06-16 23-06-36", None, at(2024, 6, 16, 23, 6, 36), "obs")
        self.check("Replay 2024-06-16 23-06-36", None, at(2024, 6, 16, 23, 6, 36), "obs")

    def test_xbox_game_bar(self):
        self.check("Halo Infinite 2026-01-31 18-04-12", "Halo Infinite", at(2026, 1, 31, 18, 4, 12), "xbox")
        self.check("Phone Link 7_26_2026 2_14_23 PM", "Phone Link", at(2026, 7, 26, 14, 14, 23), "xbox",
                   near=stamp(2026, 7, 26, 14, 20))
        # Two-digit years: the date order is whatever the PC uses, so the file's own time decides
        self.check("Assassin's Creed Black Flag Resynced 26_08_27 17_21_34", "Assassin's Creed Black Flag Resynced",
                   at(2026, 8, 27, 17, 21, 34), "xbox", near=stamp(2026, 8, 27, 17, 30))
        self.check("Halo 05_03_2025 9_00_00 AM", "Halo", at(2025, 3, 5, 9, 0), "xbox", near=stamp(2025, 3, 5, 9, 2))
        self.check("Halo 05_03_2025 9_00_00 AM", "Halo", at(2025, 5, 3, 9, 0), "xbox", near=stamp(2025, 5, 3, 9, 2))

    def test_fallbacks(self):
        self.check("VID_20240101_123456", None, at(2024, 1, 1, 12, 34, 56), "")
        self.check("Valorant clip 2024-02-03", "Valorant", at(2024, 2, 3), "")
        self.check("ace on mirage", None, None, "", "ace on mirage")
        self.check("12345", None, None, "")


class FolderGame(unittest.TestCase):
    def test_nearest_game_folder(self):
        root = os.path.join("C:\\", "Videos", "Radeon ReLive")
        self.assertEqual(game_from_folders(os.path.join(root, "WARDOGS", "x.mp4"), root), "WARDOGS")
        self.assertIsNone(game_from_folders(os.path.join(root, "x.mp4"), root))
        medal = os.path.join("C:\\", "Medal")
        self.assertEqual(game_from_folders(os.path.join(medal, "Clips", "Valorant", "x.mp4"), medal), "Valorant")
        self.assertIsNone(game_from_folders(os.path.join(medal, "Clips", "x.mp4"), medal))


if __name__ == "__main__":
    unittest.main()
