# Third-party notices

Cliptrove itself is under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). It relies on the following.

## Included in the Windows app (`Cliptrove.exe`)

- **Python**, © Python Software Foundation, under the [PSF License](https://docs.python.org/3/license.html). A copy is in `licenses/Python-LICENSE.txt` in the app folder.
- **Tcl/Tk** (used for the folder picker), under its BSD-style license. A copy is in `licenses/Tcl-Tk-license.terms`.
- **PyInstaller's bootloader** (it starts the app), under the GPL 2.0 with an exception that allows it to be shipped with any program.
- **[FFmpeg](https://ffmpeg.org)** (`ffmpeg.exe`, `ffprobe.exe` and their libraries, in the `ffmpeg` folder), the LGPL build from [BtbN's FFmpeg-Builds](https://github.com/BtbN/FFmpeg-Builds), under the GNU LGPL version 3 or later. Its license, a copy of the GPL version 3 it builds on, and links to the exact source code are in `licenses` (`FFmpeg-LICENSE.txt`, `GPL-3.0.txt`, `FFmpeg-SOURCE.txt`). Cliptrove runs FFmpeg as a separate program, and you can swap in another build. The version is pinned in [packaging/ffmpeg.json](packaging/ffmpeg.json).

## Not included, used if available or loaded from the internet

- **[ffmpeg](https://ffmpeg.org)**, when you run Cliptrove from the source code: you install it yourself, under its own license (LGPL/GPL).
- **[Geist](https://vercel.com/font)** and **Geist Mono** (© Vercel) and **[Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk)** (© Florian Karsten), all under the SIL Open Font License 1.1. They're loaded from Google Fonts, not shipped.
- **Cover art** is shown from Steam's servers and belongs to each game's publisher. It isn't shipped with Cliptrove.

## Trademarks

SteelSeries, NVIDIA, AMD, Radeon, Xbox, OBS, Medal and Steam are trademarks of their owners. Cliptrove isn't made by, affiliated with or endorsed by any of them. Their names are only used to say which recorders Cliptrove can read clips from.
