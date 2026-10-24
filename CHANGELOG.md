# Changelog

## [Unreleased]

- **Fixed:** named audio tracks in MP4 clips from folders (Game, Chat, Mic...) showed as Track 1, 2, 3 with newer versions of ffmpeg.

## [0.5.0] - 2026-10-24

- **ffmpeg comes included.** The Windows download now has ffmpeg built in, so thumbnails, Chat/Mic audio and saving edited copies work straight away. Nothing else to install.
- **Waveforms.** Under the video, each track (Game, Chat, Mic) has its own lane showing its waveform, like in GG's editor. A lane grows and shrinks with its volume slider, so you can see your mix, and clicking a lane jumps there. Press W to hide them.
- **Portrait copies for Reels, TikTok and Shorts.** Save a 9:16 copy, either cropped (drag the frame over the video to choose what to keep) or with the whole picture on a blurred background.
- **Fades.** Saved copies can fade in and out, picture and sound.
- **Copy and paste into Discord.** After saving, Copy puts the file on the clipboard: press Ctrl+V in Discord to send it.
- **Save a still.** The camera button (or C) saves the frame on screen as a picture.
- **Smoother playback.** Clips no longer stutter in the player outside fullscreen when your browser is drawing without the graphics card, which can happen right after a graphics driver update. (Restarting the browser also brings the graphics card back.)

## [0.4.1] - 2026-10-13

- **Fixed:** in saved copies, a loud game and a loud mic at the same moment could add up past the maximum and crackle when **Even out loudness** was off. A limiter now holds just those moments under the maximum and leaves the rest of the mix as it is. Thanks to the Reddit commenter who spotted it.

## [0.4.0] - 2026-10-13

- **First-start setup.** The first time Cliptrove starts, it asks which apps you record clips with (SteelSeries GG, NVIDIA, AMD, Xbox Game Bar, OBS, Medal or any folder), with the apps it finds on your PC already ticked. Then it asks where each one saves its clips, with found folders filled in. It also offers Start with Windows and checks for ffmpeg. It only appears once, and you can skip it.
- **Fixed:** a renamed or moved clip could lose its nickname, star or trim when other clips had the same size and time.
- **Fixed:** saving a copy of a clip whose file had been moved away, or saving without ffmpeg, now says so clearly instead of failing with an error.
- **Behind the scenes:** 92 automated tests, including error cases and a browser test that clicks through the app. They run on every change, along with lint, coverage and a Windows build. Releases now publish themselves.

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
