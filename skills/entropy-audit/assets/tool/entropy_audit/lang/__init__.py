from __future__ import annotations

from pathlib import Path
from typing import Any

from entropy_audit.config import ProjectConfig
from entropy_audit.lang.base import LanguageAdapter, LanguageScaffold
from entropy_audit.lang.registry import detect_language, get_language_adapter, supported_languages


def analyze_internal_entropy(project_root: Path, project_config: ProjectConfig) -> dict[str, Any]:
    adapter = get_language_adapter(project_config.project_language)
    return adapter.analyze(project_root, project_config)


def build_internal_entropy_export(payload: dict[str, Any], language: str) -> dict[str, Any]:
    adapter = get_language_adapter(language)
    return adapter.build_export(payload)


__all__ = [
    "LanguageAdapter",
    "LanguageScaffold",
    "analyze_internal_entropy",
    "build_internal_entropy_export",
    "detect_language",
    "get_language_adapter",
    "supported_languages",
]

