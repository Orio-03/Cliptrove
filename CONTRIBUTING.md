# Contributing

Thanks for wanting to help!

## The most useful things right now

- **Example file names from recorders.** If Cliptrove puts your clips under the wrong game or date, open an issue with a few of your clip file names. Change anything personal first.
- **Bug reports.** Use the bug report form, and leave out personal paths and user names.

## Working on the code

1. Install [Python](https://www.python.org/downloads/) 3.10 or newer, and ideally [ffmpeg](https://ffmpeg.org). (The Windows app build downloads its own pinned ffmpeg: see `packaging/ffmpeg.json`.)
2. Fork the repository and clone your fork.
3. Run `python -m cliptrove --data-dir test-data --port 48660`. That runs a separate copy with its own settings, so your real library isn't touched.
4. Run the tests with `python -m unittest discover tests`. The tests that need real videos run only if ffmpeg is installed.

[How it works](docs/HOW-IT-WORKS.md) explains how the code is laid out.

### What GitHub checks for you

Every pull request runs these checks automatically (`.github/workflows/ci.yml`). The pull request can only be merged once **Tests passed** is green:

| Check | What it does |
| --- | --- |
| Lint | Looks for undefined names, unused imports and common bugs (ruff), checks the page's JavaScript, and makes sure the version has release notes in `CHANGELOG.md` |
| Unit tests | Runs all tests on Windows and Linux with Python 3.10 and 3.13. This includes error cases: requests without the token or from other sites, unknown clips, broken files, missing folders, invalid trims and exports |
| Coverage | Measures how much of the code the tests run. It fails below 75%, and the full report is attached to the run |
| Browser test | Starts Cliptrove with nothing set up and clicks through it in Chrome: the first-start setup, browsing, the player, a nickname, a star, a settings error, analytics, and quitting. It fails on any page error, and screenshots of each step are attached |
| Windows app | Builds `Cliptrove.exe`, starts it, checks the site answers, and attaches the zip so you can try the change |
| Dependency review | Flags any new dependency with known vulnerabilities |

It also runs every Monday, to catch breakage from outside (a new Python, Chrome or ffmpeg). Separately, GitHub's CodeQL scans the code for security problems.

To run the checks yourself:

```
python -m unittest discover tests
python -m pip install coverage
python -m coverage run -m unittest discover tests
python -m coverage report

python tests/e2e/make_library.py test-clips
python -m cliptrove --data-dir test-data --port 48690 --background
node tests/e2e/e2e.mjs http://127.0.0.1:48690/ test-clips test-screenshots
```

The browser test needs Chrome (or set `CHROME_PATH`) and Node 22 or newer. Start it with an empty `test-data` folder, so the first-start setup shows.

### Releases

Releases are automatic. Raise `__version__` in `cliptrove/__init__.py` and add a section for it to `CHANGELOG.md`, in the same pull request. When it's merged, `.github/workflows/release.yml` builds and checks the Windows app, then publishes the release.

### Guidelines

- Cliptrove uses only Python's standard library, and plain HTML/CSS/JS for the page. Please keep it that way.
- Keep pull requests small and focused, and add a test when you fix a bug in name parsing or analytics.
- Don't commit personal data: no real clip names, paths or screenshots of your own library.

## License of contributions

Cliptrove is under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). By opening a pull request, you agree that your contribution is shared under that license, and that the maintainer may also offer it under other terms (for example, to allow commercial use).
