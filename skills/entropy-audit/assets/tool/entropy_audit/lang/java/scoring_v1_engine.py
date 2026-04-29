from __future__ import annotations

from typing import Any

from entropy_audit.lang.java.scoring_formula import (
    AttrView,
    average,
    coalesce,
    maximum,
    minimum,
    one_minus,
    safe_div,
)


def score_dimension_v1(
    scoring_v1: dict[str, Any],
    dimension: str,
    facts: dict[str, Any],
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(scoring_v1, dict) or not scoring_v1.get("enabled"):
        return None
    dimensions = scoring_v1.get("dimensions", {}) if isinstance(scoring_v1.get("dimensions"), dict) else {}
    dimension_config = dimensions.get(dimension)
    if not isinstance(dimension_config, dict) or not dimension_config.get("enabled"):
        return None

    metric_payload = _evaluate_metrics(dimension_config, facts, details)
    score_breakdown = _score_rules(dimension_config, metric_payload["metrics"])
    return {
        "score": score_breakdown["score"],
        "level": score_breakdown["level"],
        "metrics": metric_payload["metrics"],
        "metric_definitions": metric_payload["definitions"],
        "score_breakdown": score_breakdown,
    }


def _evaluate_metrics(dimension_config: dict[str, Any], facts: dict[str, Any], details: dict[str, Any] | None) -> dict[str, Any]:
    resolved_metrics: dict[str, Any] = {}
    metric_results: dict[str, dict[str, Any]] = {}
    namespace = _formula_namespace(
        {
            "facts": facts if isinstance(facts, dict) else {},
            "details": details if isinstance(details, dict) else {},
            "metrics": resolved_metrics,
        }
    )
    for metric_id, metric_config in (dimension_config.get("metrics", {}) or {}).items():
        if not isinstance(metric_config, dict) or not metric_config.get("enabled", True):
            continue
        raw_value = _evaluate_formula(str(metric_config["formula"]), namespace)
        value = _normalize_metric_value(raw_value, metric_config)
        resolved_metrics[metric_id] = value
        metric_results[metric_id] = {
            "id": metric_id,
            "label": str(metric_config["label"]),
            "category": str(metric_config["category"]),
            "formula": str(metric_config["formula"]),
            "formula_cn": str(metric_config["formula_cn"]),
            "meaning_cn": str(metric_config["meaning_cn"]),
            "unit": str(metric_config["unit"]),
            "round_digits": int(metric_config["round_digits"]),
            "when_missing": str(metric_config["when_missing"]),
            "value": value,
        }
    return {"metrics": resolved_metrics, "definitions": metric_results}


def _score_rules(dimension_config: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    rules = [
        rule
        for rule in dimension_config.get("rules", [])
        if isinstance(rule, dict) and str(rule.get("state", "")).strip().lower() == "scored"
    ]
    total_weight = float(dimension_config.get("scorecard_weight", 0.0) or 0.0)
    internal_scale = float(dimension_config["internal_scale"])
    display_scale = float(dimension_config["display_scale"])
    display_round_digits = int(dimension_config["display_round_digits"])
    coverage_round_digits = int(dimension_config["coverage_round_digits"])

    weighted_score_sum = 0.0
    evaluated_weight = 0.0
    rule_results: list[dict[str, Any]] = []
    for rule in rules:
        result = _score_rule(rule, metrics, total_weight, internal_scale, display_scale)
        rule_results.append(result)
        weighted_score_sum += float(rule["weight"]) * float(result["score_0_100"])
        if not result["skipped"]:
            evaluated_weight += float(rule["weight"])

    score_0_100 = weighted_score_sum / total_weight if total_weight > 0 else 0.0
    display_score = round(score_0_100 * (display_scale / internal_scale), display_round_digits)
    coverage = round(evaluated_weight / total_weight, coverage_round_digits) if total_weight > 0 else 0.0
    display_bands = {
        key: round(float(value) * (display_scale / internal_scale), display_round_digits)
        for key, value in (dimension_config.get("level_bands", {}) or {}).items()
    }
    return {
        "formula_version": str(dimension_config["formula_version"]),
        "score_direction": str(dimension_config["score_direction"]),
        "score_mode": str(dimension_config["aggregation"]),
        "score": display_score,
        "level": _resolve_level(score_0_100, dimension_config.get("level_bands", {})),
        "max_score": display_scale,
        "level_bands": display_bands,
        "internal_score": round(score_0_100, 2),
        "internal_max_score": internal_scale,
        "internal_level_bands": dict(dimension_config.get("level_bands", {})),
        "configured_rule_count": len(rules),
        "evaluated_rule_count": len([item for item in rule_results if not item.get("skipped", False)]),
        "rule_count": len(rules),
        "configured_weight": round(total_weight, 3),
        "available_weight": round(evaluated_weight, 3),
        "coverage": coverage,
        "scorecard_hash": str(dimension_config.get("scorecard_hash", "")),
        "rules": rule_results,
    }


def _score_rule(
    rule: dict[str, Any],
    metrics: dict[str, Any],
    total_weight: float,
    internal_scale: float,
    display_scale: float,
) -> dict[str, Any]:
    metric_name = str(rule["metric"])
    raw_value = metrics.get(metric_name)
    rule_weight = float(rule["weight"])
    matched_condition = "default"
    status = "pass"
    skipped = raw_value is None

    if skipped:
        score_0_100 = float(rule["score_if_missing"])
        matched_condition = "missing"
        status = "missing"
    else:
        score_0_100 = float(rule["score_if_no_match"])
        for band in rule.get("bands", []):
            if _matches(raw_value, str(band.get("op", "")), band.get("value")):
                score_0_100 = float(band.get("score", score_0_100))
                matched_condition = str(band.get("label_cn") or _condition_label(str(band.get("op", "")), band.get("value")))
                status = str(band.get("status", status))
                break

    weight_ratio = rule_weight / total_weight if total_weight > 0 else 0.0
    contribution = round(display_scale * weight_ratio * (score_0_100 / internal_scale), 3)
    max_contribution = round(display_scale * weight_ratio, 3)
    return {
        "id": str(rule["id"]),
        "label": str(rule["label"]),
        "metric": metric_name,
        "category": str(rule["category"]),
        "enabled": True,
        "state": str(rule["state"]),
        "weight": round(rule_weight, 6),
        "raw_value": raw_value,
        "unit": "",
        "direction": str(rule["direction"]),
        "condition": matched_condition,
        "severity": round(score_0_100 / internal_scale, 3),
        "score_0_100": round(score_0_100, 2),
        "contribution": contribution,
        "max_contribution": max_contribution,
        "status": status,
        "skipped": skipped,
        "rule_cn": str(rule.get("rule_cn", "")),
    }


def _resolve_level(score_0_100: float, level_bands: dict[str, Any]) -> str:
    excellent = float(level_bands.get("excellent", 40.0))
    good = float(level_bands.get("good", 60.0))
    warning = float(level_bands.get("warning", 80.0))
    if score_0_100 < excellent:
        return "excellent"
    if score_0_100 < good:
        return "good"
    if score_0_100 < warning:
        return "warning"
    return "danger"


def _normalize_metric_value(raw_value: Any, metric_config: dict[str, Any]) -> Any:
    if raw_value is None:
        if str(metric_config["when_missing"]) == "zero":
            raw_value = 0.0
        else:
            return None
    if isinstance(raw_value, bool):
        raw_value = 1.0 if raw_value else 0.0
    if not isinstance(raw_value, (int, float)):
        return None
    value = float(raw_value)
    round_digits = metric_config.get("round_digits")
    if isinstance(round_digits, int):
        value = round(value, round_digits)
        if round_digits == 0:
            return int(value)
    return value


def _evaluate_formula(expression: str, namespace: dict[str, Any]) -> Any:
    if not expression.strip():
        return None
    try:
        return eval(expression, {"__builtins__": {}}, namespace)
    except Exception:
        return None


def _formula_namespace(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "facts": AttrView(context.get("facts", {})),
        "details": AttrView(context.get("details", {})),
        "metrics": AttrView(context.get("metrics", {})),
        "div": safe_div,
        "avg": average,
        "one_minus": one_minus,
        "coalesce": coalesce,
        "minimum": minimum,
        "maximum": maximum,
    }


def _matches(raw_value: object, op: str, target: object) -> bool:
    if raw_value is None or target is None:
        return False
    try:
        left = float(raw_value)
        right = float(target)
    except (TypeError, ValueError):
        left = raw_value
        right = target
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


def _condition_label(op: str, value: object) -> str:
    return f"{op}{value}"
