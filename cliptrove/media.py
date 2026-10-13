"""Everything Cliptrove does with ffmpeg: reading clips, thumbnails, Chat/Mic tracks, playable copies of .mkv
files, and saving edited copies. Without ffmpeg, clips still play; those extras are off."""
import json
import os
import re
import secrets
import subprocess
import threading
import time

from . import paths
from .util import NO_WINDOW, find_tool, path_key, retry_io, run

PLAYABLE = (".mp4", ".m4v", ".mov", ".webm")  # containers the browser plays as they are
SHARE_LIMIT = 18_000_000  # bytes: "Compressed" copies stay under 18 MB so they're easy to share

# Video encoders for precise cuts, fastest first. The first one that works on this PC is used.
ENCODERS = [
    ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "18", "-qp_p", "20", "-pix_fmt", "nv12"],
    ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", "-pix_fmt", "yuv420p"],
    ["-c:v", "h264_qsv", "-global_quality", "20", "-pix_fmt", "nv12"],
    ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"],
]


def share_settings(seconds):
    """Video bitrate (kb/s) and picture height that fit a copy of this length under SHARE_LIMIT."""
    total = SHARE_LIMIT * 0.9 * 8 / 1000 / max(seconds, 1)  # 10% headroom for the container and the encoder
    kbps = max(250, int(total - 128))  # minus the audio
    for need, height in ((9000, 1440), (4500, 1080), (1900, 720), (1100, 540)):
        if kbps >= need:
            return kbps, height
    return kbps, 480


def stamp(path):
    st = os.stat(path)
    return f"{int(st.st_mtime)}-{st.st_size}"


class Media:
    def __init__(self):
        self.ffmpeg = find_tool("ffmpeg")
        self.ffprobe = find_tool("ffprobe")
        self.encoder = None
        self.jobs = {}
        self.lock = threading.Lock()
        self.extract_lock = threading.Lock()  # one extraction at a time: the hard drive is the bottleneck
        self.remux_lock = threading.Lock()
        self.thumb_slots = threading.Semaphore(2)
        self.probes = {}
        self.prefetching = set()

    # ----- reading clips -----

    def probe(self, path):
        """Length, audio tracks and codecs of a video file (cached while the file is unchanged)."""
        st = os.stat(path)
        ck = (path_key(path), st.st_mtime, st.st_size)
        with self.lock:
            hit = self.probes.get(ck)
        if hit:
            return hit
        info = {"duration": 0.0, "audio": 1, "titles": [], "video": "", "audioCodecs": [], "width": 0, "height": 0,
                "ok": True, "probed": bool(self.ffprobe)}
        if self.ffprobe:
            r = run([self.ffprobe, "-v", "error", "-show_entries",
                     "format=duration:stream=codec_type,codec_name,width,height:stream_tags=title,handler_name",
                     "-of", "json", path], timeout=120)
            try:
                j = json.loads(r.stdout or "{}")
            except ValueError:
                j = {}
            streams = j.get("streams") or []
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio = [s for s in streams if s.get("codec_type") == "audio"]
            try:
                duration = float((j.get("format") or {}).get("duration") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            info.update(duration=duration, audio=len(audio),
                        titles=[(s.get("tags") or {}).get("title") or (s.get("tags") or {}).get("handler_name") or ""
                                for s in audio],
                        video=(video or {}).get("codec_name", ""), audioCodecs=[s.get("codec_name", "") for s in audio],
                        width=(video or {}).get("width") or 0, height=(video or {}).get("height") or 0,
                        ok=video is not None)
        with self.lock:
            self.probes[ck] = info
        return info

    def audio_count(self, path):
        """How many audio tracks (Game, Chat, Mic...) the file really has."""
        return self.probe(path)["audio"] if self.ffprobe else 1

    # ----- things made from clips, cached -----

    def playable(self, cid, path):
        """The clip itself, or for .mkv and similar files a copy repackaged as .mp4 (made once, fast and
        lossless) because browsers can't open those."""
        if path.lower().endswith(PLAYABLE) or not self.ffmpeg:
            return path
        out = os.path.join(paths.VIDEO, f"{cid}-{stamp(path)}.mp4")
        if not os.path.exists(out):
            with self.remux_lock:
                if not os.path.exists(out):
                    os.makedirs(paths.VIDEO, exist_ok=True)
                    part = out + ".part"
                    base = [self.ffmpeg, "-v", "error", "-y", "-i", path, "-map", "0:v:0", "-map", "0:a?", "-c:v", "copy"]
                    tail = ["-movflags", "+faststart", "-f", "mp4", part]
                    r = run(base + ["-c:a", "copy"] + tail)
                    if r.returncode:  # audio MP4 can't hold as it is (e.g. PCM): convert just the audio
                        r = run(base + ["-c:a", "aac", "-b:a", "192k"] + tail)
                    if r.returncode:
                        try:
                            os.remove(part)
                        except OSError:
                            pass
                        raise RuntimeError((r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
                    os.replace(part, out)
        try:
            os.utime(out)  # keep recently watched copies in the cache
        except OSError:
            pass
        return out

    def thumbnail(self, cid, path, at=None):
        """A picture from the clip, made once and cached. `at` is the time in seconds; by default a quarter of
        the way in (at most 30 s), which shows the game better than the first frame."""
        out = os.path.join(paths.THUMBS, f"{cid}-{stamp(path)}.jpg")
        if os.path.exists(out):
            return out
        if not self.ffmpeg:
            raise LookupError("No thumbnail")
        with self.thumb_slots:
            if not os.path.exists(out):
                os.makedirs(paths.THUMBS, exist_ok=True)
                if at is None:
                    d = self.probe(path)["duration"]
                    at = min(d * 0.25, 30.0) if d else 1.0
                tmp = out + f".{secrets.token_hex(3)}.jpg"
                r = run([self.ffmpeg, "-v", "error", "-y", "-ss", f"{at:.2f}", "-i", path, "-frames:v", "1",
                         "-vf", "scale=640:-2", "-q:v", "4", tmp], timeout=60)
                if r.returncode == 0 and os.path.exists(tmp):
                    os.replace(tmp, out)
                else:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
        if not os.path.exists(out):
            raise LookupError("No thumbnail")
        return out

    def audio_track(self, cid, src, n, wanted=None):
        """Path to audio track n (1 = Chat, 2 = Mic...) pulled out of the clip. Track 0 plays from the video."""
        if not self.ffmpeg:
            raise LookupError("ffmpeg isn't installed")
        stem = os.path.join(paths.AUDIO, f"{cid}-{stamp(src)}")
        want = f"{stem}-{n}.m4a"
        if not os.path.exists(want):
            with self.extract_lock:
                if not os.path.exists(want):
                    if wanted and not wanted():
                        raise LookupError("No longer needed")
                    count = self.audio_count(src)
                    if not 1 <= n < count:
                        raise LookupError("This clip has no such audio track")
                    os.makedirs(paths.AUDIO, exist_ok=True)
                    outs = [(f"{stem}-{i}.part", f"{stem}-{i}.m4a") for i in range(1, count)]
                    for codec in (["-c", "copy"], ["-c:a", "aac", "-b:a", "192k"]):  # copy if MP4 can hold it
                        args = [self.ffmpeg, "-v", "error", "-y", "-i", src]
                        for i, (part, _) in enumerate(outs, 1):  # one pass over the file for all tracks
                            args += ["-map", f"0:a:{i}", *codec, "-f", "mp4", part]
                        r = run(args)
                        if not r.returncode:
                            break
                    else:
                        raise RuntimeError((r.stderr.strip().splitlines() or ["ffmpeg failed"])[-1])
                    for part, final in outs:
                        os.replace(part, final)
        try:
            os.utime(want)  # keep recently used tracks in the cache
        except OSError:
            pass
        return want

    def prefetch(self, cid, src):
        """Get a clip's Chat/Mic ready in the background (used for the next clip on the home page)."""
        with self.lock:
            if cid in self.prefetching or not self.ffmpeg:
                return
            self.prefetching.add(cid)

        def work():
            try:
                self.audio_track(cid, src, 1)
            except Exception:  # nothing to prepare, or the clip is gone
                pass
            finally:
                self.prefetching.discard(cid)

        threading.Thread(target=work, daemon=True).start()

    def clean_cache(self):
        """Forget audio tracks and playable copies that haven't been used for a while."""
        now = time.time()
        for folder, days in ((paths.AUDIO, 14), (paths.VIDEO, 3), (paths.THUMBS, 120)):
            try:
                names = os.listdir(folder)
            except OSError:
                continue
            for name in names:
                path = os.path.join(folder, name)
                try:
                    if name.endswith(".part") or os.path.getmtime(path) < now - days * 86400:
                        os.remove(path)
                except OSError:
                    pass

    # ----- saving edited copies -----

    def video_encoder(self):
        if self.encoder is None:
            self.encoder = ENCODERS[-1]
            for enc in ENCODERS[:-1]:
                test = [self.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=0.2",
                        *enc, "-f", "null", "-"]
                if run(test, timeout=60).returncode == 0:
                    self.encoder = enc
                    break
        return self.encoder

    def rate_encoder(self, kbps):
        """The same encoder, set to a fixed bitrate so a compressed copy lands on a predictable size."""
        name = self.video_encoder()[1]
        rate = ["-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k"]
        if name == "h264_amf":
            return ["-c:v", name, "-quality", "quality", "-rc", "cbr", *rate, "-pix_fmt", "nv12"]
        if name == "h264_nvenc":
            return ["-c:v", name, "-preset", "p5", "-rc", "cbr", *rate, "-pix_fmt", "yuv420p"]
        if name == "h264_qsv":
            return ["-c:v", name, *rate, "-pix_fmt", "nv12"]
        return ["-c:v", "libx264", "-preset", "medium", *rate, "-pix_fmt", "yuv420p"]

    def start_export(self, src, out_dir, stem, replace, start, end, volumes, precise, loud, small):
        """Save part of a clip as a new video in out_dir (or over `replace`); returns a job id to follow."""
        if not self.ffmpeg:
            raise RuntimeError("Saving edited copies needs ffmpeg")
        start, end = float(start), float(end)
        if not (0 <= start < end) or end - start < 0.2:
            raise ValueError("Pick a start and end at least 0.2 seconds apart")
        count = self.audio_count(src)
        vols = [min(4.0, max(0.0, float(v))) for v in list(volumes)[:count]]
        vols += [1.0] * (count - len(vols))
        with self.lock:
            os.makedirs(out_dir, exist_ok=True)
            n = 1
            while True:  # never clobber another file: add (2), (3)... and reserve the name with a .part file
                out = os.path.join(out_dir, stem + (f" ({n})" if n > 1 else "") + ".mp4")
                same = replace and path_key(out) == path_key(replace)
                if (same or not os.path.exists(out)) and not os.path.exists(out + ".part"):
                    open(out + ".part", "wb").close()
                    break
                n += 1
            jid = secrets.token_hex(4)
            self.jobs[jid] = {"state": "running", "progress": 0.0, "file": os.path.basename(out), "error": "",
                              "overwrote": bool(replace)}
        threading.Thread(target=self._export, args=(jid, src, out, start, end, vols, bool(precise), bool(loud),
                                                    bool(small), replace)).start()
        return jid

    def busy(self):
        return any(j["state"] == "running" for j in self.jobs.values())

    def _export(self, jid, src, out, start, end, vols, precise, loud, small, replace=None):
        job, part = self.jobs[jid], out + ".part"
        try:
            length = end - start
            kbps, height = share_settings(length) if small else (0, 0)
            for attempt in range(3):
                args = [self.ffmpeg, "-hide_banner", "-v", "error", "-y",
                        "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src]
                # Mix every audio track into one, each at the volume picked in the player
                chains = [f"[0:a:{i}]volume={v:.3f}[a{i}]" for i, v in enumerate(vols)]
                mixed = None
                if len(vols) > 1:
                    chains.append("".join(f"[a{i}]" for i in range(len(vols)))
                                  + f"amix=inputs={len(vols)}:normalize=0:duration=longest[aout]")
                    mixed = "[aout]"
                elif vols:
                    mixed = "[a0]"
                if loud and mixed:  # bring the whole mix to normal online-video loudness
                    chains.append(f"{mixed}loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[aloud]")
                    mixed = "[aloud]"
                video = "0:v:0"
                if small:  # smaller picture for longer clips, so the size limit doesn't make it blocky
                    chains.append(f"[0:v:0]scale=-2:'min(ih,{height})'" + (",fps=30" if kbps < 2500 else "") + "[v]")
                    video = "[v]"
                if chains:
                    args += ["-filter_complex", ";".join(chains)]
                args += ["-map", video]
                if mixed:
                    args += ["-map", mixed, "-c:a", "aac", "-b:a", "128k" if small else "192k"]
                if small:
                    args += self.rate_encoder(kbps)
                elif precise:
                    args += self.video_encoder()
                else:
                    args += ["-c:v", "copy"]
                args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", "-f", "mp4", part]
                job.update(progress=0.0, retry=attempt)
                self._run_ffmpeg(args, job, length)
                if not small or os.path.getsize(part) <= SHARE_LIMIT:
                    break
                kbps = max(150, int(kbps * SHARE_LIMIT / os.path.getsize(part) * 0.9))  # came out too big: go lower
            else:
                raise RuntimeError("Couldn't get this clip under 18 MB. Try trimming it shorter.")
            retry_io(lambda: os.replace(part, out))  # the browser may be reading the old file for a moment
            if replace and path_key(replace) != path_key(out):
                retry_io(lambda: os.remove(replace))  # overwritten under a new name (its quality changed)
            job.update(state="done", progress=1.0, size=os.path.getsize(out))
        except Exception as e:  # report any failure to the page
            job.update(state="error", error=str(e))
            try:
                os.remove(part)
            except OSError:
                pass

    def _run_ffmpeg(self, args, job, length):
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             errors="replace", creationflags=NO_WINDOW)
        err = []
        reader = threading.Thread(target=lambda: err.append(p.stderr.read()))
        reader.start()
        for line in p.stdout:
            m = re.match(r"out_time_(?:us|ms)=(\d+)", line)
            if m:
                job["progress"] = min(0.99, int(m.group(1)) / 1e6 / length)
        p.wait()
        reader.join()
        if p.returncode:
            lines = "".join(err).strip().splitlines()
            raise RuntimeError(lines[-1] if lines else f"ffmpeg stopped with code {p.returncode}")
