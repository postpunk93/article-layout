# src/orchestrator.py
"""Pure decision logic for the `layout` command — no browser here.

`parse_platforms` validates the user's platform argument; `check_alive` runs the
all-or-nothing liveness gate over already-open pages (each page is navigated by
the CLI; the gate just checks its logged-in marker); `wait_until_all_closed`
blocks until the user closes every window. The CLI wires these to the browser;
tests inject fakes.
"""


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


def check_alive(pages_by_platform: dict, markers: dict, timeout_ms: int = 8000) -> list:
    """Return the platforms whose logged-in marker did NOT appear, in iteration order.

    `pages_by_platform` maps platform -> an already-navigated page; `markers` maps
    platform -> its alive selector. All-or-nothing is the caller's call: proceed only
    when the returned list is empty. Pure w.r.t. browser setup — pages are injected.
    """
    dead = []
    for platform, page in pages_by_platform.items():
        try:
            page.wait_for_selector(markers[platform], timeout=timeout_ms)
        except Exception:  # noqa: BLE001 — any failure = not logged in / not loaded
            dead.append(platform)
    return dead


def wait_until_all_closed(contexts, pump):
    """Block until the user closes every browser window.

    `contexts` is a list of (label, ctx); each ctx exposes `.pages`, and each
    page exposes `is_closed()`. `pump(page)` yields briefly to dispatch browser
    events (in real use, `page.wait_for_timeout(...)`); it may raise if the page
    just closed — that is swallowed and the context re-evaluated as closed.
    `pump` MUST block (it is the loop's only throttle — there is no other sleep).

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
            # Assumes one page per context (true today: each platform is its own
            # window). If "tabs in one window" lands, pump the first LIVE page.
            pump(live[0][1].pages[0])
        except Exception:  # noqa: BLE001 — window closed mid-pump; loop re-checks
            pass
