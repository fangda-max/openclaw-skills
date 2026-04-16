#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文档内容优化器
优化检索文档的连贯性和可读性，严格保留原始信息
"""

import sys
import json
import os
import re
from pathlib import Path

# 导入通用 LLM 客户端和配置工具
sys.path.append(str(Path(__file__).parent.parent.parent / 'universal-llm-client' / 'scripts'))
from llm_client import UniversalLLMClient
from config_utils import load_config_with_variables


class DocumentOptimizer:
    """文档内容优化器"""

    def __init__(self, config_path):
        """初始化"""
        # 加载配置并解析变量
        self.config = load_config_with_variables(config_path)

        # 初始化 LLM 客户端
        self.llm_client = UniversalLLMClient(self.config['llm'])

        # 注意：不再在初始化时加载提示词，而是在 optimize() 方法中加载
        # 因为使用的是 optimization_prompt_full.txt

        print("[OK] 文档优化器初始化成功")
        print(f"   输入: {self.config['input_file']}")
        print(f"   输出: {self.config['output_file']}")

    def _clean_llm_output(self, content):
        """清理模型额外输出。"""
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL)
        return content.strip()

    def is_truncated_output(self, optimized):
        """检测常见的截断特征。"""
        stripped = optimized.rstrip()
        if not stripped:
            return True

        suspicious_suffixes = (':', '：', '-', '1.', '2.', '3.', '4.', '5.', '（', '【', '>', '、')
        if stripped.endswith(suspicious_suffixes):
            return True

        last_line = stripped.splitlines()[-1].strip()
        if re.match(r'^\d+\.$', last_line):
            return True
        if last_line.startswith('- ') and len(last_line) <= 3:
            return True

        return False

    def optimize_full_document(self, original_content, prompt_template):
        """整篇文档一次性优化。"""
        prompt = prompt_template.format(full_content=original_content)

        try:
            print("   正在整篇优化文档...")
            print(f"   文档长度: {len(original_content)} 字符")
            optimized = self.llm_client.call(prompt)
            optimized = self._clean_llm_output(optimized)
            return optimized, True, None
        except Exception as e:
            print(f"   [WARNING] 整篇优化异常: {e}")
            return original_content, False, str(e)

    def validate_quality(self, original, optimized):
        """质量验证"""
        # 1. 完整性检查：字符数比例
        original_len = len(original)
        optimized_len = len(optimized)
        completeness = optimized_len / original_len if original_len > 0 else 0

        # 2. 一致性检查：简单的关键词保留率
        # 提取关键词（长度 >= 2 的中文词）
        original_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,}', original))
        optimized_keywords = set(re.findall(r'[\u4e00-\u9fa5]{2,}', optimized))

        if original_keywords:
            consistency = len(original_keywords & optimized_keywords) / len(original_keywords)
        else:
            consistency = 1.0

        return {
            "completeness": completeness,
            "consistency": consistency,
            "passed": (
                completeness >= self.config['quality_thresholds']['completeness'] and
                consistency >= self.config['quality_thresholds']['consistency']
            )
        }

    def optimize(self):
        """执行优化"""
        print("\n" + "="*80)
        print("开始文档优化")
        print("="*80)

        output_file = self.config['output_file']
        report_file = self.config.get('report_file', 'optimization_report.json')

        try:
            # 1. 读取完整文档
            print(f"\n[FILE] 读取文档: {self.config['input_file']}")
            with open(self.config['input_file'], 'r', encoding='utf-8') as f:
                original_content = f.read()

            print(f"   文档大小: {len(original_content)} 字符")

            # 2. 整篇优化文档
            print(f"\n[PROCESS] 开始整篇优化文档...")

            prompt_path = Path(__file__).parent.parent / 'prompts' / 'optimization_prompt_full.txt'
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
            optimized_content, llm_success, error = self.optimize_full_document(
                original_content,
                prompt_template
            )

            quality = self.validate_quality(original_content, optimized_content)
            quality["chunk_index"] = 1
            quality["original_length"] = len(original_content)
            quality["optimized_length"] = len(optimized_content)
            quality_reports = [quality]

            if self.is_truncated_output(optimized_content):
                quality["passed"] = False
                quality["error"] = "疑似输出截断，已回滚原文"
                optimized_content = original_content
                quality["completeness"] = 1.0
                quality["consistency"] = 1.0
                quality["optimized_length"] = len(optimized_content)
                print("   [WARNING] 整篇输出疑似截断，已回滚原文")
            elif not llm_success:
                quality["passed"] = False
                quality["error"] = error
                optimized_content = original_content
                quality["completeness"] = 1.0
                quality["consistency"] = 1.0
                quality["optimized_length"] = len(optimized_content)
                print("   [WARNING] 整篇调用失败，已回滚原文")
            elif quality["completeness"] < self.config['quality_thresholds']['completeness']:
                quality["passed"] = False
                quality["error"] = (
                    f"完整性不足: {quality['completeness']:.1%} < "
                    f"{self.config['quality_thresholds']['completeness']:.1%}"
                )
                optimized_content = original_content
                quality["completeness"] = 1.0
                quality["consistency"] = 1.0
                quality["optimized_length"] = len(optimized_content)
                print("   [WARNING] 整篇完整性不足，已回滚原文")
            else:
                print(
                    f"   [OK] 整篇优化成功 "
                    f"(完整性: {quality['completeness']:.1%}, 一致性: {quality['consistency']:.1%})"
                )

            # 3. 生成输出文档
            print(f"\n[WRITE] 生成优化文档...")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(optimized_content)

            # 4. 生成质量报告
            report = self._generate_quality_report(quality_reports)

            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

            print(f"\n[OK] 优化完成")
            print(f"   原始文档: {self.config['input_file']}")
            print(f"   优化文档: {output_file}")
            print(f"   质量报告: {report_file}")

        except KeyboardInterrupt:
            print("\n\n[WARNING] 用户中断操作")
            print("正在清理临时文件...")
            if os.path.exists(output_file):
                os.remove(output_file)
                print(f"   已删除: {output_file}")
            if os.path.exists(report_file):
                os.remove(report_file)
                print(f"   已删除: {report_file}")
            raise

        except Exception as e:
            print(f"\n\n[ERROR] 优化过程中发生错误: {type(e).__name__}")
            print(f"   错误信息: {str(e)}")
            print("正在清理临时文件...")
            if os.path.exists(output_file):
                os.remove(output_file)
                print(f"   已删除: {output_file}")
            if os.path.exists(report_file):
                os.remove(report_file)
                print(f"   已删除: {report_file}")
            raise

    def _generate_quality_report(self, quality_reports):
        """生成质量报告"""
        report = {
            "total_chunks": len(quality_reports),
            "passed_chunks": sum(1 for r in quality_reports if r.get("passed", False)),
            "failed_chunks": sum(1 for r in quality_reports if not r.get("passed", False)),
            "avg_completeness": sum(r["completeness"] for r in quality_reports) / len(quality_reports),
            "avg_consistency": sum(r["consistency"] for r in quality_reports) / len(quality_reports),
            "details": quality_reports
        }

        report_path = self.config.get('report_file', 'optimization_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    """主函数"""
    print("="*80)
    print("文档内容优化器")
    print("="*80)

    # 配置文件路径
    config_path = Path(__file__).parent.parent / 'config.json'

    # 初始化优化器
    optimizer = DocumentOptimizer(config_path)

    # 执行优化
    optimizer.optimize()


if __name__ == "__main__":
    main()
