from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tomllib
from typing import Any


SUPPORTED_DIMENSIONS = ("structure", "semantic", "behavior", "cognition", "style")
VALID_RULE_CATEGORIES = {"general", "custom"}
VALID_WHEN_MISSING = {"null", "zero"}
VALID_RULE_STATES = {"scored", "disabled", "experimental"}
VALID_SCORE_DIRECTIONS = {"higher_is_worse", "lower_is_worse"}
VALID_AGGREGATIONS = {"fixed_weighted_average"}


def load_scoring_v1(project_root: Path) -> dict[str, Any] | None:
    path = project_root / "entropy.config.toml"
    if not path.exists():
        return None
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    root = raw.get("code_entropy", {}) if isinstance(raw, dict) else {}
    if not isinstance(root, dict):
        raise ValueError("Missing [code_entropy.scoring_v1] section in entropy.config.toml")
    scoring_v1 = root.get("scoring_v1")
    return build_scoring_v1(scoring_v1, source_path=path)


def build_scoring_v1(raw_scoring_v1: object, *, source_path: Path | None = None) -> dict[str, Any]:
    if not isinstance(raw_scoring_v1, dict) or not raw_scoring_v1:
        raise ValueError("Missing or invalid [code_entropy.scoring_v1] section in entropy.config.toml")
    normalized = deepcopy(raw_scoring_v1)
    normalized["enabled"] = _require_bool(normalized, "enabled", "[code_entropy.scoring_v1]")
    normalized["schema_version"] = _require_string(normalized, "schema_version", "[code_entropy.scoring_v1]")
    normalized["formula_version"] = _require_string(normalized, "formula_version", "[code_entropy.scoring_v1]")
    migrated_dimensions = _require_string_list(
        normalized.get("migrated_dimensions"),
        "[code_entropy.scoring_v1].migrated_dimensions",
    )
    invalid_dimensions = [name for name in migrated_dimensions if name not in SUPPORTED_DIMENSIONS]
    if invalid_dimensions:
        raise ValueError(f"Unsupported scoring_v1 migrated dimensions: {', '.join(invalid_dimensions)}")
    normalized["migrated_dimensions"] = migrated_dimensions

    defaults = _require_dict(normalized.get("defaults"), "[code_entropy.scoring_v1.defaults]")
    normalized_defaults = {
        "internal_scale": float(_require_number(defaults, "internal_scale", "[code_entropy.scoring_v1.defaults]", minimum=1e-9)),
        "display_scale": float(_require_number(defaults, "display_scale", "[code_entropy.scoring_v1.defaults]", minimum=1e-9)),
        "display_round_digits": int(_require_number(defaults, "display_round_digits", "[code_entropy.scoring_v1.defaults]", integer=True, minimum=0)),
        "coverage_round_digits": int(_require_number(defaults, "coverage_round_digits", "[code_entropy.scoring_v1.defaults]", integer=True, minimum=0)),
        "score_direction": _require_string(
            defaults,
            "score_direction",
            "[code_entropy.scoring_v1.defaults]",
            allowed=VALID_SCORE_DIRECTIONS,
        ).lower(),
        "aggregation": _require_string(
            defaults,
            "aggregation",
            "[code_entropy.scoring_v1.defaults]",
            allowed=VALID_AGGREGATIONS,
        ).lower(),
    }
    normalized["defaults"] = normalized_defaults

    raw_dimensions = _require_dict(normalized.get("dimensions"), "[code_entropy.scoring_v1.dimensions]")
    dimensions: dict[str, dict[str, Any]] = {}
    for name in migrated_dimensions:
        dimension_raw = _require_dict(raw_dimensions.get(name), f"[code_entropy.scoring_v1.dimensions.{name}]")
        dimensions[name] = _normalize_dimension(name, dimension_raw, normalized_defaults)
    normalized["dimensions"] = dimensions
    normalized["source_path"] = str(source_path) if source_path else None
    return refresh_scoring_v1_metadata(normalized)


def refresh_scoring_v1_metadata(scoring_v1: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(scoring_v1, dict):
        return {}
    dimensions = scoring_v1.get("dimensions", {})
    if isinstance(dimensions, dict):
        for name, dimension_config in dimensions.items():
            if not isinstance(dimension_config, dict):
                continue
            rules = [
                rule
                for rule in dimension_config.get("rules", [])
                if isinstance(rule, dict)
            ]
            scorecard_weight = sum(float(rule.get("weight", 0.0) or 0.0) for rule in rules if str(rule.get("state", "")).strip().lower() == "scored")
            dimension_config["scorecard_weight"] = round(scorecard_weight, 6)
            dimension_config["scorecard_hash"] = _stable_hash(
                {
                    "label": dimension_config.get("label"),
                    "formula_version": dimension_config.get("formula_version"),
                    "internal_scale": dimension_config.get("internal_scale"),
                    "display_scale": dimension_config.get("display_scale"),
                    "level_bands": dimension_config.get("level_bands"),
                    "metrics": dimension_config.get("metrics"),
                    "rules": rules,
                }
            )
            dimensions[name] = dimension_config
        scoring_v1["dimensions"] = dimensions
    scoring_v1["config_hash"] = _stable_hash(
        {
            "schema_version": scoring_v1.get("schema_version"),
            "formula_version": scoring_v1.get("formula_version"),
            "migrated_dimensions": scoring_v1.get("migrated_dimensions"),
            "defaults": scoring_v1.get("defaults"),
            "dimensions": scoring_v1.get("dimensions"),
        }
    )
    return scoring_v1


def _normalize_dimension(name: str, raw_dimension: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(raw_dimension)
    normalized["label"] = _require_string(normalized, "label", f"[code_entropy.scoring_v1.dimensions.{name}]")
    normalized["enabled"] = _require_bool(normalized, "enabled", f"[code_entropy.scoring_v1.dimensions.{name}]")
    normalized["formula_version"] = _require_string(normalized, "formula_version", f"[code_entropy.scoring_v1.dimensions.{name}]")
    normalized["internal_scale"] = float(normalized.get("internal_scale", defaults["internal_scale"]))
    normalized["display_scale"] = float(normalized.get("display_scale", defaults["display_scale"]))
    normalized["display_round_digits"] = int(normalized.get("display_round_digits", defaults["display_round_digits"]))
    normalized["coverage_round_digits"] = int(normalized.get("coverage_round_digits", defaults["coverage_round_digits"]))
    normalized["score_direction"] = str(normalized.get("score_direction", defaults["score_direction"])).strip().lower()
    if normalized["score_direction"] not in VALID_SCORE_DIRECTIONS:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{name}].score_direction is invalid")
    normalized["aggregation"] = str(normalized.get("aggregation", defaults["aggregation"])).strip().lower()
    if normalized["aggregation"] not in VALID_AGGREGATIONS:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{name}].aggregation is invalid")

    level_bands = _require_dict(normalized.get("level_bands"), f"[code_entropy.scoring_v1.dimensions.{name}.level_bands]")
    excellent = float(_require_number(level_bands, "excellent", f"[code_entropy.scoring_v1.dimensions.{name}.level_bands]"))
    good = float(_require_number(level_bands, "good", f"[code_entropy.scoring_v1.dimensions.{name}.level_bands]"))
    warning = float(_require_number(level_bands, "warning", f"[code_entropy.scoring_v1.dimensions.{name}.level_bands]"))
    if not excellent < good < warning:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{name}.level_bands] must satisfy excellent < good < warning")
    normalized["level_bands"] = {"excellent": excellent, "good": good, "warning": warning}

    metrics_raw = _require_dict(normalized.get("metrics"), f"[code_entropy.scoring_v1.dimensions.{name}.metrics]")
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric_raw in metrics_raw.items():
        if isinstance(metric_raw, dict):
            metrics[str(metric_id).strip()] = _normalize_metric(metric_id, metric_raw, name)
    normalized["metrics"] = metrics

    rules_raw = normalized.get("rules", [])
    if not isinstance(rules_raw, list) or not rules_raw:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{name}.rules] must be a non-empty array of tables")
    rules = [_normalize_rule(rule, name, metrics) for rule in rules_raw if isinstance(rule, dict)]
    scorecard_weight = sum(float(rule["weight"]) for rule in rules if rule["state"] == "scored")
    if scorecard_weight <= 0:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{name}] must provide at least one scored rule")
    normalized["rules"] = rules
    normalized["scorecard_weight"] = round(scorecard_weight, 6)
    normalized["scorecard_hash"] = _stable_hash(
        {
            "label": normalized["label"],
            "formula_version": normalized["formula_version"],
            "internal_scale": normalized["internal_scale"],
            "display_scale": normalized["display_scale"],
            "level_bands": normalized["level_bands"],
            "metrics": metrics,
            "rules": rules,
        }
    )
    return normalized


def _normalize_metric(metric_id: str, raw_metric: dict[str, Any], dimension: str) -> dict[str, Any]:
    normalized = deepcopy(raw_metric)
    category = _require_string(
        normalized,
        "category",
        f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]",
    ).lower()
    if category not in VALID_RULE_CATEGORIES:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}].category must be general/custom")
    when_missing = _require_string(
        normalized,
        "when_missing",
        f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]",
    ).lower()
    if when_missing not in VALID_WHEN_MISSING:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}].when_missing must be null/zero")
    return {
        "id": str(metric_id).strip(),
        "label": _require_string(normalized, "label", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "category": category,
        "enabled": _require_bool(normalized, "enabled", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "formula": _require_string(normalized, "formula", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "formula_cn": _require_string(normalized, "formula_cn", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "meaning_cn": _require_string(normalized, "meaning_cn", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "unit": _require_string(normalized, "unit", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]"),
        "round_digits": int(_require_number(normalized, "round_digits", f"[code_entropy.scoring_v1.dimensions.{dimension}.metrics.{metric_id}]", integer=True, minimum=0)),
        "when_missing": when_missing,
    }


def _normalize_rule(rule: dict[str, Any], dimension: str, metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    normalized = deepcopy(rule)
    rule_id = _require_string(normalized, "id", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]")
    metric_name = _require_string(normalized, "metric", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]")
    if metric_name not in metrics:
        raise ValueError(f"Unknown scoring_v1 metric '{metric_name}' referenced by rule '{rule_id}'")
    category = _require_string(normalized, "category", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]").lower()
    if category not in VALID_RULE_CATEGORIES:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{dimension}.rules].category must be general/custom")
    state = _require_string(normalized, "state", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]").lower()
    if state not in VALID_RULE_STATES:
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{dimension}.rules].state must be scored/disabled/experimental")
    direction = _require_string(
        normalized,
        "direction",
        f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]",
        allowed=VALID_SCORE_DIRECTIONS,
    ).lower()
    bands = normalized.get("bands", [])
    if not isinstance(bands, list):
        raise ValueError(f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands] must be an array of tables")
    return {
        "id": rule_id,
        "label": _require_string(normalized, "label", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]"),
        "category": category,
        "state": state,
        "metric": metric_name,
        "weight": float(_require_number(normalized, "weight", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]", minimum=0.0)),
        "direction": direction,
        "score_if_no_match": float(_require_number(normalized, "score_if_no_match", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]", minimum=0.0)),
        "score_if_missing": float(_require_number(normalized, "score_if_missing", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]", minimum=0.0)),
        "rule_cn": _require_string(normalized, "rule_cn", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules]"),
        "bands": [_normalize_band(band, dimension, rule_id) for band in bands if isinstance(band, dict)],
    }


def _normalize_band(band: dict[str, Any], dimension: str, rule_id: str) -> dict[str, Any]:
    normalized = deepcopy(band)
    return {
        "op": _require_string(normalized, "op", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands]"),
        "value": _require_number(normalized, "value", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands]"),
        "score": float(_require_number(normalized, "score", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands]", minimum=0.0)),
        "status": _require_string(normalized, "status", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands]"),
        "label_cn": _require_string(normalized, "label_cn", f"[code_entropy.scoring_v1.dimensions.{dimension}.rules[{rule_id}].bands]"),
    }


def _stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _require_dict(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Missing or invalid {path} section in entropy.config.toml")
    return value


def _require_string(data: dict[str, Any], key: str, path: str, *, allowed: set[str] | None = None) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string in entropy.config.toml")
    normalized = value.strip()
    if allowed is not None and normalized.lower() not in {item.lower() for item in allowed}:
        allowed_text = ", ".join(sorted(allowed))
        raise ValueError(f"{path}.{key} must be one of: {allowed_text}")
    return normalized


def _require_bool(data: dict[str, Any], key: str, path: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{path}.{key} must be true or false in entropy.config.toml")
    return value


def _require_number(
    data: dict[str, Any],
    key: str,
    path: str,
    *,
    integer: bool = False,
    minimum: float | None = None,
) -> float | int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}.{key} must be a number in entropy.config.toml")
    result = int(value) if integer else float(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{path}.{key} must be >= {minimum}")
    return result


def _require_string_list(value: object, path: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty string array in entropy.config.toml")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path} must contain only non-empty strings in entropy.config.toml")
        normalized.append(item.strip())
    return normalized
