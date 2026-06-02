# tests/test_no_bare_control_modifier.py
"""Guard: keyboard presses must use ControlOrMeta (Cmd on macOS), never bare Control.

A bare press("Control+...") does not paste / select-all / bold on macOS, so it
would silently break every paste-based adapter there. ControlOrMeta resolves per-OS.
"""
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"


def test_no_bare_control_press_in_adapters():
    offenders = []
    for py in SRC.glob("*_adapter.py"):
        for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            # 'press("Control+' matches bare Control but NOT 'ControlOrMeta+'
            if 'press("Control+' in line:
                offenders.append(f"{py.name}:{i}")
    assert offenders == [], f"Use ControlOrMeta, not bare Control: {offenders}"
