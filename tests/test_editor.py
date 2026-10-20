"""The editing tools: waveforms, portrait copies, fades, stills, copying to the clipboard, and the ffmpeg that
comes with the Windows app."""
import array
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

import support
from support import Running, TempDir, folder_settings, needs_ffmpeg, real_clip
from cliptrove import clipboard, media, util
from cliptrove.library import TAGS
from cliptrove.media import Media, peak, portrait_graph
from cliptrove.util import NO_WINDOW


def ffmpeg_out(*args):
    return subprocess.run([support.FFMPEG, "-v", "error", *args], check=True, capture_output=True,
                          creationflags=NO_WINDOW).stdout


def brightness(path, at=0.0):
    """Average brightness (0-255) of the picture at `at` seconds."""
    return ffmpeg_out("-ss", str(at), "-i", path, "-frames:v", "1", "-vf", "scale=1:1,format=gray", "-f", "rawvideo", "-")[0]


def loudest(path, start, length):
    """The loudest sample (0-1) in part of a video's audio."""
    raw = ffmpeg_out("-ss", str(start), "-t", str(length), "-i", path, "-ac", "1", "-f", "s16le", "-")
    samples = array.array("h", raw)
    return max((abs(s) for s in samples), default=0) / 32767


class Pieces(unittest.TestCase):
    """The parts that don't need ffmpeg."""

    def test_peak(self):
        self.assertEqual(peak(array.array("h", [0, 100, -32767, 5])), 255)  # full scale
        self.assertEqual(peak(array.array("h", [16384, -10])), 229)  # half: 6 dB down, of the 60 shown
        self.assertEqual(peak(array.array("h", [33, -2])), 0)  # 60 dB down: the floor
        self.assertEqual(peak(array.array("h", [0, 0])), 0)
        self.assertEqual(peak(array.array("h")), 0)

    def test_portrait_filters(self):
        crop = portrait_graph("crop", 0.25, 1080)
        self.assertIn("crop=w='min(iw,ih*9/16)'", crop)
        self.assertIn("*0.2500", crop)
        self.assertTrue(crop.endswith("scale=1080:1920,setsar=1[v]"))
        blur = portrait_graph("blur", 0.5, 719, ["fps=30"])
        self.assertIn("gblur", blur)
        self.assertIn("overlay=(W-w)/2:(H-h)/2,fps=30,setsar=1[v]", blur)
        self.assertIn("scale=718:1276", blur)  # sizes are always even, as video encoders need

    def test_tags_on_saved_copies(self):
        for name in ("x__edit (vertical) (18MB)", "x__edit (18MB)", "x__edit (vertical)", "x__edit"):
            self.assertEqual(TAGS.sub("", name), "x__edit")
        self.assertEqual(TAGS.sub("", "a (vertical) b"), "a (vertical) b")

    def test_unknown_shape_is_refused(self):
        m = Media()
        m.ffmpeg = "ffmpeg"
        with TempDir() as tmp:
            src = support.fake_clip(tmp.sub("a.mp4"))
            for shape, fit in (("square", "crop"), ("portrait", "stretch")):
                with self.assertRaises(ValueError):
                    m.start_export(src, tmp.sub("out"), "x", None, 0, 1, [1], False, False, False, shape=shape, fit=fit)


class Encoders(unittest.TestCase):
    def test_the_first_encoder_that_works_is_used(self):
        m = Media()
        m.ffmpeg = "ffmpeg"
        works = {"h264_mf"}
        with mock.patch.object(media, "run", side_effect=lambda args, **kw: mock.Mock(
                returncode=0 if args[args.index("-c:v") + 1] in works else 1)):
            self.assertEqual(m.video_encoder()[1], "h264_mf")  # e.g. the bundled ffmpeg on a PC without a GPU encoder
        self.assertEqual(m.rate_encoder(900)[:2], ["-c:v", "h264_mf"])
        m.encoder = None
        with mock.patch.object(media, "run", return_value=mock.Mock(returncode=1)):
            with self.assertRaises(RuntimeError):
                m.video_encoder()

    def test_bitrate_settings_for_each_encoder(self):
        m = Media()
        for enc in media.ENCODERS:
            m.encoder = enc
            args = m.rate_encoder(1500)
            self.assertEqual(args[1], enc[1])
            self.assertIn("1500k", args)


class BundledFFmpeg(unittest.TestCase):
    def test_the_windows_app_uses_its_own_ffmpeg_first(self):
        with TempDir() as tmp:
            exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
            tools = tmp.sub("Cliptrove", "ffmpeg")
            os.makedirs(tools)
            open(os.path.join(tools, exe), "wb").close()
            with mock.patch.object(sys, "frozen", True, create=True), \
                    mock.patch.object(sys, "executable", tmp.sub("Cliptrove", "Cliptrove.exe")):
                self.assertEqual(util.find_tool("ffmpeg"), os.path.join(tools, exe))
            self.assertIsNone(util.bundled_tools_dir())  # running from the source code


class Clipboard(unittest.TestCase):
    def test_file_list_format(self):
        data = clipboard.dropfiles([r"C:\a.mp4", r"D:\b c.png"])
        self.assertEqual(data[:20], b"\x14\x00\x00\x00" + b"\x00" * 12 + b"\x01\x00\x00\x00")
        self.assertEqual(data[20:].decode("utf-16-le"), "C:\\a.mp4\0D:\\b c.png\0\0")

    def test_only_on_windows(self):
        with mock.patch.object(clipboard.sys, "platform", "linux"):
            self.assertFalse(clipboard.supported())
            with self.assertRaises(ValueError):
                clipboard.copy_files(["/tmp/a.mp4"])

    @unittest.skipUnless(sys.platform == "win32" and os.environ.get("CI"), "replaces the clipboard: only on CI")
    def test_round_trip(self):
        with TempDir() as tmp:
            path = tmp.sub("clip with spaces.mp4")
            open(path, "wb").close()
            try:
                clipboard.copy_files([path])
                self.assertEqual(clipboard.copied_files(), [path])
            except (RuntimeError, OSError) as e:
                self.skipTest(f"no clipboard here: {e}")


@needs_ffmpeg
class WithFFmpeg(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TempDir().__enter__()
        cls.clip = real_clip(cls.tmp.sub("clips", "Game 2026.01.02 - 20.00.00.01.DVR.mp4"), seconds=3, peak=0.5)
        cls.m = Media()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.__exit__(None, None, None)

    def export(self, name, **look):
        out_dir = self.tmp.sub("edits")
        small = look.pop("small", False)
        jid = self.m.start_export(self.clip, out_dir, name, None, 0, 3, [1, 1], False, False, small, **look)
        for _ in range(900):
            job = self.m.jobs[jid]
            if job["state"] != "running":
                break
            time.sleep(0.1)
        self.assertEqual(job["state"], "done", job)
        return os.path.join(out_dir, job["file"])

    def test_waveforms(self):
        w = self.m.waves("w1", self.clip)
        self.assertEqual(len(w["tracks"]), 2)
        for track in w["tracks"]:
            self.assertAlmostEqual(len(track) * w["step"], 3.0, delta=0.15)  # covers the whole clip
            self.assertLess(abs(sorted(track)[len(track) // 2] - 229), 8)  # the test tone is at half volume (-6 dB)
        self.assertEqual(self.m.waves("w1", self.clip), w)  # cached
        self.assertEqual(len([n for n in os.listdir(support.paths.WAVES) if n.startswith("w1-")]), 1)  # no leftovers
        self.assertEqual(w["floor"], media.WAVE_FLOOR)

    def test_portrait_crop(self):
        out = self.export("crop", shape="portrait", fit="crop", crop_x=0)
        info = self.m.probe(out)
        self.assertEqual((info["width"], info["height"]), (1080, 1920))
        self.assertAlmostEqual(info["duration"], 3.0, delta=0.3)

    def test_portrait_blurred_background_compressed(self):
        out = self.export("blur", shape="portrait", fit="blur", small=True)
        info = self.m.probe(out)
        self.assertAlmostEqual(info["width"] / info["height"], 9 / 16, delta=0.01)
        self.assertLessEqual(os.path.getsize(out), media.SHARE_LIMIT)

    def test_fades(self):
        plain, faded = self.export("plain", fade=False), self.export("faded", fade=True)
        self.assertLess(brightness(faded, 0), brightness(plain, 0) / 3)  # starts from black
        self.assertGreater(brightness(faded, 1.5), brightness(plain, 1.5) * 0.8)  # the middle is untouched
        self.assertLess(loudest(faded, 0, 0.03), loudest(faded, 1.0, 0.5) / 3)  # and from silence

    def test_saving_a_still(self):
        out_dir = self.tmp.sub("stills")
        first = self.m.save_still(self.clip, out_dir, "pic", 1.0)
        second = self.m.save_still(self.clip, out_dir, "pic", 2.0)
        self.assertEqual((first, second), ("pic.png", "pic (2).png"))
        with open(os.path.join(out_dir, first), "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        with self.assertRaises(LookupError):
            self.m.save_still(self.tmp.sub("nope.mp4"), out_dir, "x", 0)


@needs_ffmpeg
class ThroughTheServer(unittest.TestCase):
    def test_editing_tools(self):
        def library(tmp):
            real_clip(tmp.sub("clips", "Game", "Game 2026.01.02 - 20.00.00.01.DVR.mp4"), seconds=2, peak=0.4)
            return folder_settings(tmp.sub("clips"), exportDir=tmp.sub("edits"))
        cs = Running(library)
        try:
            for _ in range(50):  # the new file is read in the background
                clip = cs.page()["clips"][0]
                if clip["full"]:
                    break
                time.sleep(0.1)
            cid = clip["id"]
            status, w = cs.get_json(f"/api/waves/{cid}")
            self.assertEqual((status, len(w["tracks"])), (200, 2))
            self.assertEqual(cs.get_json("/api/waves/nope")[0], 404)

            status, still = cs.post_json("/api/still", {"id": cid, "at": 1.25})
            self.assertEqual((status, still["file"]), (200, "Game 2026.01.02 - 20.00.00.01.DVR__still 0m01,2s.png"))

            status, body = cs.post_json("/api/export", {"id": cid, "start": 0, "end": 2, "volumes": [1, 1], "name": "tall",
                                                        "shape": "portrait", "fit": "blur", "fade": True})
            self.assertEqual(status, 200)
            for _ in range(600):
                job = cs.get_json(f"/api/job/{body['job']}")[1]
                if job["state"] != "running":
                    break
                time.sleep(0.1)
            self.assertEqual((job["state"], job["file"]), ("done", "Game 2026.01.02 - 20.00.00.01.DVR__tall (vertical).mp4"), job)
            edits = cs.get_json("/api/edited")[1]["items"]
            self.assertEqual([e["title"] for e in edits], ["tall"])  # the tag isn't part of the title

            self.assertEqual(cs.post_json("/api/copy", {"file": "missing.mp4"})[0], 400)
            self.assertEqual(cs.post_json("/api/copy", {"file": "../library.json"})[0], 400)  # only the export folder
            if sys.platform != "win32":
                status, err = cs.post_json("/api/copy", {"file": job["file"]})
                self.assertEqual((status, "Windows" in err["error"]), (400, True))
            elif os.environ.get("CI"):  # (don't replace the clipboard on a developer's PC)
                self.assertIn(cs.post_json("/api/copy", {"file": job["file"]})[0], (200, 500))
            self.assertEqual(cs.page()["meta"]["clipboard"], sys.platform == "win32")
        finally:
            cs.close()


if __name__ == "__main__":
    unittest.main()
