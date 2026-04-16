#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通用 LLM API 客户端
支持多种模型提供商：Aliyun, OpenAI, Claude, GLM, MiniMax 等
"""

import sys
import json
import os
import requests
import time
from datetime import datetime


class UniversalLLMClient:
    """通用 LLM API 客户端"""

    def _write_debug_log(self, message):
        """将调试日志写入 web-app 指定的日志文件。"""
        log_file = os.getenv('WEB_APP_LOG_FILE', '').strip()
        if not log_file:
            return

        try:
            log_path = os.path.abspath(log_file)
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    def __init__(self, config):
        """初始化"""
        self.provider = config.get('provider', 'aliyun')
        # 优先使用显式配置，其次再回退到环境变量，避免旧环境变量覆盖当前 skill 配置
        self.api_key = config.get('api_key', '') or os.getenv('API_KEY') or ''
        self.api_url = self._normalize_api_url(config.get('api_url', ''))
        self.model = config.get('model', '')
        self.temperature = config.get('temperature', 0.3)
        self.max_tokens = config.get('max_tokens', 2000)

        # 友好的错误提示
        if not self.api_key or self.api_key.startswith('${'):
            error_msg = (
                "\n" + "="*80 + "\n"
                "[ERROR] API_KEY 未设置\n"
                "="*80 + "\n"
                "请设置环境变量 API_KEY，有以下几种方式：\n\n"
                "1. Windows PowerShell:\n"
                "   $env:API_KEY=\"your-api-key-here\"\n\n"
                "2. Windows CMD:\n"
                "   set API_KEY=your-api-key-here\n\n"
                "3. Linux/Mac:\n"
                "   export API_KEY=\"your-api-key-here\"\n\n"
                "4. 或者在 config.json 中直接填写 API Key（不推荐）\n"
                "="*80
            )
            raise ValueError(error_msg)

        if not self.api_url:
            raise ValueError(f"[ERROR] 缺少 API URL 配置 (api_url)")

        if not self.model:
            raise ValueError(f"[ERROR] 缺少模型配置 (model)")

        print(f"[OK] LLM 客户端初始化成功")
        print(f"   提供商: {self.provider}")
        print(f"   模型: {self.model}")
        self._write_debug_log(
            f"LLM client initialized | provider={self.provider} | model={self.model} | api_url={self.api_url}"
        )

    def _normalize_api_url(self, api_url):
        """兼容根地址和完整接口地址两种写法。"""
        api_url = (api_url or '').rstrip('/')

        default_urls = {
            'aliyun': 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
            'openai': 'https://api.openai.com/v1/chat/completions',
            'claude': 'https://api.anthropic.com/v1/messages',
            'glm': 'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            'minimax': 'https://api.minimaxi.com/v1/text/chatcompletion_v2'
        }

        if not api_url:
            return default_urls.get(self.provider, '')

        if self.provider == 'openai' and api_url == 'https://api.openai.com':
            return f'{api_url}/v1/chat/completions'

        return api_url

    def call(self, prompt, retry=3):
        """调用 LLM API"""
        last_error = None
        self._write_debug_log(
            f"LLM call start | provider={self.provider} | model={self.model} | api_url={self.api_url} | prompt_len={len(prompt)} | retry={retry}"
        )

        for attempt in range(retry):
            try:
                if self.provider == 'aliyun':
                    return self._call_aliyun(prompt)
                elif self.provider == 'openai':
                    return self._call_openai(prompt)
                elif self.provider == 'claude':
                    return self._call_claude(prompt)
                elif self.provider == 'glm':
                    return self._call_glm(prompt)
                elif self.provider == 'minimax':
                    return self._call_minimax(prompt)
                else:
                    raise ValueError(f"不支持的提供商: {self.provider}")

            except requests.exceptions.Timeout as e:
                last_error = e
                self._write_debug_log(
                    f"LLM timeout | provider={self.provider} | model={self.model} | attempt={attempt + 1}/{retry} | error={str(e)}"
                )
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    print(f"   [WARNING] API 请求超时，{wait_time}秒后重试... (第 {attempt + 1}/{retry} 次)")
                    time.sleep(wait_time)
                else:
                    print(f"   [ERROR] API 请求超时，已重试 {retry} 次，请检查网络连接或 API 服务状态")

            except requests.exceptions.ConnectionError as e:
                last_error = e
                self._write_debug_log(
                    f"LLM connection error | provider={self.provider} | model={self.model} | attempt={attempt + 1}/{retry} | error={str(e)}"
                )
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    print(f"   [WARNING] 网络连接失败，{wait_time}秒后重试... (第 {attempt + 1}/{retry} 次)")
                    time.sleep(wait_time)
                else:
                    print(f"   [ERROR] 网络连接失败，已重试 {retry} 次，请检查网络连接")

            except json.JSONDecodeError as e:
                last_error = e
                self._write_debug_log(
                    f"LLM JSON decode error | provider={self.provider} | model={self.model} | attempt={attempt + 1}/{retry} | error={str(e)}"
                )
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    print(f"   [WARNING] API 返回格式错误，{wait_time}秒后重试... (第 {attempt + 1}/{retry} 次)")
                    print(f"   详细信息: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"   [ERROR] API 返回格式错误，已重试 {retry} 次")
                    print(f"   这可能是 {self.provider} API 的响应格式问题，请联系 API 提供商")

            except KeyError as e:
                last_error = e
                self._write_debug_log(
                    f"LLM response missing field | provider={self.provider} | model={self.model} | attempt={attempt + 1}/{retry} | error={str(e)}"
                )
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    print(f"   [WARNING] API 响应缺少必要字段，{wait_time}秒后重试... (第 {attempt + 1}/{retry} 次)")
                    print(f"   缺少字段: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"   [ERROR] API 响应格式不符合预期，已重试 {retry} 次")
                    print(f"   缺少字段: {str(e)}")

            except Exception as e:
                last_error = e
                self._write_debug_log(
                    f"LLM call error | provider={self.provider} | model={self.model} | attempt={attempt + 1}/{retry} | error_type={type(e).__name__} | error={str(e)}"
                )
                if attempt < retry - 1:
                    wait_time = 2 ** attempt
                    print(f"   [WARNING] API 调用失败，{wait_time}秒后重试... (第 {attempt + 1}/{retry} 次)")
                    print(f"   错误类型: {type(e).__name__}")
                    print(f"   错误信息: {str(e)}")
                    time.sleep(wait_time)
                else:
                    print(f"   [ERROR] API 调用失败，已重试 {retry} 次")
                    print(f"   错误类型: {type(e).__name__}")
                    print(f"   错误信息: {str(e)}")

        # 所有重试都失败后，抛出最后一个错误
        raise last_error

    def _call_aliyun(self, prompt):
        """调用阿里云通义千问"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.model,
            'input': {
                'prompt': prompt
            },
            'parameters': {
                'temperature': self.temperature,
                'max_tokens': self.max_tokens
            }
        }

        response = requests.post(self.api_url, headers=headers, json=data, timeout=(10, 300))
        response.raise_for_status()

        result = response.json()
        if result.get('output', {}).get('text'):
            return result['output']['text']
        else:
            raise ValueError(f"API 返回异常: {result}")

    def _call_openai(self, prompt):
        """调用 OpenAI API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        self._write_debug_log(f"HTTP POST -> {self.api_url} | provider=openai | model={self.model}")
        response = requests.post(self.api_url, headers=headers, json=data, timeout=(10, 300))
        self._write_debug_log(f"HTTP response <- {self.api_url} | status={response.status_code}")
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content']

    def _call_claude(self, prompt):
        """调用 Claude API"""
        headers = {
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json'
        }

        data = {
            'model': self.model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        response = requests.post(self.api_url, headers=headers, json=data, timeout=(10, 300))
        response.raise_for_status()

        result = response.json()
        return result['content'][0]['text']

    def _call_glm(self, prompt):
        """调用智谱 GLM API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        self._write_debug_log(f"HTTP POST -> {self.api_url} | provider=glm | model={self.model}")
        response = requests.post(self.api_url, headers=headers, json=data, timeout=(10, 300))
        self._write_debug_log(f"HTTP response <- {self.api_url} | status={response.status_code}")
        response.raise_for_status()

        result = response.json()
        return result['choices'][0]['message']['content']

    def _call_minimax(self, prompt):
        """调用 MiniMax API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        data = {
            'model': self.model,
            'messages': [
                {'role': 'user', 'content': prompt}
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }

        try:
            self._write_debug_log(f"HTTP POST -> {self.api_url} | provider=minimax | model={self.model}")
            response = requests.post(self.api_url, headers=headers, json=data, timeout=(10, 300))
            self._write_debug_log(f"HTTP response <- {self.api_url} | status={response.status_code}")

            # MiniMax API 可能返回多行 JSON，只取第一行
            response_text = response.text.strip()
            if '\n' in response_text:
                # 取第一行 JSON
                first_line = response_text.split('\n')[0]
                result = json.loads(first_line)
            else:
                result = response.json()

            # 检查是否有错误
            if 'error' in result:
                error_info = result['error']
                error_type = error_info.get('type', 'unknown')
                error_msg = error_info.get('message', 'Unknown error')

                if error_type == 'overloaded_error':
                    raise ValueError(f"MiniMax API 服务器过载: {error_msg}")
                else:
                    raise ValueError(f"MiniMax API 错误 ({error_type}): {error_msg}")

            # 某些 MiniMax 响应把错误放在 base_resp 里
            base_resp = result.get('base_resp', {})
            base_status_code = base_resp.get('status_code', 0)
            if base_status_code and base_status_code != 0:
                base_status_msg = base_resp.get('status_msg', 'Unknown error')
                raise ValueError(
                    f"MiniMax API 错误 (base_resp:{base_status_code}): {base_status_msg}"
                )

            # 正常响应处理
            response.raise_for_status()

            # 验证响应格式
            if 'choices' not in result:
                raise ValueError(f"MiniMax API 响应缺少 'choices' 字段，完整响应: {result}")

            if not result['choices'] or len(result['choices']) == 0:
                raise ValueError(f"MiniMax API 返回空的 choices 数组，完整响应: {result}")

            if 'message' not in result['choices'][0]:
                raise ValueError(f"MiniMax API 响应缺少 'message' 字段，完整响应: {result}")

            if 'content' not in result['choices'][0]['message']:
                raise ValueError(f"MiniMax API 响应缺少 'content' 字段，完整响应: {result}")

            return result['choices'][0]['message']['content']

        except requests.exceptions.HTTPError as e:
            # HTTP 错误（4xx, 5xx）
            try:
                error_detail = response.json()
                raise ValueError(f"MiniMax API HTTP 错误 {response.status_code}: {error_detail}")
            except:
                raise ValueError(f"MiniMax API HTTP 错误 {response.status_code}: {response.text}")

        except json.JSONDecodeError as e:
            # JSON 解析错误
            raise ValueError(f"MiniMax API 返回非 JSON 格式数据: {response.text[:200]}")
