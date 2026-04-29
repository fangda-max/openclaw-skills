from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from entropy_audit.config import ProjectConfig


@dataclass(slots=True)
class LanguageScaffold:
    config_text: str
    calibration_text: str
    notes: list[str] = field(default_factory=list)


class LanguageAdapter(ABC):
    name: str

    @abstractmethod
    def detect(self, project_root: Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def analyze(self, project_root: Path, project_config: ProjectConfig) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def build_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def scaffold_project(self, project_root: Path, project_id: str, project_name: str) -> LanguageScaffold:
        raise NotImplementedError

