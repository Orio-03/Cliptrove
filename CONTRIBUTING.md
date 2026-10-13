# Contributing

Thanks for wanting to help!

## The most useful things right now

- **Example file names from recorders.** If Cliptrove puts your clips under the wrong game or date, open an issue with a few of your clip file names. Change anything personal first.
- **Bug reports.** Use the bug report form, and leave out personal paths and user names.

## Working on the code

1. Install [Python](https://www.python.org/downloads/) 3.10 or newer, and ideally [ffmpeg](https://ffmpeg.org).
2. Fork the repository and clone your fork.
3. Run `python -m cliptrove --data-dir test-data --port 48660`. That runs a separate copy with its own settings, so your real library isn't touched.
4. Run the tests with `python -m unittest discover tests`.

[How it works](docs/HOW-IT-WORKS.md) explains how the code is laid out.

### Guidelines

- Cliptrove uses only Python's standard library, and plain HTML/CSS/JS for the page. Please keep it that way.
- Keep pull requests small and focused, and add a test when you fix a bug in name parsing or analytics.
- Don't commit personal data: no real clip names, paths or screenshots of your own library.

## License of contributions

Cliptrove is under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). By opening a pull request, you agree that your contribution is shared under that license, and that the maintainer may also offer it under other terms (for example, to allow commercial use).
