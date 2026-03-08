"""Optional native fast paths with safe Python fallback."""

from __future__ import annotations

from typing import Iterable

try:
    from . import _fastcore
except Exception:  # pragma: no cover - optional accelerator
    _fastcore = None


def contains_any(text: str, patterns: Iterable[str]) -> bool:
    values = tuple(patterns)
    if _fastcore is not None:
        return bool(_fastcore.contains_any(text, values))
    return any(pattern and pattern in text for pattern in values)


def prefix_matches(prefix: str, options: Iterable[str]) -> list[str]:
    values = list(options)
    if _fastcore is not None:
        result = _fastcore.prefix_matches(prefix, values)
        return [str(item) for item in result]
    return [option for option in values if option.startswith(prefix)]
