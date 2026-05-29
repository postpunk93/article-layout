# src/orchestrator.py
"""Pure decision logic for the `layout` command — no browser here.

`parse_platforms` validates the user's platform argument; `precheck` runs the
all-or-nothing liveness gate. The CLI wires these to the real `is_alive` and to
the browser; tests inject fakes.
"""
from typing import Callable


def parse_platforms(arg: str, known: list[str]) -> list[str]:
    """Resolve the user's platform argument to a list of known platforms.

    Expands "all" to the known list; tolerates surrounding whitespace and drops
    empty tokens; de-duplicates while preserving first-seen order; raises
    ValueError naming any unknown platform(s).
    """
    if arg == "all":
        return list(dict.fromkeys(known))
    requested = [s.strip() for s in arg.split(",") if s.strip()]
    unknown = [p for p in requested if p not in known]
    if unknown:
        raise ValueError(f"unknown platform(s): {', '.join(unknown)}; known: {', '.join(known)}")
    return list(dict.fromkeys(requested))


def precheck(client: str, platforms: list[str],
             alive_fn: Callable[[str, str], bool]) -> tuple[bool, list[tuple[str, str]]]:
    """Return (ok, dead) where dead is a list of (client, platform) tuples.

    ok is True only if EVERY requested session is alive (all-or-nothing).
    """
    dead = [(client, p) for p in platforms if not alive_fn(client, p)]
    return (not dead, dead)
