"""Minimal text UI helpers that replace the rich library.

All output goes through plain ``print()`` / ``input()``.
Rich markup tags (``[bold]``, ``[nn.tool]``, etc.) are stripped
automatically so callers can keep the same format strings.
"""

from __future__ import annotations

import re
from typing import Any


# Regex that matches rich-style markup tags: [bold], [/bold], [nn.tool], [dim], etc.
_MARKUP_RE = re.compile(r"\[/?[\w.#, ]+\]")


def strip_markup(text: str) -> str:
    """Remove rich markup tags from *text*."""
    return _MARKUP_RE.sub("", text)


def cprint(*args: Any, **kwargs: Any) -> None:
    """Print with rich markup stripped."""
    parts = []
    for a in args:
        parts.append(strip_markup(str(a)) if isinstance(a, str) else str(a))
    print(*parts, **kwargs)


def cinput(prompt: str = "") -> str:
    """input() with rich markup stripped from *prompt*."""
    return input(strip_markup(prompt))


def print_table(
    title: str | None,
    columns: list[str],
    rows: list[list[str]],
    *,
    col_widths: list[int] | None = None,
) -> None:
    """Print a simple aligned text table."""
    all_rows = [columns] + rows
    if col_widths is None:
        col_widths = [
            max(len(strip_markup(str(row[i]))) for row in all_rows)
            for i in range(len(columns))
        ]

    if title:
        print(f"\n  {strip_markup(title)}")
        print(f"  {'─' * (sum(col_widths) + 3 * (len(columns) - 1))}")

    for row in all_rows:
        cells = []
        for i, cell in enumerate(row):
            clean = strip_markup(str(cell))
            width = col_widths[i] if i < len(col_widths) else len(clean)
            cells.append(clean.ljust(width))
        print(f"  {'   '.join(cells)}")

    print()


def print_panel(content: str, title: str = "") -> None:
    """Print a simple bordered panel."""
    clean = strip_markup(content)
    clean_title = strip_markup(title)
    lines = clean.splitlines()
    width = max(len(line) for line in lines) if lines else 40
    width = max(width, len(clean_title) + 4)
    border = "─" * (width + 2)
    print()
    if clean_title:
        print(f"  ┌─ {clean_title} {'─' * max(0, width - len(clean_title) - 2)}┐")
    else:
        print(f"  ┌{border}┐")
    for line in lines:
        print(f"  │ {line.ljust(width)} │")
    print(f"  └{border}┘")


def print_rule(text: str = "", width: int = 60) -> None:
    """Print a horizontal rule with optional centered text."""
    clean = strip_markup(text)
    if clean:
        pad = max(0, width - len(clean) - 4)
        print(f"{'─' * 2} {clean} {'─' * pad}")
    else:
        print("─" * width)
