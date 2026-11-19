#!/usr/bin/env python3
"""Prepare, launch, and inspect independently budgeted Terra sandbox batches."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toksec.batch import main

if __name__ == '__main__':
    raise SystemExit(main())
