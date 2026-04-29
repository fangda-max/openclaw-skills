from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


TYPE_PATTERN = re.compile(r"(?:public|private|protected)?\s*(?:class|interface|enum)\s+(\w+)")


def build_detail_export(project_root: Path, monitor_config: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    exclude_dirs = set(monitor_config["project"].get("exclude_dirs", []))
    include_extensions = {
        str(value).strip().lower()
        for value in monitor_config["project"].get("include_extensions", [])
        if str(value).strip()
    }
    glossary = monitor_config.get("glossary", {})
    strategy = monitor_config.get("strategy", {}) if isinstance(monitor_config.get("strategy"), dict) else {}
    glossary_strategy = _dict_value(strategy.get("glossary"))
    detectors = monitor_config.get("detectors", {}) if isinstance(monitor_config.get("detectors"), dict) else {}
    detail_export = monitor_config.get("detail_export", {}) if isinstance(monitor_config.get("detail_export"), dict) else {}
    limits = _dict_value(detail_export.get("limits"))
    java_files = _java_files(project_root, exclude_dirs, include_extensions)
    return {
        "generated_at": datetime.now().isoformat(),
        "project_root": str(project_root),
        "todos": _collect_todos(project_root, java_files, _dict_value(detectors.get("cognition")), limits),
        "large_files_and_methods": _collect_large_files_and_methods(project_root, java_files, _dict_value(detectors.get("cognition")), limits),
        "directory_stats": _collect_directory_stats(project_root, java_files, _dict_value(detectors.get("structure")), limits),
        "naming_analysis": _collect_naming_analysis(project_root, java_files, glossary, glossary_strategy, _dict_value(detectors.get("semantic")), limits),
        "exception_stats": _collect_exception_stats(project_root, java_files, _dict_value(detectors.get("behavior")), limits),
    }


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _java_files(project_root: Path, exclude_dirs: set[str], include_extensions: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in project_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in include_extensions:
            continue
        try:
            parts = path.relative_to(project_root).parts
        except ValueError:
            continue
        if any(part in exclude_dirs for part in parts):
            continue
        files.append(path)
    return sorted(files)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path, root: Path) -> str:
    return os.path.relpath(path, root)


def _matches_bucket(relative_path: str, aliases: list[str], match_mode: str) -> bool:
    if not aliases:
        return False
    lowered = relative_path.lower()
    if match_mode == "contains":
        return any(alias in lowered for alias in aliases)
    segments = lowered.split(os.sep)
    return any(alias in segments for alias in aliases)


def _normalize_relative_path(relative_path: str) -> str:
    normalized = str(relative_path).replace("\\", "/").strip().strip("/")
    return "" if normalized == "." else normalized.lower()


def _normalize_path_prefixes(prefixes: list[object]) -> list[str]:
    normalized_prefixes: list[str] = []
    for value in prefixes:
        normalized = _normalize_relative_path(str(value))
        if normalized:
            normalized_prefixes.append(normalized)
    return normalized_prefixes


def _matched_prefixes(relative_path: str, prefixes: list[str]) -> list[str]:
    if not prefixes:
        return []
    normalized_path = _normalize_relative_path(relative_path)
    if not normalized_path:
        return []
    return [
        prefix
        for prefix in prefixes
        if normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
    ]


def _matched_aliases(relative_path: str, aliases: list[str], match_mode: str) -> list[str]:
    if not aliases:
        return []
    normalized_path = _normalize_relative_path(relative_path)
    if match_mode == "contains":
        return [alias for alias in aliases if alias in normalized_path]
    segments = normalized_path.split("/") if normalized_path else []
    return [alias for alias in aliases if alias in segments]


def _resolve_bucket_matches(relative_path: str, prefixes: list[str], aliases: list[str], match_mode: str) -> list[dict[str, str]]:
    if prefixes:
        return [{"source": "prefix", "value": value} for value in _matched_prefixes(relative_path, prefixes)]
    return [{"source": "alias", "value": value} for value in _matched_aliases(relative_path, aliases, match_mode)]


def _extract_terms(value: str, token_patterns: list[re.Pattern[str]], min_term_length: int = 4) -> list[str]:
    terms: list[str] = []
    for pattern in token_patterns:
        for match in pattern.findall(value):
            token = match[0] if isinstance(match, tuple) else match
            token = str(token).strip()
            if len(token) >= min_term_length:
                terms.append(token)
    return terms


def _collect_todos(project_root: Path, java_files: list[Path], cognition_detectors: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    markers = {
        str(key).strip().lower(): re.compile(str(pattern), re.IGNORECASE)
        for key, pattern in _dict_value(cognition_detectors.get("debt_markers")).items()
        if str(key).strip() and str(pattern).strip()
    }
    owner_patterns = [re.compile(str(pattern)) for pattern in cognition_detectors.get("owner_patterns", []) if str(pattern).strip()]
    top_files_limit = int(limits["todo_top_files"])
    todo_item_limit = int(limits["todo_items"])

    todos: list[dict[str, Any]] = []
    marker_counts: dict[str, int] = defaultdict(int)
    for path in java_files:
        rel_path = _rel(path, project_root)
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            for pattern_type, pattern in markers.items():
                match = pattern.search(line)
                if not match:
                    continue
                content = str(match.group(1) if match.lastindex else "").strip()
                has_owner = any(owner_pattern.search(content) for owner_pattern in owner_patterns)
                marker_counts[pattern_type] += 1
                todos.append({
                    "type": pattern_type.upper(),
                    "file": rel_path,
                    "line": line_no,
                    "content": content,
                    "has_owner": has_owner,
                })

    by_file: dict[str, int] = defaultdict(int)
    for item in todos:
        by_file[item["file"]] += 1
    return {
        "total_count": len(todos),
        "with_owner": len([item for item in todos if item["has_owner"]]),
        "marker_counts": dict(sorted(marker_counts.items(), key=lambda item: item[0])),
        "top_files": [
            {"file": file, "count": count}
            for file, count in sorted(by_file.items(), key=lambda item: item[1], reverse=True)[: top_files_limit]
        ],
        "items": todos[: todo_item_limit],
    }


def _collect_large_files_and_methods(project_root: Path, java_files: list[Path], cognition_detectors: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    complexity = _dict_value(cognition_detectors.get("complexity"))
    large_file_threshold = int(complexity["large_file_lines_threshold"])
    large_file_warning = int(complexity["large_file_warning_threshold"])
    large_file_danger = int(complexity["large_file_danger_threshold"])
    large_method_threshold = int(complexity["large_method_lines_threshold"])
    large_files_limit = int(limits["large_files"])
    large_methods_limit = int(limits["large_methods"])
    method_signature_pattern = re.compile(
        str(complexity["method_signature_pattern"]).strip()
    )

    large_files: list[dict[str, Any]] = []
    large_methods: list[dict[str, Any]] = []
    for path in java_files:
        rel_path = _rel(path, project_root)
        try:
            content = _read_text(path)
        except OSError:
            continue
        lines = content.splitlines()
        non_blank = len([line for line in lines if line.strip()])
        if non_blank > large_file_threshold:
            level = "danger" if non_blank > large_file_danger else "warning" if non_blank > large_file_warning else "info"
            large_files.append({
                "file": rel_path,
                "lines": non_blank,
                "level": level,
            })

        for match in method_signature_pattern.finditer(content):
            method_name = match.group(2) if match.lastindex and match.lastindex >= 2 else "unknown"
            start = match.end()
            brace_count = 1
            end = start
            for index in range(start, len(content)):
                if content[index] == "{":
                    brace_count += 1
                elif content[index] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = index
                        break
            method_lines = content[start:end].count("\n")
            if method_lines > large_method_threshold:
                large_methods.append({
                    "file": rel_path,
                    "method": method_name,
                    "lines": method_lines,
                    "start_line": content[:match.start()].count("\n") + 1,
                })

    large_files.sort(key=lambda item: item["lines"], reverse=True)
    large_methods.sort(key=lambda item: item["lines"], reverse=True)
    return {
        "large_file_count": len(large_files),
        "large_method_count": len(large_methods),
        "large_file_threshold": large_file_threshold,
        "large_method_threshold": large_method_threshold,
        "large_files": large_files[: large_files_limit],
        "large_methods": large_methods[: large_methods_limit],
    }


def _collect_directory_stats(project_root: Path, java_files: list[Path], structure_detectors: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    shared_buckets = _dict_value(structure_detectors.get("shared_buckets"))
    directory_distribution = _dict_value(structure_detectors.get("directory_distribution"))
    shared_aliases = [str(value).strip().lower() for value in shared_buckets.get("shared_aliases", []) if str(value).strip()]
    utility_aliases = [str(value).strip().lower() for value in shared_buckets.get("utility_aliases", []) if str(value).strip()]
    shared_path_prefixes = _normalize_path_prefixes(list(shared_buckets.get("shared_path_prefixes", [])))
    utility_path_prefixes = _normalize_path_prefixes(list(shared_buckets.get("utility_path_prefixes", [])))
    match_mode = str(shared_buckets["match_mode"]).strip().lower()
    oversized_dir_file_threshold = int(directory_distribution["oversized_dir_file_threshold"])
    top_n_concentration_count = int(directory_distribution["top_n_concentration_count"])
    top_directories_limit = int(limits["directory_top"])
    directory_sample_files_limit = int(limits["directory_sample_files"])
    shared_common_files_limit = int(limits["shared_common_files"])
    shared_util_files_limit = int(limits["shared_util_files"])

    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"files": 0, "lines": 0, "file_list": []})
    common_files: list[dict[str, Any]] = []
    util_files: list[dict[str, Any]] = []
    shared_bucket_files: list[dict[str, Any]] = []
    for path in java_files:
        rel_path = _rel(path, project_root)
        rel_dir = os.path.dirname(rel_path) or "."
        normalized_rel_dir = _normalize_relative_path(rel_dir)
        try:
            non_blank = len([line for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()])
        except OSError:
            non_blank = 0
        stats[rel_dir]["files"] += 1
        stats[rel_dir]["lines"] += non_blank
        stats[rel_dir]["file_list"].append(os.path.basename(rel_path))
        common_matches = _resolve_bucket_matches(normalized_rel_dir, shared_path_prefixes, shared_aliases, match_mode)
        utility_matches = _resolve_bucket_matches(normalized_rel_dir, utility_path_prefixes, utility_aliases, match_mode)
        if common_matches:
            common_files.append({
                "path": rel_path,
                "dir": normalized_rel_dir or ".",
                "match_source_applied": common_matches[0]["source"],
                "match_values_applied": [item["value"] for item in common_matches],
            })
        if utility_matches:
            util_files.append({
                "path": rel_path,
                "dir": normalized_rel_dir or ".",
                "match_source_applied": utility_matches[0]["source"],
                "match_values_applied": [item["value"] for item in utility_matches],
            })
        if common_matches or utility_matches:
            shared_bucket_files.append({
                "path": rel_path,
                "dir": normalized_rel_dir or ".",
                "common": bool(common_matches),
                "utility": bool(utility_matches),
                "common_match_source_applied": common_matches[0]["source"] if common_matches else None,
                "utility_match_source_applied": utility_matches[0]["source"] if utility_matches else None,
                "common_match_values_applied": [item["value"] for item in common_matches],
                "utility_match_values_applied": [item["value"] for item in utility_matches],
            })

    sorted_stats = sorted(stats.items(), key=lambda item: item[1]["files"], reverse=True)
    top_dirs = [
        {"dir": directory, "files": value["files"], "lines": value["lines"], "sample_files": value["file_list"][: directory_sample_files_limit]}
        for directory, value in sorted_stats[: top_directories_limit]
    ]
    oversized_dirs = [
        {"dir": directory, "files": value["files"], "lines": value["lines"], "sample_files": value["file_list"][: directory_sample_files_limit]}
        for directory, value in sorted_stats
        if value["files"] >= oversized_dir_file_threshold
    ]
    top_n_dirs = [
        {"dir": directory, "files": value["files"], "lines": value["lines"], "sample_files": value["file_list"][: directory_sample_files_limit]}
        for directory, value in sorted_stats[: top_n_concentration_count]
    ]
    top_n_file_sum = sum(int(item["files"]) for item in top_n_dirs)
    return {
        "directory_count": len(stats),
        "top_directories": top_dirs,
        "oversized_dir_file_threshold": oversized_dir_file_threshold,
        "oversized_dir_count": len([1 for _, value in sorted_stats if value["files"] >= oversized_dir_file_threshold]),
        "oversized_directories": oversized_dirs,
        "top_n_concentration_count": top_n_concentration_count,
        "top_n_concentration_file_sum": top_n_file_sum,
        "top_n_concentration_directories": top_n_dirs,
        "shared_aliases": shared_aliases,
        "utility_aliases": utility_aliases,
        "shared_path_prefixes": shared_path_prefixes,
        "utility_path_prefixes": utility_path_prefixes,
        "shared_bucket_files": sorted(shared_bucket_files, key=lambda item: str(item["path"]))[: max(shared_common_files_limit, shared_util_files_limit)],
        "common_files": sorted(common_files, key=lambda item: str(item["path"]))[: shared_common_files_limit],
        "util_files": sorted(util_files, key=lambda item: str(item["path"]))[: shared_util_files_limit],
    }


def _collect_naming_analysis(
    project_root: Path,
    java_files: list[Path],
    glossary: dict[str, Any],
    glossary_strategy: dict[str, Any],
    semantic_detectors: dict[str, Any],
    limits: dict[str, Any],
) -> dict[str, Any]:
    term_extraction = _dict_value(semantic_detectors.get("term_extraction"))
    min_term_length = int(glossary_strategy["min_term_length"])
    duplicate_classes_limit = int(limits["duplicate_classes"])
    duplicate_class_files_limit = int(limits["duplicate_class_files"])
    glossary_terms_limit = int(limits["glossary_terms"])
    term_variant_preview_limit = int(limits["term_variant_preview"])
    scan_targets = {
        str(value).strip().lower()
        for value in term_extraction.get("scan_targets", [])
        if str(value).strip()
    }
    token_patterns = [
        re.compile(str(pattern))
        for pattern in term_extraction.get("token_patterns", [])
        if str(pattern).strip()
    ]

    class_names: dict[str, list[str]] = defaultdict(list)
    term_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    glossary_entries: dict[str, set[str]] = {}
    for term_config in glossary.values():
        if not isinstance(term_config, dict):
            continue
        standard = str(term_config.get("standard", "")).strip()
        if not standard:
            continue
        variants = {standard}
        variants.update(str(item).strip() for item in term_config.get("variants", []) if str(item).strip())
        glossary_entries[standard] = variants

    for path in java_files:
        rel_path = _rel(path, project_root)
        try:
            content = _read_text(path)
        except OSError:
            continue
        found_classes = TYPE_PATTERN.findall(content)
        for class_name in found_classes:
            class_names[class_name].append(rel_path)

        targets: list[str] = []
        if "file_stem" in scan_targets:
            targets.append(path.stem)
        if "class_name" in scan_targets:
            targets.extend(found_classes)
        for target in targets:
            for word in _extract_terms(target, token_patterns, min_term_length=min_term_length):
                for standard, variants in glossary_entries.items():
                    if any(variant and variant in word for variant in variants):
                        term_usage[standard][word] += 1

    duplicates = [
        {"name": name, "count": len(paths), "files": paths[: duplicate_class_files_limit]}
        for name, paths in sorted(class_names.items(), key=lambda item: len(item[1]), reverse=True)
        if len(paths) > 1
    ]
    terms = [
        {
            "standard": standard,
            "variant_count": len(variants),
            "usage_count": sum(variants.values()),
            "variants": [
                {"name": name, "count": count}
                for name, count in sorted(variants.items(), key=lambda item: item[1], reverse=True)[: term_variant_preview_limit]
            ],
        }
        for standard, variants in sorted(term_usage.items())
    ][: glossary_terms_limit]
    return {
        "total_class_names": len(class_names),
        "duplicate_class_count": len(duplicates),
        "duplicate_classes": duplicates[: duplicate_classes_limit],
        "glossary_usage": terms,
        "term_scan_targets": sorted(scan_targets),
    }


def _collect_exception_stats(project_root: Path, java_files: list[Path], behavior_detectors: dict[str, Any], limits: dict[str, Any]) -> dict[str, Any]:
    return_patterns = _dict_value(behavior_detectors.get("return_patterns"))
    exception_pattern_text = str(return_patterns["exception_pattern"]).strip()
    exception_types_limit = int(limits["exception_types"])
    exception_files_limit = int(limits["exception_files"])
    exception_pattern = re.compile(exception_pattern_text)

    exceptions: dict[str, list[str]] = defaultdict(list)
    for path in java_files:
        rel_path = _rel(path, project_root)
        try:
            content = _read_text(path)
        except OSError:
            continue
        for exception_type in exception_pattern.findall(content):
            if isinstance(exception_type, tuple):
                exception_type = next((str(item) for item in exception_type if str(item).strip()), "")
            exception_type = str(exception_type).strip()
            if not exception_type:
                continue
            exceptions[exception_type].append(rel_path)

    top_exceptions = [
        {"type": exc_type, "count": len(files), "files": sorted(set(files))[: exception_files_limit]}
        for exc_type, files in sorted(exceptions.items(), key=lambda item: len(item[1]), reverse=True)
    ]
    return {
        "exception_type_count": len(exceptions),
        "top_exceptions": top_exceptions[: exception_types_limit],
    }
