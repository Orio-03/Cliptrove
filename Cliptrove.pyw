"""Double-click to open Cliptrove without a console window (the start-with-Windows shortcut runs this too)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cliptrove.app import main  # noqa: E402

main()
