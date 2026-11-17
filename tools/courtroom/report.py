"""Drop-in standalone wrapper for courtroom.report."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from courtroom.report import *  # noqa: E402,F403
from courtroom.report import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
