#!/usr/bin/env python
"""Run PrintSplit straight from a checkout, without installing it.

    python printsplit.py config/hedelius.toml
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from printsplit.cli import run  # noqa: E402

if __name__ == "__main__":
    run()
