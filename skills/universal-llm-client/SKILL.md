---
name: universal-llm-client
description: Universal LLM API client supporting multiple providers (Aliyun, OpenAI, Claude, GLM, MiniMax) with unified interface. Provides automatic retry mechanism and environment variable support for API keys.
---

> **依赖安装**:
> - 核心依赖：`pip install requests`
> - Python 3.7+

# Universal LLM Client

## Use This Skill When

- 需要调用多种 LLM 提供商的 API
- 需要统一的 LLM 调用接口
- 作为其他 Skill 的基础依赖模块
- 需要自动重试机制和错误处理

## Default Deliverables

本 Skill 是基础库，不直接生成文件，而是提供 Python API：

```python
from llm_client import UniversalLLMClient

client = UniversalLLMClient(config)
response = client.call(prompt)
```

## Hard Rules

- **统一接口**：所有提供商使用相同的调用方式
- **自动重试**：API 调用失败自动重试（默认 3 次）
- **环境变量支持**：API Key 支持从环境变量读取
- **错误处理**：提供详细的错误信息和日志

## Workflow

### Step 1: 初始化客户端
1. 加载配置（provider, api_key, api_url, model 等）
2. 解析环境变量（如 `${API_KEY}`）
3. 验证配置完整性
4. 初始化对应提供商的客户端

### Step 2: 调用 LLM
1. 构建请求体（根据提供商格式）
2. 发送 HTTP 请求
3. 解析响应
4. 提取文本内容
5. 失败则自动重试

### Step 3: 错误处理
1. 捕获网络错误
2. 捕获 API 错误
3. 记录错误日志
4. 返回错误信息

## Configuration

### config.json 示例

```json
{
  "llm": {
    "provider": "claude",
    "api_key": "${API_KEY}",
    "api_url": "https://api.anthropic.com/v1/messages",
    "model": "claude-opus-4-6",
    "temperature": 0.3,
    "max_tokens": 2000
  }
}
```

### 环境变量

```bash
export API_KEY="your-api-key-here"
```

### 支持的 LLM 提供商

| 提供商 | provider 值 | 默认 API URL |
|--------|-------------|--------------|
| 阿里云通义千问 | `aliyun` | https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation |
| OpenAI | `openai` | https://api.openai.com/v1/chat/completions |
| Claude | `claude` | https://api.anthropic.com/v1/messages |
| 智谱 GLM | `glm` | https://open.bigmodel.cn/api/paas/v4/chat/completions |
| MiniMax | `minimax` | https://api.minimaxi.com/v1/text/chatcompletion_v2 |

### 配置参数说明

- `provider` - 提供商名称（必填）
- `api_key` - API 密钥（必填，支持环境变量）
- `api_url` - API 端点（可选，有默认值）
- `model` - 模型 ID（必填）
- `temperature` - 温度参数（0-1，默认 0.3）
- `max_tokens` - 最大 token 数（默认 2000）

## Usage

### 基本使用

```python
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / 'skills' / 'universal-llm-client' / 'scripts'))

from llm_client import UniversalLLMClient

# 配置
config = {
    "provider": "claude",
    "api_key": "sk-ant-xxx",
    "api_url": "https://api.anthropic.com/v1/messages",
    "model": "claude-opus-4-6",
    "temperature": 0.3,
    "max_tokens": 2000
}

# 初始化客户端
client = UniversalLLMClient(config)

# 调用
response = client.call("你好，请介绍一下你自己")
print(response)
```

### 使用环境变量

```python
import os

config = {
    "provider": "openai",
    "api_key": os.getenv("API_KEY"),  # 从环境变量读取
    "model": "gpt-4",
    "temperature": 0.1
}

client = UniversalLLMClient(config)
response = client.call("Explain quantum computing")
```

### 从配置文件加载

```python
from config_utils import load_config

config = load_config("config.json")
client = UniversalLLMClient(config["llm"])
response = client.call(prompt)
```

## Examples

### 示例 1：使用 Claude

```python
config = {
    "provider": "claude",
    "api_key": "sk-ant-xxx",
    "model": "claude-opus-4-6",
    "temperature": 0.1,
    "max_tokens": 1000
}

client = UniversalLLMClient(config)
response = client.call("从以下文本中提取关键词：标讯管理模块需要实现中标公告的分页查询功能")
print(response)
# 输出: {"keywords": ["标讯管理", "中标公告", "分页查询"]}
```

### 示例 2：使用 OpenAI

```python
config = {
    "provider": "openai",
    "api_key": "sk-xxx",
    "model": "gpt-4",
    "temperature": 0.3
}

client = UniversalLLMClient(config)
response = client.call("Summarize this document in 3 bullet points...")
```

### 示例 3：使用阿里云通义千问

```python
config = {
    "provider": "aliyun",
    "api_key": "sk-xxx",
    "model": "qwen-max",
    "temperature": 0.5
}

client = UniversalLLMClient(config)
response = client.call("优化以下文档的可读性...")
```

### 示例 4：使用 MiniMax

```python
config = {
    "provider": "minimax",
    "api_key": "xxx",
    "api_url": "https://api.minimaxi.com/v1/text/chatcompletion_v2",
    "model": "MiniMax-M2.7",
    "temperature": 0.1
}

client = UniversalLLMClient(config)
response = client.call("生成一份产品需求文档...")
```

## Integration with Other Skills

### 依赖关系

```
universal-llm-client (基础模块)
    ↑
    │ 依赖
    ├── keyword-extractor
    ├── doc-content-optimizer
    ├── enterprise-requirement-doc-pro
    └── precise-knowledge-retriever (语义匹配模式)
```

### 在其他 Skill 中使用

```python
# 在 keyword-extractor 中
from llm_client import UniversalLLMClient

class KeywordExtractor:
    def __init__(self, config_path):
        config = load_config(config_path)
        self.llm_client = UniversalLLMClient(config["llm"])
    
    def extract(self, user_input):
        prompt = self.build_prompt(user_input)
        response = self.llm_client.call(prompt)
        return self.parse_response(response)
```

## Dependencies

### External Dependencies
- `requests` - HTTP 请求库
- Python 标准库：`json`, `os`, `sys`, `time`

### No Internal Dependencies
本 Skill 是基础模块，不依赖其他 Skill

## Error Handling

### API Key 未设置
**错误**：`API key not found`
**解决方案**：
```bash
export API_KEY="your-api-key-here"
```

### API 调用失败
**错误**：`HTTP Error 401: Unauthorized`
**解决方案**：检查 API Key 是否正确

**错误**：`HTTP Error 429: Too Many Requests`
**解决方案**：等待一段时间后重试，或升级 API 配额

**错误**：`Connection timeout`
**解决方案**：检查网络连接和 API URL

### 响应解析失败
**错误**：`Failed to parse LLM response`
**解决方案**：
1. 检查 LLM 返回格式
2. 调整提示词
3. 增加 max_tokens

### 提供商不支持
**错误**：`Unsupported provider: xxx`
**解决方案**：使用支持的提供商（aliyun/openai/claude/glm/minimax）

## Core Features

### 1. 统一接口
所有提供商使用相同的调用方式：
```python
client = UniversalLLMClient(config)
response = client.call(prompt)
```

### 2. 自动重试机制
```python
# 默认重试 3 次
client = UniversalLLMClient(config, max_retries=3)
```

### 3. 环境变量支持
```json
{
  "api_key": "${API_KEY}"  // 自动从环境变量读取
}
```

### 4. 详细日志
```
[LLM] 调用 claude API...
[LLM] 请求成功 (耗时: 1.2s)
[LLM] 返回内容长度: 156 字符
```

### 5. 错误处理
- 网络错误自动重试
- API 错误详细日志
- 超时自动中断

## API Reference

### UniversalLLMClient

#### `__init__(config, max_retries=3)`
初始化 LLM 客户端

**参数**:
- `config` (dict) - LLM 配置
  - `provider` (str) - 提供商名称
  - `api_key` (str) - API 密钥
  - `api_url` (str, optional) - API 端点
  - `model` (str) - 模型 ID
  - `temperature` (float, optional) - 温度参数
  - `max_tokens` (int, optional) - 最大 token 数
- `max_retries` (int) - 最大重试次数

#### `call(prompt)`
调用 LLM API

**参数**:
- `prompt` (str) - 提示词

**返回**:
- `str` - LLM 返回的文本内容

**异常**:
- `ValueError` - 配置错误
- `RuntimeError` - API 调用失败

## Version

v1.0.0
