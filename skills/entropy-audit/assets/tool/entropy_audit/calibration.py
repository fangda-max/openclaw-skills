from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any


def _require_dict(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid {path} section in entropy.calibration.toml")
    return value


def _require_string(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string in entropy.calibration.toml")
    return value.strip()


def _normalize_string_array_table(data: dict[str, Any], path: str) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for key, value in data.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{path} contains an empty key in entropy.calibration.toml")
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{path}.{normalized_key} must be a string array in entropy.calibration.toml")
        normalized[normalized_key] = [item.strip() for item in value if item.strip()]
    return normalized


def _normalize_bool_table(data: dict[str, Any], path: str) -> dict[str, bool]:
    normalized: dict[str, bool] = {}
    for key, value in data.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            raise ValueError(f"{path} contains an empty key in entropy.calibration.toml")
        if not isinstance(value, bool):
            raise ValueError(f"{path}.{normalized_key} must be true or false in entropy.calibration.toml")
        normalized[normalized_key] = value
    return normalized


def load_calibration(calibration_path: str | Path) -> dict[str, Any]:
    path = Path(calibration_path)
    if not path.exists():
        raise FileNotFoundError(f"Calibration file not found: {path}")

    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("entropy.calibration.toml must contain a TOML table")

    meta = _require_dict(raw.get("meta"), "[meta]")
    exclusions = _require_dict(raw.get("exclusions"), "[exclusions]")
    flags = _require_dict(raw.get("flags"), "[flags]")

    normalized_meta = {
        "author": _require_string(meta, "author", "[meta]"),
        "generated_at": _require_string(meta, "generated_at", "[meta]"),
        "reason": _require_string(meta, "reason", "[meta]"),
    }

    for key, value in meta.items():
        normalized_key = str(key).strip()
        if normalized_key in normalized_meta:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"[meta].{normalized_key} must be a non-empty string in entropy.calibration.toml")
        normalized_meta[normalized_key] = value.strip()

    return {
        "meta": normalized_meta,
        "exclusions": _normalize_string_array_table(exclusions, "[exclusions]"),
        "flags": _normalize_bool_table(flags, "[flags]"),
        "raw": raw,
    }
