# src/adapters/__init__.py
"""Platform adapters — one module per target site.

Each adapter exposes a `build_document(...)` plus its editor URL and liveness
selector constants; `src/sessions.py` wires them into the PLATFORMS registry.
Adapters depend only on `src.ir` and `src.emit_html`, never on each other.
"""
