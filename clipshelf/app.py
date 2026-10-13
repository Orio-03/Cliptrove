"""Starting ClipShelf: python -m clipshelf (or double-click ClipShelf.bat / ClipShelf.pyw)."""
import argparse
import os
import sys
import webbrowser

from . import APP_NAME, __version__, paths


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clipshelf", description=f"{APP_NAME} {__version__}: a local library for "
                                 "your game clips. Opens in your browser at http://127.0.0.1:48650")
    ap.add_argument("--background", action="store_true",
                    help="run without stopping when the tab is closed and don't open the browser "
                         "(what the start-with-Windows shortcut uses)")
    ap.add_argument("--no-open", action="store_true", help="don't open the browser")
    ap.add_argument("--port", type=int, help="port to use instead of the one in settings (48650)")
    ap.add_argument("--data-dir", help="keep settings and caches here instead of the usual data folder")
    args = ap.parse_args(argv)
    if args.data_dir:
        paths.configure(args.data_dir)

    if sys.stdout is None or args.background:  # no window to print to: keep a small log instead
        os.makedirs(paths.DATA, exist_ok=True)
        try:
            if os.path.getsize(paths.LOG) > 1 << 20:
                os.remove(paths.LOG)
        except OSError:
            pass
        sys.stdout = sys.stderr = open(paths.LOG, "a", encoding="utf-8", buffering=1)
    sys.stdout.reconfigure(errors="replace")
    from .util import now_iso
    print(f"--- {APP_NAME} {__version__}, {now_iso()}")

    from . import settings
    from .server import running, serve
    port = args.port or settings.load()["port"]
    if running(port):
        opening = not (args.background or args.no_open)
        print(f"{APP_NAME} is already running" + (", opening it." if opening else "."))
        if opening:
            webbrowser.open(f"http://127.0.0.1:{port}/")
        return
    serve(port, background=args.background, open_browser=not (args.no_open or args.background))
