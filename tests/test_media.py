"""Everything done with ffmpeg, on tiny real videos made for the test (skipped when ffmpeg isn't installed)."""
import array
import os
import subprocess
import time
import unittest

import support
from support import Running, TempDir, folder_settings, needs_ffmpeg, real_clip
from cliptrove import media
from cliptrove.media import Media, share_settings
from cliptrove.util import NO_WINDOW


def peak(path):
    """The loudest moment in a video's audio, where 1.0 is the most a file can hold (above it, it crackles)."""
    raw = subprocess.run([support.FFMPEG, "-v", "error", "-i", path, "-map", "0:a:0", "-f", "f32le", "-"],
                         check=True, capture_output=True, creationflags=NO_WINDOW).stdout
    return max(abs(s) for s in array.array("f", raw))


class ShareSettings(unittest.TestCase):
    def test_longer_clips_get_less_bitrate_and_a_smaller_picture(self):
        last_kbps, last_height = 10 ** 9, 10 ** 9
        for seconds in (5, 15, 30, 60, 120, 300, 900):
            kbps, height = share_settings(seconds)
            self.assertLessEqual(kbps, last_kbps)
            self.assertLessEqual(height, last_height)
            last_kbps, last_height = kbps, height

    def test_there_is_a_floor(self):
        self.assertEqual(share_settings(10_000), (250, 480))
        self.assertEqual(share_settings(0)[1], 1440)  # zero length is treated as one second


class TrackNames(unittest.TestCase):
    def test_which_tag_names_a_track(self):
        self.assertEqual(media.track_title({"title": "Game", "name": "x", "handler_name": "SoundHandler"}), "Game")
        self.assertEqual(media.track_title({"name": "Chat", "handler_name": "SoundHandler"}), "Chat")  # ffmpeg 9, MP4
        self.assertEqual(media.track_title({"handler_name": "SoundHandler"}), "SoundHandler")
        self.assertEqual(media.track_title({}), "")


@needs_ffmpeg
class WithFFmpeg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TempDir().__enter__()
        cls.mp4 = real_clip(cls.tmp.sub("clips", "Game", "Game 2026.01.02 - 20.00.00.01.DVR.mp4"), extra_tracks=1)
        cls.mkv = real_clip(cls.tmp.sub("clips", "2026-01-03 10-00-00.mkv"), extra_tracks=0, audio_codec="pcm_s16le")
        cls.broken = support.fake_clip(cls.tmp.sub("clips", "broken.mp4"))
        cls.m = Media()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def wait(self, jid):
        for _ in range(600):
            job = self.m.jobs[jid]
            if job["state"] != "running":
                return job
            time.sleep(0.1)
        self.fail("export never finished")

    def test_probe(self):
        info = self.m.probe(self.mp4)
        self.assertAlmostEqual(info["duration"], 2.0, delta=0.15)
        self.assertEqual((info["audio"], info["video"], info["ok"]), (2, "h264", True))

    def test_track_names(self):
        # Named tracks in an MP4, the way recorders and ffmpeg write them. ffmpeg 9 reads them back as "name";
        # ffmpeg 6 can't read them back at all (only the generic handler name), so there's nothing to check there.
        path = self.tmp.sub("clips", "named.mp4")
        subprocess.run([support.FFMPEG, "-v", "error", "-y", "-i", self.mp4, "-map", "0", "-c", "copy",
                        "-metadata:s:a:0", "title=Game", "-metadata:s:a:1", "title=Mic", path],
                       check=True, capture_output=True, creationflags=NO_WINDOW)
        titles = self.m.probe(path)["titles"]
        if titles == ["SoundHandler", "SoundHandler"]:
            self.skipTest("this ffmpeg can't read track names back from an MP4")
        self.assertEqual(titles, ["Game", "Mic"])

    def test_probe_of_a_broken_file(self):
        info = self.m.probe(self.broken)
        self.assertFalse(info["ok"])
        self.assertEqual(info["duration"], 0.0)

    def test_thumbnail(self):
        path = self.m.thumbnail("t1", self.mp4)
        with open(path, "rb") as f:
            self.assertEqual(f.read(2), b"\xff\xd8")  # a JPEG
        self.assertEqual(self.m.thumbnail("t1", self.mp4), path)  # made once, then reused

    def test_no_thumbnail_for_a_broken_file(self):
        with self.assertRaises(LookupError):
            self.m.thumbnail("t2", self.broken)

    def test_mp4_plays_as_it_is_and_mkv_is_repackaged(self):
        self.assertEqual(self.m.playable("p1", self.mp4), self.mp4)
        out = self.m.playable("p2", self.mkv)  # PCM audio can't go in an MP4 as it is, so it's converted
        self.assertTrue(out.endswith(".mp4"))
        self.assertTrue(self.m.probe(out)["ok"])

    def test_a_broken_mkv_is_reported(self):
        bad = support.fake_clip(self.tmp.sub("clips", "bad.mkv"))
        with self.assertRaises(RuntimeError):
            self.m.playable("p3", bad)

    def test_extra_audio_tracks(self):
        path = self.m.audio_track("a1", self.mp4, 1)
        self.assertTrue(path.endswith("-1.m4a"))
        self.assertEqual(self.m.probe(path)["audio"], 1)
        with self.assertRaises(LookupError):
            self.m.audio_track("a1", self.mp4, 5)

    def test_saving_a_copy(self):
        out_dir = self.tmp.sub("edits")
        jid = self.m.start_export(self.mp4, out_dir, "copy", None, 0.5, 1.5, [1, 0.5], False, True, False)
        job = self.wait(jid)
        self.assertEqual(job["state"], "done", job)
        info = self.m.probe(os.path.join(out_dir, job["file"]))
        self.assertAlmostEqual(info["duration"], 1.0, delta=0.4)
        self.assertEqual(info["audio"], 1)  # every track mixed into one

    def test_loud_tracks_that_add_up_are_kept_under_the_maximum(self):
        # Game and Mic both peaking at 0.9 at the same moment add up to 1.8
        src = real_clip(self.tmp.sub("clips", "loud.mp4"), peak=0.9)
        out_dir = self.tmp.sub("edits-loud")
        for loud in (False, True):
            with self.subTest(even_out_loudness=loud):
                job = self.wait(self.m.start_export(src, out_dir, "loud", None, 0, 2, [1, 1], False, loud, False))
                self.assertEqual(job["state"], "done", job)
                self.assertLess(peak(os.path.join(out_dir, job["file"])), 0.95)

    def test_quiet_mixes_are_not_made_louder(self):
        src = real_clip(self.tmp.sub("clips", "quiet.mp4"), peak=0.2)
        out_dir = self.tmp.sub("edits-quiet")
        job = self.wait(self.m.start_export(src, out_dir, "quiet", None, 0, 2, [1, 1], False, False, False))
        self.assertEqual(job["state"], "done", job)
        self.assertAlmostEqual(peak(os.path.join(out_dir, job["file"])), 0.4, delta=0.05)

    def test_saving_a_small_copy(self):
        jid = self.m.start_export(self.mp4, self.tmp.sub("edits"), "small", None, 0, 2, [1, 1], False, False, True)
        job = self.wait(jid)
        self.assertEqual(job["state"], "done", job)
        self.assertLess(job["size"], media.SHARE_LIMIT)

    def test_never_overwrites_another_file(self):
        out_dir = self.tmp.sub("edits2")
        first = self.wait(self.m.start_export(self.mp4, out_dir, "same", None, 0, 1, [1], False, False, False))
        second = self.wait(self.m.start_export(self.mp4, out_dir, "same", None, 0, 1, [1], False, False, False))
        self.assertEqual((first["file"], second["file"]), ("same.mp4", "same (2).mp4"))

    def test_bad_selections_are_refused(self):
        for start, end in ((2, 1), (1, 1.1), (-1, 1)):
            with self.assertRaises(ValueError):
                self.m.start_export(self.mp4, self.tmp.sub("edits"), "x", None, start, end, [1], False, False, False)

    def test_a_source_that_vanished_is_reported(self):
        gone = real_clip(self.tmp.sub("clips", "gone.mp4"), seconds=1, extra_tracks=0)
        os.remove(gone)
        with self.assertRaises(LookupError):
            self.m.start_export(gone, self.tmp.sub("edits"), "gone", None, 0, 0.8, [1], False, False, False)
        self.assertFalse(os.path.exists(self.tmp.sub("edits", "gone.mp4.part")))

    def test_clean_cache(self):
        os.makedirs(support.paths.AUDIO, exist_ok=True)
        part = os.path.join(support.paths.AUDIO, "leftover.part")
        old = os.path.join(support.paths.AUDIO, "old.m4a")
        for p in (part, old):
            open(p, "wb").close()
        os.utime(old, (time.time() - 30 * 86400,) * 2)
        self.m.clean_cache()
        self.assertFalse(os.path.exists(part) or os.path.exists(old))


@needs_ffmpeg
class EndToEnd(unittest.TestCase):
    """The same, through the running server, the way the page uses it."""

    def test_real_clip_through_the_server(self):
        def library(tmp):
            real_clip(tmp.sub("clips", "Game", "Game 2026.01.02 - 20.00.00.01.DVR.mp4"), extra_tracks=1)
            return folder_settings(tmp.sub("clips"))
        cs = Running(library)
        try:
            for _ in range(50):  # the new file is read in the background
                clip = cs.page()["clips"][0]
                if clip["full"]:
                    break
                time.sleep(0.1)
            cid = clip["id"]
            self.assertEqual(len(clip["tracks"]), 2)
            self.assertEqual(cs.get(f"/thumb/{cid}")[0], 200)
            status, video = cs.get(f"/media/{cid}", headers={"Range": "bytes=0-99"})
            self.assertEqual((status, len(video)), (206, 100))
            self.assertEqual(cs.get(f"/audio/{cid}/1")[0], 200)
            status, _ = cs.post_json("/api/mix", {"id": cid, "tracks": [{"stream": 1, "vol": 0.4, "muted": False}]})
            self.assertEqual(status, 200)
            self.assertEqual(cs.page()["clips"][0]["tracks"][1]["volume"], 0.4)
            status, body = cs.post_json("/api/export", {"id": cid, "start": 0, "end": 1, "volumes": [1, 0.4], "name": "best"})
            self.assertEqual(status, 200)
            for _ in range(300):
                job = cs.get_json(f"/api/job/{body['job']}")[1]
                if job["state"] != "running":
                    break
                time.sleep(0.1)
            self.assertEqual(job["state"], "done", job)
            edits = cs.get_json("/api/edited")[1]["items"]
            self.assertEqual([(e["title"], e["source"]) for e in edits], [("best", cid)])  # linked to its clip
        finally:
            cs.close()


if __name__ == "__main__":
    unittest.main()
