"""Entry point for the frozen app (PyInstaller): the same as `python -m sloucher`."""
import sys

from sloucher.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
