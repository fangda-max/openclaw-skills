from __future__ import annotations

import calendar
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

IGNORED_DIR_NAMES = {
    ".git",
    ".idea",
    ".cursor",
    ".claude",
    "target",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".graphify_python",
}


def month_bounds(period: str) -> tuple[datetime, datetime]:
    year_str, month_str = period.split("-", 1)
    year = int(year_str)
    month = int(month_str)
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def isoformat_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def to_rel_posix(path: Path, root: Path) -> str:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return relative.as_posix()


def iter_markdown_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in path.parts):
            continue
        if path.suffix.lower() in {".md", ".markdown"}:
            files.append(path)
    return sorted(files)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def read_json_if_exists(path: Path | None) -> Any | None:
    if not path or not path.exists() or not path.is_file():
        return None
    return json.loads(read_text(path))


def resolve_source_path(project_root: Path, configured_path: str | None) -> Path | None:
    if not configured_path:
        return None
    path = Path(configured_path)
    if not path.is_absolute():
        path = project_root / path
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def days_between(later: datetime, earlier: datetime) -> int:
    delta = later.date() - earlier.date()
    return max(delta.days, 0)


def days_ago(days: int) -> datetime:
    return datetime.now() - timedelta(days=days)


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return float((ordered[middle - 1] + ordered[middle]) / 2)


def linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    if len(values) == 2:
        return values[1] - values[0]
    x_values = [0.0, 1.0, 2.0]
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(values) / len(values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    return numerator / denominator if denominator else 0.0


def score_status(raw_value: Any, status: str | None) -> str:
    if status:
        return status
    return "available" if raw_value is not None else "missing"
