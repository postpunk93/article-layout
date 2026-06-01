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


def wait_until_all_closed(contexts, pump):
    """Block until the user closes every browser window.

    `contexts` is a list of (label, ctx); each ctx exposes `.pages`, and each
    page exposes `is_closed()`. `pump(page)` yields briefly to dispatch browser
    events (in real use, `page.wait_for_timeout(...)`); it may raise if the page
    just closed — that is swallowed and the context re-evaluated as closed.

    This NEVER closes a window itself; it only waits for the user to do so.
    """
    while True:
        live = []
        for label, ctx in contexts:
            try:
                if any(not pg.is_closed() for pg in ctx.pages):
                    live.append((label, ctx))
            except Exception:  # noqa: BLE001 — a vanished context counts as closed
                pass
        if not live:
            return
        try:
            pump(live[0][1].pages[0])
        except Exception:  # noqa: BLE001 — window closed mid-pump; loop re-checks
            pass
