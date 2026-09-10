"""Compatibility entrypoint. Writes v2 outcomes; never changes legacy history."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pennystock.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["track", *sys.argv[1:]]))
