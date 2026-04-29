from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass(slots=True)
class ProjectFact:
    project_id: str
    project_root: str
    evaluation_period: str
    config_path: str
    language: str = "java"


@dataclass(slots=True)
class CodeEntropySignal:
    name: str
    score: float | None
    level: str | None
    score_status: str | None = None
    coverage: float | None = None
    missing_rule_ids: list[str] = field(default_factory=list)
    partial_reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    score_breakdown: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    scoring_v1: dict[str, Any] = field(default_factory=dict)
    metric_definitions: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RawFacts:
    project: ProjectFact
    code_entropy: dict[str, CodeEntropySignal] = field(default_factory=dict)
    code_entropy_summary: dict[str, Any] = field(default_factory=dict)
    code_entropy_details: dict[str, Any] = field(default_factory=dict)
    code_entropy_meta: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class NormalizedInputs:
    period: str
    project_facts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoredSnapshot:
    period: str
    project_facts: dict[str, Any] = field(default_factory=dict)
    trend: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    return value
