#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
关键词提取器
从用户需求描述中智能提取核心关键词
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


class KeywordExtractor:
    """关键词提取器"""

    def _write_debug_log(self, message):
        """写入 web-app 日志文件，便于排查 LLM 返回内容。"""
        log_file = os.getenv('WEB_APP_LOG_FILE', '').strip()
        if not log_file:
            return

        try:
            log_path = Path(log_file).resolve()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    def __init__(self, config_path=None):
        """初始化"""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config.json'

        # 加载配置并解析变量
        self.config = load_config_with_variables(config_path)

        # 初始化 LLM 客户端
        self.llm_client = UniversalLLMClient(self.config['llm'])

        # 加载提示词模板
        prompt_path = Path(__file__).parent.parent / 'prompts' / 'extraction_prompt.txt'
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()

        print("[OK] 关键词提取器初始化成功")

    def extract(self, user_input):
        """提取关键词"""
        print(f"\n[EXTRACT] 开始提取关键词...")
        print(f"   输入长度: {len(user_input)} 字符")

        # 构建提示词
        prompt = self.prompt_template.format(user_input=user_input)

        # 调用 LLM
        try:
            response = self.llm_client.call(prompt)
            response_preview = (response or '')[:500].replace('\r', '\\r').replace('\n', '\\n')
            self._write_debug_log(
                f"Step1 raw LLM response preview | len={len(response or '')} | preview={response_preview}"
            )

            # 解析 JSON
            json_match = re.search(r'\{.*?"keywords".*?\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)

            keywords = result.get('keywords', [])

            if not keywords:
                print(f"   ⚠️  未提取到关键词，LLM 返回为空")
                return []

            print(f"   提取到 {len(keywords)} 个关键词: {', '.join(keywords)}")

            return keywords

        except json.JSONDecodeError as e:
            print(f"   [ERROR] JSON 解析失败: {e}")
            print(f"   LLM 返回内容: {response[:200] if 'response' in locals() else '无'}")
            if 'response' in locals():
                response_preview = (response or '')[:500].replace('\r', '\\r').replace('\n', '\\n')
                self._write_debug_log(
                    f"Step1 JSON parse failed | error={str(e)} | raw_preview={response_preview}"
                )
            raise ValueError(f"LLM 返回内容不是有效 JSON: {e}") from e

        except Exception as e:
            print(f"   [ERROR] 提取失败: {type(e).__name__}")
            print(f"   错误信息: {str(e)}")
            raise

    def save_result(self, keywords):
        """保存结果"""
        output_file = self.config['output_file']

        try:
            result = {
                "keywords": keywords,
                "count": len(keywords)
            }

            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            print(f"\n[OK] 关键词已保存到: {output_file}")

        except Exception as e:
            print(f"\n❌ 保存失败: {type(e).__name__}")
            print(f"   错误信息: {str(e)}")
            raise


def main():
    """主函数"""
    print("="*80)
    print("关键词提取器")
    print("="*80)

    if len(sys.argv) < 2:
        print("\n用法: python extract_keywords.py <用户需求描述>")
        sys.exit(1)

    user_input = sys.argv[1]

    extractor = KeywordExtractor()
    keywords = extractor.extract(user_input)

    if keywords:
        extractor.save_result(keywords)
    else:
        print("\n[WARNING] 未提取到关键词")


if __name__ == "__main__":
    main()
