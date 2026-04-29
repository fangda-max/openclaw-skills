#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
认知熵分析器。

当前 MVP 口径聚焦六类可以落地定位的问题：
债务标记密度、未归属债务、公共知识缺口、复杂方法、大文件/大类负担、项目文档缺口。
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from entropy_audit.lang.java.scoring_v1_engine import score_dimension_v1


JAVADOC_BLOCK_RE = re.compile(r"/\*\*[\s\S]*?\*/(?:\s*@\w+(?:\([^)]*\))?)*\s*$", re.MULTILINE)
TYPE_PATTERN = re.compile(
    r"(?P<annotations>(?:@\w+(?:\([^)]*\))?\s*)*)"
    r"(?P<visibility>public|protected|private)?\s*"
    r"(?:(?:abstract|final|sealed)\s+)*"
    r"(?P<kind>class|interface|enum)\s+(?P<name>\w+)",
    re.MULTILINE,
)
METHOD_PATTERN = re.compile(
    r"(?P<annotations>(?:@\w+(?:\([^)]*\))?\s*)*)"
    r"(?P<visibility>public|protected|private)?\s*"
    r"(?:(?:static|final|abstract|synchronized|native|default)\s+)*"
    r"(?:<[^>]+>\s*)?"
    r"[\w\[\].<>?,]+\s+"
    r"(?P<name>\w+)\s*\([^;{}]*\)\s*(?:throws[^{]+)?\{",
    re.MULTILINE,
)
BRANCH_PATTERN = re.compile(r"\b(?:if|for|while|case|catch|switch)\b|&&|\|\||\?")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+]\([^)]+\)")
MARKDOWN_TABLE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"```|~~~")
COMMAND_OR_CONFIG_RE = re.compile(
    r"\b(?:mvn|gradle|java\s+-jar|docker|kubectl|npm|yarn|pnpm)\b|application\.(?:yml|yaml|properties)|pom\.xml|build\.gradle",
    re.IGNORECASE,
)


class CognitionAnalyzer:
    """认知熵分析器。"""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.project_root = Path(config["project"]["root"])
        self.exclude_dirs = set(config["project"]["exclude_dirs"])
        self.include_extensions = {
            str(value).strip().lower()
            for value in config["project"].get("include_extensions", [])
            if str(value).strip()
        }
        self.scoring_v1 = config.get("scoring_v1", {}) if isinstance(config.get("scoring_v1"), dict) else {}
        self.strategy = config["strategy"]
        self.javadoc_strategy = self.strategy["javadoc"]
        detail_export = config.get("detail_export", {}) if isinstance(config.get("detail_export"), dict) else {}
        detail_limits = detail_export.get("limits", {}) if isinstance(detail_export.get("limits"), dict) else {}
        detectors = config.get("detectors", {}) if isinstance(config.get("detectors"), dict) else {}
        cognition_detectors = detectors.get("cognition", {}) if isinstance(detectors.get("cognition"), dict) else {}
        self.debt_markers = {
            str(key).strip().lower(): str(value)
            for key, value in (
                cognition_detectors.get("debt_markers", {})
                if isinstance(cognition_detectors.get("debt_markers"), dict)
                else {}
            ).items()
            if str(key).strip() and str(value).strip()
        }
        self.owner_patterns = [str(value) for value in cognition_detectors["owner_patterns"] if str(value).strip()]
        self.project_docs_config = (
            cognition_detectors.get("project_docs", {})
            if isinstance(cognition_detectors.get("project_docs"), dict)
            else {}
        )
        self.complexity_config = cognition_detectors["complexity"] if isinstance(cognition_detectors.get("complexity"), dict) else {}
        self.large_method_threshold = int(self.complexity_config["large_method_lines_threshold"])
        self.large_class_threshold = int(self.complexity_config["large_class_lines_threshold"])
        self.large_file_threshold = int(self.complexity_config["large_file_lines_threshold"])
        self.large_file_warning_threshold = int(self.complexity_config["large_file_warning_threshold"])
        self.large_file_danger_threshold = int(self.complexity_config["large_file_danger_threshold"])
        self.branch_threshold = int(self.complexity_config.get("complex_method_branch_threshold", 12))
        self.nesting_threshold = int(self.complexity_config.get("complex_method_nesting_threshold", 4))
        self.method_signature_pattern = re.compile(str(self.complexity_config["method_signature_pattern"]).strip())
        self.todo_items_limit = int(detail_limits.get("todo_items", 500))
        self.todo_top_files_limit = int(detail_limits["todo_top_files"])
        self.todo_preview_items_limit = int(detail_limits["todo_preview_items"])
        self.todo_content_chars_limit = int(detail_limits["todo_content_chars"])
        self.knowledge_gap_limit = int(detail_limits.get("knowledge_gap_items", 500))
        self.complex_method_limit = int(detail_limits["large_methods"])
        self.large_file_limit = int(detail_limits["large_files"])

    def analyze(self) -> dict[str, Any]:
        java_files = self._iter_java_files()
        total_files = len(java_files)
        debt_stats = self._analyze_debt_markers(java_files)
        knowledge_stats = self._analyze_public_knowledge(java_files)
        complexity_stats = self._analyze_complexity(java_files)
        project_doc_stats = self._analyze_project_docs()
        facts = self._build_facts(debt_stats, knowledge_stats, complexity_stats, project_doc_stats, total_files)
        details = self._build_details(debt_stats, knowledge_stats, complexity_stats, project_doc_stats, total_files)
        v1_payload = score_dimension_v1(self.scoring_v1, "cognition", facts, details)
        if not isinstance(v1_payload, dict):
            raise ValueError("CognitionAnalyzer requires [code_entropy.scoring_v1] and a valid cognition scorecard")
        score = v1_payload["score_breakdown"]["score"]
        level = str(v1_payload["score_breakdown"].get("level", "danger"))

        return {
            "score": score,
            "level": level,
            "score_breakdown": v1_payload["score_breakdown"],
            "metrics": v1_payload["metrics"],
            "facts": facts,
            "details": details,
            "scoring_v1": v1_payload,
            "metric_definitions": v1_payload.get("metric_definitions", {}),
        }

    def _iter_java_files(self) -> list[Path]:
        candidates: list[Path] = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file_name in files:
                if Path(file_name).suffix.lower() in self.include_extensions:
                    candidates.append(Path(root, file_name))
        return sorted(candidates)

    def _rel(self, path: Path) -> str:
        return os.path.relpath(path, self.project_root)

    def _analyze_debt_markers(self, java_files: list[Path]) -> dict[str, Any]:
        markers = {
            marker: re.compile(pattern, re.IGNORECASE)
            for marker, pattern in self.debt_markers.items()
        }
        owner_patterns = [re.compile(pattern) for pattern in self.owner_patterns]
        issues: list[dict[str, Any]] = []
        marker_counts: dict[str, int] = defaultdict(int)

        for path in java_files:
            rel_path = self._rel(path)
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, 1):
                for marker, pattern in markers.items():
                    match = pattern.search(line)
                    if not match:
                        continue
                    content = str(match.group(1) if match.lastindex else "").strip()
                    has_owner = any(owner_pattern.search(content) for owner_pattern in owner_patterns)
                    marker_counts[marker] += 1
                    issues.append(
                        {
                            "type": marker.upper(),
                            "file": rel_path,
                            "line": line_no,
                            "content": content[: self.todo_content_chars_limit],
                            "has_owner": has_owner,
                        }
                    )

        files_with_debt: dict[str, int] = defaultdict(int)
        for issue in issues:
            files_with_debt[str(issue["file"])] += 1

        return {
            "total_count": len(issues),
            "with_owner": len([issue for issue in issues if issue["has_owner"]]),
            "unowned_count": len([issue for issue in issues if not issue["has_owner"]]),
            "marker_counts": dict(sorted(marker_counts.items(), key=lambda item: item[0])),
            "issues": issues,
            "unowned_issues": [issue for issue in issues if not issue["has_owner"]],
            "top_files": [
                {"file": file_name, "count": count}
                for file_name, count in sorted(files_with_debt.items(), key=lambda item: item[1], reverse=True)[: self.todo_top_files_limit]
            ],
        }

    def _has_javadoc(self, content: str, start: int, lookback_chars: int) -> bool:
        preceding = content[max(0, start - max(lookback_chars, 1)):start]
        return bool(JAVADOC_BLOCK_RE.search(preceding))

    def _visibility_of(self, match: re.Match[str]) -> str:
        return (match.group("visibility") or "package").strip().lower()

    def _knowledge_scope_label(self) -> str:
        type_vis = ",".join(self.javadoc_strategy["type_visibilities"])
        method_vis = ",".join(self.javadoc_strategy["method_visibilities"])
        return f"type[{type_vis or 'none'}] / method[{method_vis or 'none'}]"

    def _analyze_public_knowledge(self, java_files: list[Path]) -> dict[str, Any]:
        type_visibilities = set(self.javadoc_strategy["type_visibilities"])
        method_visibilities = set(self.javadoc_strategy["method_visibilities"])
        type_kinds = set(self.javadoc_strategy["type_kinds"])
        include_classes = bool(self.javadoc_strategy["include_classes"])
        include_methods = bool(self.javadoc_strategy["include_methods"])
        exclude_overrides = bool(self.javadoc_strategy["exclude_overrides"])
        class_lookback_chars = int(self.javadoc_strategy["class_lookback_chars"])
        method_lookback_chars = int(self.javadoc_strategy["method_lookback_chars"])
        target_count = 0
        documented_count = 0
        missing_issues: list[dict[str, Any]] = []

        for path in java_files:
            rel_path = self._rel(path)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            if include_classes:
                for match in TYPE_PATTERN.finditer(content):
                    visibility = self._visibility_of(match)
                    kind = str(match.group("kind") or "").lower()
                    if visibility not in type_visibilities or kind not in type_kinds:
                        continue
                    target_count += 1
                    has_doc = self._has_javadoc(content, match.start(), class_lookback_chars)
                    if has_doc:
                        documented_count += 1
                    else:
                        missing_issues.append(
                            {
                                "target_type": kind,
                                "name": str(match.group("name") or ""),
                                "visibility": visibility,
                                "file": rel_path,
                                "line": content[: match.start()].count("\n") + 1,
                            }
                        )

            if include_methods:
                for match in METHOD_PATTERN.finditer(content):
                    visibility = self._visibility_of(match)
                    annotations = str(match.group("annotations") or "")
                    if visibility not in method_visibilities:
                        continue
                    if exclude_overrides and "@Override" in annotations:
                        continue
                    target_count += 1
                    has_doc = self._has_javadoc(content, match.start(), method_lookback_chars)
                    if has_doc:
                        documented_count += 1
                    else:
                        missing_issues.append(
                            {
                                "target_type": "method",
                                "name": str(match.group("name") or ""),
                                "visibility": visibility,
                                "file": rel_path,
                                "line": content[: match.start()].count("\n") + 1,
                            }
                        )

        return {
            "documented_count": documented_count,
            "target_count": target_count,
            "missing_count": max(target_count - documented_count, 0),
            "coverage": round(documented_count / target_count, 4) if target_count else 1.0,
            "scope_label": self._knowledge_scope_label(),
            "missing_issues": missing_issues,
        }

    def _method_bounds(self, content: str, body_start: int) -> tuple[int, int]:
        brace_count = 1
        end = body_start
        for index in range(body_start, len(content)):
            char = content[index]
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = index
                    break
        return body_start, end

    def _max_nesting_depth(self, body: str) -> int:
        depth = 0
        max_depth = 0
        for char in body:
            if char == "{":
                depth += 1
                max_depth = max(max_depth, depth)
            elif char == "}":
                depth = max(depth - 1, 0)
        return max_depth

    def _analyze_complexity(self, java_files: list[Path]) -> dict[str, Any]:
        method_lines: list[int] = []
        complex_methods: list[dict[str, Any]] = []
        large_file_issues: list[dict[str, Any]] = []
        total_physical_lines = 0

        for path in java_files:
            rel_path = self._rel(path)
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            physical_lines = content.count("\n") + (1 if content else 0)
            total_physical_lines += physical_lines
            if physical_lines > self.large_file_threshold:
                level = (
                    "danger"
                    if physical_lines > self.large_file_danger_threshold
                    else "warning"
                    if physical_lines > self.large_file_warning_threshold
                    else "notice"
                )
                large_file_issues.append(
                    {
                        "file": rel_path,
                        "lines": physical_lines,
                        "level": level,
                        "reason": f"物理总行数超过 {self.large_file_threshold} 行",
                    }
                )

            for match in self.method_signature_pattern.finditer(content):
                method_name = self._method_name(match)
                body_start, body_end = self._method_bounds(content, match.end())
                body = content[body_start:body_end]
                line_count = body.count("\n")
                branch_count = len(BRANCH_PATTERN.findall(body))
                nesting_depth = self._max_nesting_depth(body)
                method_lines.append(line_count)
                reasons: list[str] = []
                if line_count > self.large_method_threshold:
                    reasons.append(f"方法体行数 > {self.large_method_threshold}")
                if branch_count >= self.branch_threshold:
                    reasons.append(f"分支数 >= {self.branch_threshold}")
                if nesting_depth >= self.nesting_threshold:
                    reasons.append(f"嵌套深度 >= {self.nesting_threshold}")
                if reasons:
                    complex_methods.append(
                        {
                            "file": rel_path,
                            "method": method_name,
                            "lines": line_count,
                            "branch_count": branch_count,
                            "nesting_depth": nesting_depth,
                            "start_line": content[: match.start()].count("\n") + 1,
                            "reason": "；".join(reasons),
                        }
                    )

        complex_methods.sort(
            key=lambda item: (int(item["lines"]), int(item["branch_count"]), int(item["nesting_depth"])),
            reverse=True,
        )
        large_file_issues.sort(key=lambda item: int(item["lines"]), reverse=True)
        total_method_lines = round(sum(method_lines), 1) if method_lines else 0.0
        avg_method_lines = round(total_method_lines / len(method_lines), 2) if method_lines else 0.0
        avg_file_lines = round(total_physical_lines / len(java_files), 2) if java_files else 0.0
        return {
            "total_methods": len(method_lines),
            "total_method_lines": total_method_lines,
            "avg_method_lines": avg_method_lines,
            "total_physical_lines": total_physical_lines,
            "avg_file_lines": avg_file_lines,
            "complex_method_count": len(complex_methods),
            "complex_methods": complex_methods,
            "large_file_class_count": len(large_file_issues),
            "large_file_class_issues": large_file_issues,
        }

    def _method_name(self, match: re.Match[str]) -> str:
        try:
            if "name" in match.groupdict():
                return str(match.group("name") or "unknown")
        except IndexError:
            pass
        if match.lastindex and match.lastindex >= 2:
            return str(match.group(2) or "unknown")
        return "unknown"

    def _config_list(self, name: str, default: list[str]) -> list[str]:
        values = self.project_docs_config.get(name, default)
        if not isinstance(values, list):
            return default
        normalized = [str(value).strip() for value in values if str(value).strip()]
        return normalized or default

    def _config_int(self, name: str, default: int) -> int:
        try:
            return int(self.project_docs_config.get(name, default))
        except (TypeError, ValueError):
            return default

    def _is_ignored_doc_path(self, path: Path, ignore_dirs: set[str]) -> bool:
        rel_parts = path.relative_to(self.project_root).parts
        return any(part in ignore_dirs for part in rel_parts[:-1])

    def _resolve_root_file_case_insensitive(self, file_name: str) -> Path | None:
        candidate = self.project_root / file_name
        if candidate.is_file():
            return candidate
        target = file_name.lower()
        try:
            for child in self.project_root.iterdir():
                if child.is_file() and child.name.lower() == target:
                    return child
        except OSError:
            return None
        return None

    def _iter_project_doc_files(self) -> list[Path]:
        entry_files = self._config_list("entry_files", ["README.md", "README_CN.md", "README.zh-CN.md", "readme.md"])
        doc_roots = self._config_list("doc_roots", ["docs", "doc", "readme", "wiki"])
        doc_globs = self._config_list("doc_globs", ["*.md", "**/*.md", "*.adoc", "**/*.adoc"])
        ignore_dirs = set(self._config_list("ignore_dirs", ["target", "build", "dist", ".git", ".idea", "node_modules", "asset", "assets", "img", "images"]))
        ignore_dirs.update(self.exclude_dirs)
        files: dict[str, Path] = {}

        for file_name in entry_files:
            path = self._resolve_root_file_case_insensitive(file_name)
            if path is not None and not self._is_ignored_doc_path(path, ignore_dirs):
                files[str(path.resolve()).lower()] = path

        for root_name in doc_roots:
            root = self.project_root / root_name
            if not root.exists() or not root.is_dir():
                continue
            for pattern in doc_globs:
                for path in root.glob(pattern):
                    if not path.is_file() or self._is_ignored_doc_path(path, ignore_dirs):
                        continue
                    if path.suffix.lower() not in {".md", ".adoc"}:
                        continue
                    files[str(path.resolve()).lower()] = path

        return sorted(files.values(), key=lambda path: self._rel(path).lower())

    def _entry_doc_files(self, doc_files: list[Path]) -> list[Path]:
        entry_files = {value.lower() for value in self._config_list("entry_files", ["README.md", "README_CN.md", "README.zh-CN.md", "readme.md"])}
        return [path for path in doc_files if path.parent == self.project_root and path.name.lower() in entry_files]

    def _strip_markdown_noise(self, content: str) -> str:
        text = re.sub(r"```[\s\S]*?```", " ", content)
        text = re.sub(r"~~~[\s\S]*?~~~", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"!\[[^\]]*]\([^)]+\)", " ", text)
        text = re.sub(r"\[[^\]]+]\([^)]+\)", " ", text)
        text = re.sub(r"[#>*_`|\\-]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _topic_aliases(self, required_topics: list[str]) -> dict[str, list[str]]:
        raw_aliases = self.project_docs_config.get("topic_aliases")
        aliases: dict[str, list[str]] = {}
        if isinstance(raw_aliases, dict):
            for topic, values in raw_aliases.items():
                topic_name = str(topic).strip()
                if not topic_name:
                    continue
                if isinstance(values, list):
                    aliases[topic_name] = [str(value).strip() for value in values if str(value).strip()]
                elif str(values).strip():
                    aliases[topic_name] = [str(values).strip()]
        return {topic: aliases.get(topic, [topic]) for topic in required_topics}

    def _analyze_project_docs(self) -> dict[str, Any]:
        enabled = bool(self.project_docs_config.get("enabled", True))
        required_topics = self._config_list(
            "required_topics",
            ["项目介绍", "环境准备", "本地启动", "配置说明", "项目结构", "构建部署", "开发规范"],
        )
        min_total_chars = self._config_int("min_total_chars", 3000)
        min_entry_chars = self._config_int("min_entry_chars", 500)
        min_doc_files = self._config_int("min_doc_files", 1)
        if not enabled:
            return {
                "enabled": False,
                "quality_score": 1.0,
                "gap_ratio": 0.0,
                "entry_exists": True,
                "entry_chars": 0,
                "doc_file_count": 0,
                "total_chars": 0,
                "required_topic_count": len(required_topics),
                "covered_topic_count": len(required_topics),
                "missing_topic_count": 0,
                "has_examples": True,
                "has_structure_signal": True,
                "code_block_count": 0,
                "table_count": 0,
                "image_count": 0,
                "link_count": 0,
                "min_total_chars": 0,
                "min_entry_chars": 0,
                "min_doc_files": 0,
                "doc_files": [],
                "topic_coverage": [],
                "issues": [],
            }

        doc_files = self._iter_project_doc_files()
        entry_docs = self._entry_doc_files(doc_files)
        docs: list[dict[str, Any]] = []
        all_content_parts: list[str] = []
        entry_chars = 0
        total_chars = 0
        code_fence_count = 0
        table_count = 0
        image_count = 0
        link_count = 0
        heading_count = 0

        for path in doc_files:
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            plain_text = self._strip_markdown_noise(content)
            char_count = len(plain_text)
            headings = [match.group(1).strip() for match in MARKDOWN_HEADING_RE.finditer(content)]
            fences = len(CODE_FENCE_RE.findall(content)) // 2
            tables = len(MARKDOWN_TABLE_ROW_RE.findall(content))
            images = len(MARKDOWN_IMAGE_RE.findall(content))
            links = len(MARKDOWN_LINK_RE.findall(content))
            rel_path = self._rel(path)
            docs.append(
                {
                    "file": rel_path,
                    "chars": char_count,
                    "headings": len(headings),
                    "code_blocks": fences,
                    "tables": tables,
                    "images": images,
                    "links": links,
                }
            )
            all_content_parts.append(content)
            total_chars += char_count
            code_fence_count += fences
            table_count += tables
            image_count += images
            link_count += links
            heading_count += len(headings)
            if path in entry_docs:
                entry_chars += char_count

        corpus = "\n".join(all_content_parts)
        corpus_lower = corpus.lower()
        topic_aliases = self._topic_aliases(required_topics)
        topic_coverage: list[dict[str, Any]] = []
        covered_topic_count = 0
        for topic in required_topics:
            aliases = topic_aliases.get(topic, [topic])
            matched_aliases = [alias for alias in aliases if alias.lower() in corpus_lower]
            covered = bool(matched_aliases)
            if covered:
                covered_topic_count += 1
            topic_coverage.append(
                {
                    "topic": topic,
                    "status": "已覆盖" if covered else "缺失",
                    "matched_aliases": ", ".join(matched_aliases[:5]) if matched_aliases else "",
                    "required_aliases": ", ".join(aliases[:8]),
                }
            )

        entry_score = 0.2 * min(entry_chars / min_entry_chars, 1.0) if min_entry_chars > 0 else 0.2
        total_volume_score = 0.2 * min(total_chars / min_total_chars, 1.0) if min_total_chars > 0 else 0.2
        topic_score = 0.4 * (covered_topic_count / len(required_topics)) if required_topics else 0.4
        has_examples = bool(code_fence_count > 0 or COMMAND_OR_CONFIG_RE.search(corpus))
        has_structure_signal = bool(table_count > 0 or image_count > 0 or heading_count >= max(3, len(required_topics) // 2))
        example_score = 0.1 if has_examples else 0.0
        structure_score = 0.1 if has_structure_signal else 0.0
        quality_score = round(min(entry_score + total_volume_score + topic_score + example_score + structure_score, 1.0), 4)
        missing_topic_count = max(len(required_topics) - covered_topic_count, 0)

        issues: list[dict[str, Any]] = []
        if not entry_docs:
            issues.append(
                {
                    "issue_type": "入口文档缺失",
                    "target": "README",
                    "current": "未找到根目录入口文档",
                    "expected": "根目录存在 README.md / README_CN.md / readme.md 等入口文档",
                    "file": "",
                }
            )
        elif entry_chars < min_entry_chars:
            issues.append(
                {
                    "issue_type": "入口文档过短",
                    "target": "README",
                    "current": f"{entry_chars} 字符",
                    "expected": f">= {min_entry_chars} 字符",
                    "file": ", ".join(self._rel(path) for path in entry_docs),
                }
            )
        if len(docs) < min_doc_files:
            issues.append(
                {
                    "issue_type": "说明文档数量不足",
                    "target": "文档文件",
                    "current": f"{len(docs)} 个",
                    "expected": f">= {min_doc_files} 个",
                    "file": "",
                }
            )
        if total_chars < min_total_chars:
            issues.append(
                {
                    "issue_type": "说明文档内容不足",
                    "target": "文档正文",
                    "current": f"{total_chars} 字符",
                    "expected": f">= {min_total_chars} 字符",
                    "file": "",
                }
            )
        for topic in topic_coverage:
            if topic["status"] == "缺失":
                issues.append(
                    {
                        "issue_type": "必需主题缺失",
                        "target": topic["topic"],
                        "current": "未命中主题别名",
                        "expected": topic["required_aliases"],
                        "file": "",
                    }
                )
        if not has_examples:
            issues.append(
                {
                    "issue_type": "缺少示例",
                    "target": "命令/配置/代码示例",
                    "current": "未发现代码块或常见启动配置命令",
                    "expected": "至少提供启动、构建、配置或调用示例",
                    "file": "",
                }
            )
        if not has_structure_signal:
            issues.append(
                {
                    "issue_type": "缺少结构化说明",
                    "target": "表格/图示/标题结构",
                    "current": "未发现表格、图片或足够标题层级",
                    "expected": "通过表格、图示或清晰标题组织说明",
                    "file": "",
                }
            )

        return {
            "enabled": True,
            "quality_score": quality_score,
            "gap_ratio": round(1.0 - quality_score, 4),
            "entry_exists": bool(entry_docs),
            "entry_chars": entry_chars,
            "doc_file_count": len(docs),
            "total_chars": total_chars,
            "required_topic_count": len(required_topics),
            "covered_topic_count": covered_topic_count,
            "missing_topic_count": missing_topic_count,
            "has_examples": has_examples,
            "has_structure_signal": has_structure_signal,
            "code_block_count": code_fence_count,
            "table_count": table_count,
            "image_count": image_count,
            "link_count": link_count,
            "min_total_chars": min_total_chars,
            "min_entry_chars": min_entry_chars,
            "min_doc_files": min_doc_files,
            "doc_files": docs,
            "topic_coverage": topic_coverage,
            "issues": issues,
        }

    def _build_facts(
        self,
        debt_stats: dict[str, Any],
        knowledge_stats: dict[str, Any],
        complexity_stats: dict[str, Any],
        project_doc_stats: dict[str, Any],
        total_files: int,
    ) -> dict[str, Any]:
        return {
            "total_files": total_files,
            "todo_count": debt_stats["total_count"],
            "todo_with_owner": debt_stats["with_owner"],
            "unowned_todo_count": debt_stats["unowned_count"],
            "knowledge_documented_count": knowledge_stats["documented_count"],
            "knowledge_target_count": knowledge_stats["target_count"],
            "complex_method_count": complexity_stats["complex_method_count"],
            "total_methods": complexity_stats["total_methods"],
            "large_file_class_count": complexity_stats["large_file_class_count"],
            "project_doc_quality_score": project_doc_stats["quality_score"],
            "project_doc_file_count": project_doc_stats["doc_file_count"],
            "project_doc_missing_topic_count": project_doc_stats["missing_topic_count"],
        }

    def _build_details(
        self,
        debt_stats: dict[str, Any],
        knowledge_stats: dict[str, Any],
        complexity_stats: dict[str, Any],
        project_doc_stats: dict[str, Any],
        total_files: int,
    ) -> dict[str, Any]:
        table_total_counts = {
            "debt_marker_issues": debt_stats["total_count"],
            "unowned_debt_issues": debt_stats["unowned_count"],
            "public_knowledge_gap_issues": knowledge_stats["missing_count"],
            "complex_method_issues": complexity_stats["complex_method_count"],
            "large_file_class_issues": complexity_stats["large_file_class_count"],
            "project_doc_issues": len(project_doc_stats["issues"]),
            "project_doc_topic_coverage": len(project_doc_stats["topic_coverage"]),
            "project_doc_files": len(project_doc_stats["doc_files"]),
        }
        return {
            "total_files": total_files,
            "todo_count": debt_stats["total_count"],
            "todo_with_owner": debt_stats["with_owner"],
            "unowned_todo_count": debt_stats["unowned_count"],
            "debt_marker_counts": debt_stats["marker_counts"],
            "owner_pattern_count": len(self.owner_patterns),
            "top_debt_files": debt_stats["top_files"],
            "knowledge_scope": knowledge_stats["scope_label"],
            "knowledge_documented_count": knowledge_stats["documented_count"],
            "knowledge_target_count": knowledge_stats["target_count"],
            "knowledge_missing_count": knowledge_stats["missing_count"],
            "knowledge_coverage": knowledge_stats["coverage"],
            "large_method_threshold": self.large_method_threshold,
            "complex_method_branch_threshold": self.branch_threshold,
            "complex_method_nesting_threshold": self.nesting_threshold,
            "complex_method_count": complexity_stats["complex_method_count"],
            "total_methods": complexity_stats["total_methods"],
            "total_method_lines": complexity_stats["total_method_lines"],
            "avg_method_lines": complexity_stats["avg_method_lines"],
            "large_file_lines_threshold": self.large_file_threshold,
            "large_class_lines_threshold": self.large_class_threshold,
            "large_file_class_count": complexity_stats["large_file_class_count"],
            "avg_file_lines": complexity_stats["avg_file_lines"],
            "project_doc_quality_score": project_doc_stats["quality_score"],
            "project_doc_gap_ratio": project_doc_stats["gap_ratio"],
            "project_doc_entry_exists": project_doc_stats["entry_exists"],
            "project_doc_entry_chars": project_doc_stats["entry_chars"],
            "project_doc_file_count": project_doc_stats["doc_file_count"],
            "project_doc_total_chars": project_doc_stats["total_chars"],
            "project_doc_required_topic_count": project_doc_stats["required_topic_count"],
            "project_doc_covered_topic_count": project_doc_stats["covered_topic_count"],
            "project_doc_missing_topic_count": project_doc_stats["missing_topic_count"],
            "project_doc_has_examples": project_doc_stats["has_examples"],
            "project_doc_has_structure_signal": project_doc_stats["has_structure_signal"],
            "project_doc_code_block_count": project_doc_stats["code_block_count"],
            "project_doc_table_count": project_doc_stats["table_count"],
            "project_doc_image_count": project_doc_stats["image_count"],
            "project_doc_link_count": project_doc_stats["link_count"],
            "project_doc_min_total_chars": project_doc_stats["min_total_chars"],
            "project_doc_min_entry_chars": project_doc_stats["min_entry_chars"],
            "project_doc_min_doc_files": project_doc_stats["min_doc_files"],
            "table_total_counts": table_total_counts,
            "debt_marker_issues": debt_stats["issues"],
            "unowned_debt_issues": debt_stats["unowned_issues"],
            "public_knowledge_gap_issues": knowledge_stats["missing_issues"],
            "complex_method_issues": complexity_stats["complex_methods"],
            "large_file_class_issues": complexity_stats["large_file_class_issues"],
            "project_doc_issues": project_doc_stats["issues"],
            "project_doc_topic_coverage": project_doc_stats["topic_coverage"],
            "project_doc_files": project_doc_stats["doc_files"],
        }
