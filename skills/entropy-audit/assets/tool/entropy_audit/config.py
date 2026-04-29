from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ProjectMetadata:
    id: str
    name: str
    language: str = "java"


@dataclass(slots=True)
class ScopeConfig:
    critical_flows: list[str] = field(default_factory=list)
    validation_targets: list[str] = field(default_factory=list)
    required_invariants: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PathsConfig:
    architecture: list[str] = field(default_factory=list)
    runbooks: list[str] = field(default_factory=list)
    plans: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SourcesConfig:
    pr_export: str = ""
    ci_export: str = ""
    issue_export: str = ""
    agent_logs: str = ""
    code_entropy_export: str = ""


@dataclass(slots=True)
class ProjectConfig:
    project: ProjectMetadata
    scope: ScopeConfig
    paths: PathsConfig
    sources: SourcesConfig
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def project_id(self) -> str:
        return self.project.id

    @property
    def project_name(self) -> str:
        return self.project.name

    @property
    def project_language(self) -> str:
        return self.project.language


def _require_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Missing or invalid [{key}] section in entropy.config.toml")
    return value


def _optional_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"Section [{key}] must be a table")
    return value


def _list_of_strings(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Field '{key}' must be a string array")
    return value


def load_config(config_path: str | Path) -> ProjectConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    project_section = _require_dict(raw, "project")
    scope_section = _optional_dict(raw, "scope")
    paths_section = _optional_dict(raw, "paths")
    sources_section = _optional_dict(raw, "sources")

    project_id = project_section.get("id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Field [project].id must be a non-empty string")

    project_name = project_section.get("name", project_id)
    if not isinstance(project_name, str) or not project_name.strip():
        raise ValueError("Field [project].name must be a non-empty string when provided")

    project_language = str(project_section.get("language", "java") or "java").strip().lower()
    if not project_language:
        raise ValueError("Field [project].language must be a non-empty string when provided")

    return ProjectConfig(
        project=ProjectMetadata(id=project_id, name=project_name, language=project_language),
        scope=ScopeConfig(
            critical_flows=_list_of_strings(scope_section, "critical_flows"),
            validation_targets=_list_of_strings(scope_section, "validation_targets"),
            required_invariants=_list_of_strings(scope_section, "required_invariants"),
        ),
        paths=PathsConfig(
            architecture=_list_of_strings(paths_section, "architecture"),
            runbooks=_list_of_strings(paths_section, "runbooks"),
            plans=_list_of_strings(paths_section, "plans"),
        ),
        sources=SourcesConfig(
            code_entropy_export=str(sources_section.get("code_entropy_export", "") or ""),
        ),
        raw=raw,
    )
