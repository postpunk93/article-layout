# tests/test_no_bare_control_modifier.py
"""Guard: keyboard presses must use ControlOrMeta (Cmd on macOS), never bare Control.

A bare press("Control+...") does not paste / select-all / bold on macOS, so it
would silently break every paste-based adapter there. ControlOrMeta resolves per-OS.
"""
import re
from pathlib import Path

ADAPTERS = Path(__file__).resolve().parent.parent / "src" / "adapters"

# Matches a press() of a bare Control modifier in either quote style, tolerating
# whitespace, but NOT the allowed ControlOrMeta form (negative lookahead on "Or").
_BARE_CONTROL = re.compile(r"""press\(\s*["']Control(?!Or)\+""")


def test_no_bare_control_press_in_adapters():
    offenders = []
    for py in ADAPTERS.glob("*.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if _BARE_CONTROL.search(line):
                offenders.append(f"{py.name}:{i}")
    assert offenders == [], f"Use ControlOrMeta, not bare Control: {offenders}"
