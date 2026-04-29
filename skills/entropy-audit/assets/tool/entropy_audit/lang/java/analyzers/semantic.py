#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语义熵分析器
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict

from entropy_audit.lang.java.scoring_v1_engine import score_dimension_v1


CLASS_DECL_RE = re.compile(r"\b(?:class|interface|enum)\s+(\w+)")
TYPE_DECL_RE = re.compile(r"\b(enum|class)\s+(\w+)\b[^{;]*\{")

RULE_ID_NAMING = "semantic.naming_inconsistency_ratio"
RULE_ID_TERM_GAP = "semantic.term_gap_ratio"
RULE_ID_STATE_DUP = "semantic.state_duplicate_ratio"
RULE_ID_STATE_SCATTER = "semantic.state_value_scatter_ratio"


class SemanticAnalyzer:
    """语义熵分析器"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.project_root = Path(config["project"]["root"])
        self.exclude_dirs = set(config["project"]["exclude_dirs"])
        self.include_extensions = {
            str(value).strip().lower()
            for value in config["project"].get("include_extensions", [])
            if str(value).strip()
        }
        self.glossary = config.get("glossary", {})
        self.glossary_source = config.get("glossary_source", {}) if isinstance(config.get("glossary_source"), dict) else {}
        self.project_glossary_missing = bool(self.glossary_source.get("missing"))
        self.scoring_v1 = config.get("scoring_v1", {}) if isinstance(config.get("scoring_v1"), dict) else {}
        self.strategy = config["strategy"]
        detail_export = config.get("detail_export", {}) if isinstance(config.get("detail_export"), dict) else {}
        detail_limits = detail_export.get("limits", {}) if isinstance(detail_export.get("limits"), dict) else {}
        detectors = config.get("detectors", {}) if isinstance(config.get("detectors"), dict) else {}
        self.semantic_detectors = detectors["semantic"] if isinstance(detectors.get("semantic"), dict) else {}
        term_extraction = self.semantic_detectors["term_extraction"] if isinstance(self.semantic_detectors.get("term_extraction"), dict) else {}
        state_detection = self.semantic_detectors["state_detection"] if isinstance(self.semantic_detectors.get("state_detection"), dict) else {}
        self.glossary_strategy = self.strategy["glossary"]
        self.missing_glossary_policy = str(self.glossary_strategy.get("missing_glossary_policy", "term_gap_only")).strip().lower()
        self.min_term_length = int(self.glossary_strategy["min_term_length"])
        self.variant_threshold = int(self.glossary_strategy["variant_threshold"])
        term_gap_strategy = self.glossary_strategy["term_gap"]
        self.term_gap_candidate_mode = str(term_gap_strategy["candidate_mode"]).strip().lower()
        self.term_gap_min_occurrences = int(term_gap_strategy["min_occurrences"])
        self.term_gap_max_candidate_terms = int(term_gap_strategy["max_candidate_terms"])
        self.ignored_terms = {str(value).lower() for value in self.glossary_strategy["ignore_terms"]}
        self.term_gap_exclude_terms = {str(value).lower() for value in term_gap_strategy["exclude_terms"]}
        self.term_scan_targets = {
            str(value).strip().lower()
            for value in term_extraction["scan_targets"]
            if str(value).strip()
        }
        self.token_patterns = [re.compile(str(pattern)) for pattern in term_extraction["token_patterns"] if str(pattern).strip()]
        self.naming_ignore_class_suffixes = [
            str(value).strip().lower()
            for value in term_extraction.get("naming_ignore_class_suffixes", [])
            if str(value).strip()
        ]
        self.state_carrier_name_patterns = [
            re.compile(str(pattern))
            for pattern in state_detection["carrier_name_patterns"]
            if str(pattern).strip()
        ]
        self.state_constant_field_pattern = re.compile(str(state_detection["constant_field_pattern"]))
        self.state_string_literal_pattern = re.compile(str(state_detection["string_literal_pattern"]))
        self.state_numeric_literal_pattern = re.compile(str(state_detection["numeric_literal_pattern"]))
        self.state_strip_prefixes = [str(value).strip().upper() for value in state_detection["strip_prefixes"] if str(value).strip()]
        self.state_strip_suffixes = [str(value).strip().upper() for value in state_detection["strip_suffixes"] if str(value).strip()]
        self.state_ignore_item_patterns = [
            re.compile(str(pattern))
            for pattern in state_detection.get("ignore_item_patterns", [])
            if str(pattern).strip()
        ]
        self.state_min_carrier_items = int(state_detection["min_carrier_items"])
        self.state_min_shared_items = int(state_detection["min_shared_items"])
        self.state_similarity_threshold = float(state_detection["similarity_threshold"])
        self.state_cluster_sample_limit = int(state_detection["cluster_sample_limit"])
        self.state_scatter_sample_limit = int(state_detection.get("scatter_sample_limit", self.state_cluster_sample_limit))
        self.state_hardcoded_context_patterns = [
            re.compile(str(pattern))
            for pattern in state_detection.get(
                "hardcoded_context_patterns",
                [r"(?i)\b(?:status|state|statusCd|statusCode|stateCd|stateCode)\b"],
            )
            if str(pattern).strip()
        ]
        self.state_context_key_literals = {
            "STATUS",
            "STATE",
            "STATUS_CD",
            "STATUS_CODE",
            "STATE_CD",
            "STATE_CODE",
            "FILE_TYPE",
            "TYPE_CD",
            "TYPE_CODE",
        }
        self.undefined_terms_limit = int(detail_limits["semantic_undefined_terms"])
        self.top_inconsistent_limit = int(detail_limits["semantic_top_inconsistent"])
        self.variant_samples_limit = int(detail_limits["semantic_variant_samples"])
        self.glossary_aliases = self._build_glossary_aliases()
        self.naming_glossary_aliases = self._build_glossary_aliases("naming")
        self.term_gap_glossary_aliases = self._build_glossary_aliases("term_gap")
        self.glossary_term_tokens = self._glossary_term_tokens()

    def analyze(self) -> Dict[str, Any]:
        naming_stats = self._analyze_naming_consistency()
        term_usage = self._analyze_term_usage()
        state_stats = self._analyze_state_definitions()
        pending_rules = self._pending_rules(naming_stats, term_usage)
        facts = self._build_facts(naming_stats, term_usage, state_stats, pending_rules)

        details = {
            "total_classes": naming_stats["total_classes"],
            "naming_inconsistency_count": naming_stats["inconsistency_count"],
            "glossary_matched_terms": naming_stats["matched_term_count"],
            "naming_matched_hit_count": naming_stats["matched_hit_count"],
            "naming_standard_hit_count": naming_stats["standard_hit_count"],
            "naming_nonstandard_hit_count": naming_stats["nonstandard_hit_count"],
            "naming_variant_family_count": naming_stats["variant_family_count"],
            "naming_patterns": naming_stats["naming_patterns"],
            "term_coverage": term_usage["coverage"],
            "undefined_terms": term_usage["undefined_count"],
            "undefined_terms_list": term_usage["undefined_terms"][: self.undefined_terms_limit],
            "defined_terms": term_usage["defined_count"],
            "term_gap_candidate_count": term_usage["candidate_count"],
            "term_gap_raw_term_count": term_usage["raw_term_count"],
            "term_gap_raw_unique_term_count": term_usage["raw_unique_term_count"],
            "term_gap_min_occurrences": self.term_gap_min_occurrences,
            "term_gap_candidate_mode": self.term_gap_candidate_mode,
            "term_gap_max_candidate_terms": self.term_gap_max_candidate_terms,
            "state_definitions": state_stats["state_count"],
            "duplicate_states": state_stats["duplicate_count"],
            "state_item_total": state_stats["state_item_total"],
            "state_unique_item_count": state_stats["unique_item_count"],
            "state_files": state_stats["state_files"],
            "state_duplicate_cluster_count": state_stats["duplicate_cluster_count"],
            "state_duplicate_clusters": state_stats["duplicate_clusters"],
            "state_scattered_value_count": state_stats["scattered_value_count"],
            "state_scattered_value_unique_count": state_stats["scattered_value_unique_count"],
            "state_scattered_value_file_count": state_stats["scattered_value_file_count"],
            "state_scattered_value_total_file_count": state_stats["scattered_value_total_file_count"],
            "state_value_reference_count": state_stats["state_value_reference_count"],
            "naming_conflict_issues": naming_stats["conflict_issues"],
            "naming_conflict_locations": naming_stats["conflict_locations"],
            "undefined_term_issues": term_usage["undefined_term_issues"],
            "undefined_term_locations": term_usage["undefined_term_locations"],
            "state_duplicate_cluster_issues": state_stats["duplicate_cluster_issues"],
            "state_duplicate_carrier_issues": state_stats["duplicate_carrier_issues"],
            "state_scattered_value_issues": state_stats["scattered_value_issues"],
            "state_scattered_value_locations": state_stats["scattered_value_locations"],
            "state_scattered_value_candidate_count": state_stats["scattered_value_candidate_count"],
            "state_scattered_value_candidate_unique_count": state_stats["scattered_value_candidate_unique_count"],
            "top_inconsistent_terms": naming_stats["top_inconsistent"],
            "term_variants": naming_stats.get("term_variants", {}),
            "glossary_mode": self.glossary_strategy["mode"],
            "glossary_enabled": bool(self.glossary_aliases),
            "naming_glossary_terms": len(self.naming_glossary_aliases),
            "term_gap_glossary_terms": len(self.term_gap_glossary_aliases),
            "naming_glossary_missing": not bool(self.naming_glossary_aliases),
            "term_gap_glossary_missing": not bool(self.term_gap_glossary_aliases),
            "glossary_source_type": self.glossary_source.get("type", "unknown"),
            "glossary_files": self.glossary_source.get("files", []),
            "glossary_missing": self.project_glossary_missing,
            "missing_glossary_policy": self.missing_glossary_policy,
            "term_scan_targets": sorted(self.term_scan_targets),
            "state_detection_mode": "carrier_item_overlap",
            "state_carrier_name_pattern_count": len(self.state_carrier_name_patterns),
            "state_ignore_item_pattern_count": len(self.state_ignore_item_patterns),
            "state_min_carrier_items": self.state_min_carrier_items,
            "state_min_shared_items": self.state_min_shared_items,
            "state_similarity_threshold": round(self.state_similarity_threshold, 2),
            "state_scatter_detection_mode": "status_context_string_literal",
        }
        v1_payload = score_dimension_v1(self.scoring_v1, "semantic", facts, details)
        if not isinstance(v1_payload, dict):
            raise ValueError("SemanticAnalyzer requires [code_entropy.scoring_v1] and a valid semantic scorecard")
        finalized = self._finalize_scoring(v1_payload, pending_rules)
        metrics = finalized["metrics"] if isinstance(finalized.get("metrics"), dict) else {}
        details["semantic_rule_overview"] = self._build_rule_overview(metrics, naming_stats, term_usage, state_stats, pending_rules)
        details["table_total_counts"] = {
            "semantic_rule_overview": len(details["semantic_rule_overview"]),
            "naming_conflict_issues": naming_stats["conflict_issue_total"],
            "naming_conflict_locations": naming_stats["conflict_location_total"],
            "undefined_term_issues": term_usage["undefined_term_issue_total"],
            "undefined_term_locations": term_usage["undefined_term_location_total"],
            "state_duplicate_cluster_issues": state_stats["duplicate_cluster_issue_total"],
            "state_duplicate_carrier_issues": state_stats["duplicate_carrier_issue_total"],
            "state_scattered_value_issues": state_stats["scattered_value_issue_total"],
            "state_scattered_value_locations": state_stats["scattered_value_location_total"],
        }
        details["score_status"] = finalized.get("score_status")
        details["coverage"] = finalized.get("coverage")
        details["missing_rule_ids"] = finalized.get("missing_rule_ids", [])
        details["partial_reason"] = finalized.get("partial_reason")
        return {
            "score": finalized["score"],
            "level": finalized["level"],
            "score_breakdown": finalized["score_breakdown"],
            "metrics": metrics,
            "facts": facts,
            "details": details,
            "scoring_v1": finalized,
            "metric_definitions": finalized.get("metric_definitions", {}),
            "score_status": finalized.get("score_status", "complete"),
            "coverage": finalized.get("coverage"),
            "missing_rule_ids": finalized.get("missing_rule_ids", []),
            "partial_reason": finalized.get("partial_reason"),
        }

    def _iter_java_files(self) -> list[Path]:
        candidates: list[Path] = []
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file_name in files:
                if Path(file_name).suffix.lower() in self.include_extensions:
                    candidates.append(Path(root, file_name))
        return candidates

    def _relative_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(path).replace("\\", "/")

    def _class_entries(self, content: str, path: Path) -> list[dict[str, Any]]:
        rel_path = self._relative_path(path)
        return [
            {
                "class_name": str(match.group(1)).strip(),
                "file": rel_path,
                "line": content[: match.start()].count("\n") + 1,
            }
            for match in CLASS_DECL_RE.finditer(content)
            if str(match.group(1)).strip()
        ]

    def _extract_tokens(self, value: str, *, minimum_length: int = 1, ignore_common_terms: bool = False) -> list[str]:
        tokens: list[str] = []
        for pattern in self.token_patterns:
            for match in pattern.findall(value):
                token = match[0] if isinstance(match, tuple) else match
                token = str(token).strip()
                if len(token) < minimum_length:
                    continue
                if ignore_common_terms and token.lower() in self.ignored_terms:
                    continue
                tokens.append(token)
        return tokens

    def _term_gap_tokens(self, value: str) -> list[str]:
        return self._extract_tokens(value, minimum_length=self.min_term_length, ignore_common_terms=True)

    def _symbol_tokens(self, value: str) -> list[str]:
        return [token.lower() for token in self._extract_tokens(value, minimum_length=1, ignore_common_terms=False)]

    def _should_ignore_class_name(self, class_name: str, match_position: str = "any") -> bool:
        if str(match_position).strip().lower() != "suffix":
            return False
        normalized = str(class_name).strip().lower()
        if not normalized:
            return True
        return any(normalized.endswith(suffix) for suffix in self.naming_ignore_class_suffixes)

    def _collect_term_symbols(self) -> tuple[list[dict[str, Any]], dict[str, int], int]:
        symbols: list[dict[str, Any]] = []
        naming_patterns = defaultdict(int)
        total_classes = 0
        for path in self._iter_java_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel_path = self._relative_path(path)
            class_entries = self._class_entries(content, path)
            total_classes += len(class_entries)
            if "file_stem" in self.term_scan_targets:
                symbols.append({"source": "file_stem", "symbol_name": path.stem, "class_name": "-", "file": rel_path, "line": 1, "tokens": self._symbol_tokens(path.stem)})
            if "class_name" in self.term_scan_targets:
                for entry in class_entries:
                    class_name = str(entry["class_name"])
                    if re.match(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)*$", class_name):
                        naming_patterns["UpperCamelCase"] += 1
                    elif "_" in class_name:
                        naming_patterns["snake_case"] += 1
                    else:
                        naming_patterns["other"] += 1
                    symbols.append({"source": "class_name", "symbol_name": class_name, "class_name": class_name, "file": entry["file"], "line": entry["line"], "tokens": self._symbol_tokens(class_name)})
        return symbols, dict(naming_patterns), total_classes

    def _build_glossary_aliases(self, scope: str | None = None) -> dict[str, list[dict[str, Any]]]:
        aliases_by_standard: dict[str, list[dict[str, Any]]] = {}
        for term_config in self.glossary.values():
            if not isinstance(term_config, dict):
                continue
            if scope:
                used_by = {
                    str(value).strip().lower()
                    for value in term_config.get("used_by", [])
                    if str(value).strip()
                }
                if scope not in used_by:
                    continue
            standard = str(term_config.get("standard", "")).strip()
            if not standard:
                continue
            match_position = str(term_config.get("match_position", "any") or "any").strip().lower()
            raw_aliases = [standard] + [str(variant).strip() for variant in term_config.get("variants", []) if str(variant).strip()]
            dedup: dict[tuple[str, ...], dict[str, Any]] = {}
            for display in raw_aliases:
                tokens = tuple(self._symbol_tokens(display))
                if not tokens:
                    continue
                is_standard = display == standard
                if tokens not in dedup or (is_standard and not bool(dedup[tokens].get("is_standard"))):
                    dedup[tokens] = {
                        "display": display,
                        "tokens": list(tokens),
                        "match_position": match_position,
                        "is_standard": is_standard,
                    }
            aliases = list(dedup.values())
            aliases.sort(key=lambda item: (-len(item["tokens"]), -len(str(item["display"])), str(item["display"]).lower()))
            aliases_by_standard[standard] = aliases
        return aliases_by_standard

    def _glossary_term_tokens(self) -> set[str]:
        tokens: set[str] = set()
        for aliases in self.term_gap_glossary_aliases.values():
            for alias in aliases:
                for token in alias["tokens"]:
                    if token and token not in self.term_gap_exclude_terms:
                        tokens.add(token)
        return tokens

    def _match_alias_tokens(self, symbol_tokens: list[str], alias_tokens: list[str], match_position: str = "any") -> bool:
        if not symbol_tokens or not alias_tokens or len(alias_tokens) > len(symbol_tokens):
            return False
        window = len(alias_tokens)
        if match_position == "prefix":
            return symbol_tokens[:window] == alias_tokens
        if match_position == "suffix":
            return symbol_tokens[-window:] == alias_tokens
        for index in range(len(symbol_tokens) - window + 1):
            if symbol_tokens[index : index + window] == alias_tokens:
                return True
        return False

    def _best_alias_for_symbol(self, symbol_tokens: list[str], aliases: list[dict[str, Any]]) -> dict[str, Any] | None:
        for alias in aliases:
            if self._match_alias_tokens(
                symbol_tokens,
                list(alias["tokens"]),
                str(alias.get("match_position", "any") or "any").strip().lower(),
            ):
                return alias
        return None

    def _analyze_naming_consistency(self) -> Dict[str, Any]:
        symbols, naming_patterns, total_classes = self._collect_term_symbols()
        glossary_ready = bool(self.naming_glossary_aliases)
        pending_config = not glossary_ready and self.missing_glossary_policy in {"term_gap_only", "all_pending"}
        pending_reason = f"{self._glossary_unavailable_reason('naming')}，命名非标准占比未参与评分" if pending_config else ""
        if not glossary_ready:
            return {
                "total_classes": total_classes,
                "naming_patterns": naming_patterns,
                "inconsistency_count": 0,
                "matched_term_count": 0,
                "matched_hit_count": 0,
                "standard_hit_count": 0,
                "nonstandard_hit_count": 0,
                "variant_family_count": 0,
                "top_inconsistent": [],
                "term_variants": {},
                "conflict_issues": [],
                "conflict_locations": [],
                "conflict_issue_total": 0,
                "conflict_location_total": 0,
                "pending_config": pending_config,
                "pending_reason": pending_reason,
            }

        term_variants = defaultdict(set)
        term_variant_samples: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        term_variant_locations: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        term_hit_count: Counter[str] = Counter()
        term_standard_hit_count: Counter[str] = Counter()
        term_nonstandard_hit_count: Counter[str] = Counter()
        for standard, aliases in self.naming_glossary_aliases.items():
            match_position = str(aliases[0].get("match_position", "any") if aliases else "any").strip().lower()
            for symbol in symbols:
                if self._should_ignore_class_name(str(symbol.get("class_name", "")), match_position):
                    continue
                alias = self._best_alias_for_symbol(list(symbol["tokens"]), aliases)
                if not alias:
                    continue
                variant = str(alias["display"])
                term_variants[standard].add(variant)
                hit = {
                    "term": standard,
                    "variant": variant,
                    "class_name": symbol["class_name"],
                    "symbol_name": symbol["symbol_name"],
                    "source": symbol["source"],
                    "file": symbol["file"],
                    "line": symbol["line"],
                }
                term_hit_count[standard] += 1
                if bool(alias.get("is_standard")):
                    term_standard_hit_count[standard] += 1
                else:
                    term_nonstandard_hit_count[standard] += 1
                term_variant_locations[standard][variant].append(hit)
                samples = term_variant_samples[standard][variant]
                if len(samples) < self.variant_samples_limit:
                    samples.append(hit)

        conflict_issues: list[dict[str, Any]] = []
        conflict_locations: list[dict[str, Any]] = []
        top_inconsistent: list[dict[str, Any]] = []
        inconsistency_count = 0
        matched_hit_count = 0
        standard_hit_count = 0
        nonstandard_hit_count = 0
        variant_family_count = 0
        for term, variants in term_variants.items():
            variant_names = sorted(variants)
            total_hits = int(term_hit_count.get(term, 0) or 0)
            standard_hits = int(term_standard_hit_count.get(term, 0) or 0)
            nonstandard_hits = int(term_nonstandard_hit_count.get(term, 0) or 0)
            if total_hits <= 0:
                continue
            matched_hit_count += total_hits
            standard_hit_count += standard_hits
            nonstandard_hit_count += nonstandard_hits
            nonstandard_variant_names = [name for name in variant_names if name != str(term)]
            nonstandard_variant_count = len(nonstandard_variant_names)
            variant_family_count += nonstandard_variant_count
            if nonstandard_hits <= 0:
                continue
            inconsistency_count += 1
            nonstandard_ratio = (nonstandard_hits / total_hits) if total_hits > 0 else 0.0
            top_inconsistent.append(
                {
                    "term": term,
                    "standard": term,
                    "variant_count": nonstandard_variant_count,
                    "matched_hits": total_hits,
                    "nonstandard_hits": nonstandard_hits,
                    "nonstandard_ratio": round(nonstandard_ratio, 4),
                    "variants": nonstandard_variant_names[: self.variant_samples_limit],
                }
            )
            sample_refs: list[str] = []
            for variant_name in nonstandard_variant_names:
                for sample in term_variant_samples.get(term, {}).get(variant_name, [])[: self.variant_samples_limit]:
                    sample_refs.append(f"{sample['file']}:{sample['line']} ({sample['symbol_name']})")
                conflict_locations.extend(term_variant_locations.get(term, {}).get(variant_name, []))
            conflict_issues.append(
                {
                    "term": term,
                    "standard": term,
                    "variant_count": nonstandard_variant_count,
                    "matched_hits": total_hits,
                    "standard_hits": standard_hits,
                    "nonstandard_hits": nonstandard_hits,
                    "nonstandard_ratio": round(nonstandard_ratio, 4),
                    "variants": ", ".join(nonstandard_variant_names) or "-",
                    "sample_locations": " | ".join(sample_refs[: self.variant_samples_limit]) or "-",
                }
            )

        top_inconsistent.sort(key=lambda item: (-int(item["nonstandard_hits"]), -int(item["variant_count"]), str(item["term"])))
        conflict_issues.sort(key=lambda item: (-int(item["nonstandard_hits"]), -int(item["variant_count"]), str(item["term"])))
        matched_term_count = len([1 for variants in term_variants.values() if variants])
        return {
            "total_classes": total_classes,
            "naming_patterns": naming_patterns,
            "inconsistency_count": inconsistency_count,
            "matched_term_count": matched_term_count,
            "matched_hit_count": matched_hit_count,
            "standard_hit_count": standard_hit_count,
            "nonstandard_hit_count": nonstandard_hit_count,
            "variant_family_count": variant_family_count,
            "top_inconsistent": top_inconsistent[: self.top_inconsistent_limit],
            "term_variants": {key: len(value) for key, value in term_variants.items()},
            "conflict_issues": conflict_issues[: self.top_inconsistent_limit],
            "conflict_locations": conflict_locations,
            "conflict_issue_total": len(conflict_issues),
            "conflict_location_total": len(conflict_locations),
            "pending_config": False,
            "pending_reason": "",
        }

    def _analyze_term_usage(self) -> Dict[str, Any]:
        term_counts: Counter[str] = Counter()
        term_display: dict[str, str] = {}
        term_occurrences: dict[str, list[dict[str, Any]]] = defaultdict(list)
        symbols, _patterns, _total_classes = self._collect_term_symbols()

        for symbol in symbols:
            for term in self._term_gap_tokens(str(symbol["symbol_name"])):
                lowered = term.lower()
                if lowered in self.term_gap_exclude_terms:
                    continue
                term_counts[lowered] += 1
                term_display.setdefault(lowered, term)
                if len(term_occurrences[lowered]) < self.variant_samples_limit:
                    term_occurrences[lowered].append(
                        {
                            "term": term,
                            "source": symbol["source"],
                            "class_name": symbol["class_name"],
                            "file": symbol["file"],
                            "line": symbol["line"],
                        }
                    )

        candidates = [(term, count) for term, count in term_counts.items() if count >= self.term_gap_min_occurrences]
        candidates.sort(key=lambda item: (-item[1], item[0]))
        if self.term_gap_candidate_mode == "top_unique_terms":
            candidates = candidates[: self.term_gap_max_candidate_terms]

        glossary_ready = bool(self.term_gap_glossary_aliases)
        if self.project_glossary_missing or not glossary_ready:
            glossary_reason = self._glossary_unavailable_reason("term_gap")
            undefined_term_issues: list[dict[str, Any]] = [
                {
                    "term": "glossary.md",
                    "count": 1,
                    "sample_locations": glossary_reason,
                }
            ]
            undefined_term_locations: list[dict[str, Any]] = [
                {
                    "term": "glossary.md",
                    "source": "project_glossary",
                    "class_name": "-",
                    "file": "glossary.md",
                    "line": 1,
                }
            ]
            undefined_terms = [{"term": term_display.get(term, term), "count": count} for term, count in candidates]
            if not undefined_terms:
                undefined_terms = [{"term": "glossary.md", "count": 1}]
            for term, count in candidates:
                display_term = term_display.get(term, term)
                sample_rows = term_occurrences.get(term, [])
                undefined_term_issues.append(
                    {
                        "term": display_term,
                        "count": count,
                        "sample_locations": " | ".join(
                            f"{row['file']}:{row['line']}" + (f" ({row['class_name']})" if row["class_name"] != "-" else "")
                            for row in sample_rows
                        ) or "-",
                    }
                )
                for row in sample_rows:
                    undefined_term_locations.append(
                        {
                            "term": display_term,
                            "source": row["source"],
                            "class_name": row["class_name"],
                            "file": row["file"],
                            "line": row["line"],
                        }
                    )
            total_terms = len(candidates) if candidates else 1
            return {
                "coverage": 0.0,
                "defined_count": 0,
                "undefined_count": total_terms,
                "undefined_terms": undefined_terms[: self.undefined_terms_limit],
                "candidate_count": len(candidates),
                "raw_term_count": sum(term_counts.values()),
                "raw_unique_term_count": len(term_counts),
                "total_terms": total_terms,
                "undefined_term_issues": undefined_term_issues[: self.undefined_terms_limit],
                "undefined_term_locations": undefined_term_locations[: self.undefined_terms_limit * self.variant_samples_limit],
                "undefined_term_issue_total": len(undefined_term_issues),
                "undefined_term_location_total": len(undefined_term_locations),
                "pending_config": False,
                "pending_reason": "",
                "scoring_basis": "missing_project_glossary_md" if self.project_glossary_missing else "missing_term_gap_glossary_terms",
            }

        pending_config = not glossary_ready and self.missing_glossary_policy == "all_pending"
        pending_reason = f"{self._glossary_unavailable_reason('term_gap')}，术语缺口未参与评分" if pending_config else ""

        defined_terms = [{"term": term_display.get(term, term), "count": count} for term, count in candidates if glossary_ready and term in self.glossary_term_tokens]
        undefined_terms = [{"term": term_display.get(term, term), "count": count} for term, count in candidates if (not glossary_ready) or term not in self.glossary_term_tokens]
        undefined_term_issues: list[dict[str, Any]] = []
        undefined_term_locations: list[dict[str, Any]] = []
        for term, count in candidates:
            if glossary_ready and term in self.glossary_term_tokens:
                continue
            display_term = term_display.get(term, term)
            sample_rows = term_occurrences.get(term, [])
            undefined_term_issues.append(
                {
                    "term": display_term,
                    "count": count,
                    "sample_locations": " | ".join(
                        f"{row['file']}:{row['line']}" + (f" ({row['class_name']})" if row["class_name"] != "-" else "")
                        for row in sample_rows
                    ) or "-",
                }
            )
            for row in sample_rows:
                undefined_term_locations.append(
                    {
                        "term": display_term,
                        "source": row["source"],
                        "class_name": row["class_name"],
                        "file": row["file"],
                        "line": row["line"],
                    }
                )

        candidate_count = len(candidates)
        coverage = (len(defined_terms) / candidate_count) if candidate_count > 0 else 0.0
        return {
            "coverage": round(coverage, 2),
            "defined_count": len(defined_terms),
            "undefined_count": len(undefined_terms),
            "undefined_terms": undefined_terms[: self.undefined_terms_limit],
            "candidate_count": candidate_count,
            "raw_term_count": sum(term_counts.values()),
            "raw_unique_term_count": len(term_counts),
            "total_terms": candidate_count,
            "undefined_term_issues": undefined_term_issues[: self.undefined_terms_limit],
            "undefined_term_locations": undefined_term_locations[: self.undefined_terms_limit * self.variant_samples_limit],
            "undefined_term_issue_total": len(undefined_term_issues),
            "undefined_term_location_total": len(undefined_term_locations),
            "pending_config": pending_config,
            "pending_reason": pending_reason,
            "scoring_basis": "project_glossary_md" if glossary_ready else "empty_glossary",
        }

    def _pending_rules(self, naming_stats: Dict[str, Any], term_usage: Dict[str, Any]) -> dict[str, str]:
        pending: dict[str, str] = {}
        if naming_stats.get("pending_config"):
            pending[RULE_ID_NAMING] = str(naming_stats.get("pending_reason", "")).strip() or "待配置 glossary，命名非标准占比未参与评分"
        if term_usage.get("pending_config"):
            pending[RULE_ID_TERM_GAP] = str(term_usage.get("pending_reason", "")).strip() or "待配置 glossary，术语缺口未参与评分"
        return pending

    def _build_facts(self, naming_stats: Dict[str, Any], term_usage: Dict[str, Any], state_stats: Dict[str, Any], pending_rules: dict[str, str]) -> Dict[str, Any]:
        return {
            "total_classes": naming_stats["total_classes"],
            "glossary_size": len(self.glossary_aliases),
            "naming_inconsistency_count": naming_stats["inconsistency_count"],
            "glossary_matched_term_count": None if RULE_ID_NAMING in pending_rules else naming_stats["matched_term_count"],
            "naming_matched_hit_count": None if RULE_ID_NAMING in pending_rules else naming_stats["matched_hit_count"],
            "naming_standard_hit_count": None if RULE_ID_NAMING in pending_rules else naming_stats["standard_hit_count"],
            "naming_nonstandard_hit_count": None if RULE_ID_NAMING in pending_rules else naming_stats["nonstandard_hit_count"],
            "naming_variant_family_count": None if RULE_ID_NAMING in pending_rules else naming_stats["variant_family_count"],
            "undefined_term_count": None if RULE_ID_TERM_GAP in pending_rules else term_usage["undefined_count"],
            "total_terms": None if RULE_ID_TERM_GAP in pending_rules else term_usage["total_terms"],
            "state_count": state_stats["state_count"],
            "duplicate_state_count": state_stats["duplicate_count"],
            "scattered_state_value_count": state_stats["scattered_value_count"],
            "state_value_reference_count": state_stats["state_value_reference_count"],
        }

    def _build_rule_overview(self, metrics: dict[str, Any], naming_stats: Dict[str, Any], term_usage: Dict[str, Any], state_stats: Dict[str, Any], pending_rules: dict[str, str]) -> list[dict[str, Any]]:
        naming_pending = pending_rules.get(RULE_ID_NAMING)
        term_gap_pending = pending_rules.get(RULE_ID_TERM_GAP)
        term_gap_suffix = ""
        if term_usage.get("scoring_basis") == "missing_project_glossary_md" and not term_gap_pending:
            term_gap_suffix = "（未找到 glossary.md，按最高风险计分）"
        elif term_usage.get("scoring_basis") == "missing_term_gap_glossary_terms" and not term_gap_pending:
            term_gap_suffix = "（未配置 used_by=term_gap 的有效术语，按最高风险计分）"
        if not term_gap_suffix:
            term_gap_suffix = "（当前按空词典口径计分）" if term_usage.get("scoring_basis") == "empty_glossary" and not term_gap_pending else ""
        return [
            {
                "rule": "命名非标准占比",
                "metric": "naming_inconsistency_ratio",
                "status": "pending_config" if naming_pending else "scored",
                "scored": not bool(naming_pending),
                "pending_reason": naming_pending or "",
                "current_value": None if naming_pending else self._format_rule_value(metrics.get("naming_inconsistency_ratio")),
                "problem_count": naming_stats["inconsistency_count"],
                "problem_unit": "变体家族",
                "count_summary": (
                    naming_pending
                    or (
                        f"配置 {len(self.naming_glossary_aliases)} 个命名术语，"
                        f"命中 {naming_stats['matched_hit_count']} 处，"
                        f"非标准 {naming_stats['nonstandard_hit_count']} 处"
                    )
                ),
                "focus": "把变体家族收敛回标准命名，优先替换非标准类名",
                "summary": naming_pending or (
                    f"{naming_stats['inconsistency_count']} 个概念出现变体家族，"
                    f"非标准命中 {naming_stats['nonstandard_hit_count']} / {naming_stats['matched_hit_count']}"
                    f"（{self._format_rule_value(metrics.get('naming_inconsistency_ratio'))}），"
                    f"涉及 {naming_stats['variant_family_count']} 个变体家族"
                ),
            },
            {
                "rule": "术语缺口",
                "metric": "term_gap_ratio",
                "status": "pending_config" if term_gap_pending else "scored",
                "scored": not bool(term_gap_pending),
                "pending_reason": term_gap_pending or "",
                "current_value": None if term_gap_pending else self._format_rule_value(metrics.get("term_gap_ratio")),
                "problem_count": term_usage["undefined_count"],
                "problem_unit": "未定义术语",
                "count_summary": term_gap_pending or (
                    f"配置 {len(self.term_gap_glossary_aliases)} 个术语，"
                    f"计分候选 {term_usage['total_terms']} 个，"
                    f"未定义 {term_usage['undefined_count']} 个"
                ),
                "focus": "把高频核心术语补入 glossary，降低词典缺口",
                "summary": term_gap_pending or f"{term_usage['undefined_count']} / {term_usage['total_terms']} 个高频候选术语未进入词典{term_gap_suffix}",
            },
            {
                "rule": "状态承载体重复",
                "metric": "state_duplicate_ratio",
                "status": "scored",
                "scored": True,
                "pending_reason": "",
                "current_value": self._format_rule_value(metrics.get("state_duplicate_ratio")),
                "problem_count": state_stats["duplicate_cluster_count"],
                "problem_unit": "重复簇",
                "count_summary": f"{state_stats['duplicate_cluster_count']} 组重复簇，{state_stats['duplicate_count']} 个冗余承载体",
                "focus": "合并并行维护的 Status/State 枚举或常量类，收敛到统一状态源",
                "summary": f"{state_stats['duplicate_cluster_count']} 组状态承载体重复簇，冗余承载体 {state_stats['duplicate_count']} 个",
            },
            {
                "rule": "状态值散落",
                "metric": "state_value_scatter_ratio",
                "status": "scored",
                "scored": True,
                "pending_reason": "",
                "current_value": self._format_rule_value(metrics.get("state_value_scatter_ratio")),
                "problem_count": state_stats["scattered_value_count"],
                "problem_unit": "硬编码状态值",
                "count_summary": (
                    f"{state_stats['scattered_value_count']} 处参与计分，"
                    f"{state_stats['scattered_value_candidate_count']} 处疑似，"
                    f"涉及 {state_stats['scattered_value_total_file_count']} 个文件"
                ),
                "focus": "把 service/controller/mapper 中的状态字面量替换为枚举或常量引用",
                "summary": (
                    f"状态上下文中发现 {state_stats['scattered_value_count']} 处可匹配承载体的硬编码字面量，"
                    f"另有 {state_stats['scattered_value_candidate_count']} 处疑似状态值用于人工确认"
                ),
            },
        ]

    def _format_rule_value(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "未提供"
        return f"{float(value) * 100:.1f}%"

    def _glossary_unavailable_reason(self, scope: str | None = None) -> str:
        source_type = str(self.glossary_source.get("type", "") or "").strip()
        if source_type == "empty_project_glossary_md":
            files = self.glossary_source.get("files", [])
            if isinstance(files, list) and files:
                return f"项目 glossary.md 未解析到有效术语配置：{', '.join(str(item) for item in files)}"
            return "项目 glossary.md 未解析到有效术语配置"
        if scope == "naming" and self.glossary_aliases and not self.naming_glossary_aliases:
            return "项目 glossary.md 未配置 used_by=naming 的有效命名治理术语"
        if scope == "term_gap" and self.glossary_aliases and not self.term_gap_glossary_aliases:
            return "项目 glossary.md 未配置 used_by=term_gap 的有效领域术语"
        return "项目根目录或扫描范围内未找到 glossary.md"

    def _finalize_scoring(self, v1_payload: dict[str, Any], pending_rules: dict[str, str]) -> dict[str, Any]:
        score_breakdown = dict(v1_payload.get("score_breakdown", {}))
        rules = [dict(rule) for rule in score_breakdown.get("rules", []) if isinstance(rule, dict)]
        configured_weight = float(score_breakdown.get("configured_weight", 0.0) or 0.0)
        internal_scale = float(score_breakdown.get("internal_max_score", 100.0) or 100.0)
        display_scale = float(score_breakdown.get("max_score", 100.0) or 100.0)
        raw_missing_rule_ids: list[str] = []
        for rule in rules:
            rule_id = str(rule.get("id", "")).strip()
            pending_reason = pending_rules.get(rule_id, "")
            rule["rule_status"] = "pending_config" if pending_reason else "scored"
            rule["scored"] = not bool(pending_reason)
            rule["pending_reason"] = pending_reason
            if pending_reason:
                raw_missing_rule_ids.append(rule_id)
                rule["raw_value"] = None
                rule["condition"] = "待配置 glossary"
                rule["score_0_100"] = None
                rule["severity"] = None
                rule["contribution"] = 0.0
                rule["max_contribution"] = 0.0

        active_rules = [rule for rule in rules if bool(rule.get("scored"))]
        available_weight = sum(float(rule.get("weight", 0.0) or 0.0) for rule in active_rules)
        weighted_score_sum = sum(float(rule.get("weight", 0.0) or 0.0) * float(rule.get("score_0_100", 0.0) or 0.0) for rule in active_rules)
        internal_score = (weighted_score_sum / available_weight) if available_weight > 0 else 0.0
        display_score = round(internal_score * (display_scale / internal_scale), 1)
        level = self._resolve_level(internal_score, score_breakdown.get("internal_level_bands", {}))
        for rule in active_rules:
            weight = float(rule.get("weight", 0.0) or 0.0)
            score_value = float(rule.get("score_0_100", 0.0) or 0.0)
            rule["contribution"] = round(display_scale * (weight / available_weight) * (score_value / internal_scale), 3) if available_weight > 0 else 0.0
            rule["max_contribution"] = round(display_scale * (weight / available_weight), 3) if available_weight > 0 else 0.0

        coverage = round((available_weight / configured_weight), 3) if configured_weight > 0 else 0.0
        score_status = "partial" if raw_missing_rule_ids else "complete"
        partial_reason = "；".join(pending_rules[rule_id] for rule_id in raw_missing_rule_ids if rule_id in pending_rules) if raw_missing_rule_ids else None

        score_breakdown["rules"] = rules
        score_breakdown["score"] = display_score
        score_breakdown["level"] = level
        score_breakdown["internal_score"] = round(internal_score, 2)
        score_breakdown["available_weight"] = round(available_weight, 3)
        score_breakdown["coverage"] = coverage
        score_breakdown["evaluated_rule_count"] = len(active_rules)
        score_breakdown["score_mode"] = "partial_weighted_average" if raw_missing_rule_ids else score_breakdown.get("score_mode", "fixed_weighted_average")
        score_breakdown["score_status"] = score_status
        score_breakdown["missing_rule_ids"] = list(raw_missing_rule_ids)
        score_breakdown["partial_reason"] = partial_reason

        v1_payload["score"] = display_score
        v1_payload["level"] = level
        v1_payload["score_breakdown"] = score_breakdown
        v1_payload["score_status"] = score_status
        v1_payload["coverage"] = coverage
        v1_payload["missing_rule_ids"] = list(raw_missing_rule_ids)
        v1_payload["partial_reason"] = partial_reason
        return v1_payload

    def _resolve_level(self, score_0_100: float, level_bands: dict[str, Any]) -> str:
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

    def _find_matching_brace(self, content: str, open_index: int) -> int:
        depth = 0
        in_string = False
        string_char = ""
        escape = False
        for index in range(open_index, len(content)):
            char = content[index]
            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == string_char:
                    in_string = False
                continue
            if char in {'"', "'"}:
                in_string = True
                string_char = char
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return index
        return -1

    def _top_level_until_semicolon(self, body: str) -> str:
        depth_round = 0
        depth_square = 0
        depth_curly = 0
        in_string = False
        string_char = ""
        escape = False
        for index, char in enumerate(body):
            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == string_char:
                    in_string = False
                continue
            if char in {'"', "'"}:
                in_string = True
                string_char = char
                continue
            if char == "(":
                depth_round += 1
            elif char == ")":
                depth_round = max(0, depth_round - 1)
            elif char == "[":
                depth_square += 1
            elif char == "]":
                depth_square = max(0, depth_square - 1)
            elif char == "{":
                depth_curly += 1
            elif char == "}":
                depth_curly = max(0, depth_curly - 1)
            elif char == ";" and depth_round == 0 and depth_square == 0 and depth_curly == 0:
                return body[:index]
        return body

    def _split_top_level_csv(self, text: str) -> list[str]:
        if not text.strip():
            return []
        parts: list[str] = []
        current: list[str] = []
        depth_round = 0
        depth_square = 0
        depth_curly = 0
        in_string = False
        string_char = ""
        escape = False
        for char in text:
            if in_string:
                current.append(char)
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == string_char:
                    in_string = False
                continue
            if char in {'"', "'"}:
                in_string = True
                string_char = char
                current.append(char)
                continue
            if char == "(":
                depth_round += 1
            elif char == ")":
                depth_round = max(0, depth_round - 1)
            elif char == "[":
                depth_square += 1
            elif char == "]":
                depth_square = max(0, depth_square - 1)
            elif char == "{":
                depth_curly += 1
            elif char == "}":
                depth_curly = max(0, depth_curly - 1)
            if char == "," and depth_round == 0 and depth_square == 0 and depth_curly == 0:
                item = "".join(current).strip()
                if item:
                    parts.append(item)
                current = []
                continue
            current.append(char)
        tail = "".join(current).strip()
        if tail:
            parts.append(tail)
        return parts

    def _normalize_state_token(self, value: str) -> str:
        normalized = str(value or "").strip().strip('"').strip("'")
        if not normalized:
            return ""
        normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized)
        normalized = normalized.strip("_").upper()
        if not normalized:
            return ""
        for prefix in self.state_strip_prefixes:
            if prefix and normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        for suffix in self.state_strip_suffixes:
            if suffix and normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    def _matches_state_carrier(self, name: str) -> bool:
        return any(pattern.search(name) for pattern in self.state_carrier_name_patterns)

    def _should_ignore_state_item(self, normalized_item: str) -> bool:
        if not normalized_item:
            return True
        return any(pattern.search(normalized_item) for pattern in self.state_ignore_item_patterns)

    def _normalize_state_constant(self, constant_name: str, rhs: str) -> str:
        normalized_name = self._normalize_state_token(constant_name)
        if normalized_name:
            if self._should_ignore_state_item(normalized_name):
                return ""
            return normalized_name
        for match in self.state_string_literal_pattern.findall(rhs):
            normalized_literal = self._normalize_state_token(match[0] if isinstance(match, tuple) else match)
            if normalized_literal and not self._should_ignore_state_item(normalized_literal):
                return normalized_literal
        numeric_match = self.state_numeric_literal_pattern.search(rhs)
        if numeric_match:
            normalized_numeric = self._normalize_state_token(numeric_match.group(1))
            if normalized_numeric and not self._should_ignore_state_item(normalized_numeric):
                return normalized_numeric
        return ""

    def _extract_state_items(self, carrier_kind: str, body: str) -> list[str]:
        items: list[str] = []
        if carrier_kind == "enum":
            header = self._top_level_until_semicolon(body)
            for item in self._split_top_level_csv(header):
                match = re.match(r"^\s*([A-Z][A-Z0-9_]*)\b", item)
                if not match:
                    continue
                normalized = self._normalize_state_token(match.group(1))
                if normalized and not self._should_ignore_state_item(normalized):
                    items.append(normalized)
            return items
        for match in self.state_constant_field_pattern.finditer(body):
            constant_name = match.group(1)
            rhs = match.group(2)
            normalized = self._normalize_state_constant(constant_name, rhs)
            if normalized:
                items.append(normalized)
        return items

    def _collect_state_carriers(self) -> list[dict[str, Any]]:
        carriers: list[dict[str, Any]] = []
        for path in self._iter_java_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in TYPE_DECL_RE.finditer(content):
                carrier_kind = str(match.group(1)).strip().lower()
                carrier_name = str(match.group(2)).strip()
                if not self._matches_state_carrier(carrier_name):
                    continue
                body_start = match.end() - 1
                body_end = self._find_matching_brace(content, body_start)
                if body_end <= body_start:
                    continue
                body = content[body_start + 1 : body_end]
                normalized_items = sorted(set(self._extract_state_items(carrier_kind, body)))
                if len(normalized_items) < self.state_min_carrier_items:
                    continue
                carriers.append(
                    {
                        "kind": carrier_kind,
                        "name": carrier_name,
                        "file": self._relative_path(path),
                        "line": content[: match.start()].count("\n") + 1,
                        "items": normalized_items,
                    }
                )
        carriers.sort(key=lambda item: (item["file"], item["name"], item["kind"]))
        return carriers

    def _carrier_similarity(self, left: dict[str, Any], right: dict[str, Any]) -> tuple[float, list[str]]:
        shared = sorted(set(left["items"]) & set(right["items"]))
        if len(shared) < self.state_min_shared_items:
            return 0.0, []
        min_items = min(len(left["items"]), len(right["items"]))
        if min_items <= 0:
            return 0.0, []
        similarity = len(shared) / min_items
        return similarity, shared

    def _analyze_duplicate_state_clusters(self, carriers: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
        if len(carriers) < 2:
            return 0, []
        adjacency: dict[int, set[int]] = defaultdict(set)
        pair_similarity: dict[tuple[int, int], tuple[float, list[str]]] = {}
        for left_index in range(len(carriers)):
            for right_index in range(left_index + 1, len(carriers)):
                similarity, shared = self._carrier_similarity(carriers[left_index], carriers[right_index])
                if similarity + 1e-9 < self.state_similarity_threshold:
                    continue
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)
                pair_similarity[(left_index, right_index)] = (similarity, shared)

        visited: set[int] = set()
        clusters: list[dict[str, Any]] = []
        duplicate_count = 0
        for start_index in range(len(carriers)):
            if start_index in visited or start_index not in adjacency:
                continue
            stack = [start_index]
            component: list[int] = []
            visited.add(start_index)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor in visited:
                        continue
                    visited.add(neighbor)
                    stack.append(neighbor)
            if len(component) <= 1:
                continue
            component.sort()
            duplicate_count += len(component) - 1
            item_counter: Counter[str] = Counter()
            max_similarity = 0.0
            for index in component:
                item_counter.update(carriers[index]["items"])
            for left_pos, left_index in enumerate(component):
                for right_index in component[left_pos + 1 :]:
                    key = (left_index, right_index) if left_index < right_index else (right_index, left_index)
                    similarity, _shared = pair_similarity.get(key, (0.0, []))
                    max_similarity = max(max_similarity, similarity)
            shared_items = [item for item, count in item_counter.most_common() if count >= 2][: self.state_cluster_sample_limit]
            clusters.append(
                {
                    "carrier_count": len(component),
                    "redundant_count": len(component) - 1,
                    "similarity_metric": "overlap_coefficient",
                    "max_pair_similarity": round(max_similarity, 2),
                    "shared_items": shared_items,
                    "carriers": [
                        {
                            "kind": carriers[index]["kind"],
                            "name": carriers[index]["name"],
                            "file": carriers[index]["file"],
                            "line": carriers[index]["line"],
                            "items": carriers[index]["items"][: self.state_cluster_sample_limit],
                        }
                        for index in component[: self.state_cluster_sample_limit]
                    ],
                }
            )
        clusters.sort(key=lambda item: (-item["carrier_count"], -item["max_pair_similarity"], item["carriers"][0]["file"]))
        return duplicate_count, clusters[: self.state_cluster_sample_limit]

    def _line_has_state_context(self, line: str) -> bool:
        if any(pattern.search(line) for pattern in self.state_hardcoded_context_patterns):
            return True
        return bool(re.search(r"(?i)(?:status|state|fileType|typeCd|typeCode)", line))

    def _string_literals_in_line(self, line: str) -> list[str]:
        values: list[str] = []
        for match in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', line):
            raw_value = match.group(1)
            if raw_value:
                values.append(raw_value)
        return values

    def _literal_is_context_key(self, normalized: str) -> bool:
        return normalized in self.state_context_key_literals

    def _should_skip_scattered_value_line(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if stripped.startswith(("//", "*", "/*", "@")):
            return True
        return bool(re.search(r"\b(?:public|protected|private)?\s*(?:static\s+)?final\s+", stripped))

    def _collect_scattered_state_values(self, carriers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        carrier_files = {str(carrier["file"]) for carrier in carriers}
        carrier_items = {str(item) for carrier in carriers for item in carrier.get("items", [])}
        values: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        for path in self._iter_java_files():
            rel_path = self._relative_path(path)
            if rel_path in carrier_files:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line_number, line in enumerate(content.splitlines(), start=1):
                if self._should_skip_scattered_value_line(line):
                    continue
                if not self._line_has_state_context(line):
                    continue
                for raw_value in self._string_literals_in_line(line):
                    normalized = self._normalize_state_token(raw_value)
                    if not normalized or self._literal_is_context_key(normalized) or self._should_ignore_state_item(normalized):
                        continue
                    item = {
                        "value": normalized,
                        "raw_value": raw_value,
                        "file": rel_path,
                        "line": line_number,
                        "context": line.strip()[:160],
                        "has_carrier_item": normalized in carrier_items,
                        "confidence": "high" if normalized in carrier_items else "candidate",
                    }
                    if normalized in carrier_items:
                        values.append(item)
                    else:
                        candidates.append(item)
        values.sort(key=lambda item: (item["value"], item["file"], item["line"]))
        candidates.sort(key=lambda item: (item["value"], item["file"], item["line"]))
        return values, candidates

    def _build_scattered_state_issues(self, scattered_values: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in scattered_values:
            by_value[str(item["value"])].append(item)
        issues: list[dict[str, Any]] = []
        locations: list[dict[str, Any]] = []
        for value, items in by_value.items():
            files = sorted({str(item["file"]) for item in items})
            scored_items = [item for item in items if str(item.get("confidence", "")).strip() == "high"]
            candidate_items = [item for item in items if str(item.get("confidence", "")).strip() != "high"]
            sample_locations = " | ".join(f"{item['file']}:{item['line']}" for item in items[: self.state_scatter_sample_limit])
            issues.append(
                {
                    "value": value,
                    "confidence": "high" if scored_items else "candidate",
                    "occurrence_count": len(items),
                    "scored_occurrence_count": len(scored_items),
                    "candidate_occurrence_count": len(candidate_items),
                    "file_count": len(files),
                    "has_carrier_item": any(bool(item.get("has_carrier_item")) for item in items),
                    "sample_locations": sample_locations,
                }
            )
            for item in items:
                locations.append(
                    {
                        "value": value,
                        "raw_value": item["raw_value"],
                        "file": item["file"],
                        "line": item["line"],
                        "context": item["context"],
                        "confidence": item.get("confidence", "high"),
                        "scored": str(item.get("confidence", "high")) == "high",
                    }
                )
        issues.sort(
            key=lambda item: (
                0 if str(item.get("confidence")) == "high" else 1,
                -int(item["occurrence_count"]),
                -int(item["file_count"]),
                str(item["value"]),
            )
        )
        locations.sort(key=lambda item: (0 if str(item.get("confidence")) == "high" else 1, str(item["value"]), str(item["file"]), int(item["line"])))
        return issues, locations

    def _analyze_state_definitions(self) -> Dict[str, Any]:
        carriers = self._collect_state_carriers()
        duplicate_count, duplicate_clusters = self._analyze_duplicate_state_clusters(carriers)
        scattered_values, scattered_value_candidates = self._collect_scattered_state_values(carriers)
        all_scattered_values = scattered_values + scattered_value_candidates
        scattered_value_issues, scattered_value_locations = self._build_scattered_state_issues(all_scattered_values)
        scattered_value_candidate_issues, scattered_value_candidate_locations = self._build_scattered_state_issues(scattered_value_candidates)
        unique_items = sorted({item for carrier in carriers for item in carrier["items"]})
        duplicate_cluster_issues: list[dict[str, Any]] = []
        duplicate_carrier_issues: list[dict[str, Any]] = []
        for index, cluster in enumerate(duplicate_clusters, start=1):
            cluster_id = f"C{index}"
            duplicate_cluster_issues.append(
                {
                    "cluster_id": cluster_id,
                    "carrier_count": cluster["carrier_count"],
                    "redundant_count": cluster["redundant_count"],
                    "shared_items": ", ".join(cluster.get("shared_items", [])),
                    "carrier_names": ", ".join(f"{carrier['name']}@{carrier['file']}:{carrier['line']}" for carrier in cluster.get("carriers", [])),
                }
            )
            for carrier in cluster.get("carriers", []):
                duplicate_carrier_issues.append(
                    {
                        "cluster_id": cluster_id,
                        "name": carrier["name"],
                        "kind": carrier["kind"],
                        "file": carrier["file"],
                        "line": carrier["line"],
                        "items": ", ".join(carrier.get("items", [])),
                    }
                )
        return {
            "state_count": len(carriers),
            "duplicate_count": duplicate_count,
            "state_files": len({carrier["file"] for carrier in carriers}),
            "state_item_total": sum(len(carrier["items"]) for carrier in carriers),
            "unique_item_count": len(unique_items),
            "scattered_value_count": len(scattered_values),
            "scattered_value_unique_count": len({item["value"] for item in scattered_values}),
            "scattered_value_file_count": len({item["file"] for item in scattered_values}),
            "scattered_value_candidate_count": len(scattered_value_candidates),
            "scattered_value_candidate_unique_count": len({item["value"] for item in scattered_value_candidates}),
            "scattered_value_total_file_count": len({item["file"] for item in all_scattered_values}),
            "state_value_reference_count": len(scattered_values) + sum(len(carrier["items"]) for carrier in carriers),
            "duplicate_cluster_count": len(duplicate_clusters),
            "duplicate_clusters": duplicate_clusters,
            "duplicate_cluster_issues": duplicate_cluster_issues,
            "duplicate_carrier_issues": duplicate_carrier_issues,
            "scattered_value_issues": scattered_value_issues,
            "scattered_value_locations": scattered_value_locations,
            "scattered_value_candidate_issues": scattered_value_candidate_issues,
            "scattered_value_candidate_locations": scattered_value_candidate_locations,
            "duplicate_cluster_issue_total": len(duplicate_cluster_issues),
            "duplicate_carrier_issue_total": len(duplicate_carrier_issues),
            "scattered_value_issue_total": len({item["value"] for item in all_scattered_values}),
            "scattered_value_location_total": len(all_scattered_values),
            "scattered_value_candidate_issue_total": len({item["value"] for item in scattered_value_candidates}),
            "scattered_value_candidate_location_total": len(scattered_value_candidates),
        }
