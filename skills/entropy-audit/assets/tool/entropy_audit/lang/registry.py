from __future__ import annotations

from pathlib import Path

from entropy_audit.lang.base import LanguageAdapter
from entropy_audit.lang.java import JavaLanguageAdapter


_ADAPTERS: dict[str, LanguageAdapter] = {
    "java": JavaLanguageAdapter(),
}


def supported_languages() -> list[str]:
    return sorted(_ADAPTERS)


def get_language_adapter(name: str) -> LanguageAdapter:
    key = str(name or "").strip().lower()
    if key not in _ADAPTERS:
        supported = ", ".join(supported_languages())
        raise ValueError(f"Unsupported language '{name}'. Supported languages: {supported}")
    return _ADAPTERS[key]


def detect_language(project_root: Path) -> str:
    for name, adapter in _ADAPTERS.items():
        if adapter.detect(project_root):
            return name
    supported = ", ".join(supported_languages())
    raise ValueError(f"Unable to detect a supported language in {project_root}. Supported languages: {supported}")

