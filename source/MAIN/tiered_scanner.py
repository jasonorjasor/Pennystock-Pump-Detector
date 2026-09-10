"""Compatibility entrypoint for the versioned completed-session scanner."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pennystock.core import calculate_pump_score, assign_tiers
from pennystock.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["scan", *sys.argv[1:]]))
