#!/usr/bin/env python3
"""LIMER's single source-tree command entry point (Python standard library)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'python'))
from limerlab.cli import main

if __name__ == '__main__':
    main()
