"""Drop-in standalone wrapper for courtroom.opus_client."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from courtroom.opus_client import *  # noqa: E402,F403
