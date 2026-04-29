#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构熵分析器
分析项目的结构、依赖关系和模块组织
"""

import os
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict

from entropy_audit.lang.java.scoring_v1_engine import score_dimension_v1


class StructureAnalyzer:
    """结构熵分析器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.project_root = Path(config['project']['root'])
        self.exclude_dirs = set(config['project']['exclude_dirs'])
        self.include_extensions = {
            str(value).strip().lower()
            for value in config['project'].get('include_extensions', [])
            if str(value).strip()
        }
        self.scoring_v1 = config.get('scoring_v1', {}) if isinstance(config.get('scoring_v1'), dict) else {}
        detail_export = config.get('detail_export', {}) if isinstance(config.get('detail_export'), dict) else {}
        detail_limits = detail_export.get('limits', {}) if isinstance(detail_export.get('limits'), dict) else {}
        detectors = config.get('detectors', {}) if isinstance(config.get('detectors'), dict) else {}
        structure_detectors = detectors.get('structure', {}) if isinstance(detectors.get('structure'), dict) else {}
        self.shared_bucket_detector = structure_detectors.get('shared_buckets', {}) if isinstance(structure_detectors.get('shared_buckets'), dict) else {}
        self.directory_distribution_detector = structure_detectors.get('directory_distribution', {}) if isinstance(structure_detectors.get('directory_distribution'), dict) else {}
        self.shared_aliases = [str(value).strip().lower() for value in self.shared_bucket_detector['shared_aliases'] if str(value).strip()]
        self.utility_aliases = [str(value).strip().lower() for value in self.shared_bucket_detector['utility_aliases'] if str(value).strip()]
        self.shared_path_prefixes = self._normalize_path_prefixes(self.shared_bucket_detector.get('shared_path_prefixes', []))
        self.utility_path_prefixes = self._normalize_path_prefixes(self.shared_bucket_detector.get('utility_path_prefixes', []))
        self.bucket_match_mode = str(self.shared_bucket_detector['match_mode']).strip().lower()
        self.oversized_dir_file_threshold = int(self.directory_distribution_detector['oversized_dir_file_threshold'])
        self.top_n_concentration_count = int(self.directory_distribution_detector['top_n_concentration_count'])
        self.top_large_directories_limit = int(detail_limits['top_large_directories'])
    
    def analyze(self) -> Dict[str, Any]:
        """执行结构熵分析"""
        # 1. 统计各目录的文件数
        dir_stats = self._analyze_directory_structure()
        
        # 2. 识别common/util目录
        common_util_stats = self._analyze_common_util()
        
        # 3. 分析依赖关系（基于 import 的精确强连通分量检测）

        facts = self._build_facts(dir_stats, common_util_stats)
        details = {
            'total_files': dir_stats['total_files'],
            'total_directories': dir_stats['total_dirs'],
            'common_files': common_util_stats['common_files'],
            'util_files': common_util_stats['util_files'],
            'shared_bucket_total': common_util_stats['shared_bucket_total'],
            'shared_bucket_overlap_files': common_util_stats['shared_bucket_overlap_files'],
            'shared_aliases': common_util_stats['shared_aliases'],
            'utility_aliases': common_util_stats['utility_aliases'],
            'shared_path_prefixes': common_util_stats['shared_path_prefixes'],
            'utility_path_prefixes': common_util_stats['utility_path_prefixes'],
            'shared_bucket_dirs': common_util_stats['shared_bucket_dirs'],
            'common_bucket_dirs': common_util_stats['common_bucket_dirs'],
            'utility_bucket_dirs': common_util_stats['utility_bucket_dirs'],
            'max_dir_files': dir_stats['max_dir_files'],
            'max_dir_name': dir_stats['max_dir_name'],
            'oversized_dir_count': dir_stats['oversized_dir_count'],
            'oversized_dir_file_threshold': dir_stats['oversized_dir_file_threshold'],
            'oversized_dirs': dir_stats['oversized_dirs'],
            'top_n_dir_file_sum': dir_stats['top_n_dir_file_sum'],
            'top_n_concentration_count': dir_stats['top_n_concentration_count'],
            'top_n_concentration_dirs': dir_stats['top_n_concentration_dirs'],
            'avg_files_per_dir': dir_stats['avg_files_per_dir'],
            'top_large_dirs': dir_stats['top_large_dirs']
        }
        v1_payload = score_dimension_v1(self.scoring_v1, 'structure', facts, details)
        if not isinstance(v1_payload, dict):
            raise ValueError("StructureAnalyzer requires [code_entropy.scoring_v1] and a valid structure scorecard")
        score = v1_payload['score_breakdown']['score']
        level = str(v1_payload['score_breakdown'].get('level', 'danger'))
        
        return {
            'score': score,
            'level': level,
            'score_breakdown': v1_payload['score_breakdown'],
            'metrics': v1_payload['metrics'],
            'facts': facts,
            'details': details,
            'scoring_v1': v1_payload,
            'metric_definitions': v1_payload.get('metric_definitions', {}),
        }
    
    def _analyze_directory_structure(self) -> Dict[str, Any]:
        """分析目录结构"""
        dir_file_counts = defaultdict(int)
        total_files = 0
        total_dirs = 0
        
        for root, dirs, files in os.walk(self.project_root):
            # 过滤排除目录
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            # 统计Java文件
            source_files = [f for f in files if Path(f).suffix.lower() in self.include_extensions]
            if source_files:
                rel_path = os.path.relpath(root, self.project_root)
                dir_file_counts[rel_path] = len(source_files)
                total_files += len(source_files)
                total_dirs += 1
        
        # 找出文件最多的目录
        if dir_file_counts:
            max_dir = max(dir_file_counts.items(), key=lambda x: x[1])
            max_dir_name, max_dir_files = max_dir
        else:
            max_dir_name, max_dir_files = "N/A", 0
        
        sorted_dirs = sorted(dir_file_counts.items(), key=lambda x: x[1], reverse=True)
        top_large_dirs = sorted_dirs[: self.top_large_directories_limit]
        all_oversized_dirs = [
            (directory, count)
            for directory, count in sorted_dirs
            if count >= self.oversized_dir_file_threshold
        ]
        top_n_concentration_dirs = sorted_dirs[: self.top_n_concentration_count]
        top_n_dir_file_sum = sum(count for _, count in top_n_concentration_dirs)
        
        avg_files = total_files / total_dirs if total_dirs > 0 else 0
        
        return {
            'total_files': total_files,
            'total_dirs': total_dirs,
            'max_dir_files': max_dir_files,
            'max_dir_name': max_dir_name,
            'oversized_dir_count': len(all_oversized_dirs),
            'oversized_dir_file_threshold': self.oversized_dir_file_threshold,
            'oversized_dirs': [{'dir': d, 'files': c} for d, c in all_oversized_dirs[: self.top_large_directories_limit]],
            'top_n_dir_file_sum': top_n_dir_file_sum,
            'top_n_concentration_count': self.top_n_concentration_count,
            'top_n_concentration_dirs': [{'dir': d, 'files': c} for d, c in top_n_concentration_dirs],
            'avg_files_per_dir': round(avg_files, 2),
            'top_large_dirs': [{'dir': d, 'files': c} for d, c in top_large_dirs],
            'dir_file_counts': dict(dir_file_counts)
        }

    def _normalize_relative_path(self, relative_path: str) -> str:
        normalized = str(relative_path).replace('\\', '/').strip().strip('/')
        return '' if normalized == '.' else normalized.lower()

    def _normalize_path_prefixes(self, prefixes: List[str]) -> List[str]:
        normalized_prefixes: List[str] = []
        for value in prefixes:
            normalized = self._normalize_relative_path(str(value))
            if normalized:
                normalized_prefixes.append(normalized)
        return normalized_prefixes

    def _matches_prefix(self, relative_path: str, prefixes: List[str]) -> bool:
        if not prefixes:
            return False
        normalized_path = self._normalize_relative_path(relative_path)
        if not normalized_path:
            return False
        return any(
            normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
            for prefix in prefixes
        )

    def _matched_prefixes(self, relative_path: str, prefixes: List[str]) -> List[str]:
        if not prefixes:
            return []
        normalized_path = self._normalize_relative_path(relative_path)
        if not normalized_path:
            return []
        return [
            prefix
            for prefix in prefixes
            if normalized_path == prefix or normalized_path.startswith(f"{prefix}/")
        ]

    def _matches_bucket(self, relative_path: str, aliases: List[str]) -> bool:
        if not aliases:
            return False
        normalized_path = self._normalize_relative_path(relative_path)
        if self.bucket_match_mode == 'contains':
            return any(alias in normalized_path for alias in aliases)
        segments = normalized_path.split('/') if normalized_path else []
        return any(alias in segments for alias in aliases)

    def _matched_aliases(self, relative_path: str, aliases: List[str]) -> List[str]:
        if not aliases:
            return []
        normalized_path = self._normalize_relative_path(relative_path)
        if self.bucket_match_mode == 'contains':
            return [alias for alias in aliases if alias in normalized_path]
        segments = normalized_path.split('/') if normalized_path else []
        return [alias for alias in aliases if alias in segments]

    def _resolve_bucket_matches(self, relative_path: str, prefixes: List[str], aliases: List[str]) -> List[Dict[str, str]]:
        if prefixes:
            prefix_hits = self._matched_prefixes(relative_path, prefixes)
            return [{'source': 'prefix', 'value': value} for value in prefix_hits]
        alias_hits = self._matched_aliases(relative_path, aliases)
        return [{'source': 'alias', 'value': value} for value in alias_hits]
    
    def _analyze_common_util(self) -> Dict[str, Any]:
        """分析common/util目录"""
        common_files = 0
        util_files = 0
        shared_bucket_total = 0
        shared_bucket_overlap_files = 0
        common_bucket_dirs = []
        utility_bucket_dirs = []
        shared_bucket_dirs = []
        
        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            rel_path = os.path.relpath(root, self.project_root)
            normalized_rel_path = self._normalize_relative_path(rel_path)
            
            common_matches = self._resolve_bucket_matches(normalized_rel_path, self.shared_path_prefixes, self.shared_aliases)
            utility_matches = self._resolve_bucket_matches(normalized_rel_path, self.utility_path_prefixes, self.utility_aliases)
            is_common = bool(common_matches)
            is_util = bool(utility_matches)
            
            java_files_count = len([f for f in files if Path(f).suffix.lower() in self.include_extensions])
            
            if is_common:
                common_files += java_files_count
                common_bucket_dirs.append({
                    'dir': normalized_rel_path or '.',
                    'files': java_files_count,
                    'matches': common_matches,
                    'match_source_applied': common_matches[0]['source'],
                    'match_values_applied': [item['value'] for item in common_matches],
                })
            if is_util:
                util_files += java_files_count
                utility_bucket_dirs.append({
                    'dir': normalized_rel_path or '.',
                    'files': java_files_count,
                    'matches': utility_matches,
                    'match_source_applied': utility_matches[0]['source'],
                    'match_values_applied': [item['value'] for item in utility_matches],
                })
            if is_common or is_util:
                shared_bucket_total += java_files_count
                shared_bucket_dirs.append({
                    'dir': normalized_rel_path or '.',
                    'files': java_files_count,
                    'common': is_common,
                    'utility': is_util,
                    'common_matches': common_matches,
                    'utility_matches': utility_matches,
                    'common_match_source_applied': common_matches[0]['source'] if common_matches else None,
                    'utility_match_source_applied': utility_matches[0]['source'] if utility_matches else None,
                    'common_match_values_applied': [item['value'] for item in common_matches],
                    'utility_match_values_applied': [item['value'] for item in utility_matches],
                })
            if is_common and is_util:
                shared_bucket_overlap_files += java_files_count
        
        return {
            'common_files': common_files,
            'util_files': util_files,
            'shared_bucket_total': shared_bucket_total,
            'shared_bucket_overlap_files': shared_bucket_overlap_files,
            'total_common_util': shared_bucket_total,
            'shared_aliases': list(self.shared_aliases),
            'utility_aliases': list(self.utility_aliases),
            'shared_path_prefixes': list(self.shared_path_prefixes),
            'utility_path_prefixes': list(self.utility_path_prefixes),
            'shared_bucket_dirs': shared_bucket_dirs[: self.top_large_directories_limit],
            'common_bucket_dirs': common_bucket_dirs[: self.top_large_directories_limit],
            'utility_bucket_dirs': utility_bucket_dirs[: self.top_large_directories_limit],
        }

    def _build_facts(self, dir_stats: Dict[str, Any], common_util_stats: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'total_files': dir_stats['total_files'],
            'total_dirs': dir_stats['total_dirs'],
            'common_files': common_util_stats['common_files'],
            'util_files': common_util_stats['util_files'],
            'shared_bucket_total': common_util_stats['shared_bucket_total'],
            'max_dir_files': dir_stats['max_dir_files'],
            'oversized_dir_count': dir_stats['oversized_dir_count'],
            'oversized_dir_file_threshold': dir_stats['oversized_dir_file_threshold'],
            'top_n_dir_file_sum': dir_stats['top_n_dir_file_sum'],
            'top_n_concentration_count': dir_stats['top_n_concentration_count'],
        }
    
