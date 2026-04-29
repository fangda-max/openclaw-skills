#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Code entropy summary calculation."""

from __future__ import annotations

from typing import Any, Dict


SUPPORTED_ENTROPIES = ("structure", "semantic", "behavior", "cognition", "style")


class EntropyCalculator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.scoring_v1_config = config.get("scoring_v1", {}) if isinstance(config.get("scoring_v1"), dict) else {}
        self.weights = self._require_dict(config.get("weights"), "monitor.weights")
        self.score_models = self._require_dict(config.get("score_models"), "monitor.score_models")
        self.health_model_config = self._require_dict(self.score_models.get("health"), "monitor.score_models.health")
        self.health_formula_version = self._require_string(
            self.health_model_config.get("formula_version"),
            "monitor.score_models.health.formula_version",
        )
        self.health_entropy_scale = self._require_number(
            self.health_model_config.get("entropy_score_scale"),
            "monitor.score_models.health.entropy_score_scale",
            minimum=1e-9,
        )
        self.health_output_scale = self._require_number(
            self.health_model_config.get("output_scale"),
            "monitor.score_models.health.output_scale",
            minimum=1e-9,
        )
        self.health_normalize_weights = self._require_bool(
            self.health_model_config.get("normalize_weights"),
            "monitor.score_models.health.normalize_weights",
        )
        self.health_invert_scores = self._require_bool(
            self.health_model_config.get("invert_scores"),
            "monitor.score_models.health.invert_scores",
        )
        self.health_round_digits = int(
            self._require_number(
                self.health_model_config.get("round_digits"),
                "monitor.score_models.health.round_digits",
                minimum=0,
                integer=True,
            )
        )
        self.total_entropy_bands = self._resolve_total_entropy_bands()
        thresholds = config.get("thresholds", {}) if isinstance(config.get("thresholds"), dict) else {}
        self.health_excellent = self._number_or_default(thresholds.get("health_score_excellent"), 60.0)
        self.health_good = self._number_or_default(thresholds.get("health_score_good"), 40.0)
        self.health_warning = self._number_or_default(thresholds.get("health_score_warning"), 20.0)

    def calculate_summary(
        self,
        results: Dict[str, Any],
        trend: Dict[str, Any] | None = None,
        reference_payloads: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        structure_score = self._score_of(results, "structure")
        semantic_score = self._score_of(results, "semantic")
        behavior_score = self._score_of(results, "behavior")
        cognition_score = self._score_of(results, "cognition")
        style_score = self._score_of(results, "style")
        entropy_scores = {
            "structure": structure_score,
            "semantic": semantic_score,
            "behavior": behavior_score,
            "cognition": cognition_score,
            "style": style_score,
        }
        total_entropy_score = self._calculate_total_entropy_score(entropy_scores)
        total_entropy_level, total_entropy_icon = self._entropy_state(total_entropy_score)
        health_score = self._calculate_health_score(entropy_scores)
        health_level, health_icon = self._health_state(health_score)
        partial_dimensions: list[dict[str, Any]] = []
        dimension_statuses: dict[str, Any] = {}
        for name in SUPPORTED_ENTROPIES:
            item = results.get(name, {}) if isinstance(results.get(name), dict) else {}
            score_status = str(item.get("score_status", "complete") or "complete")
            coverage = item.get("coverage")
            missing_rule_ids = item.get("missing_rule_ids", [])
            partial_reason = item.get("partial_reason")
            dimension_statuses[name] = {
                "score_status": score_status,
                "coverage": coverage,
                "missing_rule_ids": list(missing_rule_ids) if isinstance(missing_rule_ids, list) else [],
                "partial_reason": partial_reason,
            }
            if score_status == "partial":
                partial_dimensions.append(
                    {
                        "dimension": name,
                        "coverage": coverage,
                        "missing_rule_ids": list(missing_rule_ids) if isinstance(missing_rule_ids, list) else [],
                        "reason": partial_reason,
                    }
                )

        return {
            "total_entropy_score": total_entropy_score,
            "total_entropy_level": total_entropy_level,
            "total_entropy_icon": total_entropy_icon,
            "health_score": health_score,
            "health_level": health_level,
            "health_icon": health_icon,
            "derived_health_formula": "100 - total_entropy_score",
            "formula_version": self.health_formula_version,
            "score_status": "partial" if partial_dimensions else "complete",
            "partial_dimensions": partial_dimensions,
            "partial_reason": "；".join(
                str(item.get("reason")).strip()
                for item in partial_dimensions
                if str(item.get("reason", "")).strip()
            ) or None,
            "dimension_statuses": dimension_statuses,
            "entropy_scores": {name: round(score, 1) for name, score in entropy_scores.items()},
            "entropy_weights": self._normalized_entropy_weights(),
            "statistics": self._build_statistics(results),
        }

    def _score_of(self, results: Dict[str, Any], key: str) -> float:
        value = results.get(key, {}).get("score")
        return float(value) if isinstance(value, (int, float)) else 0.0

    def _build_statistics(self, results: Dict[str, Any]) -> Dict[str, Any]:
        structure = results.get("structure", {}).get("details", {}) if isinstance(results.get("structure"), dict) else {}
        cognition = results.get("cognition", {}).get("details", {}) if isinstance(results.get("cognition"), dict) else {}
        return {
            "total_files": int(structure.get("total_files", 0) or 0),
            "total_todos": int(cognition.get("todo_count", 0) or 0),
            "common_files": int(structure.get("common_files", 0) or 0),
            "shared_bucket_total": int(structure.get("shared_bucket_total", structure.get("common_files", 0) or 0) or 0),
        }

    def _normalized_entropy_weights(self) -> Dict[str, float]:
        raw_weights = {
            name: float(self.weights.get(f"{name}_entropy", 0.0) or 0.0)
            for name in SUPPORTED_ENTROPIES
        }
        total = sum(weight for weight in raw_weights.values() if weight > 0)
        if total <= 0:
            return {name: 0.0 for name in SUPPORTED_ENTROPIES}
        return {name: round(max(0.0, weight) / total, 4) for name, weight in raw_weights.items()}

    def _calculate_total_entropy_score(self, entropy_scores: Dict[str, float]) -> float:
        weighted_sum = 0.0
        total_weight = 0.0
        for name in SUPPORTED_ENTROPIES:
            weight = self._require_number(self.weights.get(f"{name}_entropy"), f"monitor.weights.{name}_entropy", minimum=0.0)
            if weight <= 0:
                continue
            score = float(entropy_scores.get(name, 0.0) or 0.0)
            normalized_score = max(0.0, min(score, self.health_entropy_scale))
            weighted_sum += normalized_score * weight
            total_weight += weight

        if self.health_normalize_weights and total_weight > 0:
            weighted_sum /= total_weight
        total_entropy_score = weighted_sum * (self.health_output_scale / self.health_entropy_scale)
        return round(total_entropy_score, self.health_round_digits)

    def _calculate_health_score(self, entropy_scores: Dict[str, float]) -> float:
        total_entropy_score = self._calculate_total_entropy_score(entropy_scores)
        if self.health_invert_scores:
            derived = self.health_output_scale - total_entropy_score
        else:
            derived = total_entropy_score
        return round(max(0.0, min(derived, self.health_output_scale)), self.health_round_digits)

    def _health_state(self, health_score: float) -> tuple[str, str]:
        if health_score >= self.health_excellent:
            return "excellent", "🟢"
        if health_score >= self.health_good:
            return "good", "🟡"
        if health_score >= self.health_warning:
            return "warning", "⚠️"
        return "danger", "🔴"

    def _entropy_state(self, entropy_score: float) -> tuple[str, str]:
        excellent = float(self.total_entropy_bands["excellent"])
        good = float(self.total_entropy_bands["good"])
        warning = float(self.total_entropy_bands["warning"])
        if entropy_score < excellent:
            return "excellent", "🟢"
        if entropy_score < good:
            return "good", "🟡"
        if entropy_score < warning:
            return "warning", "⚠️"
        return "danger", "🔴"

    def _resolve_total_entropy_bands(self) -> Dict[str, float]:
        dimensions = self.scoring_v1_config.get("dimensions", {}) if isinstance(self.scoring_v1_config.get("dimensions"), dict) else {}
        for name in SUPPORTED_ENTROPIES:
            dimension = dimensions.get(name)
            if not isinstance(dimension, dict):
                continue
            bands = dimension.get("level_bands")
            if not isinstance(bands, dict):
                continue
            try:
                excellent = float(bands.get("excellent"))
                good = float(bands.get("good"))
                warning = float(bands.get("warning"))
            except (TypeError, ValueError):
                continue
            if excellent < good < warning:
                return {"excellent": excellent, "good": good, "warning": warning}
        return {"excellent": 40.0, "good": 60.0, "warning": 80.0}

    def _number_or_default(self, value: Any, default: float) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return default

    def _require_dict(self, value: Any, path: str) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(f"Missing or invalid {path} section for EntropyCalculator")
        return value

    def _require_string(self, value: Any, path: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path} must be a non-empty string for EntropyCalculator")
        return value.strip()

    def _require_bool(self, value: Any, path: str) -> bool:
        if not isinstance(value, bool):
            raise ValueError(f"{path} must be true or false for EntropyCalculator")
        return value

    def _require_number(self, value: Any, path: str, minimum: float | None = None, integer: bool = False) -> float | int:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path} must be a number for EntropyCalculator")
        normalized = int(value) if integer else float(value)
        if minimum is not None and normalized < minimum:
            raise ValueError(f"{path} must be >= {minimum} for EntropyCalculator")
        return normalized
