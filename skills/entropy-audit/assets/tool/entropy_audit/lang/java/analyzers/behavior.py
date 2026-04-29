#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行为熵分析器
分析错误处理、返回格式、API一致性等
"""

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from entropy_audit.lang.java.project_profile import is_controller_candidate
from entropy_audit.lang.java.scoring_v1_engine import score_dimension_v1


class BehaviorAnalyzer:
    """行为熵分析器"""

    def __init__(self, config: Dict[str, Any]):
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
        detail_export = config.get("detail_export", {}) if isinstance(config.get("detail_export"), dict) else {}
        detail_limits = detail_export.get("limits", {}) if isinstance(detail_export.get("limits"), dict) else {}
        detectors = config.get("detectors", {}) if isinstance(config.get("detectors"), dict) else {}
        self.behavior_detectors = detectors["behavior"] if isinstance(detectors.get("behavior"), dict) else {}
        self.project_meta = config["meta"] if isinstance(config.get("meta"), dict) else {}
        self.controller_strategy = self.strategy["controller"]
        self.return_strategy = self.strategy["return_formats"]
        self.project_strategy = self.strategy["project"]
        self.error_pattern_config = self.behavior_detectors["error_patterns"] if isinstance(self.behavior_detectors.get("error_patterns"), dict) else {}
        self.return_pattern_config = self.behavior_detectors["return_patterns"] if isinstance(self.behavior_detectors.get("return_patterns"), dict) else {}
        self.wrapped_error_response_config = (
            self.behavior_detectors["wrapped_error_responses"]
            if isinstance(self.behavior_detectors.get("wrapped_error_responses"), dict)
            else {}
        )
        self.project_kind = str(self.project_meta["project_kind"]).strip().lower()
        self.project_detection_mode = str(self.project_meta["project_detection_mode"]).strip()
        self.preferred_wrapper_preview = int(detail_limits["preferred_wrapper_preview"])
        self.top_error_patterns_limit = int(detail_limits["behavior_top_error_patterns"])
        self.top_return_formats_limit = int(detail_limits["behavior_top_return_formats"])
        self.top_exception_types_limit = int(detail_limits["behavior_top_exception_types"])
        self.business_exception_config = (
            self.behavior_detectors.get("business_exceptions", {})
            if isinstance(self.behavior_detectors.get("business_exceptions"), dict)
            else {}
        )

    def analyze(self) -> Dict[str, Any]:
        """执行行为熵分析"""
        error_stats = self._analyze_error_handling()
        return_stats = self._analyze_return_formats()
        exception_stats = self._analyze_exceptions()
        behavior_stats = self._analyze_behavior_semantics()
        facts = self._build_facts(error_stats, return_stats, exception_stats, behavior_stats)
        details = {
            "error_handling_patterns": error_stats["pattern_count"],
            "return_format_types": return_stats["format_count"],
            "exception_types": exception_stats["exception_count"],
            "error_consistency": error_stats["consistency_score"],
            "return_consistency": return_stats["consistency_score"],
            "top_error_patterns": error_stats["top_patterns"],
            "top_return_formats": return_stats["top_formats"],
            "top_exceptions": exception_stats["top_exceptions"],
            "project_kind": self.project_kind,
            "project_detection_mode": self.project_detection_mode,
            "controller_candidates": return_stats["controller_candidates"],
            "configured_return_scan_scope": return_stats["configured_scan_scope"],
            "return_scan_scope": return_stats["scan_scope"],
            "return_analysis_mode": return_stats["analysis_mode"],
            "return_degraded_reason": return_stats["degraded_reason"],
            "preferred_return_wrappers": return_stats["preferred_wrappers"],
            "catch_block_count": behavior_stats["catch_block_count"],
            "failure_strategy_count": behavior_stats["failure_strategy_count"],
            "failure_strategy_total_count": behavior_stats["failure_strategy_total_count"],
            "failure_strategy_dominant_count": behavior_stats["failure_strategy_dominant_count"],
            "swallowed_catch_count": behavior_stats["swallowed_catch_count"],
            "error_return_contract_count": behavior_stats["error_return_contract_count"],
            "error_return_contract_total_count": behavior_stats["error_return_contract_total_count"],
            "error_return_contract_dominant_count": behavior_stats["error_return_contract_dominant_count"],
            "generic_exception_throw_count": behavior_stats["generic_exception_throw_count"],
            "exception_throw_count": behavior_stats["exception_throw_count"],
            "business_exception_throw_count": behavior_stats["business_exception_throw_count"],
            "standard_business_exception_throw_count": behavior_stats["standard_business_exception_throw_count"],
            "nonstandard_business_exception_throw_count": behavior_stats["nonstandard_business_exception_throw_count"],
            "standard_business_exceptions": behavior_stats["standard_business_exceptions"],
            "business_exception_detection_mode": behavior_stats["business_exception_detection_mode"],
            "failure_strategy_distribution": behavior_stats["failure_strategy_distribution"],
            "error_return_contract_distribution": behavior_stats["error_return_contract_distribution"],
            "table_total_counts": {
                "failure_strategy_issues": len(behavior_stats["failure_strategy_issues"]),
                "swallowed_exception_issues": len(behavior_stats["swallowed_exception_issues"]),
                "error_return_contract_issues": len(behavior_stats["error_return_contract_issues"]),
                "generic_exception_issues": len(behavior_stats["generic_exception_issues"]),
                "business_exception_convergence_issues": len(behavior_stats["business_exception_convergence_issues"]),
            },
            "failure_strategy_issues": behavior_stats["failure_strategy_issues"],
            "swallowed_exception_issues": behavior_stats["swallowed_exception_issues"],
            "error_return_contract_issues": behavior_stats["error_return_contract_issues"],
            "generic_exception_issues": behavior_stats["generic_exception_issues"],
            "business_exception_convergence_issues": behavior_stats["business_exception_convergence_issues"],
        }
        v1_payload = score_dimension_v1(self.scoring_v1, "behavior", facts, details)
        if not isinstance(v1_payload, dict):
            raise ValueError("BehaviorAnalyzer requires [code_entropy.scoring_v1] and a valid behavior scorecard")
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
        return candidates

    def _is_controller_candidate(self, path: Path, content: str) -> bool:
        return is_controller_candidate(self.project_root, path, content, self.controller_strategy)

    def _build_error_patterns(self) -> dict[str, str]:
        wrappers = [str(value).strip() for value in self.return_strategy.get("wrapper_types", []) if str(value).strip()]
        patterns = {str(key): str(value) for key, value in self.error_pattern_config.items() if str(key).strip() and str(value).strip()}
        method_names = [
            str(value).strip()
            for value in self.wrapped_error_response_config.get("method_names", [])
            if str(value).strip()
        ]
        include_return_only = bool(self.wrapped_error_response_config.get("include_return_only", True))
        if wrappers and method_names:
            joined = "|".join(re.escape(wrapper) for wrapper in wrappers)
            methods = "|".join(re.escape(method_name) for method_name in method_names)
            prefix = r"return\s+" if include_return_only else r"(?:return\s+)?"
            patterns["wrapped_error_response"] = (
                rf"{prefix}(?:new\s+)?(?:[\w$.]+\.)?(?:{joined})\b(?:<[^>]+>)?\s*\.\s*(?:{methods})\s*\("
            )
        return patterns

    def _build_return_patterns(self) -> dict[str, str]:
        patterns: dict[str, str] = {}
        string_literal_pattern = str(self.return_pattern_config["string_literal_pattern"]).strip()
        boolean_literal_pattern = str(self.return_pattern_config["boolean_literal_pattern"]).strip()
        null_return_pattern = str(self.return_pattern_config["null_return_pattern"]).strip()
        named_reference_pattern = str(self.return_pattern_config["named_reference_pattern"]).strip()
        for wrapper in self.return_strategy.get("wrapper_types", []):
            patterns[str(wrapper)] = rf"return\s+(?:new\s+)?(?:[\w$.]+\.)?{re.escape(str(wrapper))}\b(?:<[^>]+>)?"
        for map_type in self.return_strategy.get("map_types", []):
            patterns[str(map_type)] = rf"return\s+(?:new\s+)?(?:[\w$.]+\.)?{re.escape(str(map_type))}\b(?:<[^>]+>)?"
        for collection_type in self.return_strategy.get("collection_types", []):
            patterns[str(collection_type)] = rf"return\s+(?:new\s+)?(?:[\w$.]+\.)?{re.escape(str(collection_type))}\b(?:<[^>]+>)?"
        if self.return_strategy["count_scalar_literals"] and string_literal_pattern:
            patterns["String"] = string_literal_pattern
        if self.return_strategy["count_scalar_literals"] and boolean_literal_pattern:
            patterns["Boolean"] = boolean_literal_pattern
        if self.return_strategy["count_null_returns"] and null_return_pattern:
            patterns["Null"] = null_return_pattern
        if self.return_strategy["count_named_references"] and named_reference_pattern:
            patterns["NamedReference"] = named_reference_pattern
        return patterns

    def _mask_java_text(self, content: str) -> str:
        """Mask comments and string/char literals while preserving offsets and newlines."""
        chars = list(content)
        i = 0
        length = len(chars)
        while i < length:
            ch = chars[i]
            nxt = chars[i + 1] if i + 1 < length else ""
            if ch == "/" and nxt == "/":
                chars[i] = chars[i + 1] = " "
                i += 2
                while i < length and chars[i] != "\n":
                    chars[i] = " "
                    i += 1
                continue
            if ch == "/" and nxt == "*":
                chars[i] = chars[i + 1] = " "
                i += 2
                while i + 1 < length:
                    if chars[i] == "*" and chars[i + 1] == "/":
                        chars[i] = chars[i + 1] = " "
                        i += 2
                        break
                    if chars[i] != "\n":
                        chars[i] = " "
                    i += 1
                continue
            if ch in {'"', "'"}:
                quote = ch
                chars[i] = " "
                i += 1
                escaped = False
                while i < length:
                    current = chars[i]
                    if current != "\n":
                        chars[i] = " "
                    if escaped:
                        escaped = False
                    elif current == "\\":
                        escaped = True
                    elif current == quote:
                        i += 1
                        break
                    i += 1
                continue
            i += 1
        return "".join(chars)

    def _find_matching(self, text: str, open_index: int, open_char: str, close_char: str) -> int:
        depth = 0
        for index in range(open_index, len(text)):
            if text[index] == open_char:
                depth += 1
            elif text[index] == close_char:
                depth -= 1
                if depth == 0:
                    return index
        return -1

    def _line_no(self, content: str, index: int) -> int:
        return content.count("\n", 0, max(index, 0)) + 1

    def _rel_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return path.as_posix()

    def _sample_context(self, content: str, line: int) -> str:
        lines = content.splitlines()
        if not lines:
            return ""
        start = max(line - 2, 0)
        end = min(line + 1, len(lines))
        return " ".join(line_text.strip() for line_text in lines[start:end] if line_text.strip())[:500]

    def _iter_catch_blocks(self, masked: str) -> list[tuple[int, int, int]]:
        blocks: list[tuple[int, int, int]] = []
        for match in re.finditer(r"\bcatch\s*\(", masked):
            paren_index = masked.find("(", match.start())
            if paren_index < 0:
                continue
            paren_end = self._find_matching(masked, paren_index, "(", ")")
            if paren_end < 0:
                continue
            brace_index = paren_end + 1
            while brace_index < len(masked) and masked[brace_index].isspace():
                brace_index += 1
            if brace_index >= len(masked) or masked[brace_index] != "{":
                continue
            brace_end = self._find_matching(masked, brace_index, "{", "}")
            if brace_end < 0:
                continue
            blocks.append((match.start(), brace_index + 1, brace_end))
        return blocks

    def _iter_return_statements(self, masked: str) -> list[tuple[int, int, str]]:
        statements: list[tuple[int, int, str]] = []
        for match in re.finditer(r"\breturn\b", masked):
            index = match.end()
            paren_depth = 0
            bracket_depth = 0
            while index < len(masked):
                ch = masked[index]
                if ch == "(":
                    paren_depth += 1
                elif ch == ")" and paren_depth > 0:
                    paren_depth -= 1
                elif ch == "[":
                    bracket_depth += 1
                elif ch == "]" and bracket_depth > 0:
                    bracket_depth -= 1
                elif ch == ";" and paren_depth == 0 and bracket_depth == 0:
                    statements.append((match.start(), index + 1, masked[match.start() : index + 1]))
                    break
                index += 1
        return statements

    def _wrapped_error_response_pattern(self) -> str:
        wrappers = [str(value).strip() for value in self.return_strategy.get("wrapper_types", []) if str(value).strip()]
        method_names = [
            str(value).strip()
            for value in self.wrapped_error_response_config.get("method_names", [])
            if str(value).strip()
        ]
        if not wrappers or not method_names:
            return r"$^"
        joined = "|".join(re.escape(wrapper) for wrapper in wrappers)
        methods = "|".join(re.escape(method_name) for method_name in method_names)
        return rf"\b(?:new\s+)?(?:[\w$.]+\.)?(?:{joined})\b(?:<[^>]+>)?\s*\.\s*(?:{methods})\s*\("

    def _classify_catch_strategy(self, body_original: str, body_masked: str) -> str:
        if not body_masked.strip():
            return "empty_swallow"
        wrapped_error = re.search(self._wrapped_error_response_pattern(), body_original)
        if wrapped_error and re.search(r"\breturn\b", body_masked):
            return "return_wrapped_error"
        if re.search(r"\bthrow\s+new\s+(?:Exception|RuntimeException|Throwable)\b", body_masked):
            return "rethrow_generic_exception"
        if re.search(r"\bthrow\b", body_masked):
            return "rethrow_specific_exception"
        if re.search(r"\breturn\s+null\b", body_masked):
            return "return_null"
        if re.search(r"\breturn\s+(?:-?\d+|ERROR_\w+)\b", body_masked):
            return "return_error_code"
        if re.search(r"\breturn\b", body_masked):
            return "return_other"
        if self._marks_failure_without_exit(body_original, body_masked):
            return "mark_failure_state"
        if re.search(r"\b(?:log|logger)\s*\.\s*(?:error|warn|debug|info)\s*\(", body_masked) or re.search(r"\.printStackTrace\s*\(", body_masked):
            return "log_only"
        return "swallow_other"

    def _marks_failure_without_exit(self, body_original: str, body_masked: str) -> bool:
        if re.search(r"\.\s*set(?:Result|Error|Fail|Exception|Status|Code|Msg|Message|Flag)\w*\s*\(", body_masked):
            return True
        if re.search(r"\.\s*put\s*\(\s*\"(?:result|ret|error|fail|exception|status|code|msg|message)", body_original, re.IGNORECASE):
            return True
        if re.search(r"\b(?:fail|error|exception)\w*\s*(?:\+\+|=)", body_masked, re.IGNORECASE):
            return True
        return False

    def _classify_error_return_contract(self, statement_original: str, statement_masked: str) -> str | None:
        if re.search(self._wrapped_error_response_pattern(), statement_original):
            return "wrapped_error_response"
        if re.search(r"\breturn\s+null\b", statement_masked):
            return "return_null"
        if re.search(r"\breturn\s+(?:-?\d+|ERROR_\w+)\b", statement_masked):
            return "return_error_code"
        if re.search(str(self.return_pattern_config["string_literal_pattern"]), statement_original):
            return "return_string"
        if re.search(str(self.return_pattern_config["boolean_literal_pattern"]), statement_masked):
            return "return_boolean"
        return None

    def _business_exception_settings(self) -> tuple[set[str], list[re.Pattern[str]], str]:
        configured = [
            str(value).strip()
            for value in self.business_exception_config.get("standard_types", [])
            if str(value).strip()
        ]
        if not configured:
            configured = ["BusinessException"]
            mode = "default_standard_type"
        else:
            mode = "configured_standard_types"
        patterns = [
            str(value).strip()
            for value in self.business_exception_config.get("name_patterns", [])
            if str(value).strip()
        ]
        if not patterns:
            patterns = [r"BusinessException$", r"BizException$", r"BssException$", r"ServiceException$"]
        return set(configured), [re.compile(pattern) for pattern in patterns], mode

    def _is_business_exception(self, exception_type: str, standard_types: set[str], patterns: list[re.Pattern[str]]) -> bool:
        if exception_type in standard_types:
            return True
        return any(pattern.search(exception_type) for pattern in patterns)

    def _analyze_behavior_semantics(self) -> Dict[str, Any]:
        strategy_counts: dict[str, int] = defaultdict(int)
        contract_counts: dict[str, int] = defaultdict(int)
        failure_strategy_issues: list[dict[str, object]] = []
        swallowed_exception_issues: list[dict[str, object]] = []
        error_return_contract_issues: list[dict[str, object]] = []
        generic_exception_issues: list[dict[str, object]] = []
        business_exception_issues: list[dict[str, object]] = []
        standard_business_exceptions, business_patterns, business_mode = self._business_exception_settings()
        exception_throw_count = 0
        generic_exception_throw_count = 0
        business_exception_throw_count = 0
        standard_business_exception_throw_count = 0

        for path in self._iter_java_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            masked = self._mask_java_text(content)
            rel_path = self._rel_path(path)
            is_controller = self._is_controller_candidate(path, content)

            for catch_start, body_start, body_end in self._iter_catch_blocks(masked):
                line = self._line_no(content, catch_start)
                body_original = content[body_start:body_end]
                body_masked = masked[body_start:body_end]
                strategy = self._classify_catch_strategy(body_original, body_masked)
                strategy_counts[strategy] += 1
                row = {
                    "strategy": strategy,
                    "file": rel_path,
                    "line": line,
                    "context": self._sample_context(content, line),
                }
                failure_strategy_issues.append(row)
                if strategy in {"empty_swallow", "log_only", "swallow_other"}:
                    swallowed_exception_issues.append(row)

            if is_controller:
                for start, end, _statement in self._iter_return_statements(masked):
                    statement_original = content[start:end]
                    statement_masked = masked[start:end]
                    contract = self._classify_error_return_contract(statement_original, statement_masked)
                    if contract is None:
                        continue
                    contract_counts[contract] += 1
                    line = self._line_no(content, start)
                    error_return_contract_issues.append(
                        {
                            "contract": contract,
                            "file": rel_path,
                            "line": line,
                            "context": self._sample_context(content, line),
                        }
                    )

            for match in re.finditer(r"\bthrow\s+new\s+(\w*Exception|Throwable)\b", masked):
                exception_type = match.group(1)
                exception_throw_count += 1
                line = self._line_no(content, match.start())
                row = {
                    "exception_type": exception_type,
                    "file": rel_path,
                    "line": line,
                    "context": self._sample_context(content, line),
                }
                if exception_type in {"Exception", "RuntimeException", "Throwable"}:
                    generic_exception_throw_count += 1
                    generic_exception_issues.append(row)
                if self._is_business_exception(exception_type, standard_business_exceptions, business_patterns):
                    business_exception_throw_count += 1
                    is_standard = exception_type in standard_business_exceptions
                    if is_standard:
                        standard_business_exception_throw_count += 1
                    else:
                        business_exception_issues.append({**row, "standard": "否"})

            if is_controller:
                for match in re.finditer(r"\bthrow\s+new\s+(\w*Exception|Throwable)\b", masked):
                    contract_counts["throw_exception"] += 1
                    line = self._line_no(content, match.start())
                    error_return_contract_issues.append(
                        {
                            "contract": "throw_exception",
                            "file": rel_path,
                            "line": line,
                            "context": self._sample_context(content, line),
                        }
                    )

        strategy_total = sum(strategy_counts.values())
        contract_total = sum(contract_counts.values())
        return {
            "catch_block_count": strategy_total,
            "failure_strategy_count": len(strategy_counts),
            "failure_strategy_total_count": strategy_total,
            "failure_strategy_dominant_count": max(strategy_counts.values()) if strategy_counts else 0,
            "swallowed_catch_count": len(swallowed_exception_issues),
            "error_return_contract_count": len(contract_counts),
            "error_return_contract_total_count": contract_total,
            "error_return_contract_dominant_count": max(contract_counts.values()) if contract_counts else 0,
            "generic_exception_throw_count": generic_exception_throw_count,
            "exception_throw_count": exception_throw_count,
            "business_exception_throw_count": business_exception_throw_count,
            "standard_business_exception_throw_count": standard_business_exception_throw_count,
            "nonstandard_business_exception_throw_count": business_exception_throw_count - standard_business_exception_throw_count,
            "standard_business_exceptions": ", ".join(sorted(standard_business_exceptions)),
            "business_exception_detection_mode": business_mode,
            "failure_strategy_distribution": [
                {"strategy": key, "count": value}
                for key, value in sorted(strategy_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "error_return_contract_distribution": [
                {"contract": key, "count": value}
                for key, value in sorted(contract_counts.items(), key=lambda item: item[1], reverse=True)
            ],
            "failure_strategy_issues": failure_strategy_issues,
            "swallowed_exception_issues": swallowed_exception_issues,
            "error_return_contract_issues": error_return_contract_issues,
            "generic_exception_issues": generic_exception_issues,
            "business_exception_convergence_issues": business_exception_issues,
        }

    def _analyze_error_handling(self) -> Dict[str, Any]:
        """分析错误处理模式"""
        error_patterns = defaultdict(int)
        file_count = 0
        patterns_to_check = self._build_error_patterns()

        for path in self._iter_java_files():
            file_count += 1
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern_name, pattern in patterns_to_check.items():
                matches = len(re.findall(pattern, content))
                if matches > 0:
                    error_patterns[pattern_name] += matches

        pattern_count = len(error_patterns)
        if pattern_count > 0:
            max_count = max(error_patterns.values())
            total_count = sum(error_patterns.values())
            consistency_score = max_count / total_count if total_count > 0 else 0
        else:
            consistency_score = 1.0

        top_patterns = sorted(error_patterns.items(), key=lambda item: item[1], reverse=True)[: self.top_error_patterns_limit]
        return {
            "pattern_count": pattern_count,
            "consistency_score": round(consistency_score, 2),
            "patterns": dict(error_patterns),
            "top_patterns": [{"pattern": pattern, "count": count} for pattern, count in top_patterns],
            "file_count": file_count,
        }

    def _analyze_return_formats(self) -> Dict[str, Any]:
        """分析返回格式"""
        return_formats = defaultdict(int)
        controller_candidates = 0
        configured_scope = str(self.return_strategy["scan_scope"]).strip().lower()
        scan_scope = configured_scope
        formats_to_check = self._build_return_patterns()

        if configured_scope == "controllers":
            for path in self._iter_java_files():
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if self._is_controller_candidate(path, content):
                    controller_candidates += 1

        degrade_without_controllers = bool(self.project_strategy["degrade_without_controllers"])
        controllerless_scope = str(self.project_strategy["controllerless_return_scope"]).strip().lower()

        analysis_mode = "all_java" if configured_scope == "all_java" else "controllers_only"
        degraded_reason = None
        if configured_scope == "controllers" and controller_candidates == 0 and degrade_without_controllers:
            degraded_reason = f"no_controller_candidates:{self.project_kind}"
            if controllerless_scope == "all_java":
                scan_scope = "all_java"
                analysis_mode = "degraded_to_all_java"
            else:
                scan_scope = "skip"
                analysis_mode = "skipped_no_controller"
        elif configured_scope == "controllers" and controller_candidates == 0:
            degraded_reason = f"no_controller_candidates:{self.project_kind}"
            analysis_mode = "controllers_empty"

        if scan_scope == "skip":
            return {
                "format_count": 0,
                "consistency_score": None,
                "formats": {},
                "top_formats": [],
                "controller_candidates": controller_candidates,
                "configured_scan_scope": configured_scope,
                "scan_scope": scan_scope,
                "analysis_mode": analysis_mode,
                "degraded_reason": degraded_reason,
                "preferred_wrappers": [str(value) for value in self.return_strategy.get("wrapper_types", [])[: self.preferred_wrapper_preview]],
            }

        for path in self._iter_java_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            is_controller = self._is_controller_candidate(path, content)
            if scan_scope == "controllers" and not is_controller:
                continue

            for format_name, pattern in formats_to_check.items():
                matches = len(re.findall(pattern, content))
                if matches > 0:
                    return_formats[format_name] += matches

        format_count = len(return_formats)
        if format_count > 0:
            max_count = max(return_formats.values())
            total_count = sum(return_formats.values())
            consistency_score = max_count / total_count if total_count > 0 else 0
        else:
            consistency_score = 1.0

        top_formats = sorted(return_formats.items(), key=lambda item: item[1], reverse=True)[: self.top_return_formats_limit]
        return {
            "format_count": format_count,
            "consistency_score": round(consistency_score, 2),
            "formats": dict(return_formats),
            "top_formats": [{"format": format_name, "count": count} for format_name, count in top_formats],
            "controller_candidates": controller_candidates,
            "configured_scan_scope": configured_scope,
            "scan_scope": scan_scope,
            "analysis_mode": analysis_mode,
            "degraded_reason": degraded_reason,
            "preferred_wrappers": [str(value) for value in self.return_strategy.get("wrapper_types", [])[: self.preferred_wrapper_preview]],
        }

    def _analyze_exceptions(self) -> Dict[str, Any]:
        """分析异常类型"""
        exceptions = defaultdict(int)
        exception_pattern = str(self.return_pattern_config["exception_pattern"]).strip()

        for path in self._iter_java_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            matches = re.findall(exception_pattern, content)
            for exception_type in matches:
                if isinstance(exception_type, tuple):
                    exception_type = next((str(item) for item in exception_type if str(item).strip()), "")
                exception_type = str(exception_type).strip()
                if not exception_type:
                    continue
                exceptions[exception_type] += 1

        exception_count = len(exceptions)
        top_exceptions = sorted(exceptions.items(), key=lambda item: item[1], reverse=True)[: self.top_exception_types_limit]
        return {
            "exception_count": exception_count,
            "exceptions": dict(exceptions),
            "top_exceptions": [{"type": exception_type, "count": count} for exception_type, count in top_exceptions],
        }

    def _build_facts(
        self,
        error_stats: Dict[str, Any],
        return_stats: Dict[str, Any],
        exception_stats: Dict[str, Any],
        behavior_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        error_counts = list(error_stats.get("patterns", {}).values()) if isinstance(error_stats.get("patterns"), dict) else []
        return_counts = list(return_stats.get("formats", {}).values()) if isinstance(return_stats.get("formats"), dict) else []
        return_total = sum(return_counts) if return_stats.get("scan_scope") != "skip" else None
        return_max = max(return_counts) if return_counts else (0 if return_total == 0 else None)
        return {
            "error_pattern_max_count": max(error_counts) if error_counts else 0,
            "error_pattern_total_count": sum(error_counts),
            "return_format_max_count": return_max,
            "return_format_total_count": return_total,
            "exception_count": exception_stats["exception_count"],
            "total_files": error_stats["file_count"],
            "failure_strategy_total_count": behavior_stats["failure_strategy_total_count"],
            "failure_strategy_dominant_count": behavior_stats["failure_strategy_dominant_count"],
            "swallowed_catch_count": behavior_stats["swallowed_catch_count"],
            "catch_block_count": behavior_stats["catch_block_count"],
            "error_return_contract_total_count": behavior_stats["error_return_contract_total_count"],
            "error_return_contract_dominant_count": behavior_stats["error_return_contract_dominant_count"],
            "generic_exception_throw_count": behavior_stats["generic_exception_throw_count"],
            "exception_throw_count": behavior_stats["exception_throw_count"],
            "business_exception_throw_count": behavior_stats["business_exception_throw_count"],
            "standard_business_exception_throw_count": behavior_stats["standard_business_exception_throw_count"],
            "nonstandard_business_exception_throw_count": behavior_stats["nonstandard_business_exception_throw_count"],
        }
