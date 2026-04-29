from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


SUPPORTED_PROJECT_KINDS = {"auto", "spring_web", "batch_job", "plain_java", "library"}


def _iter_java_files(
    project_root: Path,
    exclude_dirs: set[str],
    include_extensions: set[str],
    limit: int | None = None,
) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(project_root):
        dirs[:] = [name for name in dirs if name not in exclude_dirs]
        for name in names:
            if Path(name).suffix.lower() not in include_extensions:
                continue
            files.append(Path(root, name))
            if limit is not None and len(files) >= limit:
                return files
    return files


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _annotation_match(content: str, annotations: list[str]) -> bool:
    return any(re.search(rf"@\s*{re.escape(annotation)}\b", content) for annotation in annotations)


def _path_keyword_match(relative_path: str, keywords: list[str]) -> bool:
    lowered = relative_path.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _class_name_keyword_match(class_name: str, keywords: list[str]) -> bool:
    lowered = class_name.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def is_controller_candidate(project_root: Path, path: Path, content: str, controller_strategy: dict[str, Any]) -> bool:
    file_name = path.stem
    relative = path.relative_to(project_root).as_posix().lower()
    suffixes = _string_list(controller_strategy.get("file_name_suffixes"))
    annotations = _string_list(controller_strategy.get("class_annotations"))
    package_keywords = [value.lower() for value in _string_list(controller_strategy.get("package_keywords"))]

    if bool(controller_strategy.get("detect_by_filename")) and any(file_name.endswith(suffix) for suffix in suffixes):
        return True
    if bool(controller_strategy.get("detect_by_annotation")) and _annotation_match(content, annotations):
        return True
    if bool(controller_strategy.get("detect_by_package")) and _path_keyword_match(relative, package_keywords):
        return True
    return False


def detect_project_profile(
    project_root: Path,
    exclude_dirs: list[str],
    include_extensions: list[str],
    strategy: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    controller_strategy = strategy.get("controller", {}) if isinstance(strategy.get("controller"), dict) else {}
    project_strategy = strategy.get("project", {}) if isinstance(strategy.get("project"), dict) else {}

    configured_kind = str(project_strategy.get("kind", "") or "").strip().lower()
    if configured_kind not in SUPPORTED_PROJECT_KINDS:
        configured_kind = "auto"

    if configured_kind != "auto":
        return {
            "kind": configured_kind,
            "detection_mode": "configured",
            "controller_candidates": 0,
            "web_indicators": 0,
            "batch_indicators": 0,
            "files_sampled": 0,
        }

    web_annotations = _string_list(project_strategy.get("web_class_annotations"))
    web_package_keywords = [value.lower() for value in _string_list(project_strategy.get("web_package_keywords"))]
    batch_annotations = _string_list(project_strategy.get("batch_class_annotations"))
    batch_package_keywords = [value.lower() for value in _string_list(project_strategy.get("batch_package_keywords"))]
    batch_class_keywords = _string_list(project_strategy.get("batch_class_name_keywords"))

    controller_candidates = 0
    web_indicators = 0
    batch_indicators = 0
    files_sampled = 0
    excluded = set(exclude_dirs)
    source_extensions = {
        str(value).strip().lower()
        for value in include_extensions
        if str(value).strip()
    }

    for path in _iter_java_files(project_root, excluded, source_extensions, limit=limit):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files_sampled += 1
        relative = path.relative_to(project_root).as_posix().lower()

        if is_controller_candidate(project_root, path, content, controller_strategy):
            controller_candidates += 1
        if _annotation_match(content, web_annotations) or _path_keyword_match(relative, web_package_keywords):
            web_indicators += 1
        if (
            _annotation_match(content, batch_annotations)
            or _path_keyword_match(relative, batch_package_keywords)
            or _class_name_keyword_match(path.stem, batch_class_keywords)
        ):
            batch_indicators += 1

    if controller_candidates > 0 or web_indicators > 0:
        kind = "spring_web"
    elif batch_indicators > 0:
        kind = "batch_job"
    else:
        kind = "plain_java"

    return {
        "kind": kind,
        "detection_mode": "auto",
        "controller_candidates": controller_candidates,
        "web_indicators": web_indicators,
        "batch_indicators": batch_indicators,
        "files_sampled": files_sampled,
    }
