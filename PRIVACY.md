# Privacy

**Short version: Cliptrove runs entirely on your own PC.**

- No account.
- No tracking or usage statistics.
- Nothing is uploaded. Your clips, their names, your nicknames and your analytics never leave your computer.

## What Cliptrove reads

- **The clip folders you add in Settings.** It reads each video's name, date, length and audio tracks, and makes small thumbnails.
- **SteelSeries GG's clip library**, if GG is installed. It makes a temporary copy of GG's database and reads that copy, so GG's own files are never opened for writing.

## What it changes on your PC

- **Your clips are never moved, renamed or edited.**
- When you save an edited copy, Cliptrove writes a **new** video into your "Edited Clips" folder (you choose which folder in Settings).
- "Save changes" on an edited copy overwrites that copy only. It never touches the original clip.
- "Start with Windows" adds or removes a shortcut in your Windows Startup folder.

## What it stores, and where

Everything Cliptrove keeps is in one folder: `%LOCALAPPDATA%\Cliptrove` on Windows. Settings > About has a button to open it.

| File | What's in it |
| --- | --- |
| `settings.json` | Your clip folders and where edited copies go |
| `library.json` | Your nicknames, stars, trims, audio levels and games, and a log of title changes |
| `index.json` | Length and audio tracks of each clip, so they're only read once |
| `covers.json` | Which cover art was found for each game |
| `covers\` | Cover pictures you added yourself |
| `cache\` | Thumbnails, extracted audio tracks and playable copies of .mkv clips |
| `cliptrove.log` | What Cliptrove did while running in the background (it contains file paths) |

## What goes over the internet

Cliptrove only talks to these services:

| Service | Why | What it sends |
| --- | --- | --- |
| Steam (`store.steampowered.com`, `api.steampowered.com`, Steam's image servers) | To find cover art for your games | Game names and Steam app IDs. Each game is looked up once and the answer is cached. |
| Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) | To load the page's fonts (Geist and Space Grotesk) | A normal request for the font files |

Like any website, these services see your IP address when your PC contacts them. Cliptrove never sends the names of your clips, your nicknames, your folders or your analytics anywhere.

There are no update checks, ads or analytics services.

## The local site

Cliptrove shows its pages through a small web server that only listens on your own PC (`127.0.0.1`), so other devices on your network can't reach it.

Each time it starts, it makes a random secret that only its own page knows. Every request has to carry that secret, and has to be addressed to `127.0.0.1` or `localhost`. That stops other websites open in your browser from reading your library or controlling Cliptrove.

## Analytics and predictions

The Analytics tab and its "Up next" predictions are worked out on your PC, from the dates of your clips. The prediction model is trained on your own history each time and is never sent anywhere. [How it works](docs/HOW-IT-WORKS.md#analytics-and-up-next) explains the model.

## Removing everything

1. In Settings, turn off **Start with Windows**.
2. Close Cliptrove, then delete the folder you unzipped it to.
3. Delete `%LOCALAPPDATA%\Cliptrove`: paste that into File Explorer's address bar to find it.

Your clips and edited copies stay where they are.

## Sharing logs or screenshots

If you report a bug, **remove anything personal first**. `cliptrove.log` and screenshots of Settings can show your Windows user name and folder names.
