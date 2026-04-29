from __future__ import annotations

from typing import Any


class AttrView:
    def __init__(self, payload: dict[str, Any] | None):
        self._payload = payload if isinstance(payload, dict) else {}

    def __getattr__(self, name: str) -> Any:
        return _wrap_value(self._payload.get(name))


def _wrap_value(value: Any) -> Any:
    if isinstance(value, dict):
        return AttrView(value)
    if isinstance(value, list):
        return [_wrap_value(item) for item in value]
    return value


def safe_div(numerator: Any, denominator: Any, default: Any = None) -> float | None:
    if numerator is None or denominator is None:
        return None
    try:
        numerator_value = float(numerator)
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if abs(denominator_value) < 1e-9:
        return float(default) if isinstance(default, (int, float)) else None
    return numerator_value / denominator_value


def average(*values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def one_minus(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return 1.0 - float(value)


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def minimum(*values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return min(numbers)


def maximum(*values: Any) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, (int, float))]
    if not numbers:
        return None
    return max(numbers)
