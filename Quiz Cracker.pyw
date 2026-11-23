"""Windowless desktop entry point for Quiz Cracker (launches via pythonw.exe)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quiz_cracker import main

if __name__ == "__main__":
    main()
