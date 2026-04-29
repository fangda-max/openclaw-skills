from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import re
from typing import Any

from entropy_audit.collectors import collect_code_entropy_facts
from entropy_audit.calibration import load_calibration
from entropy_audit.config import load_config
from entropy_audit.lang import detect_language, get_language_adapter, supported_languages
from entropy_audit.models import NormalizedInputs, ProjectFact, RawFacts, ScoredSnapshot, to_dict
from entropy_audit.reporter import (
    build_code_entropy_detail_exports,
    render_code_entropy_detail_pages,
    render_html_dashboard,
    render_rule_catalog,
)
from entropy_audit.utils import ensure_directory, read_json_if_exists, write_json


def _project_slug(project_root: Path) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", project_root.name).strip("-").lower()
    return slug or "java-project"


def _resolve_config_path(project_root: Path, config_path: Path | None) -> Path:
    target = config_path if config_path is not None else project_root / "entropy.config.toml"
    return target if target.is_absolute() else target.resolve()


def _resolve_calibration_path(project_root: Path, calibration_path: Path | None) -> Path:
    target = calibration_path if calibration_path is not None else project_root / "entropy.calibration.toml"
    return target if target.is_absolute() else target.resolve()


def _load_manual_flags(calibration_path: Path | None) -> tuple[dict[str, Any], list[str]]:
    if not calibration_path or not calibration_path.exists():
        return {}, []

    payload = load_calibration(calibration_path)
    flags = payload.get("flags", {})
    notes = []
    exclusions = payload.get("exclusions", {})
    for key, value in exclusions.items():
        notes.append(f"manual exclusion {key}: {value}")
    return flags, notes



def _dedupe_notes(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _code_entropy_results_from_project_facts(project_facts: dict[str, Any]) -> dict[str, Any]:
    code_entropy = project_facts.get("code_entropy", {}) if isinstance(project_facts.get("code_entropy"), dict) else {}
    results: dict[str, Any] = {}
    for key, value in code_entropy.items():
        if not isinstance(value, dict):
            continue
        results[str(key)] = {
            "score": value.get("score"),
            "level": value.get("level"),
            "score_status": value.get("score_status"),
            "coverage": value.get("coverage"),
            "missing_rule_ids": value.get("missing_rule_ids"),
            "partial_reason": value.get("partial_reason"),
            "details": value.get("details") if isinstance(value.get("details"), dict) else {},
            "metrics": value.get("metrics") if isinstance(value.get("metrics"), dict) else {},
            "facts": value.get("facts") if isinstance(value.get("facts"), dict) else {},
            "score_breakdown": value.get("score_breakdown") if isinstance(value.get("score_breakdown"), dict) else {},
            "scoring_v1": value.get("scoring_v1") if isinstance(value.get("scoring_v1"), dict) else {},
            "metric_definitions": value.get("metric_definitions") if isinstance(value.get("metric_definitions"), dict) else {},
        }
    return results



def _rewrite_code_entropy_export(snapshot: ScoredSnapshot, out_dir: Path) -> None:
    if not isinstance(snapshot.project_facts, dict):
        return

    results = _code_entropy_results_from_project_facts(snapshot.project_facts)
    if not results:
        return

    export_path = out_dir / "code_entropy_export.json"
    existing_export = read_json_if_exists(export_path)
    if not isinstance(existing_export, dict):
        existing_export = {}

    timestamp = str(snapshot.trend.get("generated_at", "") or "") if isinstance(snapshot.trend, dict) else ""
    timestamp = timestamp or datetime.now().astimezone().isoformat()
    export: dict[str, Any] = dict(results)
    summary = snapshot.project_facts.get("code_entropy_summary")
    if isinstance(summary, dict):
        export["summary"] = summary
    meta = snapshot.project_facts.get("code_entropy_meta")
    if isinstance(meta, dict):
        export["meta"] = meta
    if snapshot.project_facts.get("code_entropy_details_file"):
        export["details_file"] = snapshot.project_facts.get("code_entropy_details_file")
    if isinstance(snapshot.trend, dict) and snapshot.trend:
        export["trend"] = snapshot.trend
    export["timestamp"] = timestamp
    export["date"] = timestamp[:10]
    export["source"] = existing_export.get("source") or f"entropy_audit.lang.{snapshot.project_facts.get('project_language', 'java')}.internal_entropy"
    write_json(export_path, export)


def _write_rule_catalog(config_target: Path, config_payload: dict[str, Any]) -> Path:
    catalog_target = config_target.with_name("rule_catalog.html")
    ensure_directory(catalog_target.parent)
    catalog_tmp = catalog_target.with_name(f"{catalog_target.name}.tmp")
    catalog_tmp.write_text(render_rule_catalog(config_payload, source_path=config_target), encoding="utf-8")
    catalog_tmp.replace(catalog_target)
    return catalog_target


def init_project(project_root: Path, language: str, config_path: Path | None, calibration_path: Path | None, force: bool = False) -> tuple[Path, Path, list[str]]:
    project_root = project_root.resolve()
    chosen_language = detect_language(project_root) if language == "auto" else language
    adapter = get_language_adapter(chosen_language)
    config_target = _resolve_config_path(project_root, config_path)
    calibration_target = _resolve_calibration_path(project_root, calibration_path)
    existing_targets = [target for target in (config_target, calibration_target) if target.exists()]
    if existing_targets and not force:
        if config_target.exists():
            validated_config = load_config(config_target)
            catalog_target = _write_rule_catalog(config_target, validated_config.raw)
            return config_target, calibration_target, [
                f"Existing config detected; generated rule catalog without overwriting config: {catalog_target}",
            ]
        joined = ", ".join(str(target) for target in existing_targets)
        raise FileExistsError(f"Refusing to overwrite existing files: {joined}. Use --force to replace them.")

    scaffold = adapter.scaffold_project(project_root, _project_slug(project_root), project_root.name or "Java Project")
    ensure_directory(config_target.parent)
    ensure_directory(calibration_target.parent)
    generated_at = datetime.now().astimezone().isoformat()
    config_tmp = config_target.with_name(f"{config_target.name}.tmp")
    calibration_tmp = calibration_target.with_name(f"{calibration_target.name}.tmp")
    catalog_target = config_target.with_name("rule_catalog.html")
    catalog_tmp = catalog_target.with_name(f"{catalog_target.name}.tmp")
    config_tmp.write_text(scaffold.config_text, encoding="utf-8")
    calibration_tmp.write_text(
        scaffold.calibration_text.replace("{{CALIBRATION_GENERATED_AT}}", f'"{generated_at}"'),
        encoding="utf-8",
    )
    try:
        validated_config = load_config(config_tmp)
        load_calibration(calibration_tmp)
        if chosen_language == "java":
            from entropy_audit.lang.java.runner import build_monitor_config

            build_monitor_config(project_root, validated_config)
        catalog_tmp.write_text(render_rule_catalog(validated_config.raw, source_path=config_target), encoding="utf-8")
    except Exception:
        for candidate in (config_tmp, calibration_tmp, catalog_tmp):
            if candidate.exists():
                candidate.unlink()
        raise
    config_tmp.replace(config_target)
    calibration_tmp.replace(calibration_target)
    catalog_tmp.replace(catalog_target)
    return config_target, calibration_target, scaffold.notes


def collect(
    project_root: Path,
    config_path: Path | None,
    calibration_path: Path | None,
    period: str,
    out_dir: Path,
) -> tuple[RawFacts, NormalizedInputs]:
    project_root = project_root.resolve()
    config_path = _resolve_config_path(project_root, config_path)
    config = load_config(config_path)
    _manual_flags, calibration_notes = _load_manual_flags(
        _resolve_calibration_path(project_root, calibration_path) if calibration_path else None
    )
    raw_facts = RawFacts(
        project=ProjectFact(
            project_id=config.project_id,
            project_root=str(project_root),
            evaluation_period=period,
            config_path=str(config_path),
            language=config.project_language,
        )
    )
    raw_facts = collect_code_entropy_facts(project_root, config, raw_facts)

    project_facts = {
        "project_id": raw_facts.project.project_id,
        "project_root": raw_facts.project.project_root,
        "project_language": raw_facts.project.language,
        "config_path": raw_facts.project.config_path,
        "code_entropy": to_dict(raw_facts.code_entropy),
        "code_entropy_summary": to_dict(raw_facts.code_entropy_summary),
        "code_entropy_details_file": "code_entropy_details.json" if raw_facts.code_entropy_details else "",
        "code_entropy_meta": to_dict(raw_facts.code_entropy_meta),
    }
    normalized = NormalizedInputs(
        period=period,
        project_facts=project_facts,
        notes=_dedupe_notes(list(raw_facts.notes) + calibration_notes),
    )

    ensure_directory(out_dir)
    write_json(out_dir / "raw_facts.json", to_dict(raw_facts))
    write_json(out_dir / "normalized_inputs.json", to_dict(normalized))
    if raw_facts.code_entropy:
        code_entropy_export = {
            **to_dict(raw_facts.code_entropy),
            "summary": to_dict(raw_facts.code_entropy_summary),
            "meta": to_dict(raw_facts.code_entropy_meta),
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "source": f"entropy_audit.lang.{config.project_language}.internal_entropy",
            "details_file": "code_entropy_details.json" if raw_facts.code_entropy_details else "",
        }
        write_json(out_dir / "code_entropy_export.json", code_entropy_export)
    if raw_facts.code_entropy_details:
        write_json(out_dir / "code_entropy_details.json", to_dict(raw_facts.code_entropy_details))
    return raw_facts, normalized


def score(inputs_path: Path, calibration_path: Path | None, out_dir: Path, config_path: Path | None = None) -> ScoredSnapshot:
    normalized_payload = read_json_if_exists(inputs_path)
    if not isinstance(normalized_payload, dict):
        raise ValueError("normalized_inputs.json is missing or invalid")

    notes = normalized_payload.get("notes", [])
    if not isinstance(notes, list):
        notes = []
    snapshot = ScoredSnapshot(
        period=str(normalized_payload.get("period", "unknown")),
        project_facts=normalized_payload.get("project_facts", {}) if isinstance(normalized_payload.get("project_facts"), dict) else {},
        notes=_dedupe_notes([str(note) for note in notes]),
    )
    ensure_directory(out_dir)
    write_json(out_dir / "metrics.json", to_dict(snapshot))
    _rewrite_code_entropy_export(snapshot, out_dir)
    return snapshot


def _cleanup_legacy_report_outputs(out_dir: Path) -> None:
    for filename in ("monthly-entropy-report.md", "quarterly-entropy-report.md"):
        target = out_dir / filename
        if target.exists():
            target.unlink()


def report(metrics_path: Path, period: str, mode: str, out_dir: Path) -> Path:
    ensure_directory(out_dir)
    _cleanup_legacy_report_outputs(out_dir)
    payload = read_json_if_exists(metrics_path)
    if not isinstance(payload, dict):
        raise ValueError("metrics.json is missing or invalid")
    snapshot = ScoredSnapshot(
        period=payload.get("period", period),
        project_facts=payload.get("project_facts", {}) if isinstance(payload.get("project_facts"), dict) else {},
        trend=payload.get("trend", {}) if isinstance(payload.get("trend"), dict) else {},
        notes=payload.get("notes", []) if isinstance(payload.get("notes"), list) else [],
    )

    full_code_entropy_details = {}
    details_file = snapshot.project_facts.get("code_entropy_details_file", "")
    if isinstance(details_file, str) and details_file:
        maybe_details = read_json_if_exists(out_dir / details_file)
        if isinstance(maybe_details, dict):
            full_code_entropy_details = maybe_details

    detail_dir = out_dir / "code-entropy-details"
    ensure_directory(detail_dir)
    for key, payload in build_code_entropy_detail_exports(snapshot, full_code_entropy_details).items():
        write_json(detail_dir / f"{key}.json", payload)
    for key, content in render_code_entropy_detail_pages(snapshot, full_code_entropy_details).items():
        (detail_dir / f"{key}.html").write_text(content, encoding="utf-8")

    html_content = render_html_dashboard(snapshot)
    html_target = out_dir / "entropy-dashboard.html"
    html_target.write_text(html_content, encoding="utf-8")
    return html_target


def run_pipeline(project_root: Path, config_path: Path | None, calibration_path: Path | None, period: str, mode: str, out_dir: Path) -> None:
    collect(project_root, config_path, calibration_path, period, out_dir)
    score(out_dir / "normalized_inputs.json", calibration_path, out_dir, config_path=config_path)
    report(out_dir / "metrics.json", period, mode, out_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Code entropy audit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--project-root", required=True)
    init_parser.add_argument("--language", choices=["auto", *supported_languages()], default="auto")
    init_parser.add_argument("--config-path")
    init_parser.add_argument("--calibration-path")
    init_parser.add_argument("--force", action="store_true")

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--project-root", required=True)
    collect_parser.add_argument("--config")
    collect_parser.add_argument("--calibration")
    collect_parser.add_argument("--period", required=True)
    collect_parser.add_argument("--out-dir", required=True)

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--inputs", required=True)
    score_parser.add_argument("--config")
    score_parser.add_argument("--calibration")
    score_parser.add_argument("--out-dir", required=True)

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--metrics", required=True)
    report_parser.add_argument("--period", required=True)
    report_parser.add_argument("--mode", choices=["monthly", "quarterly"], required=True)
    report_parser.add_argument("--out-dir", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--project-root", required=True)
    run_parser.add_argument("--config")
    run_parser.add_argument("--calibration")
    run_parser.add_argument("--period", required=True)
    run_parser.add_argument("--mode", choices=["monthly", "quarterly"], required=True)
    run_parser.add_argument("--out-dir", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init":
        init_project(
            Path(args.project_root),
            args.language,
            Path(args.config_path) if args.config_path else None,
            Path(args.calibration_path) if args.calibration_path else None,
            force=bool(args.force),
        )
        return
    if args.command == "collect":
        collect(
            Path(args.project_root),
            Path(args.config) if args.config else None,
            Path(args.calibration) if args.calibration else None,
            args.period,
            Path(args.out_dir),
        )
        return
    if args.command == "score":
        score(
            Path(args.inputs),
            Path(args.calibration) if args.calibration else None,
            Path(args.out_dir),
            config_path=Path(args.config) if args.config else None,
        )
        return
    if args.command == "report":
        report(Path(args.metrics), args.period, args.mode, Path(args.out_dir))
        return
    if args.command == "run":
        run_pipeline(
            Path(args.project_root),
            Path(args.config) if args.config else None,
            Path(args.calibration) if args.calibration else None,
            args.period,
            args.mode,
            Path(args.out_dir),
        )
        return


if __name__ == "__main__":
    main()
