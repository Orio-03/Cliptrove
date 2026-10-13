# Changelog

## [0.4.0] - 2026-10-13

- **First-start setup.** The first time Cliptrove starts, it asks which apps you record clips with (SteelSeries GG, NVIDIA, AMD, Xbox Game Bar, OBS, Medal or any folder), with the apps it finds on your PC already ticked. Then it asks where each one saves its clips, with found folders filled in. It also offers Start with Windows and checks for ffmpeg. It only appears once, and you can skip it.

## [0.3.0] - 2026-10-13

The first public release.

- **Works with any recorder:**
  - SteelSeries GG, read straight from its library.
  - NVIDIA, AMD, Xbox Game Bar, OBS, Medal, or any folder of videos.
  - The game and date are worked out from each recorder's file names and folders.
- **Home page:** your newest clips play in a carousel above a tile for each game, with cover art.
- **Player:**
  - an audio mixer for every recorded track (Game, Chat, Mic...), remembered per clip
  - trimming, stars, nicknames and keyboard shortcuts
- **Edited copies:** saved in original quality, or compressed under 18 MB for Discord. They get their own tab, where further edits overwrite the copy unless you say otherwise.
- **Analytics:**
  - what you played over time, your top games, when you play, and a clip calendar
  - **Up next**: which games you're likely to play next week, with how well that has worked on your own past weeks
- **Settings:** clip folders (with suggestions found on your PC), where copies are saved, and Start with Windows.
- **.mkv clips** play, and new clips show up by themselves.
- **A Windows app** that doesn't need Python.
