# ClipShelf

A local library for your game clips. Browse them by game, watch them, give them nicknames, mix their audio
tracks, trim them and save edited copies, all in your browser. ClipShelf runs on your own PC: nothing is
uploaded, and your clip files are never moved or changed.

It works with clips from:

| Recorder | How ClipShelf reads it |
| --- | --- |
| **SteelSeries GG** (Moments) | Straight from GG's library: titles, stars, trims and Game/Chat/Mic levels |
| **NVIDIA** (ShadowPlay / NVIDIA App) | Folder: `Game 2024.06.16 - 23.06.36.02.DVR.mp4` in a folder per game |
| **AMD** (Radeon ReLive / Adrenalin) | Folder: `Game_replay_2026.09.12-17.41.mp4` in a folder per game |
| **Xbox Game Bar** | Folder: `Game 2026-01-31 18-04-12.mp4`, or in your PC's own date format |
| **OBS Studio** | Folder: `2024-06-16 23-06-36.mkv` (no game in the name, so you pick it) |
| **Medal**, or any folder of videos | Folder: the game comes from the folder name, the date from the file |

## Features

- **Home page** with your 5 newest clips playing in a carousel, and every game as a tile with Steam cover art
- **Hover a clip to preview it**, with sound at a volume you choose
- **Player** with keyboard shortcuts, frame stepping, loop and speed control
- **Audio mixer**: set the volume of each recorded track (Game, Chat, Mic...) up to 200%, remembered per clip
- **Nicknames** for clips (GG's own titles are tracked in a change log too)
- **Stars, trims and games** for any clip, kept by ClipShelf
- **Save edited copies**: trimmed, with your audio mix, in original quality or compressed under 18 MB for
  Discord. They appear in an **Edited** tab, where further edits overwrite the copy unless you say otherwise
- **New clips show up by themselves** while the page is open
- **.mkv clips play** (repackaged for the browser on the fly, without re-encoding)

## Requirements

- Windows 10 or 11 (macOS and Linux should work, except starting with Windows; not tested yet)
- [Python](https://www.python.org/downloads/) 3.10 or newer. ClipShelf uses only Python's standard library
- [ffmpeg](https://ffmpeg.org/), for Chat/Mic audio, thumbnails of folder clips, .mkv playback and saving copies.
  On Windows: `winget install Gyan.FFmpeg`. Without it, clips still play
- Chrome or Edge recommended. Firefox can't play HEVC clips

## Getting started

1. Download this repository (Code > Download ZIP) and unzip it anywhere, or `git clone` it.
2. Double-click **ClipShelf.bat**. Your browser opens at <http://127.0.0.1:48650>.
3. On the first run, open **Settings** (the gear at the top right). Add your clip folders; ClipShelf suggests the
   ones it finds for NVIDIA, AMD, Xbox Game Bar and OBS. SteelSeries GG is picked up on its own.
4. Optional: in Settings, turn on **Start with Windows**, so ClipShelf runs in the background and the site is
   always there.

From a terminal you can also run `python -m clipshelf`. Options:

```
--background    keep running when the tab is closed, and don't open the browser
--no-open       don't open the browser
--port N        use another port than 48650
--data-dir DIR  keep settings and caches somewhere else
```

## Where things are kept

Everything ClipShelf stores is in one folder, `%LOCALAPPDATA%\ClipShelf` on Windows (Settings > About has a
button to open it):

| File | What's in it |
| --- | --- |
| `settings.json` | Your clip folders and where edited copies go |
| `library.json` | Your nicknames, stars, trims, audio levels, games, and the change log |
| `index.json` | Length and audio tracks of each clip in your folders, so they're only read once |
| `covers/` | Your own cover pictures: name a picture after the game, like `VALORANT.jpg` |
| `cache/` | Thumbnails, extracted audio tracks and playable copies of .mkv clips (safe to delete) |

Edited copies are saved to an "Edited Clips" folder inside your first clips folder, unless you choose another
one in Settings.

## Privacy

The site only listens on 127.0.0.1, so other devices can't reach it. Every request needs a token that only the
page has, so other websites open in your browser can't use it either. ClipShelf only goes online to fetch cover
art from Steam, and the only things it sends are game names and Steam app IDs.

## Notes

- ClipShelf isn't made by or affiliated with SteelSeries, NVIDIA, AMD, Microsoft, OBS or Medal.
- SteelSeries GG's library format isn't documented. A GG update could change it. If that happens, GG clips stop
  showing up until ClipShelf is updated; nothing else is affected.

## Development

```
python -m unittest discover tests
```

The code is in `clipshelf/`:

- `sources/` reads each recorder (`gg.py`, `folder.py`).
- `names.py` works out the game and date from file names.
- `library.py` merges everything.
- `media.py` wraps ffmpeg.
- `server.py` is the local web server.
- `web/` holds the page itself.
