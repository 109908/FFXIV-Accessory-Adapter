#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convenience CLI for model analysis from the repository root."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from accessory_adapter.model_analysis import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
