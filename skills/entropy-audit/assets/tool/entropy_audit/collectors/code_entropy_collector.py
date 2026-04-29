from __future__ import annotations

from pathlib import Path

from entropy_audit.config import ProjectConfig
from entropy_audit.lang import analyze_internal_entropy, build_internal_entropy_export
from entropy_audit.models import CodeEntropySignal, RawFacts
from entropy_audit.utils import read_json_if_exists, resolve_source_path


SUPPORTED_ENTROPIES = ("structure", "semantic", "behavior", "cognition", "style")


def collect_code_entropy_facts(project_root: Path, config: ProjectConfig, raw_facts: RawFacts) -> RawFacts:
    code_entropy_config = config.raw.get("code_entropy")
    if isinstance(code_entropy_config, dict) and code_entropy_config.get("enabled") is False:
        raw_facts.notes.append("Code entropy internal analyzer disabled by [code_entropy].enabled")
        return raw_facts

    source_path = resolve_source_path(project_root, config.sources.code_entropy_export)
    if source_path:
        payload = read_json_if_exists(source_path)
        source_label = f"external export: {source_path}"
    else:
        payload = build_internal_entropy_export(analyze_internal_entropy(project_root, config), config.project_language)
        source_label = f"internal analyzer ({config.project_language})"

    if not isinstance(payload, dict):
        if config.sources.code_entropy_export:
            raw_facts.notes.append("Code entropy export path configured but not readable")
        else:
            raw_facts.notes.append("Code entropy export not provided; code-native entropy signals unavailable")
        return raw_facts

    for entropy_name in SUPPORTED_ENTROPIES:
        item = payload.get(entropy_name)
        if not isinstance(item, dict):
            continue
        raw_facts.code_entropy[entropy_name] = CodeEntropySignal(
            name=entropy_name,
            score=float(item.get("score")) if item.get("score") is not None else None,
            level=str(item.get("level")) if item.get("level") is not None else None,
            score_status=str(item.get("score_status")) if item.get("score_status") is not None else None,
            coverage=float(item.get("coverage")) if item.get("coverage") is not None else None,
            missing_rule_ids=[
                str(rule_id)
                for rule_id in item.get("missing_rule_ids", [])
                if str(rule_id).strip()
            ] if isinstance(item.get("missing_rule_ids"), list) else [],
            partial_reason=str(item.get("partial_reason")) if item.get("partial_reason") is not None else None,
            details=item.get("details") if isinstance(item.get("details"), dict) else {},
            score_breakdown=item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {},
            metrics=item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
            facts=item.get("facts") if isinstance(item.get("facts"), dict) else {},
            scoring_v1=item.get("scoring_v1") if isinstance(item.get("scoring_v1"), dict) else {},
            metric_definitions=item.get("metric_definitions") if isinstance(item.get("metric_definitions"), dict) else {},
        )

    summary = payload.get("summary")
    if isinstance(summary, dict):
        raw_facts.code_entropy_summary = summary
        raw_facts.notes.append(
            "Code entropy total entropy / derived health: "
            f"{summary.get('total_entropy_score', 'unknown')} / {summary.get('health_score', 'unknown')}"
        )
    details_export = payload.get("details_export")
    if isinstance(details_export, dict):
        raw_facts.code_entropy_details = details_export
    meta = payload.get("meta")
    if isinstance(meta, dict):
        raw_facts.code_entropy_meta = meta
    raw_facts.notes.append(f"Code entropy source: {source_label}")
    return raw_facts
